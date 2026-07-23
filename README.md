# Piping-E3D-Job-Intelligence

Local-first job intelligence, matching and tracking for piping, AVEVA E3D, PDMS, SP3D, offshore, refinery, nuclear and global EPC opportunities.

> **Current status:** verified public-source collection runs automatically in GitHub every day at 09:00 Asia/Kolkata. Private local ingestion supports text, PDF, Word, saved `.eml`, image OCR and user-authorized Gmail job alerts while keeping personal source files and evidence outside Git.

## Safety boundaries

- Use only public, permitted APIs, feeds, sitemaps and employer career pages.
- Respect robots.txt, conservative request limits and platform terms.
- Never bypass CAPTCHAs, login walls or access controls.
- Never commit CVs, application records, recruiter lists, databases, evidence or credentials.
- Public-source GitHub automation and private local imports remain separate.
- Gmail uses only the official read-only Gmail API scope.
- Detected contacts are stored as `PUBLIC_UNVERIFIED` or `ALERT_SUPPLIED`, never automatically verified.
- OCR and inferred vacancy fields always require review.
- SQLite is the source of truth. Excel is a review and tracking output.

## Implemented capabilities

- SQLite jobs, identity aliases, source health, evidence, private-import, Gmail-alert and run-proof tables
- Stable cross-source duplicate handling and transactional upserts
- Preservation of user-managed application and recruiter fields
- Config-driven worldwide role, software, sector and location normalization
- Explainable YAML-controlled 0–100 piping/E3D match scoring
- Verified McDermott and Wood Oracle career sources
- Verified Bechtel SAP SuccessFactors public listings
- Verified Petrofac SelectMinds new, hot and India listings
- Greenhouse, Lever, SmartRecruiters, RSS/Atom and sitemap collectors
- Constrained public employer HTML collector with domain, robots and response controls
- Daily GitHub Actions collection at 09:00 Asia/Kolkata with verified artifacts
- Text, PDF, Word, saved `.eml` and image-OCR private imports
- User-authorized Gmail API alert ingestion with multiple jobs per email
- SHA-256 evidence protection and private/Gmail evidence verification
- Multi-sheet Excel export including source, Gmail, private-import and daily-summary proof
- Windows private-folder and Gmail runners with Task Scheduler installers

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

## User-authorized Gmail alerts

After creating a Google Desktop OAuth client and saving the credential locally:

```powershell
.\.venv\Scripts\python.exe -m job_intelligence.cli gmail-auth `
  --credentials private-config\gmail_credentials.json `
  --token private-config\gmail_token.json

.\scripts\run_gmail_alerts.ps1
```

The Gmail importer reads matching alerts through the read-only scope, stores hashed `.eml` evidence locally, extracts multiple distinct job links, deduplicates against official sources and updates the same workbook.

See `docs/GMAIL_ALERTS.md`.

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
13. `Gmail_Alerts`
14. `Gmail_Alert_Jobs`
15. `Run_Proof`
16. `Daily_Summary`

## Repository layout

```text
config/                     Roles, locations, sources, employer registry and scoring
src/job_intelligence/       Application, collectors and private/Gmail imports
tests/                      Unit, migration, fixture and end-to-end tests
scripts/                    Windows and GitHub execution helpers
docs/                       Operation, safety and import guides
.github/workflows/          CI and scheduled collection
```

## Remaining controlled phases

1. Additional live-proven priority EPC employer connectors.
2. Workday, SuccessFactors, iCIMS, Taleo, SelectMinds, Teamtailor, Workable, Ashby and source-specific rendered-page connectors.
3. Recruiter and engineering-consultancy source expansion.
4. Optional email or Telegram high-priority notifications.
5. Production backup/restore, Windows restart recovery and 7–14-day soak proof.

No fixed coverage percentage is promised. The objective is broad, evidence-backed coverage of verified public sources and authorized alerts through one auditable tracker.
