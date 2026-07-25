from __future__ import annotations

import base64
import hashlib
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .database import _upsert_job, connect
from .deduplicate import canonicalize_url
from .manual_import import create_manual_job
from .models import JobRecord, utc_now_iso
from .private_import import init_private_import_tables

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_GMAIL_QUERY = (
    "newer_than:30d (job OR jobs OR vacancy OR vacancies OR hiring OR career) -from:notifications@github.com -from:github -subject:Run failed -subject:failed"
)
_ROLE_TERMS = (
    "piping",
    "pipe layout",
    "plant layout",
    "e3d",
    "aveva",
    "pdms",
    "sp3d",
    "smartplant 3d",
    "smart 3d",
    "piping designer",
    "piping engineer",
    "model coordinator",
    "pipe support",
)
_JOB_URL_TERMS = (
    "/job/",
    "/jobs/",
    "/careers/job/",
    "/viewjob",
    "/jobdetails",
    "/job-detail",
    "jobid=",
    "job_id=",
)
_EXCLUDED_LINK_TERMS = (
    "unsubscribe",
    "preferences",
    "privacy",
    "terms",
    "settings",
    "help",
    "support",
    "login",
    "sign-in",
    "signin",
    "profile",
    "talent-community",
    "talentnetwork",
)
_GENERIC_LINK_TEXT = {
    "apply",
    "apply now",
    "view",
    "view job",
    "view jobs",
    "learn more",
    "details",
    "open",
    "click here",
}
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_LABEL_PATTERNS = {
    "company": re.compile(
        r"(?:^|\n)\s*(?:company|employer|organisation|organization)\s*:\s*"
        r"([^\n|;]{2,160})",
        re.IGNORECASE,
    ),
    "location": re.compile(
        r"(?:^|\n)\s*(?:location|job location|work location)\s*:\s*"
        r"([^\n|;]{2,160})",
        re.IGNORECASE,
    ),
    "title": re.compile(
        r"(?:^|\n)\s*(?:job title|position|role)\s*:\s*([^\n|;]{2,180})",
        re.IGNORECASE,
    ),
}
_PORTAL_DOMAINS = {
    "linkedin.com": "LinkedIn",
    "naukri.com": "Naukri",
    "indeed.com": "Indeed",
    "glassdoor.com": "Glassdoor",
    "foundit.in": "Foundit",
    "monster.com": "Monster",
    "gulftalent.com": "GulfTalent",
    "bayt.com": "Bayt",
    "naukrigulf.com": "Naukrigulf",
    "rigzone.com": "Rigzone",
    "energyjobline.com": "Energy Jobline",
    "oilandgasjobsearch.com": "Oil and Gas Job Search",
    "epcengineer.com": "EPC Engineer",
}


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    title: str
    company: str
    location: str
    url: str
    context: str
    review_required: bool


@dataclass(frozen=True, slots=True)
class GmailMessageImportResult:
    message_id: str
    status: str
    created: int = 0
    updated: int = 0
    job_keys: tuple[str, ...] = ()
    evidence_path: str = ""
    error_message: str = ""


@dataclass(slots=True)
class GmailImportSummary:
    attempted: int = 0
    processed: int = 0
    duplicates: int = 0
    no_match: int = 0
    failed: int = 0
    jobs_created: int = 0
    jobs_updated: int = 0
    results: list[GmailMessageImportResult] = field(default_factory=list)


