# Piping-E3D-Job-Intelligence

Worldwide, local-first job intelligence, matching and tracking for piping, AVEVA E3D,
PDMS, SP3D, offshore, refinery, nuclear, energy and EPC opportunities.

> **Current implementation:** global role/location taxonomies, five enabled official
> employer sources, staged ATS sources, recruiter coverage, read-only Gmail alerts,
> private document/email/OCR imports, strict database identity, cross-source workbook
> deduplication and one verified daily Excel tracker.

## Safety boundaries

- Use only official public pages, permitted feeds, sitemaps and documented APIs.
- Respect robots.txt, conservative request limits and platform terms.
- Never bypass CAPTCHA, login walls or access controls.
- Never commit Gmail OAuth files, CVs, application records, databases or evidence.
- Gmail access is local, user-authorized and read-only.
- OCR and inferred vacancy fields always require review.
- SQLite remains the strict source of truth; Excel is the operating review output.

## Coverage

### Enabled official sources

- McDermott — Oracle HCM
- Wood — Oracle HCM
- Petrofac — SelectMinds public pages
- Bechtel — SuccessFactors public pages
- Worley — Eightfold public pages

### Fully configured staged sources

- KBR — Phenom
- AtkinsRealis — public rendered careers
- Fluor — Eightfold
- Technip Energies — public rendered careers
- Jacobs — public rendered careers

Staged sources remain disabled until their exact listing, pagination, detail, evidence and
failure-behavior proof passes.

### Recruiter and specialist coverage

The registry includes Airswift, NES Fircroft, Brunel, Petroplan, Orion, TRS Staffing,
MPH, Spencer Ogden, WRS, Matchtech, First Recruitment Group, Progressive Recruitment,
Energy Resourcing, Rigzone, Energy Jobline and Oil and Gas Job Search.

### Authorized alert coverage

Local Gmail OAuth imports user-authorized alerts from LinkedIn, Naukri, Indeed, Bayt,
GulfTalent, employers and recruiters without scraping authenticated pages.

## Quick start on Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,gmail]"
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

Install the daily Windows task:

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

## Gmail alerts

Save the downloaded Desktop OAuth client file locally as:

```text
private-input\gmail_credentials.json
```

Run Gmail import directly:

```powershell
.\.venv\Scripts\python.exe scripts\import_gmail_alerts.py `
  --db data/database/jobs.db `
  --credentials private-input/gmail_credentials.json `
  --token private-output/gmail/token.json `
  --evidence-dir private-output/evidence `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Public collection only

```powershell
job-intel --db data/database/jobs.db collect `
  --sources config/sources.yaml `
  --evidence-dir data/raw `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Private vacancy import

Place TXT, PDF, DOCX, EML or image vacancies under `private-input`, then run:

```powershell
.\scripts\run_private_import.ps1
```

## Worldwide workbook

The workbook includes:

- `Daily_Summary`
- `New_Today`
- `High_Priority`
- `Worldwide_Dedup`
- `All_Active`
- `All_Source_Rows`
- `Duplicate_Variants`
- `Manual_Review`
- `Applied`
- `Follow_Up`
- `Rejected`
- `Expired`
- `Recruiter_Contacts`
- `Country_Summary`
- `Company_Summary`
- `Employer_Coverage`
- `Recruiter_Coverage`
- `Source_Health`
- `Source_Evidence`
- `Private_Imports`
- `Run_Proof`

The deduplicated view keeps the strongest row while preserving all source variants and
application URLs. Database identity remains strict and non-destructive.

## Automatic GitHub collection

`daily-live-job-intelligence` runs every day at 09:00 Asia/Kolkata and uploads a verified
14-day artifact. GitHub automation remains public-source-only; Gmail tokens, private
vacancies, CVs and application records stay local.

## Verification

```powershell
job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

A failed or partial source remains visibly failed. Collection, evidence, workbook or
verification failure cannot be reported as a successful daily run.
