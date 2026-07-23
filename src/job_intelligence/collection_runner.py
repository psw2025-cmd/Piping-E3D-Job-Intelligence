from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .collectors import COLLECTORS, collect_public_html, collect_sitemap
from .collectors.common import EvidenceArtifact
from .collectors.http_client import HttpClient, SafeHttpClient
from .database import connect, record_source_health, upsert_jobs
from .models import JobRecord
from .proof import finish_run, record_evidence, start_run
from .scoring import score_job
from .source_config import SourceSpec, load_source_config

_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,10}$")
_LONG_PAREN = re.compile(r"\(([^()]*)\)")
_DEFAULT_TITLE_TERMS = (
    "piping",
    "pipe layout",
    "plant layout",
    "e3d",
    "aveva e3d",
    "pdms",
    "sp3d",
    "smart 3d",
    "smartplant 3d",
    "3d model",
    "pipe support",
)
_GENERIC_DESIGN_TITLES = (
    "mechanical designer",
    "mechanical design engineer",
    "designer mechanical",
    "plant designer",
)
_GENERIC_DESIGN_CONTEXT = (
    "e3d",
    "aveva e3d",
    "pdms",
    "sp3d",
    "smart 3d",
    "smartplant 3d",
    "piping layout",
)


@dataclass(frozen=True, slots=True)
class SourceRunResult:
    source_id: str
    status: str
    jobs_collected: int
    new_jobs: int
    updated_jobs: int
    error_message: str = ""


@dataclass(slots=True)
class CollectionRunSummary:
    run_id: str
    status: str
    sources_attempted: int = 0
    sources_passed: int = 0
    sources_failed: int = 0
    jobs_collected: int = 0
    new_jobs: int = 0
    updated_jobs: int = 0
    source_results: list[SourceRunResult] = field(default_factory=list)


def _evidence_suffix(value: str) -> str:
    suffix = value.lower() if value.startswith(".") else f".{value.lower()}"
    return suffix if _SAFE_SUFFIX.fullmatch(suffix) else ".bin"


def _save_evidence(
    db_path: str | Path,
    evidence_root: str | Path,
    run_id: str,
    source_id: str,
    artifacts: list[EvidenceArtifact],
) -> None:
    destination = Path(evidence_root) / source_id / run_id
    destination.mkdir(parents=True, exist_ok=True)
    try:
        for index, artifact in enumerate(artifacts, start=1):
            digest = hashlib.sha256(artifact.body).hexdigest()
            suffix = _evidence_suffix(artifact.suffix)
            path = destination / f"{index:04d}_{digest[:16]}{suffix}"
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(artifact.body)
            temporary.replace(path)
            evidence_id = hashlib.sha256(
                f"{run_id}|{source_id}|{index}|{artifact.source_url}|{digest}".encode()
            ).hexdigest()
            record_evidence(
                db_path,
                evidence_id=evidence_id,
                run_id=run_id,
                source_id=source_id,
                source_url=artifact.source_url,
                file_path=str(path),
                sha256=digest,
                content_type=artifact.content_type,
                status_code=artifact.status_code,
                size_bytes=len(artifact.body),
            )
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        with connect(db_path) as connection:
            connection.execute(
                "DELETE FROM source_evidence WHERE run_id=? AND source_id=?",
                (run_id, source_id),
            )
        raise


def _delete_evidence(
    db_path: str | Path,
    evidence_root: str | Path,
    run_id: str,
    source_id: str,
) -> None:
    destination = Path(evidence_root) / source_id / run_id
    shutil.rmtree(destination, ignore_errors=True)
    with connect(db_path) as connection:
        connection.execute(
            "DELETE FROM source_evidence WHERE run_id=? AND source_id=?",
            (run_id, source_id),
        )


def _prepare_jobs(spec: SourceSpec, jobs: list[JobRecord], config_dir: Path) -> None:
    for job in jobs:
        job.source_name = job.source_name or spec.name
        result = score_job(job, config_dir=config_dir)
        job.match_score = result.score
        job.priority = result.priority
        job.match_reasons = "; ".join(result.reasons)
        job.gaps = "; ".join(result.gaps)


def _title_scope(title: str) -> str:
    def replace(match: re.Match[str]) -> str:
        content = " ".join(match.group(1).split())
        lowered = content.lower()
        if len(content.split()) > 4 or any(
            term in lowered
            for term in ("project", "rotation", "subsea cable", "wht's")
        ):
            return " "
        return f" {content} "

    cleaned = _LONG_PAREN.sub(replace, title)
    if cleaned.count("(") > cleaned.count(")"):
        cleaned = cleaned.rsplit("(", 1)[0]
    return " ".join(cleaned.lower().split())


def _title_matches_profile(spec: SourceSpec, job: JobRecord) -> bool:
    scoped_title = _title_scope(job.title)
    title_terms = (
        spec.text_list_option("title_terms")
        or spec.text_list_option("include_terms")
        or _DEFAULT_TITLE_TERMS
    )
    if any(term.lower() in scoped_title for term in title_terms):
        return True
    if any(term in scoped_title for term in _GENERIC_DESIGN_TITLES):
        searchable = job.searchable_text
        return any(term in searchable for term in _GENERIC_DESIGN_CONTEXT)
    return False


def _filter_profile_jobs(spec: SourceSpec, jobs: list[JobRecord]) -> list[JobRecord]:
    if not spec.bool_option("profile_filter", True):
        return jobs
    return [job for job in jobs if _title_matches_profile(spec, job)]


