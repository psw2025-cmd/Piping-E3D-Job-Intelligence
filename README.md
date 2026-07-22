# Piping-E3D-Job-Intelligence

Local-first job intelligence, matching and tracking for piping, AVEVA E3D, PDMS, offshore, refinery, nuclear and EPC opportunities.

> **Current status:** Phase 3 employer registry. The production source file now contains verified official McDermott career searches for Chennai, Dubai and Doha. Public Greenhouse, Lever, SmartRecruiters, RSS/Atom, sitemap `JobPosting`, and constrained public employer HTML collectors are tested. OCR, Gmail ingestion, alerts and a user dashboard remain future work.

## Safety boundaries

- Use only public, permitted APIs, RSS feeds, sitemaps and career pages.
- Respect robots.txt, conservative rate limits and platform terms.
- Do not bypass CAPTCHAs, login walls or access controls.
- Do not use rotating proxies for blocked sources.
- Never commit CVs, application records, recruiter lists, databases, downloaded evidence or API keys.
- A detected email is marked `PUBLIC_UNVERIFIED`; the system never guesses that it is valid.
- SQLite is the source of truth. Excel is a review and tracking output.
- Raw public source responses are retained locally with SHA-256 proof and are ignored by Git.

## Implemented capabilities

- SQLite schemas and migrations for jobs, identity aliases, source health, evidence and run proof
- Stable duplicate handling across URL enrichment, changing descriptions and repeated imports
- Preservation of user-managed application status and recruiter data during automated refreshes
- Explainable YAML-controlled 0–100 role-fit scoring
- Evidence-preserving manual vacancy-text import
- Public Greenhouse Job Board collector
- Public Lever Postings collector with pagination
- Public SmartRecruiters Posting collector with optional detail fetches
- Public RSS and Atom collector
- Robots-aware XML sitemap traversal with schema.org `JobPosting` extraction
- Constrained public employer HTML collector with domain allowlists, pagination, role filters, required location markers and detail-page evidence
- Verified McDermott Chennai, Dubai and Doha source definitions
- Separate production, template and network-free CI source configurations
- Per-source timeout, rate-limit, response-size, redirect, item and allowed-domain controls
- Source failure isolation and partial-run reporting
- Multi-sheet Excel export with source-health, evidence and run-proof sheets
- Database, evidence-hash and Excel verification commands
- GitHub Actions tests, lint and network-free CLI proof flow
- Windows PowerShell installation and daily runner

## Quick start on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
job-intel --db data/database/jobs.db init-db
```

## Source files

- `config/sources.yaml` — production registry with verified active employer sources
- `config/sources.example.yaml` — disabled templates for new source types
- `config/sources.ci.yaml` — network-free GitHub Actions smoke configuration
- `config/employer_registry.yaml` — priority employer research and connector status

Validate the production registry before collecting:

```powershell
job-intel validate-sources --sources config/sources.yaml
```

Detailed source and safety instructions are in `docs/PUBLIC_SOURCES.md`.

## Collect, export and verify

```powershell
job-intel --db data/database/jobs.db collect `
  --sources config/sources.yaml `
  --evidence-dir data/raw `
  --output data/exports/Piping_E3D_Jobs.xlsx

job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

Collection exits with:

- `0` when all selected sources pass, or when no source is enabled;
- `1` for a partial run containing both passed and failed sources;
- `2` when all selected sources fail or Excel export fails.

## Manual vacancy import

Create a UTF-8 text file containing one vacancy, then import it:

```powershell
job-intel --db data/database/jobs.db import-text `
  --title "Senior E3D Piping Designer" `
  --company "Example EPC" `
  --location "Mumbai" `
  --file ".\private-input\vacancy.txt" `
  --source-url "https://example.com/jobs/123"
```

## Excel workbook

The generated workbook contains:

1. `New_Today`
2. `High_Priority`
3. `All_Active`
4. `Manual_Review`
5. `Applied`
6. `Follow_Up`
7. `Expired`
8. `Recruiter_Contacts`
9. `Source_Health`
10. `Source_Evidence`
11. `Run_Proof`

## Repository layout

```text
config/                     Target roles, locations, employer/source registries and scoring
src/job_intelligence/       Application and collector code
tests/                      Unit, migration, fixture and end-to-end tests
scripts/                    Windows installation and daily execution helpers
docs/                       Scope, security and source-operation guides
.github/workflows/          Automated validation
```

## Next controlled phases

1. Add verified connectors for Worley, Bechtel, Wood, KBR, Petrofac and other priority EPC employers.
2. Add review-required PDF and image OCR imports.
3. Add Gmail job-alert ingestion without scraping restricted platforms.
4. Add optional email or Telegram high-priority alerts.
5. Add application follow-up controls and a local dashboard.
6. Add Windows Task Scheduler setup and recovery verification.

No fixed coverage percentage is promised. The objective is verifiable coverage of selected public sources plus one tracker for manually discovered opportunities.
