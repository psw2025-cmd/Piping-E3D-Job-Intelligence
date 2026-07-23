from pathlib import Path

from job_intelligence.deduplicate import canonicalize_url
from job_intelligence.models import JobRecord
from job_intelligence.normalization import enrich_job
from job_intelligence.worldwide_views import registry_frames, taxonomy_frames

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def test_workday_location_codes_are_normalized() -> None:
    cases = [
        ("CA.ON.Mississauga.2251 Speakman Drive", "Mississauga", "Canada"),
        ("US.TN.Oak Ridge.545 Oak Ridge Turnpike", "Oak Ridge", "United States"),
        ("US.NV.Henderson", "Henderson", "United States"),
        ("GB.Bristol.The Hub", "Bristol", "United Kingdom"),
        ("AR.Buenos Aires.1840 Arevalo", "Buenos Aires", "Argentina"),
    ]
    for location, city, country in cases:
        job = JobRecord(title="Senior Piping Engineer", company="EPC", location=location)
        enrich_job(job, config_dir=CONFIG_DIR)
        assert (job.city, job.country) == (city, country)


def test_expanded_role_aliases_are_normalized() -> None:
    cases = {
        "Principal Designer - Piping Layout": "Principal Piping Designer",
        "Lead Piping Designer": "Lead Piping Designer",
        "Senior Mechanical/Piping Designer": "Senior Mechanical Piping Designer",
        "Sr. Piping Stress Analyst": "Piping Stress Analyst",
        "Piping Material Engineer": "Piping Materials Engineer",
    }
    for title, expected in cases.items():
        job = JobRecord(title=title, company="EPC")
        enrich_job(job, config_dir=CONFIG_DIR)
        assert job.normalized_role == expected


def test_portal_and_taxonomy_matrices_load() -> None:
    employers, recruiters, portals = registry_frames(CONFIG_DIR)
    roles, locations = taxonomy_frames(CONFIG_DIR)
    assert "JobStreet Job Alerts" in set(portals["company"])
    assert len(employers) >= 25
    assert len(recruiters) >= 15
    assert len(roles) >= 30
    assert len(locations) >= 100


def test_sensitive_tracking_tokens_are_removed_but_job_id_is_preserved() -> None:
    url = (
        "https://www.gulftalent.com/uae/jobs/pmc-lead-piping-engineer-610832"
        "?utm_source=jobalert&jwt=secret&trackingId=abc"
    )
    assert canonicalize_url(url) == (
        "https://www.gulftalent.com/uae/jobs/pmc-lead-piping-engineer-610832"
    )
    indeed = "https://bh.indeed.com/rc/clk/dl?jk=abc123&from=ja&tk=secret"
    assert canonicalize_url(indeed) == (
        "https://bh.indeed.com/rc/clk/dl?jk=abc123"
    )
