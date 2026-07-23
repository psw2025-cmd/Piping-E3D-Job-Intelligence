from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Mapping

import pytest
import requests
import yaml

from job_intelligence.collectors import collect_public_html
from job_intelligence.collectors import http_client
from job_intelligence.collectors.http_client import FetchedResponse, SafeHttpClient
from job_intelligence.collectors.oracle_hcm import _matches_terms
from job_intelligence.database import fetch_jobs, upsert_job
from job_intelligence.models import JobRecord
from job_intelligence.normalization import load_profile_taxonomy, normalize_role
from job_intelligence.scoring import load_scoring_profile, score_job
from job_intelligence.source_config import SourceSpec


class FakeResponse:
    def __init__(
        self,
        url: str,
        status_code: int,
        *,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = chunks or []
        self.closed = False
        self.is_redirect = status_code in {301, 302, 303, 307, 308}
        self.is_permanent_redirect = status_code in {301, 308}

    def iter_content(self, chunk_size: int) -> Any:
        del chunk_size
        yield from self._chunks

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.trust_env = True
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"No fake response remaining for {url}")
        return self.responses.pop(0)


class RedirectingFixtureClient:
    user_agent = "FixtureCrawler/1.0"

    def __init__(self, routes: dict[str, FetchedResponse]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        del params, allowed_statuses
        self.calls.append(url)
        return self.routes[url]


def _public_dns(*_args: Any, **_kwargs: Any) -> list[tuple[Any, ...]]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", 443),
        )
    ]


def _html_response(requested_url: str, final_url: str, body: str) -> FetchedResponse:
    del requested_url
    return FetchedResponse(
        url=final_url,
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        content=body.encode("utf-8"),
    )


def _public_html_source() -> SourceSpec:
    return SourceSpec(
        source_id="redirect_guard",
        name="Redirect guard fixture",
        source_type="public_html",
        enabled=True,
        company="Example EPC",
        options={
            "url": "https://allowed.example/jobs",
            "allowed_domains": ["allowed.example"],
            "job_link_patterns": ["/jobs/"],
            "anchor_text_patterns": ["piping"],
            "fetch_details": True,
            "deny_on_robots_error": True,
            "max_items": 5,
        },
    )


def test_oracle_location_terms_use_phrase_boundaries() -> None:
    assert _matches_terms("Mumbai, Maharashtra, India", ("india",))
    assert _matches_terms("Muscat, Oman", ("oman",))
    assert not _matches_terms("Indianapolis, Indiana, United States", ("india",))
    assert not _matches_terms("Bucharest, Romania", ("oman",))


def test_explicit_scoring_profile_does_not_auto_load_other_taxonomy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment_config = tmp_path / "environment"
    environment_config.mkdir()
    (environment_config / "roles.yaml").write_text(
        yaml.safe_dump(
            {
                "target_roles": ["Environment Role"],
                "role_families": {
                    "Environment Canonical": ["environment role"],
                },
            }
        ),
        encoding="utf-8",
    )
    (environment_config / "locations.yaml").write_text("{}\n", encoding="utf-8")
    (environment_config / "scoring.yaml").write_text("{}\n", encoding="utf-8")

    explicit_config = tmp_path / "explicit"
    explicit_config.mkdir()
    (explicit_config / "roles.yaml").write_text(
        yaml.safe_dump({"target_roles": ["Custom Pipe Role"]}),
        encoding="utf-8",
    )
    (explicit_config / "locations.yaml").write_text("{}\n", encoding="utf-8")
    (explicit_config / "scoring.yaml").write_text("{}\n", encoding="utf-8")

    monkeypatch.setenv("JOB_INTEL_CONFIG_DIR", str(environment_config))
    profile = load_scoring_profile(explicit_config)
    job = JobRecord(title="Environment Role", company="Example EPC")

    score_job(job, profile=profile)

    assert job.normalized_role == ""


def test_every_configured_target_role_normalizes_to_itself() -> None:
    root = Path(__file__).resolve().parents[1] / "config"
    roles = yaml.safe_load((root / "roles.yaml").read_text(encoding="utf-8"))
    taxonomy = load_profile_taxonomy(root)

    mismatches = {
        role: normalize_role(JobRecord(title=role, company="Example EPC"), taxonomy)
        for role in roles["target_roles"]
        if normalize_role(JobRecord(title=role, company="Example EPC"), taxonomy)
        != role
    }

    assert mismatches == {}


def test_rescored_reimport_can_clear_stale_profile_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    first = JobRecord(
        title="Senior Piping Engineer",
        company="Example EPC",
        apply_url="https://example.com/jobs/123",
        normalized_role="Senior Piping Engineer",
        location="Mumbai, India",
        city="Mumbai",
        country="India",
        closing_at="2026-08-01",
        employment_type="Permanent",
        software_text="AVEVA E3D",
        sector="Refinery",
        match_score=90,
        match_reasons="Initial scoring proof",
        priority="critical",
    )
    assert upsert_job(db_path, first) is True

    rescored = JobRecord(
        title=first.title,
        company=first.company,
        apply_url=first.apply_url,
        location="",
        normalized_role="",
        city="",
        country="",
        closing_at="",
        employment_type="",
        software_text="",
        sector="",
        match_score=0,
        gaps="Target role wording not detected",
        priority="low",
    )
    assert upsert_job(db_path, rescored) is False

    row = fetch_jobs(db_path)[0]
    for column in (
        "normalized_role",
        "city",
        "country",
        "closing_at",
        "employment_type",
        "software_text",
        "sector",
    ):
        assert row[column] == ""
    assert row["match_score"] == 0
    assert row["priority"] == "low"


def test_safe_http_client_blocks_redirect_outside_source_domains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_client.socket, "getaddrinfo", _public_dns)
    redirect = FakeResponse(
        "https://allowed.example/jobs",
        302,
        headers={"location": "https://outside.example/jobs"},
    )
    session = FakeSession([redirect])
    client = SafeHttpClient(
        session=session,
        allowed_domains={"allowed.example"},
        rate_limit_per_minute=60_000,
    )

    with pytest.raises(ValueError, match="outside allowed domains"):
        client.get("https://allowed.example/jobs")

    assert len(session.calls) == 1
    assert redirect.closed is True


def test_public_html_rejects_redirected_listing_before_evidence() -> None:
    listing_url = "https://allowed.example/jobs"
    client = RedirectingFixtureClient(
        {
            listing_url: _html_response(
                listing_url,
                "https://outside.example/jobs",
                "<html><body>outside content</body></html>",
            )
        }
    )

    with pytest.raises(ValueError, match="redirected outside allowed domains"):
        collect_public_html(
            _public_html_source(),
            client,
            respect_robots_txt=False,
        )


def test_public_html_redirected_detail_keeps_only_allowed_listing() -> None:
    listing_url = "https://allowed.example/jobs"
    detail_url = "https://allowed.example/jobs/123"
    listing = f"""
    <a href="{detail_url}">
      Senior Piping Engineer Job ID: 123 Mumbai, India Full Time
    </a>
    """
    client = RedirectingFixtureClient(
        {
            listing_url: _html_response(listing_url, listing_url, listing),
            detail_url: _html_response(
                detail_url,
                "https://outside.example/jobs/123",
                json.dumps({"title": "Outside job"}),
            ),
        }
    )

    result = collect_public_html(
        _public_html_source(),
        client,
        respect_robots_txt=False,
    )

    assert [job.title for job in result.jobs] == ["Senior Piping Engineer"]
    assert [artifact.source_url for artifact in result.evidence] == [listing_url]
    assert any("detail fetch failed" in warning for warning in result.warnings)
