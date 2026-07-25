from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.lever import collect_lever
from job_intelligence.collectors.sitemap import collect_sitemap
from job_intelligence.collectors.smartrecruiters import collect_smartrecruiters
from job_intelligence.source_config import SourceSpec


class FakeClient:
    def __init__(
        self,
        routes: dict[str, list[FetchedResponse]],
        *,
        user_agent: str = "FixtureCrawler/1.0",
    ) -> None:
        self.routes = routes
        self.user_agent = user_agent
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        self.calls.append((url, params))
        values = self.routes[url]
        if not values:
            raise AssertionError(f"No fake response remaining for {url}")
        return values.pop(0)


def response(
    url: str,
    payload: object,
    content_type: str = "application/json",
    status_code: int = 200,
) -> FetchedResponse:
    content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return FetchedResponse(
        url=url,
        status_code=status_code,
        headers={"content-type": content_type},
        content=content,
    )


def source(source_type: str, **options: object) -> SourceSpec:
    return SourceSpec(
        source_id=f"limit_{source_type}",
        name=f"Limit {source_type}",
        source_type=source_type,
        enabled=True,
        company="Example EPC",
        options=options,
    )


def test_lever_stops_when_server_returns_more_than_requested() -> None:
    url = "https://api.lever.co/v0/postings/example"
    payload = [
        {
            "id": str(index),
            "text": f"Piping Engineer {index}",
            "hostedUrl": f"https://jobs.lever.co/example/{index}",
        }
        for index in range(3)
    ]
    client = FakeClient({url: [response(url, payload)]})

    result = collect_lever(
        source("lever", site="example", max_items=1, page_size=100),
        client,
    )

    assert len(result.jobs) == 1
    assert len(client.calls) == 1


def test_smartrecruiters_stops_before_excess_detail_requests() -> None:
    list_url = "https://api.smartrecruiters.com/v1/companies/example/postings"
    first_detail_url = f"{list_url}/one"
    payload = {
        "content": [
            {"id": "one", "name": "Piping Engineer One"},
            {"id": "two", "name": "Piping Engineer Two"},
        ]
    }
    client = FakeClient(
        {
            list_url: [response(list_url, payload)],
            first_detail_url: [
                response(
                    first_detail_url,
                    {
                        "id": "one",
                        "name": "Piping Engineer One",
                        "postingUrl": "https://example.com/jobs/one",
                    },
                )
            ],
        }
    )

    result = collect_smartrecruiters(
        source(
            "smartrecruiters",
            company_identifier="example",
            max_items=1,
            page_size=100,
            fetch_details=True,
        ),
        client,
    )

    assert len(result.jobs) == 1
    assert [call[0] for call in client.calls] == [list_url, first_detail_url]


def test_sitemap_caps_multiple_job_postings_on_one_page() -> None:
    sitemap_url = "https://example.com/jobs.xml"
    page_url = "https://example.com/careers/multiple"
    robots_url = "https://example.com/robots.txt"
    sitemap = (
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"<url><loc>{page_url}</loc></url></urlset>"
    ).encode()
    job_graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "JobPosting",
                "title": "Piping Engineer One",
                "hiringOrganization": {"name": "Example EPC"},
                "url": f"{page_url}#one",
            },
            {
                "@type": "JobPosting",
                "title": "Piping Engineer Two",
                "hiringOrganization": {"name": "Example EPC"},
                "url": f"{page_url}#two",
            },
        ],
    }
    page = (
        "<script type='application/ld+json'>"
        + json.dumps(job_graph)
        + "</script>"
    ).encode()
    client = FakeClient(
        {
            sitemap_url: [response(sitemap_url, sitemap, "application/xml")],
            robots_url: [response(robots_url, b"", "text/plain", 404)],
            page_url: [response(page_url, page, "text/html")],
        }
    )

    result = collect_sitemap(
        source("sitemap", url=sitemap_url, max_items=1),
        client,
    )

    assert len(result.jobs) == 1


def test_sitemap_robots_uses_same_user_agent_as_http_client() -> None:
    sitemap_url = "https://example.com/jobs.xml"
    page_url = "https://example.com/careers/blocked"
    robots_url = "https://example.com/robots.txt"
    sitemap = (
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"<url><loc>{page_url}</loc></url></urlset>"
    ).encode()
    robots = b"""User-agent: FixtureCrawler
Disallow: /careers/blocked

User-agent: *
Allow: /
"""
    client = FakeClient(
        {
            sitemap_url: [response(sitemap_url, sitemap, "application/xml")],
            robots_url: [response(robots_url, robots, "text/plain")],
        },
        user_agent="FixtureCrawler/1.0",
    )

    result = collect_sitemap(source("sitemap", url=sitemap_url), client)

    assert result.jobs == []
    assert page_url not in [call[0] for call in client.calls]


def test_lever_rejects_repeated_full_pages() -> None:
    url = "https://api.lever.co/v0/postings/example"
    repeated = [{"id": "invalid", "text": ""}]
    client = FakeClient(
        {url: [response(url, repeated), response(url, repeated)]}
    )

    with pytest.raises(ValueError, match="repeated a pagination page"):
        collect_lever(
            source(
                "lever",
                site="example",
                max_items=1,
                page_size=1,
                max_pages=4,
            ),
            client,
        )

    assert len(client.calls) == 2


def test_smartrecruiters_rejects_repeated_full_pages() -> None:
    url = "https://api.smartrecruiters.com/v1/companies/example/postings"
    repeated = {"content": [{"id": "invalid", "name": ""}]}
    client = FakeClient(
        {url: [response(url, repeated), response(url, repeated)]}
    )

    with pytest.raises(ValueError, match="repeated a pagination page"):
        collect_smartrecruiters(
            source(
                "smartrecruiters",
                company_identifier="example",
                fetch_details=False,
                max_items=1,
                page_size=1,
                max_pages=4,
            ),
            client,
        )

    assert len(client.calls) == 2
