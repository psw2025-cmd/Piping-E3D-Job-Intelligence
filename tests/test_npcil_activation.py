from pathlib import Path

import pandas as pd

from job_intelligence.coverage_overrides import apply_worldwide_company_overrides
from job_intelligence.coverage_proof import apply_coverage_proof
from job_intelligence.coverage_registry import coverage_frames
from job_intelligence.registry_config import load_registry_rows
from job_intelligence.source_config import load_source_config


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_npcil_production_source_is_enabled_and_bounded() -> None:
    root = repository_root()
    config = load_source_config(root / "config" / "sources.yaml")
    sources = {source.source_id: source for source in config.sources}

    npcil = sources["npcil_public_notices"]
    assert npcil.enabled is True
    assert npcil.source_type == "public_notice"
    assert npcil.int_option("max_items", 100) == 5
    assert npcil.int_option("max_pdf_pages", 40) == 10
    assert npcil.int_option("rate_limit_per_minute", 30) <= 10
    assert npcil.bool_option("deny_on_robots_error", True) is True


def test_registry_fragment_marks_npcil_active_and_indian_oil_fallback() -> None:
    root = repository_root()
    employers = load_registry_rows(
        root / "config",
        filename="employer_registry.yaml",
        key="employers",
    )
    by_company = {entry["company"]: entry for entry in employers}

    npcil = by_company["Nuclear Power Corporation of India"]
    indian_oil = by_company["Indian Oil Corporation"]
    assert npcil["status"] == "active_supported"
    assert npcil["source_ids"] == ["npcil_public_notices"]
    assert indian_oil["status"] == "email_alert_ingestion_ready"
    assert indian_oil["source_ids"] == []


def test_coverage_proof_uses_npcil_health_and_does_not_inflate_indian_oil() -> None:
    root = repository_root()
    jobs = pd.DataFrame()
    source_health = pd.DataFrame(
        [
            {
                "source_id": "npcil_public_notices",
                "status": "pass",
                "last_attempt_at": "2026-07-23T09:22:00+00:00",
                "last_success_at": "2026-07-23T09:22:00+00:00",
            }
        ]
    )
    frames = coverage_frames(jobs, source_health, config_dir=root / "config")
    frames = apply_worldwide_company_overrides(
        frames,
        source_health,
        config_dir=root / "config",
    )
    frames = apply_coverage_proof(frames)
    registry = frames["Company_Registry"].set_index("company_id")

    assert registry.loc["npcil", "status"] == "ACTIVE_DIRECT"
    assert bool(registry.loc["npcil", "coverage_proven"])
    assert registry.loc["indian_oil", "status"] == "ACTIVE_GMAIL_ALERT"
    assert bool(registry.loc["indian_oil", "coverage_ready"])
    assert not bool(registry.loc["indian_oil", "coverage_proven"])
