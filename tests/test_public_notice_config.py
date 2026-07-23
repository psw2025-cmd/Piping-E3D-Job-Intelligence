from pathlib import Path

import pytest

from job_intelligence.source_config import load_source_config


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_staged_india_notice_source_validates_and_remains_disabled() -> None:
    config = load_source_config(
        repository_root() / "config" / "sources.india-notices.yaml"
    )

    assert {source.source_id for source in config.sources} == {
        "npcil_public_notices",
    }
    assert all(source.source_type == "public_notice" for source in config.sources)
    assert all(not source.enabled for source in config.sources)


def test_notice_config_requires_listing_host_in_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources:
          - id: invalid_notice
            name: Invalid notice
            type: public_notice
            company: Example Company
            url: https://example.com/jobs
            allowed_domains: [documents.example.com]
            notice_link_patterns: [.pdf]
            enabled: false
        policy:
          respect_robots_txt: true
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="listing host"):
        load_source_config(path)


def test_notice_config_rejects_non_text_patterns(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources:
          - id: invalid_notice
            name: Invalid notice
            type: public_notice
            company: Example Company
            url: https://example.com/jobs
            allowed_domains: [example.com]
            notice_link_patterns: [.pdf, 123]
            enabled: false
        policy:
          respect_robots_txt: true
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty text"):
        load_source_config(path)
