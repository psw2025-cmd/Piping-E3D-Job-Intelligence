from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from job_intelligence import public_contacts
from job_intelligence.public_contacts import Contact, Failure, Target


def _cf_encode(value: str, key: int = 0x12) -> str:
    return f"{key:02x}" + "".join(
        f"{ord(character) ^ key:02x}" for character in value
    )


def test_normalize_email_rejects_invalid_and_file_extensions() -> None:
    assert (
        public_contacts.normalize_email("MAILTO:Jobs@Example.COM?subject=CV")
        == "jobs@example.com"
    )
    assert public_contacts.normalize_email("bad..name@example.com") == ""
    assert public_contacts.normalize_email("asset@logo.png") == ""
    assert public_contacts.normalize_email("missing-at.example.com") == ""


def test_extract_emails_handles_mailto_obfuscation_and_cloudflare() -> None:
    protected = _cf_encode("talent@example.com")
    html = f"""
    <html><body>
      <a href="mailto:careers@example.com?subject=Application">Send CV</a>
      <span>hr [at] example [dot] com</span>
      <span data-cfemail="{protected}">protected</span>
    </body></html>
    """
    found = public_contacts.extract_emails(html, html_content=True)
    assert found["careers@example.com"][0] == "mailto"
    assert found["hr@example.com"][0] == "text_obfuscation"
    assert found["talent@example.com"][0] == "cloudflare_obfuscation"


def test_load_targets_accepts_company_and_official_jobs_url(tmp_path: Path) -> None:
    registry = tmp_path / "recruiters_like.yaml"
    registry.write_text(
        """
recruiters:
  - company: Airswift Proof
    official_jobs_url: https://www.airswift-proof.example/jobs
  - company: Registry Proof
    official_careers_url: https://careers.registry-proof.example/
    public_job_url: https://jobs.registry-proof.example/
""",
        encoding="utf-8",
    )
    targets = public_contacts.load_targets([registry])
    assert len(targets) == 2
    by_name = {t.organization: t for t in targets}
    assert by_name["Airswift Proof"].urls == ("https://www.airswift-proof.example/jobs",)
    assert by_name["Registry Proof"].urls == (
        "https://careers.registry-proof.example/",
        "https://jobs.registry-proof.example/",
    )


def test_load_targets_recurses_deduplicates_and_shards(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        """
organizations:
  - name: Example EPC
    record_type: employer
    country: India
    official_domain: https://example.com
    careers_url: https://example.com/careers
  - canonical_company_name: Example EPC
    official_domain: https://example.com
    careers_url: https://example.com/careers
  - name: Agency One
    record_type: recruiter
    country: UAE
    website: https://agency.example.org
nested:
  companies:
    - name: Company Three
      url: https://three.example.net/jobs
""",
        encoding="utf-8",
    )
    all_targets = public_contacts.load_targets([registry])
    assert [target.organization for target in all_targets] == [
        "Example EPC",
        "Agency One",
        "Company Three",
    ]
    shard_zero = public_contacts.load_targets(
        [registry], shard_index=0, shard_count=2
    )
    shard_one = public_contacts.load_targets(
        [registry], shard_index=1, shard_count=2
    )
    assert len(shard_zero) + len(shard_one) == len(all_targets)
    assert {target.organization for target in shard_zero}.isdisjoint(
        {target.organization for target in shard_one}
    )


def test_mailbox_type_official_domain_and_verification() -> None:
    hosts = frozenset({"example.co.uk", "www.example.co.uk"})
    assert public_contacts.mailbox_type("careers@example.co.uk") == (
        "job_or_recruitment"
    )
    assert public_contacts.mailbox_type("info@example.co.uk") == "general_business"
    assert public_contacts.mailbox_type("person.name@example.co.uk") == (
        "excluded_non_role"
    )
    assert public_contacts.is_official_domain(
        "careers@jobs.example.co.uk", hosts
    )
    assert not public_contacts.is_official_domain("careers@gmail.com", hosts)
    assert public_contacts.verification_decision("job_or_recruitment", "mx") == (
        "verified_official_job_mailbox",
        100,
        "",
    )
    status, score, reason = public_contacts.verification_decision(
        "general_business", "dns_timeout"
    )
    assert status == "manual_review_dns"
    assert score == 30
    assert "dns_timeout" in reason


