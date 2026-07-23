from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _load_mapping(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"registry root must be a mapping: {path}")
    return loaded


def load_registry_rows(
    config_dir: str | Path,
    *,
    filename: str,
    key: str,
    identity_field: str = "company",
) -> list[dict[str, Any]]:
    root = Path(config_dir)
    base_path = root / filename
    documents: list[tuple[Path, dict[str, Any]]] = []
    if base_path.exists():
        documents.append((base_path, _load_mapping(base_path)))

    fragment_dir = root / f"{Path(filename).stem}.d"
    if fragment_dir.exists():
        for fragment in sorted(fragment_dir.glob("*.yaml")):
            documents.append((fragment, _load_mapping(fragment)))

    rows: list[dict[str, Any]] = []
    seen: dict[str, Path] = {}
    for path, document in documents:
        raw_rows = document.get(key, [])
        if not isinstance(raw_rows, list):
            raise ValueError(f"registry key {key!r} must be a list: {path}")
        for raw in raw_rows:
            if not isinstance(raw, dict):
                raise ValueError(f"registry rows must be mappings: {path}")
            identity = str(raw.get(identity_field, "")).strip()
            if not identity:
                raise ValueError(
                    f"registry row requires {identity_field!r}: {path}"
                )
            normalized = identity.casefold()
            if normalized in seen:
                raise ValueError(
                    f"duplicate registry {identity_field} {identity!r}: "
                    f"{seen[normalized]} and {path}"
                )
            seen[normalized] = path
            rows.append(dict(raw))
    return rows
