from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pytest

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_html import collect_public_html
from job_intelligence.source_config import SourceSpec, load_source_config


class FakeClient:
    user_agent = "FixtureCrawler/1.0"

    def __init__(self, routes: dict[str, list[FetchedResponse]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        self.calls.append((url, params))
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


def source(**options: object) -> SourceSpec:
    return SourceSpec(
        source_id="mcdermott_test",
        name="McDermott test",
        source_type="public_html",
        enabled=True,
        company="McDermott",
        options=options,
    )


def test_role_and_location_filters_skip_hot_jobs_and_scan_later_pages() -> None:
    page_zero = "https://www.mcdermott.com/careers/search-apply?page=0"
    page_one = "https://www.mcdermott.com/careers/search-apply?page=1"
    unrelated_url = (
        "https://edsv.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/job/100"
    )
    relevant_url = (
        "https://edsv.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/job/200"
    )
    page_zero_html = f"""
    <html><body>
      <a href="{unrelated_url}">
        Hot Job Senior Piping Engineer Job ID: 100 Houston, Texas, United States Full Time
      </a>
      <a href="{unrelated_url}?other=1">
        Finance Analyst Job ID: 101 Dubai, Dubai, United Arab Emirates Full Time
      </a>
    </body></html>
    """
    page_one_html = f"""
    <html><body>
      <a href="{relevant_url}">
        Principal Piping Engineer Job ID: 200 Dubai, Dubai, United Arab Emirates Full Time
      </a>
    </body></html>
    """
    detail_json_ld = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Principal Piping Engineer",
        "description": "<p>AVEVA E3D offshore piping role.</p>",
        "hiringOrganization": {"name": "McDermott"},
        "jobLocation": {
            "address": {
                "addressLocality": "Dubai",
                "addressCountry": "United Arab Emirates",
            }
        },
        "url": relevant_url,
    }
    detail_html = (
        "<html><script type='application/ld+json'>"
        + json.dumps(detail_json_ld)
        + "</script></html>"
    )
    client = FakeClient(
        {
            page_zero: [html_response(page_zero, page_zero_html)],
            page_one: [html_response(page_one, page_one_html)],
            relevant_url: [html_response(relevant_url, detail_html)],
        }
    )

    result = collect_public_html(
        source(
            url=page_zero,
            page_url_template=(
                "https://www.mcdermott.com/careers/search-apply?page={page}"
            ),
            page_start=0,
            page_step=1,
            max_pages=2,
            max_items=10,
            allowed_domains=[
                "www.mcdermott.com",
                "edsv.fa.us2.oraclecloud.com",
            ],
            job_link_patterns=["/hcmUI/CandidateExperience/en/sites/CX_1/job/"],
            anchor_text_patterns=["Piping", "E3D", "PDMS"],
            required_anchor_text_patterns=[
                "Dubai",
                "United Arab Emirates",
            ],
            exclude_anchor_text_patterns=["Hot Job"],
            fetch_details=True,
            deny_on_robots_error=True,
        ),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Principal Piping Engineer"
    assert result.jobs[0].location == "Dubai, United Arab Emirates"
    assert [call[0] for call in client.calls] == [
        page_zero,
        page_one,
        relevant_url,
    ]


def test_fallback_detail_parser_extracts_public_labels() -> None:
    listing_url = "https://www.mcdermott.com/careers/search-apply?page=0"
    detail_url = (
        "https://edsv.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/job/300"
    )
    listing_html = f"""
    <a href="{detail_url}">
      Senior Piping Designer Job ID: 300 Chennai, Tamil Nadu, India Full Time
    </a>
    """
    detail_html = """
    <html>
      <head><title>Senior Piping Designer - Job Details</title></head>
      <body><main>
        <h1>Senior Piping Designer</h1>
        <p>Posting Date: 2026-07-22</p>
        <p>Work Location: Chennai, Tamil Nadu, India</p>
        <p>Job Schedule: Full Time</p>
        <p>AVEVA E3D and PDMS piping layout responsibilities.</p>
      </main></body>
    </html>
    """
    client = FakeClient(
        {
            listing_url: [html_response(listing_url, listing_html)],
            detail_url: [html_response(detail_url, detail_html)],
        }
    )

    result = collect_public_html(
        source(
            url=listing_url,
            allowed_domains=[
                "www.mcdermott.com",
                "edsv.fa.us2.oraclecloud.com",
            ],
            job_link_patterns=["/hcmUI/CandidateExperience/en/sites/CX_1/job/"],
            anchor_text_patterns=["Piping"],
            required_anchor_text_patterns=["Chennai", "India"],
            max_items=5,
            fetch_details=True,
            deny_on_robots_error=True,
        ),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Piping Designer"
    assert job.location == "Chennai, Tamil Nadu, India"
    assert job.published_at == "2026-07-22"
    assert job.job_type == "Full Time"
    assert "AVEVA E3D" in job.description


def test_public_html_generated_page_cannot_leave_allowlist() -> None:
    spec = source(
        url="https://www.mcdermott.com/careers/search-apply?page=0",
        page_url_template="https://malicious.example/jobs?page={page}",
        max_pages=1,
        allowed_domains=["www.mcdermott.com"],
        job_link_patterns=["/job/"],
        fetch_details=False,
        deny_on_robots_error=True,
    )

    with pytest.raises(ValueError, match="outside allowed domains"):
        collect_public_html(spec, FakeClient({}), respect_robots_txt=False)


def test_public_html_config_rejects_non_text_role_filters(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources:
          - id: invalid_public_html
            name: Invalid public HTML
            type: public_html
            company: Example EPC
            url: https://example.com/jobs
            allowed_domains: [example.com]
            job_link_patterns: [/job/]
            required_anchor_text_patterns: [Mumbai, 123]
            enabled: true
        policy:
          respect_robots_txt: true
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contain only text"):
        load_source_config(path)
