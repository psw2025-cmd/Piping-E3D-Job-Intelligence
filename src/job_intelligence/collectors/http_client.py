from __future__ import annotations

import ipaddress
import json
import socket
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urljoin, urlsplit

import requests

DEFAULT_USER_AGENT = "Piping-E3D-Job-Intelligence/0.5 (+public-job-monitor)"


@dataclass(frozen=True, slots=True)
class FetchedResponse:
    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes

    @property
    def text(self) -> str:
        encoding = "utf-8"
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type.lower():
            encoding = (
                content_type.lower()
                .split("charset=", 1)[1]
                .split(";", 1)[0]
                .strip()
            )
        return self.content.decode(encoding or "utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class HttpClient(Protocol):
    user_agent: str

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse: ...

    def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, object],
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse: ...


def validate_public_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"only public HTTP(S) URLs are allowed: {url}")
    if parsed.username or parsed.password:
        raise ValueError("credentials embedded in URLs are not allowed")

    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError(f"local network URL is not allowed: {url}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError(f"non-public IP address is not allowed: {url}")


def _validate_resolved_host(url: str) -> None:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no hostname: {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"hostname could not be resolved: {host}") from exc
    if not addresses:
        raise ValueError(f"hostname resolved to no addresses: {host}")
    for result in addresses:
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise ValueError(
                f"hostname resolved to non-public address {address}: {host}"
            )


class SafeHttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        max_response_bytes: int = 15_000_000,
        user_agent: str = DEFAULT_USER_AGENT,
        rate_limit_per_minute: int = 30,
        max_redirects: int = 5,
        allowed_domains: Iterable[str] | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be >= 1")
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be >= 1")
        if rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")
        if max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.user_agent = user_agent
        self.max_redirects = max_redirects
        self.allowed_domains = frozenset(
            str(domain).strip().lower()
            for domain in (allowed_domains or ())
            if str(domain).strip()
        )
        self.minimum_interval = 60.0 / rate_limit_per_minute
        self._last_request_at = 0.0
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "Accept": (
                    "application/json, application/xml, text/xml, "
                    "text/html;q=0.9, */*;q=0.5"
                ),
                "User-Agent": self.user_agent,
            }
        )

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < self.minimum_interval:
            time.sleep(self.minimum_interval - elapsed)

    def _validate_target(self, url: str) -> None:
        validate_public_http_url(url)
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if self.allowed_domains and host not in self.allowed_domains:
            raise ValueError(f"URL host is outside allowed domains: {url}")
        _validate_resolved_host(url)

    def _read_limited_content(self, response: requests.Response) -> bytes:
        declared_length = response.headers.get("content-length")
        if declared_length:
            try:
                if int(declared_length) > self.max_response_bytes:
                    raise ValueError(
                        f"response exceeded {self.max_response_bytes} bytes: "
                        f"{response.url}"
                    )
            except ValueError as exc:
                if "response exceeded" in str(exc):
                    raise

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            if not chunk:
                continue
            total += len(chunk)
            if total > self.max_response_bytes:
                raise ValueError(
                    f"response exceeded {self.max_response_bytes} bytes: "
                    f"{response.url}"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _finalize(
        self,
        response: requests.Response,
        *,
        allowed_statuses: set[int],
    ) -> FetchedResponse:
        validate_public_http_url(response.url)
        if response.status_code not in allowed_statuses:
            response.raise_for_status()
        content = self._read_limited_content(response)
        return FetchedResponse(
            url=response.url,
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            content=content,
        )

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        current_url = url
        current_params = params
        allowed = allowed_statuses or set()

        for redirect_count in range(self.max_redirects + 1):
            self._validate_target(current_url)
            self._wait_for_rate_limit()
            response = self.session.get(
                current_url,
                params=current_params,
                timeout=self.timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
            self._last_request_at = time.monotonic()
            try:
                location = response.headers.get("location")
                if response.is_redirect or response.is_permanent_redirect:
                    if not location:
                        raise ValueError(f"redirect response has no Location: {response.url}")
                    if redirect_count >= self.max_redirects:
                        raise ValueError(
                            f"too many redirects while fetching: {url}"
                        )
                    current_url = urljoin(response.url, location)
                    current_params = None
                    continue
                return self._finalize(response, allowed_statuses=allowed)
            finally:
                response.close()

        raise ValueError(f"too many redirects while fetching: {url}")

    def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, object],
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        current_url = url
        current_body: Mapping[str, object] | None = json_body
        allowed = allowed_statuses or set()

        for redirect_count in range(self.max_redirects + 1):
            self._validate_target(current_url)
            self._wait_for_rate_limit()
            if current_body is None:
                response = self.session.get(
                    current_url,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                )
            else:
                response = self.session.post(
                    current_url,
                    json=current_body,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                )
            self._last_request_at = time.monotonic()
            try:
                location = response.headers.get("location")
                if response.is_redirect or response.is_permanent_redirect:
                    if not location:
                        raise ValueError(f"redirect response has no Location: {response.url}")
                    if redirect_count >= self.max_redirects:
                        raise ValueError(
                            f"too many redirects while posting: {url}"
                        )
                    current_url = urljoin(response.url, location)
                    if response.status_code in {301, 302, 303}:
                        current_body = None
                    continue
                return self._finalize(response, allowed_statuses=allowed)
            finally:
                response.close()

        raise ValueError(f"too many redirects while posting: {url}")