def _profile_audit_warnings(raw_count: int, filtered_count: int) -> list[str]:
    if raw_count == 0:
        return ["ZERO_RAW_CANDIDATES: source returned no profile candidates"]
    rejected = raw_count - filtered_count
    if filtered_count == 0:
        return [
            f"ZERO_FILTERED_TARGETS: raw_candidates={raw_count}; filtered_targets=0"
        ]
    if rejected:
        return [
            f"PROFILE_FILTER_AUDIT: raw_candidates={raw_count}; "
            f"filtered_targets={filtered_count}; rejected={rejected}"
        ]
    return []


def _select_sources(source_config, only_source_ids: set[str] | None):
    if only_source_ids is not None:
        configured_ids = {source.source_id for source in source_config.sources}
        unknown = sorted(only_source_ids - configured_ids)
        if unknown:
            raise ValueError(f"unknown source ids requested: {', '.join(unknown)}")
        enabled_ids = {
            source.source_id for source in source_config.sources if source.enabled
        }
        disabled = sorted(only_source_ids - enabled_ids)
        if disabled:
            raise ValueError(f"requested source ids are disabled: {', '.join(disabled)}")
    return [
        source
        for source in source_config.sources
        if source.enabled
        and (only_source_ids is None or source.source_id in only_source_ids)
    ]


def collect_sources(
    db_path: str | Path,
    source_config_path: str | Path,
    evidence_root: str | Path,
    *,
    only_source_ids: set[str] | None = None,
    client_factory: Callable[[SourceSpec], HttpClient] | None = None,
) -> CollectionRunSummary:
    config_path = Path(source_config_path)
    source_config = load_source_config(config_path)
    selected = _select_sources(source_config, only_source_ids)
    run_id = uuid.uuid4().hex
    summary = CollectionRunSummary(run_id=run_id, status="running")
    start_run(db_path, run_id)
    errors: list[str] = []

    for spec in selected:
        summary.sources_attempted += 1
        factory = client_factory or (
            lambda source: SafeHttpClient(
                timeout_seconds=source.int_option("timeout_seconds", 30),
                max_response_bytes=source.int_option(
                    "max_response_bytes", 15_000_000
                ),
                rate_limit_per_minute=source.int_option("rate_limit_per_minute", 30),
                max_redirects=source.int_option("max_redirects", 5, minimum=0),
            )
        )
        result = None
        evidence_saved = False
        stage = "collect"
        try:
            client = factory(spec)
            if spec.source_type == "sitemap":
                result = collect_sitemap(
                    spec,
                    client,
                    respect_robots_txt=source_config.policy["respect_robots_txt"],
                )
            elif spec.source_type == "public_html":
                result = collect_public_html(
                    spec,
                    client,
                    respect_robots_txt=source_config.policy["respect_robots_txt"],
                )
            else:
                result = COLLECTORS[spec.source_type](spec, client)
            if source_config.policy["retain_source_evidence"]:
                _save_evidence(
                    db_path, evidence_root, run_id, spec.source_id, result.evidence
                )
                evidence_saved = True
            stage = "score"
            raw_count = len(result.jobs)
            _prepare_jobs(spec, result.jobs, config_path.parent)
            result.jobs = _filter_profile_jobs(spec, result.jobs)
            result.warnings.extend(_profile_audit_warnings(raw_count, len(result.jobs)))
            stage = "upsert"
            new_jobs, updated_jobs = upsert_jobs(db_path, result.jobs)
            stage = "health"
            warning_message = " | ".join(result.warnings)
            source_status = "pass_with_warnings" if warning_message else "pass"
            record_source_health(
                db_path,
                spec.source_id,
                spec.name,
                source_status,
                records_found=len(result.jobs),
                error_message=warning_message,
            )
            summary.sources_passed += 1
            summary.jobs_collected += len(result.jobs)
            summary.new_jobs += new_jobs
            summary.updated_jobs += updated_jobs
            summary.source_results.append(
                SourceRunResult(
                    spec.source_id,
                    source_status,
                    len(result.jobs),
                    new_jobs,
                    updated_jobs,
                    warning_message,
                )
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if evidence_saved and stage == "upsert":
                try:
                    _delete_evidence(db_path, evidence_root, run_id, spec.source_id)
                except Exception as cleanup_exc:
                    message += (
                        " | evidence cleanup failed: "
                        f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                    )
            fetched_count = len(result.jobs) if result is not None else 0
            errors.append(f"{spec.source_id}: {message}")
            record_source_health(
                db_path,
                spec.source_id,
                spec.name,
                "fail",
                records_found=fetched_count,
                error_message=message,
            )
            summary.sources_failed += 1
            summary.source_results.append(
                SourceRunResult(spec.source_id, "fail", fetched_count, 0, 0, message)
            )

    if summary.sources_failed and summary.sources_passed:
        summary.status = "partial"
    elif summary.sources_failed:
        summary.status = "fail"
    elif not selected:
        summary.status = "no_sources"
    else:
        summary.status = "pass"

    finish_run(
        db_path,
        run_id,
        status=summary.status,
        sources_attempted=summary.sources_attempted,
        sources_passed=summary.sources_passed,
        sources_failed=summary.sources_failed,
        jobs_collected=summary.jobs_collected,
        new_jobs=summary.new_jobs,
        error_message=" | ".join(errors),
    )
    return summary
