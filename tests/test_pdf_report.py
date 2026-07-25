from __future__ import annotations

from pathlib import Path

from job_intelligence.database import init_database, upsert_job
from job_intelligence.models import JobRecord, utc_now_iso
from job_intelligence.pdf_report import generate_executive_digest


def test_generate_executive_digest(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    out_path = tmp_path / "digest.md"
    
    init_database(db_path)
    job = JobRecord(
        job_key="test-key-1",
        source_name="Test Source",
        company="KBR",
        title="Piping Layout Engineer",
        normalized_role="Piping Engineer",
        location="Chennai, India",
        apply_url="https://kbr.com/jobs/1",
        match_score=95,
        published_at=utc_now_iso(),
        found_at=utc_now_iso(),
    )
    upsert_job(db_path, job)
    
    generated = generate_executive_digest(db_path, out_path, min_score=80)
    assert generated.exists()
    
    content = generated.read_text(encoding="utf-8")
    assert "Executive Job Intelligence Digest" in content
    assert "Piping Layout Engineer" in content
    assert "KBR" in content
    assert "95 / 100" in content
