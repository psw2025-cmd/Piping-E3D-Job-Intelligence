from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_html import collect_public_html
from job_intelligence.source_config import SourceSpec
from job_intelligence.source_registry import load_source_registry


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
            raise AssertionError(f"No fixture response remaining for {url}")
        return responses.pop(0)


def html_response(url: str, body: str) -> FetchedResponse:
    return FetchedResponse(
        url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def test_generic_apply_anchor_uses_job_card_context_and_keeps_agency_separate() -> None:
    listing_url = "https://www.airswift.com/jobs?page_num=1"
    detail_url = "https://www.airswift.com/jobs/senior-piping-designer-123"
    listing_html = f"""
    <html><body>
      <article>
        <span>Contract</span>
        <span>Date Published: 23 Jul 2026</span>
        <span>Location: Mumbai, India</span>
        <h3>Senior Piping Designer</h3>
        <p>AVEVA E3D refinery layout role.</p>
        <a href="{detail_url}">View Job and Apply</a>
      </article>
      <article>
        <h3>Finance Analyst</h3>
        <a href="/jobs/finance-999">View Job and Apply</a>
      </article>
    </body></html>
    """
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Piping Designer",
        "hiringOrganization": {"name": "Airswift"},
        "description": (
            "<p>AVEVA E3D and PDMS piping layout. Contact jobs@airswift.example.</p>"
        ),
        "datePosted": "2026-07-23",
        "employmentType": "CONTRACTOR",
        "jobLocation": {
            "address": {"addressLocality": "Mumbai", "addressCountry": "India"}
        },
        "url": detail_url,
    }
    detail_html = (
        "<html><script type='application/ld+json'>"
        + json.dumps(posting)
        + "</script></html>"
    )
    client = FakeClient(
        {
            listing_url: [html_response(listing_url, listing_html)],
            detail_url: [html_response(detail_url, detail_html)],
        }
    )
    spec = SourceSpec(
        source_id="airswift_fixture",
        name="Airswift fixture",
        source_type="public_html",
        enabled=True,
        company="Undisclosed client",
        options={
            "agency_name": "Airswift",
            "replace_agency_company": True,
            "url": listing_url,
            "allowed_domains": ["www.airswift.com"],
            "job_link_patterns": ["/jobs/"],
            "anchor_text_patterns": ["piping designer", "e3d", "pdms"],
            "exclude_anchor_text_patterns": ["finance"],
            "fetch_details": True,
            "deny_on_robots_error": True,
            "max_items": 10,
        },
    )

    result = collect_public_html(spec, client, respect_robots_txt=False)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Piping Designer"
    assert job.company == "Undisclosed client"
    assert job.agency_name == "Airswift"
    assert job.location == "Mumbai, India"
    assert job.recruiter_email == "jobs@airswift.example"
    assert job.contact_confidence == "PUBLIC_UNVERIFIED"
    assert job.contact_source_url == detail_url
    assert client.calls == [listing_url, detail_url]


def test_recruiter_sources_are_enabled_and_config_driven() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_source_registry(root / "config" / "sources.yaml")
    by_id = {source.source_id: source for source in registry.sources}

    expected = {
        "airswift_global_public": "Airswift",
        "nesfircroft_piping_public": "NES Fircroft",
        "brunel_global_public": "Brunel",
    }
    for source_id, agency in expected.items():
        source = by_id[source_id]
        assert source.enabled is True
        assert source.source_type == "public_html"
        assert source.company == "Undisclosed client"
        assert source.options["agency_name"] == agency
        assert source.bool_option("replace_agency_company", False) is True
        assert source.bool_option("fetch_details", False) is True
        assert source.bool_option("deny_on_robots_error", False) is True
        assert source.int_option("timeout_seconds", 30) <= 30
        assert source.int_option("max_response_bytes", 5_000_000) <= 5_000_000