def init_gmail_tables(db_path: str | Path) -> None:
    init_private_import_tables(db_path)
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS gmail_alert_messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL DEFAULT '',
                sender TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL DEFAULT '',
                query_text TEXT NOT NULL DEFAULT '',
                evidence_path TEXT NOT NULL DEFAULT '',
                sha256 TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                jobs_created INTEGER NOT NULL DEFAULT 0,
                jobs_updated INTEGER NOT NULL DEFAULT 0,
                error_message TEXT NOT NULL DEFAULT '',
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gmail_alert_jobs (
                message_id TEXT NOT NULL,
                job_key TEXT NOT NULL,
                candidate_index INTEGER NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (message_id, job_key)
            );

            CREATE INDEX IF NOT EXISTS idx_gmail_alert_status
                ON gmail_alert_messages(status, imported_at);
            CREATE INDEX IF NOT EXISTS idx_gmail_alert_job_key
                ON gmail_alert_jobs(job_key);
            """
        )


def _message_parts(message: Message) -> tuple[str, str]:
    plain: list[str] = []
    html: list[str] = []
    parts: Iterable[Message] = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = str(part.get_content())
        except (LookupError, UnicodeDecodeError, ValueError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace")
        if content_type == "text/html":
            html.append(content)
        else:
            plain.append(content)
    return "\n".join(plain).strip(), "\n".join(html).strip()


def _portal_name(sender: str) -> str:
    address = parseaddr(sender)[1].lower()
    domain = address.rsplit("@", 1)[-1] if "@" in address else ""
    for suffix, name in _PORTAL_DOMAINS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return name
    display = parseaddr(sender)[0].strip()
    return display or domain or "Gmail alert"


def _clean_text(value: str, limit: int = 4000) -> str:
    return " ".join(value.split())[:limit]


def _contains_role_term(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in _ROLE_TERMS)


def _is_job_link(url: str, context: str) -> bool:
    lowered = url.lower()
    if not lowered.startswith(("http://", "https://")):
        return False
    if any(term in lowered for term in _EXCLUDED_LINK_TERMS):
        return False
    return any(term in lowered for term in _JOB_URL_TERMS) or _contains_role_term(context)


def _unwrap_google_url(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host not in {"google.com", "www.google.com"} or parsed.path != "/url":
        return url
    query = parse_qs(parsed.query)
    for key in ("q", "url"):
        candidate = (query.get(key) or [""])[0].strip()
        if candidate.startswith(("http://", "https://")):
            return candidate
    return url


def _label_value(text: str, field: str) -> str:
    match = _LABEL_PATTERNS[field].search(text)
    return _clean_text(match.group(1), 180) if match else ""


def _candidate_title(anchor_text: str, context: str) -> str:
    anchor = _clean_text(anchor_text, 180).strip(" -:|")
    if anchor.lower() not in _GENERIC_LINK_TEXT and _contains_role_term(anchor):
        return anchor
    labeled = _label_value(context, "title")
    if labeled:
        return labeled
    for line in context.splitlines():
        candidate = _clean_text(line, 180).strip(" -:|")
        if 4 <= len(candidate) <= 180 and _contains_role_term(candidate):
            return candidate
    return anchor if anchor.lower() not in _GENERIC_LINK_TEXT else ""


def _html_candidates(html_text: str) -> list[AlertCandidate]:
    if not html_text:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[AlertCandidate] = []
    for anchor in soup.find_all("a", href=True):
        raw_url = str(anchor.get("href", "")).strip()
        url = _unwrap_google_url(raw_url)
        parent = anchor.find_parent(["article", "li", "tr", "div", "td", "section"])
        context = (parent or anchor).get_text("\n", strip=True)
        anchor_text = anchor.get_text(" ", strip=True)
        if not _is_job_link(url, f"{anchor_text}\n{context}"):
            continue
        title = _candidate_title(anchor_text, context)
        if not title or not _contains_role_term(f"{title} {context}"):
            continue
        company = _label_value(context, "company")
        location = _label_value(context, "location")
        candidates.append(
            AlertCandidate(
                title=title,
                company=company or "Unknown employer",
                location=location,
                url=url,
                context=_clean_text(context, 6000),
                review_required=not bool(company),
            )
        )
    return candidates


def _plain_candidates(plain_text: str) -> list[AlertCandidate]:
    if not plain_text:
        return []
    lines = [line.strip() for line in plain_text.splitlines()]
    candidates: list[AlertCandidate] = []
    url_pattern = re.compile(r"https?://[^\s<>\]\[\"']+", re.IGNORECASE)
    for index, line in enumerate(lines):
        for match in url_pattern.finditer(line):
            url = _unwrap_google_url(match.group(0).rstrip(".,);]"))
            nearby = "\n".join(lines[max(0, index - 3) : min(len(lines), index + 4)])
            if not _is_job_link(url, nearby):
                continue
            same_line_title = line[: match.start()].strip(" -:|")
            title = _candidate_title(same_line_title, nearby)
            if not title or not _contains_role_term(f"{title} {nearby}"):
                continue
            company = _label_value(nearby, "company")
            location = _label_value(nearby, "location")
            candidates.append(
                AlertCandidate(
                    title=title,
                    company=company or "Unknown employer",
                    location=location,
                    url=url,
                    context=_clean_text(nearby, 6000),
                    review_required=not bool(company),
                )
            )
    return candidates


def extract_alert_candidates(raw_message: bytes) -> tuple[Message, tuple[AlertCandidate, ...]]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    plain_text, html_text = _message_parts(message)
    combined: list[AlertCandidate] = _html_candidates(html_text)
    combined.extend(_plain_candidates(plain_text))
    deduplicated: list[AlertCandidate] = []
    seen: set[str] = set()
    for candidate in combined:
        key = canonicalize_url(candidate.url) or (
            f"{candidate.title.lower()}|{candidate.company.lower()}|"
            f"{candidate.location.lower()}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(candidate)
    return message, tuple(deduplicated)


def _received_at(message: Message, internal_date_ms: str = "") -> str:
    if internal_date_ms:
        try:
            from datetime import UTC, datetime

            return datetime.fromtimestamp(int(internal_date_ms) / 1000, UTC).replace(
                microsecond=0
            ).isoformat()
        except (TypeError, ValueError, OSError):
            pass
    date_header = str(message.get("date", "")).strip()
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
            if parsed.tzinfo is None:
                from datetime import UTC

                parsed = parsed.replace(tzinfo=UTC)
            return parsed.replace(microsecond=0).isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    return utc_now_iso()


def _public_contact(text: str, sender: str) -> str:
    sender_address = parseaddr(sender)[1].lower()
    for address in _EMAIL_PATTERN.findall(text):
        lowered = address.lower()
        if lowered == sender_address:
            continue
        if any(term in lowered for term in ("noreply", "no-reply", "donotreply")):
            continue
        return lowered
    return ""


def _store_evidence(
    raw_message: bytes,
    evidence_root: Path,
    digest: str,
) -> tuple[Path, bool]:
    destination_dir = evidence_root / digest[:2]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{digest}.eml"
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError(f"existing Gmail evidence hash mismatch: {destination}")
        return destination, False
    temporary = destination.with_suffix(".eml.tmp")
    temporary.write_bytes(raw_message)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
        temporary.unlink(missing_ok=True)
        raise ValueError("Gmail evidence hash verification failed")
    temporary.replace(destination)
    return destination, True


def _job_from_candidate(
    candidate: AlertCandidate,
    *,
    message: Message,
    portal: str,
    received_at: str,
    evidence_path: Path,
) -> JobRecord:
    sender = str(message.get("from", ""))
    subject = str(message.get("subject", ""))
    plain_text, html_text = _message_parts(message)
    body_text = plain_text or BeautifulSoup(html_text, "html.parser").get_text("\n")
    evidence_text = (
        f"Subject: {subject}\nFrom: {sender}\n"
        f"{candidate.context}\n{body_text[:12000]}"
    )
    job = create_manual_job(
        title=candidate.title,
        company=candidate.company,
        text=evidence_text,
        location=candidate.location,
        apply_url=candidate.url,
        source_url=candidate.url,
        source_name=f"gmail:{portal}",
        published_at=received_at,
    )
    contact = _public_contact(evidence_text, sender)
    job.recruiter_email = contact
    job.contact_confidence = "ALERT_SUPPLIED" if contact else ""
    job.contact_source_url = candidate.url if contact else ""
    job.agency_name = portal
    job.duplicate_status = "cross_source_candidate"
    if candidate.review_required and job.application_status == "new":
        job.application_status = "review_required"
    job.skills_text = (
        f"Gmail alert evidence: {evidence_path.name}; original subject: {subject}"
    )
    return job


def import_gmail_raw_message(
    db_path: str | Path,
    *,
    message_id: str,
    raw_message: bytes,
    evidence_root: str | Path,
    thread_id: str = "",
    internal_date_ms: str = "",
    query_text: str = "",
) -> GmailMessageImportResult:
    if not message_id.strip():
        raise ValueError("Gmail message_id is required")
    if not raw_message:
        raise ValueError("Gmail raw message is empty")
    init_gmail_tables(db_path)

    with connect(db_path) as connection:
        existing = connection.execute(
            "SELECT status, evidence_path FROM gmail_alert_messages WHERE message_id=?",
            (message_id,),
        ).fetchone()
        if existing and str(existing["status"]).startswith("complete"):
            linked = connection.execute(
                """
                SELECT COUNT(*)
                FROM gmail_alert_jobs AS links
                JOIN jobs ON jobs.job_key = links.job_key
                WHERE links.message_id=?
                """,
                (message_id,),
            ).fetchone()[0]
            expected = connection.execute(
                "SELECT COUNT(*) FROM gmail_alert_jobs WHERE message_id=?",
                (message_id,),
            ).fetchone()[0]
            if linked == expected:
                return GmailMessageImportResult(
                    message_id=message_id,
                    status="duplicate",
                    evidence_path=str(existing["evidence_path"]),
                )
        if existing:
            connection.execute(
                "DELETE FROM gmail_alert_jobs WHERE message_id=?",
                (message_id,),
            )
            connection.execute(
                "DELETE FROM gmail_alert_messages WHERE message_id=?",
                (message_id,),
            )

    digest = hashlib.sha256(raw_message).hexdigest()
    evidence_path, copied = _store_evidence(raw_message, Path(evidence_root), digest)
    message, candidates = extract_alert_candidates(raw_message)
    sender = str(message.get("from", ""))
    subject = str(message.get("subject", ""))
    portal = _portal_name(sender)
    received_at = _received_at(message, internal_date_ms)
    created = 0
    updated = 0
    job_keys: list[str] = []
    status = "complete" if candidates else "complete_no_match"

    try:
        with connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO gmail_alert_messages (
                    message_id, thread_id, sender, subject, received_at, query_text,
                    evidence_path, sha256, status, jobs_created, jobs_updated,
                    error_message, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'staged', 0, 0, '', ?)
                """,
                (
                    message_id,
                    thread_id,
                    sender,
                    subject,
                    received_at,
                    query_text,
                    str(evidence_path),
                    digest,
                    utc_now_iso(),
                ),
            )
            for index, candidate in enumerate(candidates):
                job = _job_from_candidate(
                    candidate,
                    message=message,
                    portal=portal,
                    received_at=received_at,
                    evidence_path=evidence_path,
                )
                if _upsert_job(connection, job):
                    created += 1
                else:
                    updated += 1
                job_keys.append(job.job_key)
                connection.execute(
                    """
                    INSERT INTO gmail_alert_jobs (
                        message_id, job_key, candidate_index, source_url
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (message_id, job.job_key, index, candidate.url),
                )
            connection.execute(
                """
                UPDATE gmail_alert_messages
                SET status=?, jobs_created=?, jobs_updated=?
                WHERE message_id=?
                """,
                (status, created, updated, message_id),
            )
    except Exception:
        if copied:
            evidence_path.unlink(missing_ok=True)
        raise

    return GmailMessageImportResult(
        message_id=message_id,
        status=status,
        created=created,
        updated=updated,
        job_keys=tuple(job_keys),
        evidence_path=str(evidence_path),
    )


def _decode_gmail_raw(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def import_gmail_service(
    service: Any,
    db_path: str | Path,
    *,
    evidence_root: str | Path,
    query: str = DEFAULT_GMAIL_QUERY,
    max_messages: int = 200,
) -> GmailImportSummary:
    if max_messages < 1 or max_messages > 5000:
        raise ValueError("max_messages must be between 1 and 5000")
    summary = GmailImportSummary()
    page_token: str | None = None
    message_refs: list[dict[str, str]] = []
    while len(message_refs) < max_messages:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=min(500, max_messages - len(message_refs)),
                pageToken=page_token,
            )
            .execute()
        )
        message_refs.extend(response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    for reference in message_refs[:max_messages]:
        message_id = str(reference.get("id", ""))
        summary.attempted += 1
        try:
            payload = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="raw")
                .execute()
            )
            raw = _decode_gmail_raw(str(payload.get("raw", "")))
            result = import_gmail_raw_message(
                db_path,
                message_id=message_id,
                thread_id=str(payload.get("threadId", "")),
                internal_date_ms=str(payload.get("internalDate", "")),
                raw_message=raw,
                evidence_root=evidence_root,
                query_text=query,
            )
        except Exception as exc:
            result = GmailMessageImportResult(
                message_id=message_id,
                status="failed",
                error_message=f"{type(exc).__name__}: {exc}",
            )
            summary.failed += 1
        else:
            if result.status == "duplicate":
                summary.duplicates += 1
            elif result.status == "complete_no_match":
                summary.no_match += 1
                summary.processed += 1
            else:
                summary.processed += 1
                summary.jobs_created += result.created
                summary.jobs_updated += result.updated
        summary.results.append(result)
    return summary


def authorize_gmail(
    *,
    credentials_path: str | Path,
    token_path: str | Path,
) -> Any:
    credentials_file = Path(credentials_path)
    token_file = Path(token_path)
    if not credentials_file.is_file():
        raise FileNotFoundError(f"Gmail OAuth credentials file not found: {credentials_file}")
    credentials: Credentials | None = None
    if token_file.is_file():
        credentials = Credentials.from_authorized_user_file(
            str(token_file),
            [GMAIL_READONLY_SCOPE],
        )
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_file),
                [GMAIL_READONLY_SCOPE],
            )
            credentials = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def verify_gmail_imports(db_path: str | Path) -> list[str]:
    init_gmail_tables(db_path)
    errors: list[str] = []
    with connect(db_path) as connection:
        messages = connection.execute(
            """
            SELECT message_id, evidence_path, sha256, status
            FROM gmail_alert_messages
            """
        ).fetchall()
        orphans = connection.execute(
            """
            SELECT links.message_id, links.job_key
            FROM gmail_alert_jobs AS links
            LEFT JOIN gmail_alert_messages AS messages
                ON messages.message_id = links.message_id
            LEFT JOIN jobs ON jobs.job_key = links.job_key
            WHERE messages.message_id IS NULL OR jobs.job_key IS NULL
            """
        ).fetchall()
    for row in messages:
        message_id = str(row["message_id"])
        if str(row["status"]) == "staged":
            errors.append(f"Gmail import is still staged: {message_id}")
        evidence = Path(str(row["evidence_path"]))
        if not evidence.exists():
            errors.append(f"Missing Gmail evidence: {evidence}")
            continue
        if hashlib.sha256(evidence.read_bytes()).hexdigest() != str(row["sha256"]):
            errors.append(f"Gmail evidence hash mismatch: {evidence}")
    for row in orphans:
        errors.append(
            f"Orphan Gmail alert link: {row['message_id']} -> {row['job_key']}"
        )
    return errors


def remove_gmail_evidence_tree(path: str | Path) -> None:
    """Test/support helper; never called by normal imports."""
    shutil.rmtree(Path(path), ignore_errors=True)
