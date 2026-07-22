from pathlib import Path
from urllib.parse import urlsplit

import yaml

from job_intelligence.source_config import load_source_config


def test_enabled_production_sources_are_registered_and_active() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_config(root / "config" / "sources.yaml")
    registry = yaml.safe_load(
        (root / "config" / "employer_registry.yaml").read_text(encoding="utf-8")
    )

    registered_active_ids: set[str] = set()
    for employer in registry["employers"]:
        official_url = str(employer.get("official_careers_url", ""))
        parsed = urlsplit(official_url)
        assert parsed.scheme == "https"
        assert parsed.hostname
        if employer["status"] == "active_supported":
            registered_active_ids.update(employer.get("source_ids", []))

    enabled_ids = {
        source.source_id for source in source_config.sources if source.enabled
    }
    assert enabled_ids
    assert enabled_ids == registered_active_ids


def test_registry_source_ids_exist_in_production_config() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_config(root / "config" / "sources.yaml")
    configured_ids = {source.source_id for source in source_config.sources}
    registry = yaml.safe_load(
        (root / "config" / "employer_registry.yaml").read_text(encoding="utf-8")
    )

    registered_ids = {
        source_id
        for employer in registry["employers"]
        for source_id in employer.get("source_ids", [])
    }
    assert registered_ids <= configured_ids
