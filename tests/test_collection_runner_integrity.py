from pathlib import Path
from typing import Mapping

import pytest

from job_intelligence import collection_runner
from job_intelligence.collection_runner import collect_sources
from job_intelligence.collectors.http_client import FetchedResponse
from job_intelligence.database import connect, fetch_jobs
from job_intelligence.source_config import SourceSpec


class OneResponseClient:
    user_agent = "test-agent"

    def __init__(self, url: str, response: FetchedResponse) -> None:
        self.url = url
        self.response = response
        self.used = False

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        del params, allowed_statuses
        assert url == self.url
        assert self.used is False
        self.used = True
        return self.response


def source_yaml(*, enabled: bool = True) -> str:
    enabled_text = "true" if enabled else "false"
    return f"""
    sources:
      - id: target_greenhouse
        name: Target Greenhouse
        type: greenhouse
        company: Example EPC
        board_token: example
        enabled: {enabled_text}
    policy:
      retain_source_evidence: true
    """


def test_unknown_only_source_fails_before_starting_run(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(source_yaml(), encoding="utf-8")
    db_path = tmp_path / "jobs.db"

    with pytest.raises(ValueError, match="unknown source ids.*missing"):
        collect_sources(
            db_path,
            config,
            tmp_path / "evidence",
            only_source_ids={"missing"},
        )

    assert db_path.exists() is False


def test_disabled_only_source_fails_instead_of_reporting_success(tmp_path: Path) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(source_yaml(enabled=False), encoding="utf-8")

    with pytest.raises(ValueError, match="source ids are disabled.*target_greenhouse"):
        collect_sources(
            tmp_path / "jobs.db",
            config,
            tmp_path / "evidence",
            only_source_ids={"target_greenhouse"},
        )


def test_evidence_failure_does_not_mutate_job_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(source_yaml(), encoding="utf-8")
    url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"
    payload = (
        b'{"jobs":[{"title":"Piping Engineer",'
        b'"absolute_url":"https://example.com/jobs/1"}]}'
    )

    def client_factory(_source: SourceSpec) -> OneResponseClient:
        return OneResponseClient(
            url,
            FetchedResponse(
                url=url,
                status_code=200,
                headers={"content-type": "application/json"},
                content=payload,
            ),
        )

    def fail_evidence(*_args, **_kwargs) -> None:
        raise OSError("simulated evidence disk failure")

    monkeypatch.setattr(collection_runner, "_save_evidence", fail_evidence)
    db_path = tmp_path / "jobs.db"
    summary = collect_sources(
        db_path,
        config,
        tmp_path / "evidence",
        client_factory=client_factory,
    )

    assert summary.status == "fail"
    assert summary.sources_failed == 1
    assert summary.new_jobs == 0
    assert fetch_jobs(db_path) == []


def test_evidence_suffix_rejects_path_like_values() -> None:
    assert collection_runner._evidence_suffix("../../outside.txt") == ".bin"
    assert collection_runner._evidence_suffix(".JSON") == ".json"


def _greenhouse_client_factory(url: str, payload: bytes):
    def factory(_source: SourceSpec) -> OneResponseClient:
        return OneResponseClient(
            url,
            FetchedResponse(
                url=url,
                status_code=200,
                headers={"content-type": "application/json"},
                content=payload,
            ),
        )

    return factory


def test_scoring_failure_retains_fetched_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(source_yaml(), encoding="utf-8")
    url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"
    payload = (
        b'{"jobs":[{"title":"Piping Engineer",'
        b'"absolute_url":"https://example.com/jobs/score"}]}'
    )

    def fail_scoring(*_args, **_kwargs) -> None:
        raise RuntimeError("simulated scoring failure")

    monkeypatch.setattr(collection_runner, "_prepare_jobs", fail_scoring)
    db_path = tmp_path / "jobs.db"
    summary = collect_sources(
        db_path,
        config,
        tmp_path / "evidence",
        client_factory=_greenhouse_client_factory(url, payload),
    )

    assert summary.status == "fail"
    assert summary.source_results[0].jobs_collected == 1
    assert fetch_jobs(db_path) == []
    with connect(db_path) as connection:
        evidence = connection.execute(
            "SELECT file_path FROM source_evidence"
        ).fetchone()
        health = connection.execute(
            "SELECT status, records_found FROM source_health"
        ).fetchone()
    assert evidence is not None
    assert Path(evidence["file_path"]).exists()
    assert tuple(health) == ("fail", 1)


def test_upsert_failure_removes_evidence_and_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "sources.yaml"
    config.write_text(source_yaml(), encoding="utf-8")
    url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"
    payload = (
        b'{"jobs":[{"title":"Piping Engineer",'
        b'"absolute_url":"https://example.com/jobs/upsert"}]}'
    )

    def fail_upsert(*_args, **_kwargs):
        raise RuntimeError("simulated upsert failure")

    monkeypatch.setattr(collection_runner, "upsert_jobs", fail_upsert)
    db_path = tmp_path / "jobs.db"
    evidence_root = tmp_path / "evidence"
    summary = collect_sources(
        db_path,
        config,
        evidence_root,
        client_factory=_greenhouse_client_factory(url, payload),
    )

    assert summary.status == "fail"
    assert fetch_jobs(db_path) == []
    with connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM source_evidence").fetchone()[0]
    assert count == 0
    run_directory = evidence_root / "target_greenhouse" / summary.run_id
    assert run_directory.exists() is False
