# Piping-E3D-Job-Intelligence

Worldwide, local-first job intelligence, matching and tracking for piping, AVEVA E3D, PDMS, SP3D, offshore, refinery, nuclear, energy and EPC opportunities.

> **Current classification:** expanded global production pilot. The repository has verified public employer collection, worldwide profile/location taxonomies, user-authorized Gmail alerts, recruiter-source support, private document/email/OCR imports, strict database identity and one daily Excel tracker. It does not claim complete access to every worldwide vacancy.

## Safety boundaries

- Use only public, permitted APIs, feeds, sitemaps and employer/recruiter career pages.
- Respect robots.txt, conservative request limits and platform terms.
- Never bypass CAPTCHAs, login walls or access controls.
- Never commit CVs, application records, recruiter lists, databases, evidence or credentials.
- Public-source GitHub automation and private local imports remain separate.
- Gmail uses only the official read-only Gmail API scope.
- Detected contacts remain `PUBLIC_UNVERIFIED` or `ALERT_SUPPLIED` until reviewed.
- OCR and inferred vacancy fields always require review.
- SQLite is the strict source of truth; Excel is the operating review output.

## Enabled public-source coverage

### Official employers

- McDermott — Oracle HCM
- Wood — Oracle HCM
- KBR — Workday
- AtkinsRealis — Workday
- Bechtel — SAP SuccessFactors public listings
- Petrofac — SelectMinds new, hot and India listings

### Specialist engineering recruiters

- Airswift — official global vacancies
- NES Fircroft — official piping vacancy search
- Brunel — official global vacancies

Employer and recruiter sources are loaded from `config/sources.yaml` plus validated `config/sources.d/*.yaml` fragments. A fragment cannot weaken the safety policy in the main file.

### Staged sources

Worley, Fluor, Technip Energies and Jacobs are configured but disabled until their exact public listing, pagination, detail, evidence and failure-behaviour proof passes. Additional employers and agencies remain in the coverage registries with Gmail-alert fallback where direct public collection is unavailable or unstable.

LinkedIn, Naukri, Indeed, Glassdoor, Bayt, GulfTalent, Rigzone and similar authenticated portals enter through user-authorized Gmail alerts or saved `.eml` evidence rather than authenticated-page scraping.

## Implemented capabilities

- SQLite jobs, identity aliases, source health, evidence, private-import, Gmail-alert and run-proof tables
- Config-driven worldwide role, software, sector and location normalization
- Explainable YAML-controlled 0–100 piping/E3D match scoring
- Global profile filtering before public-source insertion
- Oracle HCM, Workday, Greenhouse, Lever and SmartRecruiters collectors
- Constrained public HTML, RSS/Atom and sitemap collectors
- Extensible employer, recruiter, ATS and source-fragment registries
- User-authorized Gmail API alert ingestion with multiple jobs per email
- Text, PDF, Word, saved `.eml` and image-OCR private imports
- SHA-256 evidence protection and verification
- Strict database identity plus non-destructive cross-source grouping in Excel
- Daily GitHub public-source artifacts and a combined Windows public/Gmail runner
- Windows Task Scheduler installers

## Quick start on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
job-intel --db data/database/jobs.db init-db
```

## Build the worldwide workbook

```powershell
.\scripts\run_worldwide_daily.ps1
```

Output:

```text
data\exports\Piping_E3D_Jobs.xlsx
```

Install the combined daily Windows task:

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

## Automatic public collection

The `daily-live-job-intelligence` workflow runs every day at 09:00 Asia/Kolkata and can also be started manually from GitHub Actions. It validates enabled official sources, collects jobs, retains evidence, exports Excel, verifies proof and uploads a 14-day portable artifact.

See `docs/DAILY_AUTOMATION.md`.

## User-authorized Gmail alerts

After creating a Google Desktop OAuth client and saving the credential locally:

```powershell
.\.venv\Scripts\python.exe -m job_intelligence.cli gmail-auth `
  --credentials private-config\gmail_credentials.json `
  --token private-config\gmail_token.json

.\scripts\run_gmail_alerts.ps1
```

The Gmail importer uses the read-only scope, stores hashed `.eml` evidence locally, extracts multiple distinct job links, deduplicates against official sources and updates the same workbook.

See `docs/GMAIL_ALERTS.md`.

## Private vacancy import

Place supported private vacancy files under `private-input`, then run:

```powershell
.\scripts\run_private_import.ps1
```

Supported formats include TXT, Markdown, CSV, PDF, DOCX, EML and common image formats with OCR explicitly enabled.

## Collect, export and verify

```powershell
job-intel --db data/database/jobs.db collect `
  --sources config/sources.yaml `
  --evidence-dir data/raw `
  --output data/exports/Piping_E3D_Jobs.xlsx

job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Worldwide Excel workbook

The generated workbook contains:

1. `New_Today`
2. `High_Priority`
3. `Worldwide_Dedup`
4. `All_Active`
5. `All_Source_Rows`
6. `Duplicate_Variants`
7. `Manual_Review`
8. `Applied`
9. `Follow_Up`
10. `Rejected`
11. `Expired`
12. `Recruiter_Contacts`
13. `Country_Summary`
14. `Company_Summary`
15. `Employer_Coverage`
16. `Recruiter_Coverage`
17. `Source_Health`
18. `Source_Evidence`
19. `Private_Imports`
20. `Gmail_Alerts`
21. `Gmail_Alert_Jobs`
22. `Run_Proof`
23. `Daily_Summary`

`Worldwide_Dedup` keeps the strongest representative row while preserving all source variants and application URLs in `All_Source_Rows` and `Duplicate_Variants`. Database identity remains strict and non-destructive.

## Production acceptance still required

The system may be labelled fully production-proven only after:

- 20–50 live-proven active sources across employers, recruiters and authorized alerts;
- backup and restore proof;
- Windows restart and scheduler recovery proof;
- repeated direct-link and duplicate audits;
- 7–14 consecutive days of fail-closed daily runs.

No fixed coverage percentage is promised. Internal, referral-only, private, login-only, short-lived and unpublished vacancies cannot be guaranteed.
