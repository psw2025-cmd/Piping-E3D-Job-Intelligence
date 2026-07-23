from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_runner() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_cloud_daily.py"
    spec = importlib.util.spec_from_file_location("run_cloud_daily_test_target", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_cloud_daily = _load_runner()


def _fake_collection(status: str) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        run_id="run-1",
        sources_passed=1 if status == "partial" else 2,
        sources_attempted=2,
        jobs_collected=1,
        new_jobs=1,
        updated_jobs=0,
        source_results=[],
    )


def _patch_common(monkeypatch, collection_status: str, export_statuses: list[str]) -> None:
    monkeypatch.setattr(
        run_cloud_daily,
        "load_source_config",
        lambda _path: SimpleNamespace(sources=[SimpleNamespace(enabled=True)]),
    )
    monkeypatch.setattr(
        run_cloud_daily,
        "collect_sources",
        lambda _db, _sources, _evidence: _fake_collection(collection_status),
    )
    monkeypatch.setattr(
        run_cloud_daily,
        "export_excel",
        lambda _db, output: Path(output).write_text("workbook", encoding="utf-8"),
    )
    monkeypatch.setattr(run_cloud_daily, "_verify_database", lambda _db: [])
    monkeypatch.setattr(run_cloud_daily, "verify_excel", lambda _output: [])
    monkeypatch.setattr(
        run_cloud_daily,
        "set_run_export_status",
        lambda _db, _run_id, status, *_rest: export_statuses.append(status),
    )


def test_partial_collection_is_not_reported_verified(
    tmp_path: Path,
    monkeypatch,
) -> None:
    export_statuses: list[str] = []
    _patch_common(monkeypatch, "partial", export_statuses)
    monkeypatch.setattr(
        run_cloud_daily,
        "_write_bundle",
        lambda output: (Path(output) / "Piping_E3D_Daily_Bundle.zip").write_bytes(b"zip"),
    )
    output = tmp_path / "daily"
    args = SimpleNamespace(
        output=str(output),
        sources="unused.yaml",
        allow_no_sources=False,
    )

    assert run_cloud_daily.run(args) == 2

    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["exit_code"] == 2
    assert status["collection_status"] == "partial"
    assert status["verified"] is False
    assert "collection finished with status partial" in status["error"]
    assert export_statuses == ["fail"]
    summary = (output / "SUMMARY.md").read_text(encoding="utf-8")
    assert "Overall result: **FAIL**" in summary
    assert "Verification: `FAIL`" in summary


def test_bundle_failure_rewrites_status_as_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    export_statuses: list[str] = []
    _patch_common(monkeypatch, "pass", export_statuses)

    def fail_bundle(_output: Path) -> None:
        raise OSError("bundle creation failed")

    monkeypatch.setattr(run_cloud_daily, "_write_bundle", fail_bundle)
    output = tmp_path / "daily"
    args = SimpleNamespace(
        output=str(output),
        sources="unused.yaml",
        allow_no_sources=False,
    )

    assert run_cloud_daily.run(args) == 2

    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["exit_code"] == 2
    assert status["collection_status"] == "pass"
    assert status["verified"] is False
    assert status["error"] == "OSError: bundle creation failed"
    assert export_statuses == ["pass", "fail"]
    assert not (output / "Piping_E3D_Daily_Bundle.zip").exists()
    summary = (output / "SUMMARY.md").read_text(encoding="utf-8")
    assert "Overall result: **FAIL**" in summary
    assert "Verification: `FAIL`" in summary
