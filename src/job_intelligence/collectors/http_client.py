from __future__ import annotations

import ipaddress
import json
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

import requests


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
            encoding = content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip()
        return self.content.decode(encoding or "utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
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


class SafeHttpClient:
    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        max_response_bytes: int = 15_000_000,
        user_agent: str = "Piping-E3D-Job-Intelligence/0.2 (+public-job-monitor)",
        rate_limit_per_minute: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        if rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")
        self.minimum_interval = 60.0 / rate_limit_per_minute
        self._last_request_at = 0.0
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.5",
                "User-Agent": user_agent,
            }
        )

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        validate_public_http_url(url)
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < self.minimum_interval:
            time.sleep(self.minimum_interval - elapsed)
        response = self.session.get(
            url,
            params=params,
            timeout=self.timeout_seconds,
            allow_redirects=True,
        )
        self._last_request_at = time.monotonic()
        validate_public_http_url(response.url)
        if response.status_code not in (allowed_statuses or set()):
            response.raise_for_status()
        content = response.content
        if len(content) > self.max_response_bytes:
            raise ValueError(
                f"response exceeded {self.max_response_bytes} bytes: {response.url}"
            )
        return FetchedResponse(
            url=response.url,
            status_code=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            content=content,
        )
