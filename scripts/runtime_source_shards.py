from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import yaml


def split_config(input_path: Path, output_dir: Path, max_sources: int) -> dict:
      if max_sources < 1:
                raise ValueError("max_sources must be positive")
            raw = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
    all_sources = list(raw.get("sources") or [])
    enabled = [source for source in all_sources if source.get("enabled", True)]
    if not enabled:
              raise ValueError("runtime source configuration has no enabled sources")

    output_dir.mkdir(parents=True, exist_ok=True)
    shards = []
    for start in range(0, len(enabled), max_sources):
              selected = enabled[start : start + max_sources]
              shard_id = f"shard-{len(shards) + 1:03d}"
              selected_ids = {source["id"] for source in selected}
              shard_sources = copy.deepcopy(all_sources)
              for source in shard_sources:
                            source["enabled"] = bool(
                                              source.get("enabled", True) and source.get("id") in selected_ids
                            )
                        shard_raw = {
                                      "sources": shard_sources,
                                      "policy": copy.deepcopy(raw.get("policy") or {}),
                        }
        path = output_dir / f"{shard_id}.yaml"
        path.write_text(
                      yaml.safe_dump(shard_raw, sort_keys=False, allow_unicode=True),
                      encoding="utf-8",
        )
        shards.append({"id": shard_id, "source_ids": sorted(selected_ids)})

    plan = {
              "schema_version": 1,
              "input": str(input_path),
              "enabled_source_count": len(enabled),
              "max_sources_per_shard": max_sources,
              "shards": shards,
    }
    (output_dir / "plan.json").write_text(
              json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return plan


def main() -> int:
      parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-sources", type=int, default=6)
    args = parser.parse_args()
    plan = split_config(args.input, args.output_dir, args.max_sources)
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
      raise SystemExit(main())
