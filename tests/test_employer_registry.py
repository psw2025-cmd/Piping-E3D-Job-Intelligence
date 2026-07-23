from pathlib import Path
from urllib.parse import urlsplit

import yaml

from job_intelligence.source_config import load_source_config


def _registered_active_source_ids(root: Path) -> set[str]:
    registered: set[str] = set()
    registries = (
        ("employer_registry.yaml", "employers", "official_careers_url"),
        ("recruiter_registry.yaml", "recruiters", "official_jobs_url"),
    )
    for filename, records_key, url_key in registries:
        path = root / "config" / filename
        if not path.exists():
            continue
        registry = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for record in registry.get(records_key, []):
            official_url = str(record.get(url_key, ""))
            parsed = urlsplit(official_url)
            assert parsed.scheme == "https"
            assert parsed.hostname
            if record["status"] == "active_supported":
                registered.update(record.get("source_ids", []))
    return registered


def _all_registered_source_ids(root: Path) -> set[str]:
    registered: set[str] = set()
    for filename, records_key in (
        ("employer_registry.yaml", "employers"),
        ("recruiter_registry.yaml", "recruiters"),
    ):
        path = root / "config" / filename
        if not path.exists():
            continue
        registry = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        registered.update(
            source_id
            for record in registry.get(records_key, [])
            for source_id in record.get("source_ids", [])
        )
    return registered


def test_enabled_production_sources_are_registered_and_active() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_config(root / "config" / "sources.yaml")
    enabled_ids = {
        source.source_id for source in source_config.sources if source.enabled
    }

    assert enabled_ids
    assert enabled_ids == _registered_active_source_ids(root)


def test_registry_source_ids_exist_in_production_config() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_config(root / "config" / "sources.yaml")
    configured_ids = {source.source_id for source in source_config.sources}

    assert _all_registered_source_ids(root) <= configured_ids
