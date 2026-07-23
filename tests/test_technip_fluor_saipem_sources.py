from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from job_intelligence.collectors.card_html import collect_card_html
from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_html import collect_public_html
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
        del params, allowed_statuses
        self.calls.append(url)
        values = self.routes[url]
        if not values:
            raise AssertionError(f"No fixture response remaining for {url}")
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def response(
    url: str,
    body: str,
    *,
    status_code: int = 200,
    content_type: str = "text/html; charset=utf-8",
) -> FetchedResponse:
    return FetchedResponse(
        url=url,
        status_code=status_code,
        headers={"content-type": content_type},
        content=body.encode("utf-8"),
    )


def production_source(source_id: str) -> SourceSpec:
    root = Path(__file__).resolve().parents[1]
    config = load_source_config(root / "config" / "sources.yaml")
    return next(source for source in config.sources if source.source_id == source_id)


def test_technip_oracle_source_is_active_and_bounded() -> None:
    source = production_source("technip_energies_oracle")

    assert source.enabled
    assert source.source_type == "oracle_hcm"
    assert source.require_text("base_url") == "https://hcxg.fa.em2.oraclecloud.com"
    assert source.require_text("site_number") == "CX_1"
    assert source.bool_option("profile_filter", False)
    assert source.int_option("max_scan_items", 2500) <= 5000
    assert source.int_option("max_pages", 100) <= 50
    assert source.int_option("rate_limit_per_minute", 30) <= 45


def test_fluor_filters_craft_role_and_parses_public_jobposting() -> None:
    production = production_source("fluor_successfactors")
    source = replace(production, options={**production.options, "max_pages": 1})
    listing_url = source.require_text("page_url_template").format(page=0)
    pipefitter_url = "https://thrivecareers.fluor.com/job/Tatum-Pipefitter-Welder-TX/100/"
    detail_url = (
        "https://thrivecareers.fluor.com/job/Greenville-"
        "Design-Engineer-II-Piping-SC/1370488600/"
    )
    listing_html = f"""
    <html><body>
      <a href="{pipefitter_url}">Pipefitter Welder</a>
      <a href="{detail_url}">Design Engineer II - Piping</a>
    </body></html>
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Design Engineer II - Piping",
        "description": "<p>Plant piping design, layout and pipe support.</p>",
        "datePosted": "2026-07-23",
        "hiringOrganization": {"name": "Fluor"},
        "jobLocation": {
            "address": {
                "addressLocality": "Greenville",
                "addressRegion": "SC",
                "addressCountry": "United States",
            }
        },
        "url": detail_url,
    }
    detail_html = (
        "<html><script type='application/ld+json'>"
        + json.dumps(payload)
        + "</script></html>"
    )
    client = FakeClient(
        {
            listing_url: [response(listing_url, listing_html)],
            detail_url: [response(detail_url, detail_html)],
        }
    )

    result = collect_public_html(source, client, respect_robots_txt=False)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Design Engineer II - Piping"
    assert job.company == "Fluor"
    assert "Greenville" in job.location
    assert job.apply_url == detail_url
    assert pipefitter_url not in client.calls
    assert client.calls == [listing_url, detail_url]


def test_saipem_generic_links_use_isolated_card_context() -> None:
    source = production_source("saipem_card_board")
    listing_url = source.require_text("url")
    robots_url = "https://jobs.saipem.com/robots.txt"
    piping_url = "https://jobs.saipem.com/?weekdayJdUid=635529"
    unrelated_url = "https://jobs.saipem.com/?weekdayJdUid=999999"
    listing_html = f"""
    <html><body>
      <article>
        <h3>Piping &amp; Layout Engineer</h3>
        <p>Offshore - Global Projects Services AG</p>
        <a href="{piping_url}">MORE DETAILS</a>
      </article>
      <article>
        <h3>Instrumentation Engineer</h3>
        <p>Qatar</p>
        <a href="{unrelated_url}">MORE DETAILS</a>
      </article>
    </body></html>
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Piping & Layout Engineer",
        "description": "<p>Offshore piping layout and E3D model coordination.</p>",
        "datePosted": "2026-06-03",
        "validThrough": "2026-12-31",
        "hiringOrganization": {"name": "Saipem"},
        "jobLocation": {"address": {"addressCountry": "Offshore"}},
        "url": piping_url,
    }
    detail_html = (
        "<html><script type='application/ld+json'>"
        + json.dumps(payload)
        + "</script></html>"
    )
    client = FakeClient(
        {
            robots_url: [
                response(
                    robots_url,
                    "User-agent: *\nAllow: /",
                    content_type="text/plain",
                )
            ],
            listing_url: [response(listing_url, listing_html)],
            piping_url: [response(piping_url, detail_html)],
        }
    )

    result = collect_card_html(source, client)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Piping & Layout Engineer"
    assert job.company == "Saipem"
    assert job.apply_url == piping_url
    assert unrelated_url not in client.calls
    assert client.calls == [robots_url, listing_url, piping_url]


def test_saipem_detail_failure_retains_heading_not_entire_card() -> None:
    source = production_source("saipem_card_board")
    listing_url = source.require_text("url")
    robots_url = "https://jobs.saipem.com/robots.txt"
    detail_url = "https://jobs.saipem.com/?weekdayJdUid=123456"
    listing_html = f"""
    <article>
      <h3>Senior Piping Designer</h3>
      <p>India</p>
      <a href="{detail_url}">MORE DETAILS</a>
    </article>
    """
    client = FakeClient(
        {
            robots_url: [
                response(
                    robots_url,
                    "User-agent: *\nAllow: /",
                    content_type="text/plain",
                )
            ],
            listing_url: [response(listing_url, listing_html)],
            detail_url: [TimeoutError("simulated timeout")],
        }
    )

    result = collect_card_html(source, client)

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Senior Piping Designer"
    assert result.jobs[0].apply_url == detail_url
    assert any("detail fetch failed" in warning for warning in result.warnings)


def test_card_source_rejects_listing_host_outside_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources:
          - id: bad_card
            name: Bad card source
            type: card_html
            company: Example EPC
            url: https://jobs.example.com/
            allowed_domains: [other.example.com]
            job_link_patterns: [job=]
            include_terms: [piping]
            location_terms: []
            exclude_terms: []
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
