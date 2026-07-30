from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from job_intelligence.local_runner import (
    contained_child,
    exclusive_lock,
    is_transient_failure,
    redact,
    run_logged,
    run_name,
)


def test_containment_accepts_strict_child(tmp_path: Path) -> None:
    root = tmp_path / "data"
    child = root / "run-20260730-120000-attempt-1"
    assert contained_child(root, child) == child.resolve()


@pytest.mark.parametrize("candidate", [".", ".."])
def test_containment_rejects_root_and_parent(tmp_path: Path, candidate: str) -> None:
    root = tmp_path / "data"
    with pytest.raises(ValueError, match="must be a child"):
        contained_child(root, root / candidate)


def test_lock_rejects_overlap(tmp_path: Path) -> None:
    lock = tmp_path / ".lock"
    with (
        exclusive_lock(lock),
        pytest.raises(RuntimeError, match="another local public run"),
        exclusive_lock(lock),
    ):
        pass


def test_redaction_removes_tokens_credentials_and_email() -> None:
    value = (
        "pass" + "word=" + "example-value " + "ghp_" + ("x" * 24) + " user" + "@example.com"
    )
    redacted = redact(value)
    assert "example-value" not in redacted
    assert "ghp_" not in redacted
    assert "user@example.com" not in redacted


def test_transient_failure_classification() -> None:
    assert is_transient_failure("DNS name resolution timeout")
    assert is_transient_failure("HTTP 503")
    assert not is_transient_failure("SQLite integrity_check failed")


def test_run_name_is_deterministic() -> None:
    stamp = datetime(2026, 7, 30, 12, 34, 56, tzinfo=UTC)
    assert run_name(stamp, 2) == "run-20260730-123456-attempt-2"


def test_run_logged_enforces_hard_timeout(tmp_path: Path) -> None:
    started = time.monotonic()
    with (
        (tmp_path / "run.log").open("w", encoding="utf-8") as log,
        pytest.raises(TimeoutError, match="child exceeded timeout"),
    ):
        run_logged(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            log=log,
            timeout_seconds=0.2,
        )
    assert time.monotonic() - started < 3


def test_run_logged_propagates_exit_code(tmp_path: Path) -> None:
    with (tmp_path / "run.log").open("w", encoding="utf-8") as log:
        code = run_logged(
            [sys.executable, "-c", "raise SystemExit(7)"],
            cwd=tmp_path,
            log=log,
            timeout_seconds=5,
        )
    assert code == 7


def test_powershell_wrapper_has_public_safety_contract() -> None:
    script = (Path(__file__).parents[1] / "scripts/run_local_public_daily.ps1").read_text(encoding="utf-8")
    required = [".venv\\Scripts\\python.exe", "Python 3.11", "job_intelligence.local_runner", "--data-root", "--timeout-minutes"]
    assert all(value in script for value in required)
    assert "gmail-auth" not in script
    assert "gmail-import" not in script


def test_task_design_fails_closed_before_registration() -> None:
    script = (Path(__file__).parents[1] / "scripts/task_scheduler_public_daily.ps1").read_text(encoding="utf-8")
    assert "StartWhenAvailable" in script
    assert "IgnoreNew" in script
    assert "if ($Install)" in script
    assert "Register-ScheduledTask -TaskName $TaskName -InputObject $task" in script
    assert "-WorkingDirectory $RepoRoot" in script
