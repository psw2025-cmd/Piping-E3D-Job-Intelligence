from __future__ import annotations

from pathlib import Path

from .source_config import SourceConfig, SourceSpec, load_source_config


def load_source_registry(path: str | Path) -> SourceConfig:
    """Load the main source file plus sorted config/sources.d fragments.

    Fragment files contain ordinary `sources:` lists. The main file remains the
    authority for the global safety policy, so a fragment cannot weaken robots,
    CAPTCHA, proxy, or evidence-retention rules.
    """

    config_path = Path(path)
    base = load_source_config(config_path)
    combined: list[SourceSpec] = list(base.sources)
    seen = {source.source_id for source in combined}

    fragments_dir = config_path.parent / "sources.d"
    if fragments_dir.is_dir():
        for fragment_path in sorted(fragments_dir.glob("*.yaml")):
            fragment = load_source_config(fragment_path)
            for source in fragment.sources:
                if source.source_id in seen:
                    raise ValueError(
                        f"duplicate source id across registry: {source.source_id} "
                        f"({fragment_path})"
                    )
                seen.add(source.source_id)
                combined.append(source)

    return SourceConfig(tuple(combined), dict(base.policy))
