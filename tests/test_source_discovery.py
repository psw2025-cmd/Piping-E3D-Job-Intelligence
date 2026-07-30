from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_intelligence.source_config import load_source_config
from job_intelligence.source_discovery import (
    DiscoveryRecord,
    detect_source,
    extract_candidate_urls,
    slugify,
    write_outputs,
)


def test_detect_smartrecruiters_company_identifier() -> None:
    record = detect_source(
        "Ramboll",
        "https://jobs.smartrecruiters.com/Ramboll3/744000100349094-lead-piping-engineer",
    )
    assert record is not None
    assert record.platform == "smartrecruiters"
    assert record.source["company_identifier"] == "Ramboll3"
    assert record.source["enabled"] is True


def test_detect_workday_tenant_site_and_locale() -> None:
    record = detect_source(
        "KBR",
        "https://kbr.wd5.myworkdayjobs.com/en-US/KBR_Careers/job/Example",
    )
    assert record is not None
    assert record.platform == "workday"
    assert record.source["tenant"] == "kbr"
    assert record.source["site"] == "KBR_Careers"
    assert record.source["locale"] == "en-US"


def test_detect_oracle_candidate_experience_site() -> None:
    record = detect_source(
        "Wood",
        "https://ehif.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs",
    )
    assert record is not None
    assert record.platform == "oracle_hcm"
    assert record.source["site_number"] == "CX_1"
    assert record.source["base_url"] == "https://ehif.fa.em2.oraclecloud.com"


def test_extract_candidate_urls_keeps_ats_and_jobs_only() -> None:
    html = """
    <html><body>
      <a href="https://jobs.smartrecruiters.com/Ramboll3/">Jobs</a>
      <a href="/careers/job/123">Career detail</a>
      <a href="/about-us">About</a>
    </body></html>
    """
    urls = extract_candidate_urls(html, "https://example.com/careers")
    assert "https://jobs.smartrecruiters.com/Ramboll3/" in urls
    assert "https://example.com/careers/job/123" in urls
    assert all("about-us" not in url for url in urls)


def test_slugify_is_stable_and_bounded() -> None:
    assert slugify("L&T Energy Hydrocarbon") == "l-t-energy-hydrocarbon"
    assert len(slugify("A" * 100)) == 44


def test_write_outputs_validates_runtime_and_declares_no_gmail(tmp_path: Path) -> None:
    source = {
        "id": "auto-ramboll-smartrecruiters",
        "name": "Ramboll official SmartRecruiters postings",
        "type": "smartrecruiters",
        "company": "Ramboll",
        "company_identifier": "Ramboll3",
        "enabled": True,
        "profile_filter": True,
        "fetch_details": True,
        "timeout_seconds": 30,
        "rate_limit_per_minute": 20,
        "max_items": 400,
        "page_size": 100,
        "max_pages": 20,
    }
    record = DiscoveryRecord(
        company="Ramboll",
        platform="smartrecruiters",
        evidence_url="https://jobs.smartrecruiters.com/Ramboll3/",
        source=source,
        confidence="verified_public_connector",
        probe_status="pass",
        probe_jobs=1,
    )
    runtime = {
        "sources": [source],
        "policy": {
            "respect_robots_txt": True,
            "bypass_captcha": False,
            "use_rotating_proxies": False,
            "retain_source_evidence": True,
        },
    }
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"
    runtime_path = tmp_path / "runtime.yaml"
    write_outputs(
        [record],
        runtime,
        report_json=report_json,
        report_md=report_md,
        runtime_sources=runtime_path,
    )
    load_source_config(runtime_path)
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["verified"] == 1
    assert "Gmail is not used" in payload["principle"]
    markdown = report_md.read_text(encoding="utf-8")
    assert "Gmail dependency: **NONE**" in markdown
    loaded_runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
    assert loaded_runtime["sources"][0]["company_identifier"] == "Ramboll3"


def test_workday_ids_distinguish_multiple_sites_for_same_company(tmp_path: Path) -> None:
    company = "Occidental Petroleum (Oxy)"
    first = detect_source(
        company,
        "https://oxy.wd5.myworkdayjobs.com/en-US/Oxy_Careers/jobs",
    )
    second = detect_source(
        company,
        "https://oxy.wd5.myworkdayjobs.com/en-US/Oxy_Experienced_Hires/jobs",
    )
    repeated = detect_source(
        company,
        "https://oxy.wd5.myworkdayjobs.com/en-US/Oxy_Careers/jobs",
    )
    assert first is not None
    assert second is not None
    assert repeated is not None
    assert first.source["id"] != second.source["id"]
    assert first.source["id"] == repeated.source["id"]
    assert len(first.source["id"]) <= 64
    assert len(second.source["id"]) <= 64

    runtime_path = tmp_path / "multiple-workday-sites.yaml"
    runtime_path.write_text(
        yaml.safe_dump(
            {
                "sources": [first.source, second.source],
                "policy": {
                    "respect_robots_txt": True,
                    "bypass_captcha": False,
                    "use_rotating_proxies": False,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loaded = load_source_config(runtime_path)
    assert len(loaded.sources) == 2
