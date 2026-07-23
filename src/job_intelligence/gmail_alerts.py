from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .private_import import PrivateImportResult, import_private_file

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
DEFAULT_GMAIL_QUERY = (
    "newer_than:30d ("
    "from:jobalerts-noreply@linkedin.com OR "
    "from:noreply@indeed.com OR "
    "from:jobalerts@alerts.naukri.com OR "
    "from:jobalerts@naukri.com OR "
    "from:alerts@bayt.com OR "
    "from:jobalerts@gulftalent.com OR "
    "subject:(job alert) OR subject:(jobs for you) OR subject:(new jobs)"
    ")"
)


@dataclass(slots=True)
class GmailImportSummary:
    attempted: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    failed: int = 0
    review_required: int = 0
    results: list[PrivateImportResult] = field(default_factory=list)


def build_gmail_service(credentials_path: str | Path, token_path: str | Path) -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            'Gmail support is not installed; run: pip install -e ".[gmail]"'
        ) from exc

    credentials_file = Path(credentials_path).expanduser().resolve()
    token_file = Path(token_path).expanduser().resolve()
    if not credentials_file.is_file():
        raise FileNotFoundError(f"Gmail OAuth credentials file not found: {credentials_file}")

    credentials = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_file), [GMAIL_READONLY_SCOPE]
        )
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_file), [GMAIL_READONLY_SCOPE]
            )
            credentials = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _list_message_ids(service: Any, query: str, max_results: int) -> list[str]:
    if max_results < 1:
        raise ValueError("max_results must be >= 1")
    found: list[str] = []
    page_token: str | None = None
    while len(found) < max_results:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                maxResults=min(500, max_results - len(found)),
                pageToken=page_token,
            )
            .execute()
        )
        messages = response.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("Gmail list response messages must be a list")
        for item in messages:
            message_id = str(item.get("id", "")).strip() if isinstance(item, dict) else ""
            if message_id:
                found.append(message_id)
                if len(found) >= max_results:
                    break
        page_token = str(response.get("nextPageToken", "")).strip() or None
        if not page_token or not messages:
            break
    return found


def _read_raw_message(service: Any, message_id: str) -> bytes:
    response = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="raw")
        .execute()
    )
    encoded = str(response.get("raw", "")).strip()
    if not encoded:
        raise ValueError(f"Gmail message {message_id} has no raw RFC822 content")
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding)
    except Exception as exc:
        raise ValueError(f"Gmail message {message_id} raw content is invalid") from exc


def import_gmail_alerts(
    db_path: str | Path,
    evidence_root: str | Path,
    *,
    credentials_path: str | Path | None = None,
    token_path: str | Path = "private-output/gmail/token.json",
    query: str = DEFAULT_GMAIL_QUERY,
    max_results: int = 200,
    max_bytes: int = 25_000_000,
    service: Any | None = None,
) -> GmailImportSummary:
    active_service = service
    if active_service is None:
        if credentials_path is None:
            raise ValueError("credentials_path is required when service is not supplied")
        active_service = build_gmail_service(credentials_path, token_path)

    summary = GmailImportSummary()
    message_ids = _list_message_ids(active_service, query.strip(), max_results)
    with tempfile.TemporaryDirectory(prefix="job-intel-gmail-") as temporary_dir:
        staging = Path(temporary_dir)
        for message_id in message_ids:
            summary.attempted += 1
            try:
                raw = _read_raw_message(active_service, message_id)
                source = staging / f"gmail_{message_id}.eml"
                source.write_bytes(raw)
                result = import_private_file(
                    db_path, source, evidence_root, max_bytes=max_bytes
                )
            except Exception as exc:
                result = PrivateImportResult(
                    input_path=f"gmail:{message_id}",
                    status="failed",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            summary.results.append(result)
            if result.status == "created":
                summary.created += 1
            elif result.status == "updated":
                summary.updated += 1
            elif result.status == "duplicate":
                summary.duplicates += 1
            else:
                summary.failed += 1
            if result.review_required:
                summary.review_required += 1
    return summary
