from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from job_intelligence.contact_quality import clean_contacts, finalize_output, quality_mailbox_type


def _row(
    organization: str,
    email: str,
    *,
    source_url: str = "https://example.com/careers",
    status: str = "verified_official_job_mailbox",
    mailbox_type: str = "job_or_recruitment",
) -> dict[str, object]:
    return {
        "organization": organization,
        "record_type": "employer",
        "country": "India",
        "email": email,
        "mailbox_type": mailbox_type,
        "verification_status": status,
        "mail_route_status": "mx",
        "priority_score": 100,
        "source_url": source_url,
        "source_sha256": "a" * 64,
        "extraction_method": "mailto",
        "evidence_context": "Send CV",
        "discovered_at_utc": "2026-07-25T00:00:00+00:00",
        "review_reason": "",
    }


def test_quality_gate_rejects_escaped_and_non_application_mailboxes() -> None:
    assert quality_mailbox_type("u003esaudi.office@jandenul.com") == (
        "excluded",
        "escaped HTML/JavaScript prefix in local part",
    )
    assert quality_mailbox_type("e-talent.legal@framatome.com")[0] == "excluded"
    assert quality_mailbox_type("job.advert.accessibility@ramboll.com")[0] == "excluded"


def test_info_hr_is_general_not_recruitment() -> None:
    assert quality_mailbox_type("info.hr@atlascopco.com") == (
        "general_business",
        "",
    )


def test_global_email_deduplication_preserves_aliases_and_sources() -> None:
    frame = pd.DataFrame(
        [
            _row(
                "Enbridge",
                "careers@enbridge.com",
                source_url="https://www.enbridge.com/contact",
            ),
            _row(
                "Enbridge Inc.",
                "careers@enbridge.com",
                source_url="https://www.enbridge.com/careers",
            ),
            _row("Bad", "u003esaudi.office@jandenul.com"),
        ]
    )
    clean, excluded = clean_contacts(frame)
    assert len(clean) == 1
    assert len(excluded) == 1
    row = clean.iloc[0]
    assert row["email"] == "careers@enbridge.com"
    assert row["duplicate_source_count"] == 2
    assert "Enbridge" in row["organization_aliases"]
    assert "Enbridge Inc." in row["organization_aliases"]
    assert "https://www.enbridge.com/contact" in row["source_urls"]
    assert "https://www.enbridge.com/careers" in row["source_urls"]


def test_finalize_output_rebuilds_verified_package(tmp_path: Path) -> None:
    output = tmp_path / "contacts"
    output.mkdir()
    raw = pd.DataFrame(
        [
            _row("Example EPC", "careers@example.com"),
            _row(
                "Example EPC Alias",
                "careers@example.com",
                source_url="https://example.com/jobs",
            ),
            _row(
                "Example EPC",
                "info.hr@example.com",
                mailbox_type="job_or_recruitment",
            ),
            _row("Bad", "job.advert.accessibility@example.com"),
            _row("Bad", "u003eoffice@example.com"),
        ]
    )
    raw.to_csv(output / "All_Official_Contacts.csv", index=False)
    pd.DataFrame(
        [{"organization": "Example EPC", "url": "https://example.com/bad", "stage": "http", "error": "HTTP 404"}]
    ).to_csv(output / "Failures.csv", index=False)
    (output / "summary.json").write_text(
        json.dumps({"targets_scanned": 2}),
        encoding="utf-8",
    )

    archive = finalize_output(output)

    assert archive.exists()
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["targets_scanned"] == 2
    assert summary["raw_contact_rows"] == 5
    assert summary["all_official_contacts"] == 2
    assert summary["official_job_mailboxes"] == 1
    assert summary["official_general_mailboxes"] == 1
    assert summary["excluded_by_quality_gate"] == 2
    cleaned = pd.read_csv(output / "All_Official_Contacts.csv")
    assert set(cleaned["email"]) == {"careers@example.com", "info.hr@example.com"}
    assert int(
        cleaned.loc[
            cleaned["email"].eq("careers@example.com"),
            "duplicate_source_count",
        ].iloc[0]
    ) == 2
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        assert "Global_Official_Hiring_Contacts.xlsx" in names
        assert "Excluded_Quality.csv" in names
        assert "summary.json" in names