def test_scan_target_keeps_only_official_role_mailboxes(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, url: str, status: int, text: str, content_type: str) -> None:
            self.url = url
            self.status_code = status
            self.content = text.encode("utf-8")
            self.headers = {"content-type": content_type}

        @property
        def text(self) -> str:
            return self.content.decode("utf-8")

    class FakeClient:
        user_agent = "test-agent"

        def __init__(self, **_kwargs) -> None:
            pass

        def get(self, url: str, *, allowed_statuses=None, params=None):
            del allowed_statuses, params
            if url.endswith("/robots.txt"):
                return FakeResponse(url, 404, "", "text/plain")
            if url.endswith("/careers"):
                return FakeResponse(
                    url,
                    200,
                    '<a href="mailto:careers@example.com">Send your CV</a>'
                    '<a href="mailto:person.name@example.com">Recruiter</a>'
                    '<a href="mailto:jobs@gmail.com">External</a>'
                    '<a href="/contact">Contact</a>',
                    "text/html",
                )
            if url.endswith("/contact"):
                return FakeResponse(url, 200, "info@example.com", "text/html")
            return FakeResponse(url, 404, "", "text/html")

    class FakeMailValidator:
        def check(self, _domain: str) -> str:
            return "mx"

    monkeypatch.setattr(public_contacts, "SafeHttpClient", FakeClient)
    monkeypatch.setattr(public_contacts, "MailRouteValidator", FakeMailValidator)
    target = Target(
        organization="Example EPC",
        record_type="employer",
        country="India",
        urls=("https://example.com/careers",),
        hosts=frozenset({"example.com", "www.example.com"}),
    )
    contacts, failures = public_contacts.scan_target(
        target,
        max_pages=2,
        timeout_seconds=5,
        rate_limit=100,
    )
    by_email = {contact.email: contact for contact in contacts}
    assert set(by_email) == {"careers@example.com", "info@example.com"}
    assert by_email["careers@example.com"].verification_status == (
        "verified_official_job_mailbox"
    )
    assert by_email["info@example.com"].verification_status == (
        "verified_official_general_mailbox"
    )
    assert all(
        failure.stage in {"http", "robots", "fetch", "parse"}
        for failure in failures
    )


def _sample_contact(email: str, status: str, score: int) -> Contact:
    return Contact(
        organization="Example EPC",
        record_type="employer",
        country="India",
        email=email,
        mailbox_type="job_or_recruitment",
        verification_status=status,
        mail_route_status="mx",
        priority_score=score,
        source_url="https://example.com/careers",
        source_sha256="a" * 64,
        extraction_method="mailto",
        evidence_context="Send CV",
        discovered_at_utc="2026-07-25T00:00:00+00:00",
        review_reason="",
    )


def test_write_and_merge_outputs(tmp_path: Path) -> None:
    shard_one = tmp_path / "shards" / "one"
    shard_two = tmp_path / "shards" / "two"
    public_contacts.write_outputs(
        shard_one,
        [
            _sample_contact(
                "careers@example.com",
                "verified_official_job_mailbox",
                100,
            )
        ],
        [Failure("Example EPC", "https://example.com/jobs", "http", "HTTP 404")],
        1,
    )
    public_contacts.write_outputs(
        shard_two,
        [
            _sample_contact(
                "hr@example.com",
                "verified_official_job_mailbox",
                100,
            )
        ],
        [],
        1,
    )
    merged = tmp_path / "merged"
    archive = public_contacts.merge_outputs(tmp_path / "shards", merged)
    assert archive.exists()
    assert (merged / "Global_Official_Hiring_Contacts.xlsx").exists()
    contacts = pd.read_csv(merged / "All_Official_Contacts.csv")
    assert set(contacts["email"]) == {"careers@example.com", "hr@example.com"}
    summary = json.loads((merged / "summary.json").read_text(encoding="utf-8"))
    assert summary["targets_scanned"] == 2
    assert summary["official_job_mailboxes"] == 2
    with zipfile.ZipFile(archive) as bundle:
        assert "Global_Official_Hiring_Contacts.xlsx" in bundle.namelist()
        assert "SUMMARY.md" in bundle.namelist()
