# Piping-E3D-Job-Intelligence

Worldwide, local-first job intelligence, matching and tracking for piping engineering, AVEVA E3D, PDMS, SP3D, offshore, refinery, nuclear and EPC opportunities.

> **Current status:** worldwide profile and workbook foundation is implemented. This Batch B2 branch expands verified official coverage to seven employers through nine public source definitions. The system still remains **limited verified employer coverage** until recruiter sources, additional EPC employers, authorized Gmail alerts and production reliability proof are completed.

## Safety boundaries

- Use only public, permitted APIs, feeds, sitemaps and employer career pages.
- Respect robots.txt, conservative request limits and platform terms.
- Never bypass CAPTCHAs, login walls or access controls.
- Never commit CVs, application records, recruiter lists, databases, evidence or credentials.
- Public-source GitHub automation and private local imports remain separate.
- Detected email addresses are stored only as `PUBLIC_UNVERIFIED` unless independently verified through an allowed source.
- OCR and inferred vacancy fields always require review.
- Missing salary, employer, location, closing date, experience or contact data remains blank.
- SQLite is the source of truth. Excel is a review and tracking output.

## Implemented capabilities

- SQLite jobs, identity aliases, source health, evidence, private-import and run-proof tables
- Additive worldwide job schema with normalized role, city, country, sector, software, employment type, closing date and duplicate status
- Worldwide role, keyword and location alias matrices
- Stable duplicate handling and transactional source upserts
- Preservation of user-managed application and recruiter fields
- Explainable YAML-controlled 0–100 piping/E3D match scoring
- Verified public sources for:
  - McDermott — Oracle HCM
  - Wood — Oracle HCM
  - Technip Energies — Oracle HCM
  - Fluor — public SAP SuccessFactors pages
  - Saipem — context-aware official job board
  - Bechtel — public SAP SuccessFactors pages
  - Petrofac — three public SelectMinds listings
- Greenhouse, Lever, SmartRecruiters, RSS/Atom and sitemap collector foundations
- Constrained public HTML and context-aware card collectors
- Safe HTTP validation, redirect validation, response limits, robots handling and evidence hashing
- Daily GitHub Actions collection at 09:00 Asia/Kolkata with verified artifacts
- Text, PDF, Word, `.eml` and image-OCR private imports
- SHA-256 duplicate-file protection and private evidence verification
- Multi-sheet worldwide Excel export with application, source, evidence and daily-summary proof
- Windows private-folder runner and Task Scheduler installer

## Quick start on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
job-intel --db data/database/jobs.db init-db
```

## Automatic public collection

The `daily-live-job-intelligence` workflow runs every day at 09:00 Asia/Kolkata and can also be started manually from GitHub Actions. It validates enabled official sources, collects jobs, retains evidence, exports Excel, verifies all proof and uploads a 14-day portable artifact.

See `docs/DAILY_AUTOMATION.md`.

## Private vacancy import

Place private vacancy files under `private-input`, then run:

```powershell
.\scripts\run_private_import.ps1
```

Supported input types:

- `.txt`, `.md`, `.csv`
- `.pdf`
- `.docx`
- `.eml`
- `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`, `.bmp` with OCR enabled

Detailed instructions are in `docs/PRIVATE_IMPORTS.md`.

## Manual text import

```powershell
job-intel --db data/database/jobs.db import-text `
  --title "Senior E3D Piping Designer" `
  --company "Example EPC" `
  --location "Mumbai" `
  --file ".\private-input\vacancy.txt" `
  --source-url "https://example.com/jobs/123"
```

## Collect, export and verify

```powershell
job-intel --db data/database/jobs.db collect `
  --sources config/sources.yaml `
  --evidence-dir data/raw `
  --output data/exports/Piping_E3D_Jobs.xlsx

job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Excel workbook

The generated workbook contains:

1. `New_Today`
2. `High_Priority`
3. `All_Active`
4. `Manual_Review`
5. `Applied`
6. `Follow_Up`
7. `Rejected`
8. `Expired`
9. `Recruiter_Contacts`
10. `Source_Health`
11. `Source_Evidence`
12. `Private_Imports`
13. `Run_Proof`
14. `Daily_Summary`

Core vacancy columns include exact title, normalized role, company, location, city, country, apply/source URL, published and closing dates, experience, software, sector, employment type, score, explanation, gaps, public contact confidence, duplicate status and application status.

## Repository layout

```text
config/                     Roles, locations, sources, employer registry and scoring
src/job_intelligence/       Application, collectors, normalization and private imports
tests/                      Unit, migration, fixture and end-to-end tests
scripts/                    Windows and GitHub execution helpers
docs/                       Operation, safety and import guides
.github/workflows/          Automated tests and scheduled collection
```

## Remaining controlled phases

1. Add additional official EPC employers and ATS families in small verified batches.
2. Add public recruiter and engineering-consultancy sources.
3. Add user-authorized Gmail ingestion for LinkedIn, Naukri, Indeed, GulfTalent, Bayt, recruiter and employer alerts.
4. Add optional email or Telegram high-priority notifications.
5. Complete 7–14 day production reliability, backup/restore and scheduler-recovery proof.
6. Install and prove local Windows Task Scheduler and OCR dependencies on the user's computer.

No fixed worldwide coverage percentage is promised. The objective is broad, evidence-backed public-source coverage plus one auditable tracker for authorized alerts and privately discovered opportunities.
