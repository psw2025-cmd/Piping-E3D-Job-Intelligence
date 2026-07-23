from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path

from job_intelligence.database import fetch_jobs
from job_intelligence.gmail_alerts import import_gmail_alerts


class _Executable:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Messages:
    def __init__(self, raw_messages: dict[str, bytes]) -> None:
        self.raw_messages = raw_messages

    def list(self, **_kwargs):
        return _Executable(
            {"messages": [{"id": message_id} for message_id in self.raw_messages]}
        )

    def get(self, *, id: str, **_kwargs):
        encoded = base64.urlsafe_b64encode(self.raw_messages[id]).decode().rstrip("=")
        return _Executable({"raw": encoded})


class _Users:
    def __init__(self, raw_messages: dict[str, bytes]) -> None:
        self._messages = _Messages(raw_messages)

    def messages(self):
        return self._messages


class FakeGmailService:
    def __init__(self, raw_messages: dict[str, bytes]) -> None:
        self._users = _Users(raw_messages)

    def users(self):
        return self._users


def _job_alert_bytes() -> bytes:
    message = EmailMessage()
    message["Subject"] = "Senior E3D Piping Designer job alert"
    message["From"] = "LinkedIn Job Alerts <alerts@example.com>"
    message["To"] = "candidate@example.net"
    message.set_content(
        "Job Title: Senior E3D Piping Designer\n"
        "Company: Global EPC\n"
        "Location: Abu Dhabi\n"
        "AVEVA E3D offshore piping layout role.\n"
        "https://example.com/jobs/123"
    )
    return message.as_bytes()


def test_gmail_alert_import_is_read_only_and_deduplicated(tmp_path: Path) -> None:
    service = FakeGmailService({"abc123": _job_alert_bytes()})
    db_path = tmp_path / "jobs.db"
    evidence = tmp_path / "private-evidence"

    first = import_gmail_alerts(db_path, evidence, service=service)
    second = import_gmail_alerts(db_path, evidence, service=service)

    assert first.created == 1
    assert first.failed == 0
    assert second.duplicates == 1
    jobs = fetch_jobs(db_path)
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Global EPC"
    assert jobs[0]["location"] == "Abu Dhabi"


def test_gmail_alert_failure_is_isolated(tmp_path: Path) -> None:
    service = FakeGmailService({"broken": b""})
    summary = import_gmail_alerts(
        tmp_path / "jobs.db",
        tmp_path / "evidence",
        service=service,
    )
    assert summary.attempted == 1
    assert summary.failed == 1
    assert summary.results[0].status == "failed"
