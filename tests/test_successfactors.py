from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pytest

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.successfactors import collect_successfactors
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
        source_id="bechtel_fixture",
        name="Bechtel official SAP careers",
        source_type="successfactors",
        enabled=True,
        company="Bechtel",
        options=options,
    )


def base_options() -> dict[str, object]:
    return {
        "page_url_template": "https://jobs.bechtel.com/search/?q=piping&startrow={offset}",
        "job_link_pattern": "/job/",
        "include_terms": ["piping", "e3d", "plant layout"],
        "location_terms": [],
        "closed_text_patterns": [
            "job you are trying to apply for has been filled",
            "position is no longer available",
        ],
        "page_size": 25,
        "max_pages": 3,
        "max_items": 20,
    }


def test_successfactors_filters_roles_paginates_and_parses_jobposting() -> None:
    page_zero = "https://jobs.bechtel.com/search/?q=piping&startrow=0"
    page_one = "https://jobs.bechtel.com/search/?q=piping&startrow=25"
    detail_url = "https://jobs.bechtel.com/job/Perth-Senior-Piping-Engineer-12345/"
    listing = f"""
    <table>
      <tr><td><a href="{detail_url}">Senior Piping Engineer</a></td>
          <td>Perth, Western Australia</td></tr>
      <tr><td><a href="/job/Perth-Electrical-Engineer-88888/">Electrical Engineer</a></td>
          <td>Perth, Western Australia</td></tr>
    </table>
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Piping Engineer",
        "description": "<p>AVEVA E3D piping layout and pipe support role.</p>",
        "datePosted": "2026-07-23",
        "hiringOrganization": {"name": "Bechtel"},
        "jobLocation": {
            "address": {
                "addressLocality": "Perth",
                "addressCountry": "Australia",
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
            page_zero: [html_response(page_zero, listing)],
            page_one: [html_response(page_one, "<html><body>No results</body></html>")],
            detail_url: [html_response(detail_url, detail)],
        }
    )

    result = collect_successfactors(source(**base_options()), client)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Senior Piping Engineer"
    assert job.company == "Bechtel"
    assert job.location == "Perth, Australia"
    assert job.apply_url == detail_url
    assert "AVEVA E3D" in job.description
    assert client.calls == [page_zero, page_one, detail_url]
    assert len(result.evidence) == 3


def test_successfactors_skips_confirmed_closed_vacancy() -> None:
    listing_url = "https://jobs.bechtel.com/search/?q=piping&startrow=0"
    next_url = "https://jobs.bechtel.com/search/?q=piping&startrow=25"
    detail_url = "https://jobs.bechtel.com/job/London-Piping-Designer-123/"
    listing = f"<a href='{detail_url}'>Piping Designer</a> London, United Kingdom"
    client = FakeClient(
        {
            listing_url: [html_response(listing_url, listing)],
            next_url: [html_response(next_url, "<html>No results</html>")],
            detail_url: [
                html_response(
                    detail_url,
                    "<html>Job you are trying to apply for has been filled.</html>",
                )
            ],
        }
    )

    result = collect_successfactors(source(**base_options()), client)

    assert result.jobs == []
    assert any("closed vacancy skipped" in warning for warning in result.warnings)


def test_successfactors_retains_listing_when_detail_temporarily_fails() -> None:
    listing_url = "https://jobs.bechtel.com/search/?q=piping&startrow=0"
    next_url = "https://jobs.bechtel.com/search/?q=piping&startrow=25"
    detail_url = "https://jobs.bechtel.com/job/Chennai-Piping-Engineer-456/"
    listing = (
        f"<li><a href='{detail_url}'>Piping Engineer</a> "
        "Chennai, Tamil Nadu, India</li>"
    )
    client = FakeClient(
        {
            listing_url: [html_response(listing_url, listing)],
            next_url: [html_response(next_url, "<html>No results</html>")],
            detail_url: [TimeoutError("simulated timeout")],
        }
    )

    result = collect_successfactors(source(**base_options()), client)

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Piping Engineer"
    assert result.jobs[0].apply_url == detail_url
    assert any("detail fetch failed" in warning for warning in result.warnings)


def test_successfactors_config_rejects_template_without_offset(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources:
          - id: bad_successfactors
            name: Bad SAP source
            type: successfactors
            company: Example EPC
            page_url_template: https://example.com/search
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

    with pytest.raises(ValueError, match="offset"):
        load_source_config(path)
