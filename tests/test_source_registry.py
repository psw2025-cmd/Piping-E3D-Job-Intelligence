from pathlib import Path

import pytest

from job_intelligence.source_registry import load_source_registry


def test_source_fragments_are_loaded_in_deterministic_order() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = load_source_registry(root / "config" / "sources.yaml")
    ids = [source.source_id for source in registry.sources]

    assert "mcdermott_oracle" in ids
    assert "airswift_global_public" in ids
    assert "nesfircroft_piping_public" in ids
    assert "brunel_global_public" in ids
    assert ids.index("airswift_global_public") > ids.index("example_sitemap")
    assert registry.policy["bypass_captcha"] is False
    assert registry.policy["use_rotating_proxies"] is False


def test_fragment_cannot_duplicate_main_source_id(tmp_path: Path) -> None:
    main = tmp_path / "sources.yaml"
    main.write_text(
        """
sources:
  - id: duplicate_source
    name: Main
    type: rss
    company: Example
    url: https://example.com/jobs.rss
    enabled: false
policy:
  bypass_captcha: false
  use_rotating_proxies: false
""",
        encoding="utf-8",
    )
    fragments = tmp_path / "sources.d"
    fragments.mkdir()
    (fragments / "a.yaml").write_text(
        """
sources:
  - id: duplicate_source
    name: Fragment
    type: rss
    company: Example
    url: https://example.org/jobs.rss
    enabled: false
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate source id across registry"):
        load_source_registry(main)
