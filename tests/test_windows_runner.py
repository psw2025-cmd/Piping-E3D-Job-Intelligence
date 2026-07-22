from pathlib import Path


def test_failed_collect_stops_before_verify() -> None:
    script = Path("scripts/run_daily.ps1").read_text(encoding="utf-8")
    collect_check = script.index("if ($collectExit -eq 2)")
    verify_command = script.index(" -m job_intelligence.cli --db $db verify")
    assert collect_check < verify_command
    assert "possibly stale workbook" in script


def test_partial_collect_still_runs_verify() -> None:
    script = Path("scripts/run_daily.ps1").read_text(encoding="utf-8")
    verify_command = script.index(" -m job_intelligence.cli --db $db verify")
    partial_check = script.index("if ($collectExit -eq 1)")
    assert verify_command < partial_check
