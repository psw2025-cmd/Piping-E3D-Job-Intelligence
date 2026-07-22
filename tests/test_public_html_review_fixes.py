from pathlib import Path

from job_intelligence.collectors.public_html import _RobotsCache
from job_intelligence.database import connect, record_source_health


class FailingRobotsClient:
    user_agent = "test-agent"

    def __init__(self) -> None:
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        raise OSError("robots unavailable")


def test_robots_error_is_cached_for_origin() -> None:
    client = FailingRobotsClient()
    cache = _RobotsCache(client, enabled=True, deny_on_error=True)
    assert cache.can_fetch("https://example.com/jobs/1") is False
    assert cache.can_fetch("https://example.com/jobs/2") is False
    assert client.calls == 1


def test_pass_with_warnings_updates_success_timestamp(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    record_source_health(
        db_path,
        "source",
        "Source",
        "pass_with_warnings",
        records_found=1,
        error_message="detail fallback",
    )
    with connect(db_path) as connection:
        row = connection.execute(
  "SELECT status, last_success_at, error_message FROM source_health"
        ).fetchone()
    assert row["status"] == "pass_with_warnings"
    assert row["last_success_at"]
    assert row["error_message"] == "detail fallback"
