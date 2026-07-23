from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_html import collect_public_html
from job_intelligence.source_config import SourceSpec, load_source_config


class FakeClient:
    user_agent = "FixtureCrawler/1.0"

    def __init__(self, routes: dict[str, list[FetchedResponse]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        del params, allowed_statuses
        self.calls.append(url)
        responses = self.routes[url]
        if not responses:
            raise AssertionError(f"No response remaining for {url}")
        return responses.pop(0)


def html_response(url: str, body: str) -> FetchedResponse:
    return FetchedResponse(
        url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def _production_source(source_id: str) -> SourceSpec:
    root = Path(__file__).resolve().parents[1]
    config = load_source_config(root / "config" / "sources.yaml")
    return next(source for source in config.sources if source.source_id == source_id)


def test_bechtel_successfactors_source_filters_and_parses_jobposting() -> None:
    spec = _production_source("bechtel_successfactors")
    listing_url = spec.require_text("url")
    detail_url = "https://jobs.bechtel.com/job/Test-Senior-Piping-Designer/123456/"
    listing_html = f"""
    <html><body>
      <a href="/job/Test-Accountant/999999/">Accountant</a>
      <a href="{detail_url}">Senior Piping Designer</a>
    </body></html>
    """
    jobposting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Piping Designer",
        "description": "<p>Smart 3D nuclear piping layout and model review.</p>",
        "datePosted": "2026-07-23",
        "employmentType": "FULL_TIME",
        "hiringOrganization": {"name": "Bechtel"},
        "jobLocation": {
            "address": {
                "addressLocality": "Knoxville",
                "addressRegion": "TN",
                "addressCountry": "United States",
            }
        },
        "url": detail_url,
    }
    detail_html = (
        "<html><script type='application/ld+json'>"
        + json.dumps(jobposting)
        + "</script></html>"
    )
    client = FakeClient(
        {
            listing_url: [html_response(listing_url, listing_html)],
            detail_url: [html_response(detail_url, detail_html)],
        }
    )

    result = collect_public_html(spec, client, respect_robots_txt=False)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Piping Designer"
    assert job.company == "Bechtel"
    assert "Knoxville" in job.location
    assert job.published_at == "2026-07-23"
    assert job.apply_url == detail_url
    assert client.calls == [listing_url, detail_url]


def test_petrofac_selectminds_source_filters_and_parses_public_detail() -> None:
    spec = _production_source("petrofac_latest_selectminds")
    listing_url = spec.require_text("url")
    detail_url = (
        "https://petrofac.referrals.selectminds.com/jobs/"
        "senior-engineer-piping-12146"
    )
    listing_html = f"""
    <html><body>
      <a href="/jobs/finance-analyst-999">Finance Analyst</a>
      <a href="{detail_url}">Senior Engineer - Piping</a>
    </body></html>
    """
    detail_html = """
    <html><head><title>Senior Engineer - Piping - Petrofac Careers</title></head>
    <body><main>
      <h1>Senior Engineer - Piping</h1>
      <p>Location: Chennai, India</p>
      <p>Jul 18, 2026 Post Date</p>
      <p>092325 Requisition #</p>
      <p>AVEVA E3D and PDMS petrochemical piping design role.</p>
    </main></body></html>
    """
    client = FakeClient(
        {
            listing_url: [html_response(listing_url, listing_html)],
            detail_url: [html_response(detail_url, detail_html)],
        }
    )

    result = collect_public_html(spec, client, respect_robots_txt=False)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Engineer - Piping"
    assert job.company == "Petrofac"
    assert job.location == "Chennai, India"
    assert "AVEVA E3D" in job.description
    assert job.apply_url == detail_url
    assert client.calls == [listing_url, detail_url]


def test_priority_sources_are_enabled_with_conservative_controls() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_source_config(root / "config" / "sources.yaml")
    by_id = {source.source_id: source for source in config.sources}

    expected = {
        "bechtel_successfactors",
        "petrofac_latest_selectminds",
        "petrofac_hot_selectminds",
        "petrofac_india_selectminds",
    }
    assert expected <= set(by_id)
    for source_id in expected:
        source = by_id[source_id]
        assert source.enabled is True
        assert source.source_type == "public_html"
        assert source.bool_option("fetch_details", True) is True
        assert source.bool_option("deny_on_robots_error", True) is True
        assert source.int_option("timeout_seconds", 30) <= 30
        assert source.int_option("rate_limit_per_minute", 30) <= 30
        assert source.int_option("max_response_bytes", 5_000_000) <= 5_000_000
