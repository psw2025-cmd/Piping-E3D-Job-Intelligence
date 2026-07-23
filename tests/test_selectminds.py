from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pytest

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.selectminds import collect_selectminds
from job_intelligence.source_config import SourceSpec, load_source_config


class FakeClient:
    user_agent = "FixtureCrawler/1.0"

    def __init__(self, routes: dict[str, list[FetchedResponse | Exception]]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        self.calls.append(url)
        values = self.routes[url]
        if not values:
            raise AssertionError(f"No fixture response remaining for {url}")
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def html_response(url: str, body: str) -> FetchedResponse:
    return FetchedResponse(
        url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def source(**options: object) -> SourceSpec:
    return SourceSpec(
        source_id="petrofac_fixture",
        name="Petrofac official SelectMinds careers",
        source_type="selectminds",
        enabled=True,
        company="Petrofac",
        options=options,
    )


def base_options() -> dict[str, object]:
    return {
        "url": "https://petrofac.referrals.selectminds.com/latest-jobs",
        "additional_urls": [
            "https://petrofac.referrals.selectminds.com/location/india-opportunities-280"
        ],
        "job_link_pattern": "/jobs/",
        "include_terms": ["piping", "e3d", "plant layout"],
        "location_terms": [],
        "closed_text_patterns": [
            "unfortunately this position has been closed",
            "position is no longer available",
        ],
        "max_items": 20,
    }


def test_selectminds_filters_roles_deduplicates_and_parses_jobposting() -> None:
    latest_url = "https://petrofac.referrals.selectminds.com/latest-jobs"
    india_url = (
        "https://petrofac.referrals.selectminds.com/location/"
        "india-opportunities-280"
    )
    detail_url = (
        "https://petrofac.referrals.selectminds.com/jobs/"
        "senior-piping-designer-12345"
    )
    unrelated_url = (
        "https://petrofac.referrals.selectminds.com/jobs/finance-analyst-22222"
    )
    latest = f"""
    <ul>
      <li><a href="{detail_url}">Senior Piping Designer</a>
          Chennai, Tamil Nadu, India</li>
      <li><a href="{unrelated_url}">Finance Analyst</a> Chennai, India</li>
    </ul>
    """
    india = f"<a href='{detail_url}'>Senior Piping Designer</a> Chennai, India"
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Piping Designer",
        "description": "<p>AVEVA E3D and PDMS plant layout role.</p>",
        "datePosted": "2026-07-23",
        "hiringOrganization": {"name": "Petrofac"},
        "jobLocation": {
            "address": {
                "addressLocality": "Chennai",
                "addressCountry": "India",
            }
        },
        "url": detail_url,
    }
    detail = (
        "<html><script type='application/ld+json'>"
        + json.dumps(payload)
        + "</script></html>"
    )
    client = FakeClient(
        {
            latest_url: [html_response(latest_url, latest)],
            india_url: [html_response(india_url, india)],
            detail_url: [html_response(detail_url, detail)],
        }
    )

    result = collect_selectminds(source(**base_options()), client)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Piping Designer"
    assert job.company == "Petrofac"
    assert job.location == "Chennai, India"
    assert job.apply_url == detail_url
    assert "AVEVA E3D" in job.description
    assert client.calls == [latest_url, india_url, detail_url]
    assert len(result.evidence) == 3


def test_selectminds_skips_confirmed_closed_vacancy() -> None:
    latest_url = "https://petrofac.referrals.selectminds.com/latest-jobs"
    india_url = (
        "https://petrofac.referrals.selectminds.com/location/"
        "india-opportunities-280"
    )
    detail_url = (
        "https://petrofac.referrals.selectminds.com/jobs/piping-engineer-98765"
    )
    listing = f"<li><a href='{detail_url}'>Piping Engineer</a> Abu Dhabi, UAE</li>"
    client = FakeClient(
        {
            latest_url: [html_response(latest_url, listing)],
            india_url: [html_response(india_url, "<html>No matching jobs</html>")],
            detail_url: [
                html_response(
                    detail_url,
                    "<html>Unfortunately this position has been closed.</html>",
                )
            ],
        }
    )

    result = collect_selectminds(source(**base_options()), client)

    assert result.jobs == []
    assert any("closed vacancy skipped" in warning for warning in result.warnings)


def test_selectminds_retains_listing_on_detail_failure() -> None:
    latest_url = "https://petrofac.referrals.selectminds.com/latest-jobs"
    india_url = (
        "https://petrofac.referrals.selectminds.com/location/"
        "india-opportunities-280"
    )
    detail_url = (
        "https://petrofac.referrals.selectminds.com/jobs/e3d-piping-designer-54321"
    )
    listing = f"<li><a href='{detail_url}'>E3D Piping Designer</a> Mumbai, India</li>"
    client = FakeClient(
        {
            latest_url: [html_response(latest_url, listing)],
            india_url: [html_response(india_url, "<html>No matching jobs</html>")],
            detail_url: [TimeoutError("simulated timeout")],
        }
    )

    result = collect_selectminds(source(**base_options()), client)

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "E3D Piping Designer"
    assert result.jobs[0].apply_url == detail_url
    assert any("detail fetch failed" in warning for warning in result.warnings)


def test_selectminds_config_rejects_additional_external_host(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources:
          - id: bad_selectminds
            name: Bad SelectMinds source
            type: selectminds
            company: Example EPC
            url: https://example.selectminds.com/latest-jobs
            additional_urls:
              - https://malicious.example/jobs
            include_terms: [piping]
            location_terms: []
            closed_text_patterns: [closed]
            enabled: true
        policy:
          respect_robots_txt: true
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="listing host"):
        load_source_config(path)
