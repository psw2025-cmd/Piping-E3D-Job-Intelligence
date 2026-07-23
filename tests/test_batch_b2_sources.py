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


def _production_source(source_id: str) -> SourceSpec:
    root = Path(__file__).resolve().parents[1]
    config = load_source_config(root / "config" / "sources.yaml")
    return next(source for source in config.sources if source.source_id == source_id)


def test_fluor_source_filters_craft_role_and_parses_public_job() -> None:
    production = _production_source("fluor_successfactors")
    spec = replace(production, options={**production.options, "max_pages": 1})
    listing_url = spec.require_text("page_url_template").format(page=0)
    detail_url = (
        "https://thrivecareers.fluor.com/job/Greenville-"
        "Design-Engineer-II-Piping-SC/1370488600/"
    )
    listing_html = f"""
    <html><body>
      <a href="/job/Tatum-Pipefitter-Welder-TX/100/">Pipefitter Welder</a>
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

    result = collect_public_html(spec, client, respect_robots_txt=False)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Design Engineer II - Piping"
    assert job.company == "Fluor"
    assert "Greenville" in job.location
    assert job.apply_url == detail_url
    assert client.calls == [listing_url, detail_url]


def test_saipem_card_source_filters_on_card_context_and_parses_detail() -> None:
    spec = _production_source("saipem_card_board")
    listing_url = spec.require_text("url")
    robots_url = "https://jobs.saipem.com/robots.txt"
    detail_url = "https://jobs.saipem.com/?weekdayJdUid=635529"
    listing_html = f"""
    <html><body>
      <article>
        <h3>Piping &amp; Layout Engineer</h3>
        <p>Offshore - Global Projects Services AG</p>
        <a href="{detail_url}">MORE DETAILS</a>
      </article>
      <article>
        <h3>Instrumentation Engineer</h3>
        <p>Qatar</p>
        <a href="/?weekdayJdUid=999999">MORE DETAILS</a>
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
        "url": detail_url,
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
            detail_url: [response(detail_url, detail_html)],
        }
    )

    result = collect_card_html(spec, client)

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "Piping & Layout Engineer"
    assert job.company == "Saipem"
    assert "Offshore piping layout" in job.description
    assert job.apply_url == detail_url
    assert client.calls == [robots_url, listing_url, detail_url]


def test_batch_b2_sources_are_enabled_and_bounded() -> None:
    technip = _production_source("technip_energies_oracle")
    fluor = _production_source("fluor_successfactors")
    saipem = _production_source("saipem_card_board")

    assert technip.enabled and technip.source_type == "oracle_hcm"
    assert technip.require_text("base_url") == "https://hcxg.fa.em2.oraclecloud.com"
    assert technip.require_text("site_number") == "CX_1"
    assert technip.int_option("max_scan_items", 2500) <= 4000
    assert technip.int_option("rate_limit_per_minute", 30) <= 45

    assert fluor.enabled and fluor.source_type == "public_html"
    assert fluor.bool_option("deny_on_robots_error", True)
    assert fluor.int_option("max_pages", 100) <= 12
    assert fluor.int_option("rate_limit_per_minute", 30) <= 20

    assert saipem.enabled and saipem.source_type == "card_html"
    assert saipem.bool_option("deny_on_robots_error", True)
    assert saipem.int_option("max_pages", 100) == 1
    assert saipem.int_option("rate_limit_per_minute", 30) <= 15


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
