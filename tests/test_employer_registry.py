from pathlib import Path
from urllib.parse import urlsplit

from job_intelligence.registry_config import load_registry_rows
from job_intelligence.source_config import load_source_config


def test_enabled_production_sources_are_registered_and_active() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_config(root / "config" / "sources.yaml")
    employers = load_registry_rows(
        root / "config",
        filename="employer_registry.yaml",
        key="employers",
    )

    registered_active_ids: set[str] = set()
    for employer in employers:
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
    employers = load_registry_rows(
        root / "config",
        filename="employer_registry.yaml",
        key="employers",
    )

    registered_ids = {
        source_id
        for employer in employers
        for source_id in employer.get("source_ids", [])
    }
    assert registered_ids <= configured_ids
