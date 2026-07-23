# Piping-E3D-Job-Intelligence

Local-first job intelligence, matching and tracking for piping, AVEVA E3D, PDMS, offshore, refinery, nuclear and EPC opportunities.

> **Current status:** verified public-source collection runs automatically in GitHub every day at 09:00 Asia/Kolkata. The private import layer supports text, PDF, Word, `.eml` email and review-required image OCR while keeping personal source files and evidence outside Git.

## Safety boundaries

- Use only public, permitted APIs, feeds, sitemaps and employer career pages.
- Respect robots.txt, conservative request limits and platform terms.
- Never bypass CAPTCHAs, login walls or access controls.
- Never commit CVs, application records, recruiter lists, databases, evidence or credentials.
- Public-source GitHub automation and private local imports remain separate.
- Detected email addresses are stored only as `PUBLIC_UNVERIFIED`.
- OCR and inferred vacancy fields always require review.
- SQLite is the source of truth. Excel is a review and tracking output.

## Implemented capabilities

- SQLite jobs, identity aliases, source health, evidence, private-import and run-proof tables
- Stable duplicate handling and transactional source upserts
- Preservation of user-managed application and recruiter fields
- Explainable YAML-controlled 0–100 piping/E3D match scoring
- Verified McDermott and Wood Oracle career sources
- Greenhouse, Lever, SmartRecruiters, RSS/Atom and sitemap collectors
- Disabled-by-default constrained public employer HTML collector
- Safe HTTP validation, redirects, response limits, robots handling and evidence hashing
- Daily GitHub Actions collection at 09:00 Asia/Kolkata with verified artifacts
- Text, PDF, Word, `.eml` and image-OCR private imports
- SHA-256 duplicate-file protection and private evidence verification
- Multi-sheet Excel export including source and private-import proof
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
7. `Expired`
8. `Recruiter_Contacts`
9. `Source_Health`
10. `Source_Evidence`
11. `Private_Imports`
12. `Run_Proof`

## Repository layout

```text
config/                     Roles, locations, sources, employer registry and scoring
src/job_intelligence/       Application, collectors and private imports
tests/                      Unit, migration, fixture and end-to-end tests
scripts/                    Windows and GitHub execution helpers
docs/                       Operation, safety and import guides
.github/workflows/          CI and scheduled collection
```

## Next controlled phases

1. Gmail job-alert ingestion through user-authorized Google access.
2. Optional email or Telegram high-priority notifications.
3. Application follow-up controls and local dashboard.
4. Additional live-proven priority EPC employer connectors.
5. Local Task Scheduler installation and recovery proof on the user's Windows computer.

No fixed coverage percentage is promised. The objective is verifiable coverage of selected official sources plus one auditable tracker for privately discovered opportunities.
