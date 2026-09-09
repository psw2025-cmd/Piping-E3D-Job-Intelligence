from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.collectors.oracle_hcm import collect_oracle_hcm
from job_intelligence.source_config import SourceSpec


class FakeClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        del allowed_statuses
        self.calls.append(dict(params or {}))
        if not self.payloads:
            raise AssertionError(f"No fake Oracle response remaining for {url}")
        import json

        payload = self.payloads.pop(0)
        return FetchedResponse(
            url=url,
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(payload).encode("utf-8"),
        )


def source(**options: object) -> SourceSpec:
    defaults: dict[str, object] = {
        "base_url": "https://example.fa.oraclecloud.com",
        "site_number": "CX_1",
        "include_terms": ["piping", "e3d"],
        "location_terms": ["india", "qatar"],
        "max_items": 10,
        "max_scan_items": 20,
        "max_pages": 5,
        "page_size": 2,
    }
    defaults.update(options)
    return SourceSpec(
        source_id="example_oracle",
        name="Example official careers",
        source_type="oracle_hcm",
        enabled=True,
        company="Example EPC",
        options=defaults,
    )


def wrapper(
    rows: list[dict[str, Any]],
    *,
    total: int | object = 0,
    offset: int | object = 0,
    limit: int | object | None = None,
) -> dict[str, Any]:
    return {
        "items": [
            {
                "TotalJobsCount": total,
                "Limit": len(rows) if limit is None else limit,
                "Offset": offset,
                "requisitionList": rows,
            }
        ],
        "count": 1,
        "hasMore": False,
    }


def test_collects_filtered_jobs_across_pages() -> None:
    client = FakeClient(
        [
            wrapper(
                [
                    {
                        "Id": "1001",
                        "Title": "Senior Piping Designer",
                        "PrimaryLocation": "Mumbai, Maharashtra, India",
                        "PostedDate": "2026-07-22",
                        "ShortDescriptionStr": "<p>AVEVA E3D plant layout</p>",
                        "ExternalResponsibilitiesStr": "Route piping systems",
                        "ExternalQualificationsStr": "Diploma in engineering",
                        "JobFunction": "Piping",
                        "JobFamily": "Engineering",
                        "JobType": "Regular",
                        "JobSchedule": "Full time",
                    },
                    {
                        "Id": "1002",
                        "Title": "Finance Analyst",
                        "PrimaryLocation": "Chennai, Tamil Nadu, India",
                    },
                ],
                total=3,
            ),
            wrapper(
                [
                    {
                        "Id": "1003",
                        "Title": "Lead E3D Administrator",
                        "PrimaryLocation": "Doha, Qatar",
                        "PostedDate": "2026-07-21",
                        "ShortDescriptionStr": "Maintain PDMS and E3D projects",
                    }
                ],
                total=3,
                offset=2,
            ),
        ]
    )

    result = collect_oracle_hcm(source(), client)

    assert [job.title for job in result.jobs] == [
        "Senior Piping Designer",
        "Lead E3D Administrator",
    ]
    assert result.jobs[0].description.startswith("AVEVA E3D plant layout")
    assert result.jobs[0].apply_url.endswith("/sites/CX_1/job/1001")
    assert result.jobs[0].published_at == "2026-07-22"
    assert len(result.evidence) == 2
    assert "offset" not in client.calls[0]
    assert "limit" not in client.calls[0]
    assert client.calls[0]["finder"] == (
        "findReqs;siteNumber=CX_1,sortBy=POSTING_DATES_DESC,limit=2,offset=0"
    )
    assert client.calls[1]["finder"] == (
        "findReqs;siteNumber=CX_1,sortBy=POSTING_DATES_DESC,limit=2,offset=2"
    )


def test_location_filter_excludes_other_regions() -> None:
    client = FakeClient(
        [
            wrapper(
                [
                    {
                        "Id": "2001",
                        "Title": "Principal Piping Designer",
                        "PrimaryLocation": "Houston, TX, United States",
                    }
                ],
                total=1,
            )
        ]
    )

    result = collect_oracle_hcm(source(), client)
    assert result.jobs == []
    assert len(result.evidence) == 1


