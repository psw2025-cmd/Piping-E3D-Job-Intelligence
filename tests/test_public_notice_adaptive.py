from __future__ import annotations

from collections.abc import Mapping

from job_intelligence.collectors import COLLECTORS
from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_notice_adaptive import (
    collect_public_notice_adaptive,
)
from job_intelligence.source_config import SourceSpec


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
        self.calls.append(url)
        values = self.routes[url]
        if not values:
            raise AssertionError(f"No fixture response remaining for {url}")
        return values.pop(0)


def response(url: str, body: str) -> FetchedResponse:
    return FetchedResponse(
        url=url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def source(listing_url: str) -> SourceSpec:
    return SourceSpec(
        source_id="gail_fixture",
        name="GAIL fixture",
        source_type="public_notice",
        enabled=True,
        company="GAIL India",
        options={
            "url": listing_url,
            "allowed_domains": ["gailonline.com"],
            "notice_link_patterns": ["/notice/"],
            "include_notice_terms": ["career opportunities", "advertisement"],
            "exclude_notice_terms": ["result", "selected candidates"],
            "include_followup_notices": False,
            "country": "India",
            "location": "India",
            "sector": "Gas; Pipelines",
            "max_items": 5,
            "max_pdf_pages": 5,
            "deny_on_robots_error": True,
        },
    )


def test_production_dispatch_uses_adaptive_public_notice_collector() -> None:
    assert COLLECTORS["public_notice"] is collect_public_notice_adaptive


def test_embedded_gail_template_extracts_card_title_dates_and_one_notice() -> None:
    listing_url = "https://gailonline.com/Vacancies.html"
    detail_url = "https://gailonline.com/notice/piping-advertisement.html"
    faq_url = "https://gailonline.com/notice/piping-faq.html"
    listing = f"""
    <html><body><script>
    const careerData = {{
      current: `
        <div class="vacancy-card">
          <div class="vacancy-info">
            <h3>CAREER OPPORTUNITIES FOR SENIOR PIPING ENGINEER</h3>
            <p>ADVERTISEMENT NO.: GAIL/OPEN/PIPING/2026</p>
            <a href="{detail_url}">Detailed Advertisement</a>
            <a href="{faq_url}">Frequently Asked Questions (FAQs)</a>
          </div>
          <div class="vacancy-dates">
            <p><strong>Post Date:</strong>20.02.2026</p>
            <p><strong>Last Date:</strong>18.03.2026</p>
          </div>
        </div>
      `
    }};
    </script></body></html>
    """
    detail = """
    <main>
      Recruitment advertisement for Senior Piping Engineer.
      AVEVA E3D plant layout and pipe-support responsibilities.
    </main>
    """
    client = FakeClient(
        {
            listing_url: [response(listing_url, listing)],
            detail_url: [response(detail_url, detail)],
        }
    )

    result = collect_public_notice_adaptive(
        source(listing_url),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert job.title == "CAREER OPPORTUNITIES FOR SENIOR PIPING ENGINEER"
    assert job.published_at == "20.02.2026"
    assert job.closing_at == "18.03.2026"
    assert "AVEVA E3D" in job.description
    assert faq_url not in client.calls
    assert [artifact.source_url for artifact in result.evidence] == [
        listing_url,
        detail_url,
    ]


def test_normal_dom_notice_is_still_supported() -> None:
    listing_url = "https://gailonline.com/Vacancies.html"
    detail_url = "https://gailonline.com/notice/normal.html"
    listing = f"""
    <article>
      <h3>Recruitment of Piping Design Engineers</h3>
      <a href="{detail_url}">Download Advertisement</a>
      <p>Last Date: 31.07.2026</p>
    </article>
    """
    client = FakeClient(
        {
            listing_url: [response(listing_url, listing)],
            detail_url: [response(detail_url, "<main>Piping design role</main>")],
        }
    )

    result = collect_public_notice_adaptive(
        source(listing_url),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Recruitment of Piping Design Engineers"
    assert result.jobs[0].closing_at == "31.07.2026"
