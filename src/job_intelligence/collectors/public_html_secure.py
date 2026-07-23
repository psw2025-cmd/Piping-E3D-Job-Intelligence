from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from ..source_config import SourceSpec
from .common import CollectionResult
from .http_client import FetchedResponse, HttpClient
from .public_html import collect_public_html as _collect_public_html


class _DomainGuardClient:
    def __init__(self, client: HttpClient, allowed_domains: set[str]) -> None:
        self._client = client
        self._allowed_domains = allowed_domains
        self.user_agent = getattr(client, "user_agent", "")

    def _validate(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        if host not in self._allowed_domains:
            raise ValueError(f"response redirected outside allowed domains: {url}")

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        self._validate(url)
        response = self._client.get(
            url,
            params=params,
            allowed_statuses=allowed_statuses,
        )
        self._validate(response.url)
        return response

    def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, object],
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        self._validate(url)
        response = self._client.post_json(
            url,
            json_body=json_body,
            allowed_statuses=allowed_statuses,
        )
        self._validate(response.url)
        return response


def collect_public_html(
    spec: SourceSpec,
    client: HttpClient,
    *,
    respect_robots_txt: bool = True,
) -> CollectionResult:
    allowed_domains = set(spec.text_list_option("allowed_domains"))
    guarded = _DomainGuardClient(client, allowed_domains)
    return _collect_public_html(
        spec,
        guarded,
        respect_robots_txt=respect_robots_txt,
    )
