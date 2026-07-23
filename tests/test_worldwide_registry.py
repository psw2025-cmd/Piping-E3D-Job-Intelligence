from pathlib import Path

from job_intelligence.worldwide_registry import (
    ACTIVE_STATUSES,
    company_alias_frame,
    company_coverage_frame,
    country_company_matrix,
    coverage_gap_frame,
    gmail_query_groups,
    load_worldwide_registry,
)


def registry_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "worldwide_companies.yaml"


def test_worldwide_registry_has_india_batch_and_unique_ids() -> None:
    registry = load_worldwide_registry(registry_path())
    ids = [company["company_id"] for company in registry.companies]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 30

    required = {
        "engineers_india",
        "tata_consulting_engineers",
        "tata_projects",
        "reliance_industries",
        "toyo_engineering_india",
        "nuberg_epc",
        "va_tech_wabag",
        "ongc",
        "indian_oil",
        "npcil",
        "ntpc",
        "bhel",
    }
    assert required <= set(ids)


def test_active_direct_companies_have_source_ids() -> None:
    registry = load_worldwide_registry(registry_path())
    for company in registry.companies:
        if company["status"] == "ACTIVE_DIRECT":
            assert company["source_ids"], company["company_id"]


def test_india_has_multiple_coverage_paths() -> None:
    frame = company_coverage_frame(registry_path())
    india = frame[frame["country"].eq("India")]
    statuses = set(india["status"])
    assert {
        "ACTIVE_PUBLIC_NOTICE",
        "ACTIVE_GMAIL_ALERT",
        "ACTIVE_MANUAL_IMPORT",
        "STAGED_NEEDS_LIVE_PROOF",
    } <= statuses


def test_country_matrix_totals_match_registry() -> None:
    frame = company_coverage_frame(registry_path())
    matrix = country_company_matrix(registry_path())
    assert int(matrix["target_companies"].sum()) == len(frame)
    assert int(matrix["active_coverage"].sum()) == int(
        frame["status"].isin(ACTIVE_STATUSES).sum()
    )
    assert matrix["coverage_percent"].between(0, 100).all()


def test_gap_and_alias_views_are_traceable() -> None:
    gaps = coverage_gap_frame(registry_path())
    assert not gaps.empty
    assert not gaps["status"].isin(ACTIVE_STATUSES).any()

    aliases = company_alias_frame(registry_path())
    assert not aliases.empty
    assert {"company_id", "canonical_company", "alias", "country"} <= set(
        aliases.columns
    )
    assert aliases["alias"].str.strip().ne("").all()


def test_generated_gmail_queries_are_bounded_and_use_registered_names() -> None:
    queries = gmail_query_groups(
        registry_path(), newer_than_days=21, max_terms_per_query=10
    )
    assert not queries.empty
    assert queries["term_count"].between(1, 10).all()
    assert queries["gmail_query"].str.startswith("newer_than:21d").all()
    assert queries["gmail_query"].str.contains("job OR vacancy", regex=False).all()
