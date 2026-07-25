from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from job_intelligence.collection_runner import collect_sources
from job_intelligence.collectors.greenhouse import collect_greenhouse
from job_intelligence.collectors.http_client import FetchedResponse, validate_public_http_url
from job_intelligence.collectors.lever import collect_lever
from job_intelligence.collectors.rss import collect_rss
from job_intelligence.collectors.sitemap import collect_sitemap
from job_intelligence.collectors.smartrecruiters import collect_smartrecruiters
from job_intelligence.database import connect, fetch_jobs
from job_intelligence.source_config import SourceSpec, load_source_config


class FakeClient:
    def __init__(self, routes: dict[str, list[FetchedResponse]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> FetchedResponse:
        self.calls.append((url, params))
        values = self.routes[url]
        if not values:
            raise AssertionError(f"No fake response remaining for {url}")
        return values.pop(0)


def response(
    url: str,
    payload: object,
    content_type: str = "application/json",
) -> FetchedResponse:
    if isinstance(payload, bytes):
        content = payload
    else:
        content = json.dumps(payload).encode()
    return FetchedResponse(url, 200, {"content-type": content_type}, content)


def spec(source_type: str, **options: object) -> SourceSpec:
    return SourceSpec(
        source_id=f"test_{source_type}",
        name=f"Test {source_type}",
        source_type=source_type,
        enabled=True,
        company="Example EPC",
        options=options,
    )


def test_greenhouse_collector() -> None:
    url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"
    client = FakeClient(
        {
            url: [
                response(
                    url,
                    {
                        "jobs": [
                            {
                                "id": 1,
                                "title": "Senior E3D Piping Designer",
                                "company_name": "Example EPC",
                                "absolute_url": "https://boards.greenhouse.io/example/jobs/1",
                                "first_published": "2026-07-20T10:00:00Z",
                                "location": {"name": "Mumbai"},
                                "content": "<p>AVEVA E3D refinery layout role</p>",
                            }
                        ]
                    },
                )
            ]
        }
    )
    result = collect_greenhouse(spec("greenhouse", board_token="example"), client)
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Mumbai"
    assert "AVEVA E3D" in result.jobs[0].description
    assert len(result.evidence) == 1


def test_lever_pagination_and_salary() -> None:
    url = "https://api.lever.co/v0/postings/example"
    first = {
        "id": "one",
        "text": "Lead Piping Engineer",
        "descriptionPlain": "Offshore piping layout role",
        "hostedUrl": "https://jobs.lever.co/example/one",
        "applyUrl": "https://jobs.lever.co/example/one/apply",
        "categories": {"location": "UAE", "commitment": "Full-time"},
        "salaryRange": {
            "currency": "AED",
            "min": 1,
            "max": 2,
            "interval": "month",
        },
    }
    client = FakeClient({url: [response(url, [first]), response(url, [])]})
    result = collect_lever(spec("lever", site="example", page_size=1), client)
    assert len(result.jobs) == 1
    assert result.jobs[0].salary_text == "AED 1–2 per month"
    assert len(result.evidence) == 2


def test_smartrecruiters_fetches_detail() -> None:
    list_url = "https://api.smartrecruiters.com/v1/companies/example/postings"
    detail_url = f"{list_url}/123"
    client = FakeClient(
        {
            list_url: [
                response(
                    list_url,
                    {"content": [{"id": "123", "name": "Piping Engineer"}]},
                )
            ],
            detail_url: [
                response(
                    detail_url,
                    {
                        "id": "123",
                        "name": "Piping Engineer",
                        "company": {"name": "Example EPC"},
                        "location": {"city": "Pune", "country": "India"},
                        "releasedDate": "2026-07-21T00:00:00Z",
                        "postingUrl": "https://jobs.smartrecruiters.com/example/123",
                        "applyUrl": "https://jobs.smartrecruiters.com/example/123/apply",
                        "jobAd": {
                            "sections": {
                                "jobDescription": {
                                    "title": "Job Description",
                                    "text": "<p>PDMS brownfield role</p>",
                                }
                            }
                        },
                    },
                )
            ],
        }
    )
    result = collect_smartrecruiters(
        spec("smartrecruiters", company_identifier="example"),
        client,
    )
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Pune, India"
    assert "PDMS" in result.jobs[0].description


def test_rss_collector() -> None:
    url = "https://example.com/jobs.rss"
    xml = b"""<?xml version='1.0'?><rss version='2.0'><channel><item>
    <title>Senior Piping Engineer</title><link>https://example.com/jobs/1</link>
    <description><![CDATA[<p>E3D refinery role</p>]]></description>
    <pubDate>Tue, 21 Jul 2026 10:00:00 GMT</pubDate><category>Offshore</category>
    </item></channel></rss>"""
    client = FakeClient({url: [response(url, xml, "application/rss+xml")]})
    result = collect_rss(spec("rss", url=url, location="Oman"), client)
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Oman"
    assert result.jobs[0].skills_text == "Offshore"


def test_sitemap_extracts_schema_org_job() -> None:
    sitemap_url = "https://example.com/jobs-sitemap.xml"
    page_url = "https://example.com/careers/piping-engineer"
    robots_url = "https://example.com/robots.txt"
    sitemap_xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"<url><loc>{page_url}</loc></url></urlset>"
    ).encode()
    json_ld = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Piping Layout Engineer",
        "description": "<p>AVEVA E3D offshore role</p>",
        "datePosted": "2026-07-22",
        "hiringOrganization": {"name": "Example EPC"},
        "jobLocation": {
            "address": {
                "addressLocality": "Abu Dhabi",
                "addressCountry": "UAE",
            }
        },
        "url": page_url,
    }
    page = (
        "<html><script type='application/ld+json'>"
        + json.dumps(json_ld)
        + "</script></html>"
    ).encode()
    client = FakeClient(
        {
            sitemap_url: [
                response(sitemap_url, sitemap_xml, "application/xml")
            ],
            robots_url: [FetchedResponse(robots_url, 404, {}, b"")],
            page_url: [response(page_url, page, "text/html")],
        }
    )
    result = collect_sitemap(
        spec(
            "sitemap",
            url=sitemap_url,
            job_url_patterns=["/careers/"],
        ),
        client,
    )
    assert len(result.jobs) == 1
    assert result.jobs[0].location == "Abu Dhabi, UAE"
    assert len(result.evidence) == 2