def test_repeated_page_is_rejected() -> None:
    repeated = wrapper(
        [
            {
                "Id": "3001",
                "Title": "Invalid row without target terms",
                "PrimaryLocation": "Mumbai, India",
            },
            {
                "Id": "3002",
                "Title": "Another invalid row",
                "PrimaryLocation": "Mumbai, India",
            },
        ],
        total=10,
    )
    repeated["items"][0].pop("Offset")
    client = FakeClient([repeated, repeated])

    with pytest.raises(ValueError, match="repeated a pagination page"):
        collect_oracle_hcm(source(), client)


def test_invalid_response_shape_fails_closed() -> None:
    client = FakeClient([{"items": "not-a-list"}])
    with pytest.raises(ValueError, match="items must be a list"):
        collect_oracle_hcm(source(), client)


def test_empty_response_stops_without_evidence() -> None:
    client = FakeClient([wrapper([], total=0, limit=2)])
    result = collect_oracle_hcm(source(), client)
    assert result.jobs == []
    assert result.evidence == []
    assert len(client.calls) == 1


def test_one_page_response_succeeds() -> None:
    client = FakeClient([wrapper([{
        "Id": "4001", "Title": "Piping Engineer",
        "PrimaryLocation": "Mumbai, India",
    }], total=1, limit=2)])
    result = collect_oracle_hcm(source(), client)
    assert [job.title for job in result.jobs] == ["Piping Engineer"]
    assert len(client.calls) == 1


@pytest.mark.parametrize(("field", "value"), [
    ("Offset", "invalid"), ("Limit", -1), ("TotalJobsCount", "not-a-number"),
])
def test_malformed_pagination_metadata_fails_closed(
    field: str, value: object,
) -> None:
    payload = wrapper([], total=0, limit=2)
    payload["items"][0][field] = value
    client = FakeClient([payload])
    with pytest.raises(ValueError, match=field):
        collect_oracle_hcm(source(), client)


def test_ignored_offset_fails_safely() -> None:
    rows = [
        {"Id": "5001", "Title": "Unmatched role", "PrimaryLocation": "Mumbai, India"},
        {"Id": "5002", "Title": "Another unmatched role", "PrimaryLocation": "Mumbai, India"},
    ]
    client = FakeClient([
        wrapper(rows, total=4, offset=0), wrapper(rows, total=4, offset=0),
    ])
    with pytest.raises(ValueError, match="returned Offset=0 for requested offset=2"):
        collect_oracle_hcm(source(), client)


def test_max_pages_is_enforced_before_an_extra_request() -> None:
    client = FakeClient([wrapper([
        {"Id": "6001", "Title": "Other", "PrimaryLocation": "India"},
        {"Id": "6002", "Title": "Other", "PrimaryLocation": "India"},
    ], total=4)])
    with pytest.raises(ValueError, match="exceeded max_pages=1"):
        collect_oracle_hcm(source(max_pages=1), client)
    assert len(client.calls) == 1


def test_max_scan_items_bounds_request_and_termination() -> None:
    client = FakeClient([wrapper([
        {"Id": "7001", "Title": "Other", "PrimaryLocation": "India"},
        {"Id": "7002", "Title": "Other", "PrimaryLocation": "India"},
        {"Id": "7003", "Title": "Other", "PrimaryLocation": "India"},
    ], total=50, limit=3)])
    result = collect_oracle_hcm(source(max_scan_items=3, page_size=20), client)
    assert result.jobs == []
    assert len(client.calls) == 1
    assert "limit=3,offset=0" in str(client.calls[0]["finder"])


@pytest.mark.parametrize(("base_url", "site_number"), [
    ("https://edsv.fa.us2.oraclecloud.com", "CX_1"),
    ("https://ehif.fa.em2.oraclecloud.com", "CX_1"),
    ("https://hcxg.fa.em2.oraclecloud.com", "CX_1"),
])
def test_supported_employer_configuration_shapes_use_generic_finder_pagination(
    base_url: str, site_number: str,
) -> None:
    client = FakeClient([wrapper([], total=0, limit=2)])
    collect_oracle_hcm(source(base_url=base_url, site_number=site_number), client)
    assert client.calls[0]["finder"] == (
        f"findReqs;siteNumber={site_number},"
        "sortBy=POSTING_DATES_DESC,limit=2,offset=0"
    )
