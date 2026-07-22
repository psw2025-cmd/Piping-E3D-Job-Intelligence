from __future__ import annotations

from typing import Any, Mapping

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


def wrapper(rows: list[dict[str, Any]], *, total: int, offset: int = 0) -> dict[str, Any]:
    return {
        "items": [
            {
                "TotalJobsCount": total,
                "Limit": len(rows),
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
    assert [call["offset"] for call in client.calls] == [0, 2]


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
    client = FakeClient([repeated, repeated])

    with pytest.raises(ValueError, match="repeated a pagination page"):
        collect_oracle_hcm(source(), client)


def test_invalid_response_shape_fails_closed() -> None:
    client = FakeClient([{"items": "not-a-list"}])
    with pytest.raises(ValueError, match="items must be a list"):
        collect_oracle_hcm(source(), client)
