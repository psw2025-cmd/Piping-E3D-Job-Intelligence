from __future__ import annotations

import socket
from typing import Any

import pytest
import requests

from job_intelligence.collectors import http_client
from job_intelligence.collectors.http_client import SafeHttpClient


class FakeResponse:
    def __init__(
        self,
        url: str,
        status_code: int,
        *,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self.closed = False
        self.is_redirect = status_code in {301, 302, 303, 307, 308}
        self.is_permanent_redirect = status_code in {301, 308}

    def iter_content(self, chunk_size: int) -> Any:
        del chunk_size
        yield from self._chunks

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.trust_env = True
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


def public_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]


def test_post_json_enforces_size_limit_and_closes_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_client.socket, "getaddrinfo", public_dns)
    response = FakeResponse(
        "https://example.com/workday/jobs",
        200,
        chunks=[b"1234", b"56"],
    )
    session = FakeSession([response])
    client = SafeHttpClient(
        session=session,
        max_response_bytes=5,
        rate_limit_per_minute=60_000,
    )

    with pytest.raises(ValueError, match="response exceeded 5 bytes"):
        client.post_json(
            "https://example.com/workday/jobs",
            json_body={"searchText": "piping"},
        )

    assert response.closed is True
    assert session.calls[0][0] == "POST"
    assert session.calls[0][2]["allow_redirects"] is False


def test_post_redirect_to_private_target_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_client.socket, "getaddrinfo", public_dns)
    redirect = FakeResponse(
        "https://example.com/workday/jobs",
        307,
        headers={"location": "http://127.0.0.1/private"},
    )
    session = FakeSession([redirect])
    client = SafeHttpClient(session=session, rate_limit_per_minute=60_000)

    with pytest.raises(ValueError, match="non-public IP address"):
        client.post_json(
            "https://example.com/workday/jobs",
            json_body={"searchText": "piping"},
        )

    assert len(session.calls) == 1
    assert redirect.closed is True


def test_post_303_switches_to_safe_get(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_client.socket, "getaddrinfo", public_dns)
    redirect = FakeResponse(
        "https://example.com/workday/jobs",
        303,
        headers={"location": "/workday/result"},
    )
    success = FakeResponse(
        "https://example.com/workday/result",
        200,
        headers={"content-type": "application/json"},
        chunks=[b"{}"],
    )
    session = FakeSession([redirect, success])
    client = SafeHttpClient(session=session, rate_limit_per_minute=60_000)

    result = client.post_json(
        "https://example.com/workday/jobs",
        json_body={"searchText": "piping"},
    )

    assert result.json() == {}
    assert [call[0] for call in session.calls] == ["POST", "GET"]
