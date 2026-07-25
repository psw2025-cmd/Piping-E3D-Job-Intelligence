from __future__ import annotations

from collections.abc import Mapping

import pytest

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.public_notice import collect_public_notice
from job_intelligence.source_config import SourceSpec


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


def response(
    url: str,
    body: str | bytes,
    content_type: str = "text/html; charset=utf-8",
) -> FetchedResponse:
    content = body if isinstance(body, bytes) else body.encode("utf-8")
    return FetchedResponse(
        url=url,
        status_code=200,
        headers={"content-type": content_type},
        content=content,
    )


def source(**options: object) -> SourceSpec:
    return SourceSpec(
        source_id="npcil_fixture",
        name="NPCIL fixture",
        source_type="public_notice",
        enabled=True,
        company="Nuclear Power Corporation of India",
        options=options,
    )


def base_options(listing_url: str) -> dict[str, object]:
    return {
        "url": listing_url,
        "allowed_domains": ["www.npcil.nic.in"],
        "notice_link_patterns": [".pdf", "/content/"],
        "include_notice_terms": [
            "recruitment",
            "advertisement",
            "corrigendum",
            "extension",
        ],
        "exclude_notice_terms": [
            "result",
            "selected candidates",
            "admit card",
        ],
        "include_followup_notices": False,
        "country": "India",
        "location": "India",
        "sector": "Nuclear",
        "max_items": 20,
        "max_pdf_pages": 20,
        "deny_on_robots_error": True,
    }


def test_notice_table_extracts_advertisement_and_closing_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listing_url = "https://www.npcil.nic.in/content/289_1_Opportunities.aspx"
    advertisement_url = "https://www.npcil.nic.in/docs/et-2026.pdf"
    result_url = "https://www.npcil.nic.in/docs/result-2026.pdf"
    listing = f"""
    <table>
      <tr>
        <td>10.04.2026</td>
        <td>NPCIL/HQ/HRM/ET/2026/02</td>
        <td>Recruitment of Executive Trainees in Mechanical Engineering</td>
        <td>31.07.2026</td>
        <td><a href="{advertisement_url}">Download Advertisement</a></td>
      </tr>
      <tr>
        <td>20.04.2026</td>
        <td>Final result for selected candidates</td>
        <td><a href="{result_url}">Download Result</a></td>
      </tr>
    </table>
    """
    client = FakeClient(
        {
            listing_url: [response(listing_url, listing)],
            advertisement_url: [
                response(advertisement_url, b"%PDF-fixture", "application/pdf")
            ],
        }
    )
    monkeypatch.setattr(
        "job_intelligence.collectors.public_notice._extract_pdf_text",
        lambda _content, _pages: (
            "Recruitment of Executive Trainees. Piping and mechanical engineering. "
            "Last date of online application: 31 July 2026."
        ),
    )

    result = collect_public_notice(
        source(**base_options(listing_url)),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    job = result.jobs[0]
    assert "Executive Trainees" in job.title
    assert job.closing_at == "31 July 2026"
    assert job.country == "India"
    assert job.sector == "Nuclear"
    assert "Piping" in job.description
    assert result_url not in client.calls
    assert len(result.evidence) == 2


def test_corrigendum_is_retained_but_results_are_excluded() -> None:
    listing_url = "https://www.npcil.nic.in/content/289_1_Opportunities.aspx"
    correction_url = "https://www.npcil.nic.in/content/corrigendum.html"
    listing = f"""
    <ul>
      <li>
        Corrigendum: extension of last date for recruitment advertisement
        <a href="{correction_url}">Click here</a>
      </li>
      <li>
        Result and selected candidates for recruitment advertisement
        <a href="https://www.npcil.nic.in/content/result.html">Click here</a>
      </li>
    </ul>
    """
    detail = """
    <main>
      Corrigendum for recruitment of Mechanical Engineers.
      Application closes on 15 August 2026.
    </main>
    """
    client = FakeClient(
        {
            listing_url: [response(listing_url, listing)],
            correction_url: [response(correction_url, detail)],
        }
    )

    result = collect_public_notice(
        source(**base_options(listing_url)),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    assert "Notice kind: corrigendum" in result.jobs[0].description
    assert result.jobs[0].closing_at == "15 August 2026"


def test_document_failure_retains_listing_with_warning() -> None:
    listing_url = "https://www.npcil.nic.in/content/289_1_Opportunities.aspx"
    notice_url = "https://www.npcil.nic.in/docs/recruitment.pdf"
    listing = f"""
    <div>
      Recruitment advertisement for Senior Piping Engineer.
      <a href="{notice_url}">Download Advertisement</a>
    </div>
    """
    client = FakeClient(
        {
            listing_url: [response(listing_url, listing)],
            notice_url: [TimeoutError("simulated timeout")],
        }
    )

    result = collect_public_notice(
        source(**base_options(listing_url)),
        client,
        respect_robots_txt=False,
    )

    assert len(result.jobs) == 1
    assert result.jobs[0].apply_url == notice_url
    assert result.warnings
    assert "listing retained" in result.warnings[0]
    assert len(result.evidence) == 1
