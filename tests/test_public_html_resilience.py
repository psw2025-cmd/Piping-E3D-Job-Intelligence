from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from job_intelligence.collection_runner import collect_sources
from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_html import collect_public_html
from job_intelligence.database import connect, fetch_jobs
from job_intelligence.source_config import SourceSpec


class DetailFailureClient:
    user_agent = "FixtureCrawler/1.0"

    def __init__(self, listing_url: str, detail_url: str, detail_body: str | None) -> None:
        self.listing_url = listing_url
        self.detail_url = detail_url
        self.detail_body = detail_body

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        if url == self.listing_url:
            body = f"""
            <a href="{self.detail_url}">
              Senior Piping Engineer Job ID: 400 Dubai, Dubai,
              United Arab Emirates Full Time
            </a>
            """
            return FetchedResponse(
                url=url,
                status_code=200,
                headers={"content-type": "text/html"},
                content=body.encode(),
            )
        if url == self.detail_url and self.detail_body is not None:
            return FetchedResponse(
                url=url,
                status_code=200,
                headers={"content-type": "text/html"},
                content=self.detail_body.encode(),
            )
        raise TimeoutError("simulated detail timeout")


def source(listing_url: str) -> SourceSpec:
    return SourceSpec(
        source_id="mcdermott_resilience",
        name="McDermott resilience",
        source_type="public_html",
        enabled=True,
        company="McDermott",
        options={
            "url": listing_url,
            "allowed_domains": [
                "www.mcdermott.com",
                "edsv.fa.us2.oraclecloud.com",
            ],
            "job_link_patterns": [
                "/hcmUI/CandidateExperience/en/sites/CX_1/job/"
            ],
            "anchor_text_patterns": ["Piping"],
            "required_anchor_text_patterns": [
                "Dubai",
                "United Arab Emirates",
            ],
            "max_items": 5,
            "fetch_details": True,
            "deny_on_robots_error": True,
        },
    )


def test_detail_failure_keeps_official_listing_and_warning() -> None:
    listing_url = "https://www.mcdermott.com/careers/search-apply?page=0"
    detail_url = (
        "https://edsv.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/job/400"
    )

    result = collect_public_html(
        source(listing_url),
        DetailFailureClient(listing_url, detail_url, None),
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Senior Piping Engineer"
    assert result.jobs[0].location == "Dubai, Dubai, United Arab Emirates"
    assert result.jobs[0].apply_url == detail_url
    assert result.warnings
    assert "detail fetch failed" in result.warnings[0]


def test_generic_detail_title_falls_back_to_listing_title() -> None:
    listing_url = "https://www.mcdermott.com/careers/search-apply?page=0"
    detail_url = (
        "https://edsv.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/job/400"
    )
    detail_body = "<html><head><title>Job Details</title></head><body></body></html>"

    result = collect_public_html(
        source(listing_url),
        DetailFailureClient(listing_url, detail_url, detail_body),
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Senior Piping Engineer"
    assert result.jobs[0].description


def test_runner_records_pass_with_warnings(tmp_path: Path) -> None:
    listing_url = "https://www.mcdermott.com/careers/search-apply?page=0"
    detail_url = (
        "https://edsv.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/job/400"
    )
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        f"""
        sources:
          - id: mcdermott_resilience
            name: McDermott resilience
            type: public_html
            company: McDermott
            url: {listing_url}
            allowed_domains:
              - www.mcdermott.com
              - edsv.fa.us2.oraclecloud.com
            job_link_patterns:
              - /hcmUI/CandidateExperience/en/sites/CX_1/job/
            anchor_text_patterns: [Piping]
            required_anchor_text_patterns: [Dubai, United Arab Emirates]
            max_items: 5
            fetch_details: true
            deny_on_robots_error: true
            enabled: true
        policy:
          respect_robots_txt: false
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )

    summary = collect_sources(
        tmp_path / "jobs.db",
        config_path,
        tmp_path / "raw",
        client_factory=lambda _source: DetailFailureClient(
            listing_url,
            detail_url,
            None,
        ),
    )

    assert summary.status == "pass"
    assert summary.source_results[0].status == "pass_with_warnings"
    assert len(fetch_jobs(tmp_path / "jobs.db")) == 1
    with connect(tmp_path / "jobs.db") as connection:
        health = connection.execute(
            "SELECT status, error_message FROM source_health"
        ).fetchone()
    assert health["status"] == "pass_with_warnings"
    assert "detail fetch failed" in health["error_message"]
