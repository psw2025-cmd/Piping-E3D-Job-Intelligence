from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.workday import collect_workday
from job_intelligence.source_config import SourceSpec, load_source_config


class FakeClient:
    user_agent = "FixtureCrawler/1.0"

    def __init__(
        self,
        *,
        searches: list[dict[str, object]],
        details: dict[str, dict[str, object]],
    ) -> None:
        self.searches = list(searches)
        self.details = details
        self.post_calls: list[tuple[str, Mapping[str, object]]] = []
        self.get_calls: list[str] = []

    def post_json(
        self,
        url: str,
        *,
        json_body: Mapping[str, object],
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        del allowed_statuses
        self.post_calls.append((url, json_body))
        if not self.searches:
            raise AssertionError(f"No search fixture remaining for {url}")
        payload = self.searches.pop(0)
        return FetchedResponse(
            url=url,
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(payload).encode("utf-8"),
        )

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        del params, allowed_statuses
        self.get_calls.append(url)
        payload = self.details[url]
        return FetchedResponse(
            url=url,
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(payload).encode("utf-8"),
        )


def workday_spec(**overrides: object) -> SourceSpec:
    options: dict[str, object] = {
        "base_url": "https://tenant.wd5.myworkdayjobs.com",
        "tenant": "tenant",
        "site": "External_Careers",
        "locale": "en-US",
        "search_terms": ["piping", "e3d"],
        "include_terms": ["piping", "e3d", "smart 3d"],
        "location_terms": [],
        "max_items": 20,
        "max_scan_items": 100,
        "max_pages": 10,
        "page_size": 20,
    }
    options.update(overrides)
    return SourceSpec(
        source_id="fixture_workday",
        name="Fixture Workday",
        source_type="workday",
        enabled=True,
        company="Fixture EPC",
        options=options,
    )


def detail_url(path: str) -> str:
    return f"https://tenant.wd5.myworkdayjobs.com/wday/cxs/tenant/External_Careers{path}"


def test_workday_collects_details_and_deduplicates_across_search_terms() -> None:
    piping_path = "/job/Chennai/Senior-Piping-Designer_R100"
    e3d_path = "/job/Mumbai/E3D-Administrator_R200"
    client = FakeClient(
        searches=[
            {
                "total": 2,
                "jobPostings": [
                    {
                        "title": "Senior Piping Designer",
                        "externalPath": piping_path,
                        "locationsText": "Chennai, India",
                        "postedOn": "Posted 2 Days Ago",
                        "bulletFields": ["R100"],
                    },
                    {
                        "title": "Accountant",
                        "externalPath": "/job/Finance/Accountant_R999",
                        "locationsText": "Delhi, India",
                    },
                ],
            },
            {
                "total": 2,
                "jobPostings": [
                    {
                        "title": "Senior Piping Designer",
                        "externalPath": piping_path,
                        "locationsText": "Chennai, India",
                    },
                    {
                        "title": "Smart 3D / E3D Administrator",
                        "externalPath": e3d_path,
                        "locationsText": "Mumbai, India",
                    },
                ],
            },
        ],
        details={
            detail_url(piping_path): {
                "jobPostingInfo": {
                    "title": "Senior Piping Designer",
                    "location": "Chennai, Tamil Nadu, India",
                    "jobDescription": (
                        "<p>Offshore AVEVA E3D and PDMS piping layout role.</p>"
                    ),
                    "startDate": "2026-07-21",
                    "timeType": "Full time",
                    "jobReqId": "R100",
                }
            },
            detail_url(e3d_path): {
                "jobPostingInfo": {
                    "title": "Smart 3D / E3D Administrator",
                    "location": "Mumbai, Maharashtra, India",
                    "jobDescription": "<p>Smart 3D administration and model support.</p>",
                    "startDate": "2026-07-22",
                    "timeType": "Full time",
                    "jobReqId": "R200",
                    "externalUrl": (
                        "https://tenant.wd5.myworkdayjobs.com/en-US/"
                        "External_Careers/job/Mumbai/E3D-Administrator_R200"
                    ),
                }
            },
        },
    )

    result = collect_workday(workday_spec(), client)

    assert len(result.jobs) == 2
    assert {job.title for job in result.jobs} == {
        "Senior Piping Designer",
        "Smart 3D / E3D Administrator",
    }
    piping = next(job for job in result.jobs if job.title == "Senior Piping Designer")
    assert piping.company == "Fixture EPC"
    assert piping.location == "Chennai, Tamil Nadu, India"
    assert piping.published_at == "2026-07-21"
    assert piping.employment_type == "Full time"
    assert piping.apply_url.endswith(
        "/en-US/External_Careers/job/Chennai/Senior-Piping-Designer_R100"
    )
    assert len(client.get_calls) == 2
    assert len(result.evidence) == 4


def test_workday_location_filter_and_malformed_response() -> None:
    path = "/job/Calgary/Piping-Engineer_R300"
    client = FakeClient(
        searches=[
            {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Piping Engineer",
                        "externalPath": path,
                        "locationsText": "Calgary, Canada",
                    }
                ],
            }
        ],
        details={
            detail_url(path): {
                "jobPostingInfo": {
                    "title": "Piping Engineer",
                    "location": "Calgary, Canada",
                    "jobDescription": "<p>Piping layout engineering.</p>",
                }
            }
        },
    )

    result = collect_workday(
        workday_spec(search_terms=["piping"], location_terms=["india"]),
        client,
    )

    assert result.jobs == []
    assert len(result.evidence) == 2


def test_production_kbr_and_atkins_workday_sources_are_enabled() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_source_config(root / "config" / "sources.yaml")
    by_id = {source.source_id: source for source in config.sources}

    for source_id, company, host in (
        ("kbr_workday", "KBR", "kbr.wd5.myworkdayjobs.com"),
        ("atkinsrealis_workday", "AtkinsRealis", "slihrms.wd3.myworkdayjobs.com"),
    ):
        source = by_id[source_id]
        assert source.enabled is True
        assert source.source_type == "workday"
        assert source.company == company
        assert host in source.require_text("base_url")
        assert "piping" in source.text_list_option("search_terms")
        assert source.int_option("page_size", 20) <= 100
        assert source.int_option("timeout_seconds", 30) <= 30
