from pathlib import Path

import pandas as pd

from job_intelligence.coverage_overrides import apply_worldwide_company_overrides
from job_intelligence.coverage_proof import apply_coverage_proof
from job_intelligence.coverage_registry import coverage_frames
from job_intelligence.registry_config import load_registry_rows


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_eil_registry_uses_safe_alert_fallback() -> None:
    root = repository_root()
    employers = load_registry_rows(
        root / "config",
        filename="employer_registry.yaml",
        key="employers",
    )
    eil = next(entry for entry in employers if entry["company"] == "Engineers India Limited")

    assert eil["status"] == "email_alert_ingestion_ready"
    assert eil["source_ids"] == []
    assert "robots" in eil["notes"].casefold()


def test_eil_fallback_is_configured_but_not_proven_without_alert_evidence() -> None:
    root = repository_root()
    frames = coverage_frames(
        pd.DataFrame(),
        pd.DataFrame(),
        config_dir=root / "config",
    )
    frames = apply_worldwide_company_overrides(
        frames,
        pd.DataFrame(),
        config_dir=root / "config",
    )
    frames = apply_coverage_proof(frames)
    registry = frames["Company_Registry"].set_index("company_id")

    assert registry.loc["engineers_india", "status"] == "ACTIVE_GMAIL_ALERT"
    assert bool(registry.loc["engineers_india", "coverage_ready"])
    assert not bool(registry.loc["engineers_india", "coverage_proven"])
    assert registry.loc["engineers_india", "proof_state"] == "configured_unproven"
