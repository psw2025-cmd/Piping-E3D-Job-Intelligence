import pandas as pd

from job_intelligence.coverage_proof import apply_coverage_proof


def test_configured_paths_are_not_counted_until_evidence_exists() -> None:
    registry = pd.DataFrame(
        [
            {
                "company_id": "direct_pass",
                "company": "Direct Pass",
                "country": "India",
                "priority": 1,
                "status": "ACTIVE_DIRECT",
                "passing_source_count": 1,
                "jobs_found_today": 1,
                "jobs_found_30d": 1,
                "last_success_at": "2026-07-23T00:00:00+00:00",
                "official_careers_url": "https://example.com/direct-pass",
                "ats_family": "Workday",
                "recommended_next_action": "Maintain proof.",
            },
            {
                "company_id": "direct_unproven",
                "company": "Direct Unproven",
                "country": "India",
                "priority": 1,
                "status": "ACTIVE_DIRECT",
                "passing_source_count": 0,
                "jobs_found_today": 0,
                "jobs_found_30d": 0,
                "last_success_at": "",
                "official_careers_url": "https://example.com/direct-unproven",
                "ats_family": "Oracle HCM",
                "recommended_next_action": "Run source.",
            },
            {
                "company_id": "gmail_ready",
                "company": "Gmail Ready",
                "country": "India",
                "priority": 1,
                "status": "ACTIVE_GMAIL_ALERT",
                "passing_source_count": 0,
                "jobs_found_today": 0,
                "jobs_found_30d": 0,
                "last_success_at": "",
                "official_careers_url": "https://example.com/gmail-ready",
                "ats_family": "Gmail alert",
                "recommended_next_action": "Authorize Gmail.",
            },
        ]
    )
    frames = {
        "Company_Registry": registry,
        "Country_Coverage": pd.DataFrame(),
        "Missing_Companies": pd.DataFrame(),
        "Employer_Source_Status": registry.copy(),
        "Coverage_Gaps": pd.DataFrame(),
    }

    proven = apply_coverage_proof(frames)
    result = proven["Company_Registry"].set_index("company_id")
    india = proven["Country_Coverage"].iloc[0]

    assert bool(result.loc["direct_pass", "coverage_proven"])
    assert not bool(result.loc["direct_unproven", "coverage_proven"])
    assert bool(result.loc["gmail_ready", "coverage_ready"])
    assert not bool(result.loc["gmail_ready", "coverage_proven"])
    assert india["configured_coverage_paths"] == 3
    assert india["proven_operational_coverage"] == 1
    assert india["coverage_percentage"] == 33.3
