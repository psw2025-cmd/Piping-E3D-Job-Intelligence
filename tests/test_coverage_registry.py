from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from job_intelligence import coverage_registry as coverage_registry_module
from job_intelligence.coverage_registry import (
    COVERAGE_STATUSES,
    coverage_frames,
    load_gmail_query_groups,
    load_worldwide_companies,
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_worldwide_registry_contains_first_india_batch_and_active_sources() -> None:
    companies = load_worldwide_companies(
        repository_root() / "config" / "worldwide_companies.yaml"
    )
    india = [entry for entry in companies if entry["country"] == "India"]
    active_direct = [
        entry for entry in companies if entry["status"] == "ACTIVE_DIRECT"
    ]

    assert len(india) == 25
    assert len(active_direct) >= 6
    assert {entry["company_id"] for entry in india} >= {
        "engineers_india",
        "tata_consulting_engineers",
        "tata_projects",
        "reliance_industries",
        "toyo_engineering_india",
        "nuberg_epc",
        "va_tech_wabag",
        "ongc",
        "indian_oil",
        "bpcl",
        "hpcl",
        "gail",
        "petronet_lng",
        "npcil",
        "ntpc",
        "bhel",
        "assystem_india",
        "aecom_india",
        "mott_macdonald_india",
        "tractebel_india",
        "thermax",
        "praj_industries",
        "pdil",
        "mecon",
        "egis_india",
    }
    assert {entry["status"] for entry in companies} <= COVERAGE_STATUSES
    assert all(entry["official_careers_url"].startswith("https://") for entry in companies)


def test_gmail_query_groups_cover_portals_psus_employers_and_recruiters() -> None:
    groups = load_gmail_query_groups(
        repository_root() / "config" / "gmail_query_groups.yaml"
    )
    ids = {group["id"] for group in groups if group["enabled"]}
    assert {
        "job_portals_india",
        "job_portals_gulf",
        "india_psu_notices",
        "india_epc_employers",
        "worldwide_official_employers",
        "recruiters_energy_engineering",
        "nuclear_and_iter",
    } <= ids
    assert all("newer_than:" in group["query"] for group in groups)
    assert all(1 <= group["max_messages"] <= 1000 for group in groups)


def test_coverage_frames_compute_country_metrics_and_company_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 23, 6, 0, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return now.replace(tzinfo=None)
            return now.astimezone(tz)

    monkeypatch.setattr(coverage_registry_module, "datetime", FrozenDateTime)
    jobs = pd.DataFrame(
        [
            {
                "company": "Reliance Industries",
                "found_at": (now - timedelta(days=1)).isoformat(),
                "last_seen_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "company": "McDermott",
                "found_at": (now - timedelta(days=2)).isoformat(),
                "last_seen_at": (now - timedelta(days=2)).isoformat(),
            },
        ]
    )
    source_health = pd.DataFrame(
        [
            {
                "source_id": "mcdermott_oracle",
                "status": "pass",
                "last_attempt_at": "2026-07-23T05:00:00+00:00",
                "last_success_at": "2026-07-23T05:00:00+00:00",
            }
        ]
    )

    frames = coverage_frames(
        jobs,
        source_health,
        config_dir=repository_root() / "config",
    )

    registry = frames["Company_Registry"]
    reliance = registry[registry["company_id"].eq("reliance_industries")].iloc[0]
    mcdermott = registry[registry["company_id"].eq("mcdermott")].iloc[0]
    india = frames["Country_Coverage"]
    india = india[india["country"].eq("India")].iloc[0]

    assert reliance["jobs_found_30d"] == 1
    assert mcdermott["passing_source_count"] == 1
    assert india["total_target_companies"] == 25
    assert 0 < india["coverage_percentage"] < 100
    assert "Missing_Companies" in frames
    assert "ATS_Coverage" in frames
    assert "Company_Aliases" in frames


def test_invalid_registry_status_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "worldwide_companies.yaml"
    path.write_text(
        """
        companies:
          - company_id: invalid
            company: Invalid Company
            country: India
            regions: [India]
            local_entities: []
            company_aliases: [Invalid]
            employer_type: EPC contractor
            sectors: [Oil and Gas]
            official_careers_url: https://example.com/careers
            job_host: example.com
            ats_family: public_html
            source_mode: direct
            source_ids: [invalid]
            alert_supported: false
            priority: 1
            status: MADE_UP_STATUS
            verified_at: 2026-07-23
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported status"):
        load_worldwide_companies(path)
