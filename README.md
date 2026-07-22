# Piping-E3D-Job-Intelligence

Local-first job intelligence, matching and tracking for piping, AVEVA E3D, PDMS, offshore, refinery, nuclear and EPC opportunities.

> **Current status:** Phase 1 foundation. The repository contains tested storage, deterministic deduplication, explainable profile scoring, evidence-preserving manual text import, multi-sheet Excel export and verification. Public-source collectors, OCR and alerts remain planned work and are not claimed as complete.

## Safety boundaries

- Use public, permitted APIs, RSS feeds, sitemaps and career pages.
- Respect robots.txt, rate limits and platform terms.
- Do not bypass CAPTCHAs, login walls or access controls.
- Never commit CVs, application records, recruiter lists, databases, downloaded evidence or API keys.
- A detected email is marked `PUBLIC_UNVERIFIED`; the system never guesses that it is valid.
- SQLite is the source of truth. Excel is a review and tracking output.

## Included foundation

- SQLite schemas for jobs, source health and run proof
- Stable URL/field-based duplicate keys
- Explainable 0–100 role-fit scoring
- Manual vacancy-text import with source evidence fields
- Excel sheets for new, high-priority, active, applied, follow-up, expired and contact records
- Excel and database verification commands
- GitHub Actions tests and lint checks
- Windows PowerShell runner
- Configurable roles, locations, source policy and scoring rules

## Quick start on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
job-intel --db data/database/jobs.db init-db
```

Create a UTF-8 text file containing one vacancy, then import it:

```powershell
job-intel --db data/database/jobs.db import-text `
  --title "Senior E3D Piping Designer" `
  --company "Example EPC" `
  --location "Mumbai" `
  --file ".\private-input\vacancy.txt" `
  --source-url "https://example.com/jobs/123"
```

Export and verify:

```powershell
job-intel --db data/database/jobs.db export `
  --output data/exports/Piping_E3D_Jobs.xlsx

job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Repository layout

```text
config/                     Target roles, locations, policy and scoring
src/job_intelligence/       Application code
tests/                      Unit and end-to-end tests
scripts/                    Windows execution helpers
docs/                       Scope, security and roadmap
.github/workflows/          Automated validation
```

## Next controlled phases

1. Add public RSS and sitemap collectors with per-domain intervals and source-health proof.
2. Add public ATS connectors for Greenhouse, Lever and SmartRecruiters.
3. Add manual PDF/image import with review-required OCR.
4. Add Gmail job-alert ingestion without scraping restricted platforms.
5. Add optional alerts and application follow-up tracking.

No fixed coverage percentage is promised. The objective is verifiable coverage of selected public sources plus one tracker for manually discovered opportunities.
