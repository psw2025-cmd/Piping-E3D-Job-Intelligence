from pathlib import Path
from urllib.parse import urlsplit

import yaml

from job_intelligence.source_registry import load_source_registry


def _registry_records(root: Path):
    employer_registry = yaml.safe_load(
        (root / "config" / "employer_registry.yaml").read_text(encoding="utf-8")
    ) or {}
    recruiter_registry = yaml.safe_load(
        (root / "config" / "recruiters.yaml").read_text(encoding="utf-8")
    ) or {}
    for employer in employer_registry.get("employers", []):
        yield employer, "official_careers_url"
    for recruiter in recruiter_registry.get("recruiters", []):
        yield recruiter, "official_jobs_url"


def test_enabled_production_sources_are_registered_and_active() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_registry(root / "config" / "sources.yaml")

    registered_active_ids: set[str] = set()
    for record, url_key in _registry_records(root):
        official_url = str(record.get(url_key, ""))
        parsed = urlsplit(official_url)
        assert parsed.scheme == "https"
        assert parsed.hostname
        if record.get("status") == "active_supported":
            registered_active_ids.update(record.get("source_ids", []))

    enabled_ids = {
        source.source_id for source in source_config.sources if source.enabled
    }
    assert enabled_ids
    assert enabled_ids == registered_active_ids


def test_registry_source_ids_exist_in_production_registry() -> None:
    root = Path(__file__).resolve().parents[1]
    source_config = load_source_registry(root / "config" / "sources.yaml")
    configured_ids = {source.source_id for source in source_config.sources}

    registered_ids = {
        source_id
        for record, _url_key in _registry_records(root)
        for source_id in record.get("source_ids", [])
    }
    assert registered_ids <= configured_ids