def test_runner_records_evidence_and_proof(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """
        sources:
          - id: target_greenhouse
            name: Target Greenhouse
            type: greenhouse
            company: Example EPC
            board_token: example
            enabled: true
        policy:
          respect_robots_txt: true
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )
    url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"

    def client_factory(_source: SourceSpec) -> FakeClient:
        return FakeClient(
            {
                url: [
                    response(
                        url,
                        {
                            "jobs": [
                                {
                                    "title": "Senior Piping Engineer",
                                    "absolute_url": "https://example.com/jobs/1",
                                    "location": {"name": "Mumbai"},
                                    "content": "<p>AVEVA E3D refinery layout</p>",
                                }
                            ]
                        },
                    )
                ]
            }
        )

    db_path = tmp_path / "jobs.db"
    evidence_dir = tmp_path / "evidence"
    summary = collect_sources(
        db_path,
        config_path,
        evidence_dir,
        client_factory=client_factory,
    )
    assert summary.status == "pass"
    assert summary.new_jobs == 1
    assert len(fetch_jobs(db_path)) == 1
    with connect(db_path) as connection:
        evidence = connection.execute(
            "SELECT file_path, sha256 FROM source_evidence"
        ).fetchone()
        row = connection.execute("SELECT status FROM runs").fetchone()
    assert evidence is not None
    evidence_path = Path(evidence["file_path"])
    assert evidence_path.exists()
    assert row[0] == "pass"


def test_runner_isolates_source_failure(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """
        sources:
          - id: good_greenhouse
            name: Good Greenhouse
            type: greenhouse
            company: Example EPC
            board_token: example
            enabled: true
          - id: bad_rss
            name: Bad RSS
            type: rss
            company: Example EPC
            url: https://bad.example/jobs.rss
            enabled: true
        policy:
          respect_robots_txt: true
          bypass_captcha: false
          use_rotating_proxies: false
          retain_source_evidence: true
        """,
        encoding="utf-8",
    )
    greenhouse_url = "https://boards-api.greenhouse.io/v1/boards/example/jobs"

    def client_factory(source: SourceSpec):
        if source.source_id == "bad_rss":
            class BrokenClient:
                def get(self, *args, **kwargs):
                    raise TimeoutError("simulated timeout")

            return BrokenClient()
        return FakeClient(
            {
                greenhouse_url: [
                    response(
                        greenhouse_url,
                        {
                            "jobs": [
                                {
                                    "title": "Piping Engineer",
                                    "absolute_url": "https://example.com/jobs/2",
                                    "content": "<p>PDMS role</p>",
                                }
                            ]
                        },
                    )
                ]
            }
        )

    db_path = tmp_path / "jobs.db"
    summary = collect_sources(
        db_path,
        config_path,
        tmp_path / "evidence",
        client_factory=client_factory,
    )
    assert summary.status == "partial"
    assert summary.sources_passed == 1
    assert summary.sources_failed == 1
    assert len(fetch_jobs(db_path)) == 1
    with connect(db_path) as connection:
        health = {
            row["source_id"]: row["status"]
            for row in connection.execute(
                "SELECT source_id, status FROM source_health"
            )
        }
    assert health == {"bad_rss": "fail", "good_greenhouse": "pass"}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/jobs",
        "http://localhost/jobs",
        "http://192.168.1.2/jobs",
        "ftp://example.com/jobs",
        "https://user:password@example.com/jobs",
    ],
)
def test_safe_http_rejects_local_or_credential_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_public_http_url(url)


def test_source_config_rejects_unsafe_policy(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        """
        sources: []
        policy:
          bypass_captcha: true
          use_rotating_proxies: false
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bypass_captcha"):
        load_source_config(path)
