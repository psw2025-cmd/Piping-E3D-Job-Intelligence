# Gmail Job Alert Import

## Privacy model

Gmail import runs only on the user's local Windows computer. GitHub Actions never
receives Gmail credentials, OAuth tokens, messages, CVs or application records.
The requested OAuth scope is read-only:

```text
https://www.googleapis.com/auth/gmail.readonly
```

The importer does not mark messages read, archive them, delete them, apply labels or
send mail. Each matching message is downloaded as RFC822 evidence, hashed, deduplicated
and imported through the existing private-evidence pipeline.

## Google Cloud setup

1. Create or select a Google Cloud project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create an OAuth client ID for a Desktop application.
5. Download the client JSON.
6. Save it locally as:

```text
private-input\gmail_credentials.json
```

The first import opens a browser for user consent. The local refresh token is stored at:

```text
private-output\gmail\token.json
```

Both locations are ignored by Git.

Official setup reference:

```text
https://developers.google.com/workspace/gmail/api/quickstart/python
```

## Install Gmail support

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[gmail]"
```

## Run Gmail import only

```powershell
job-intel --db data/database/jobs.db import-gmail `
  --credentials private-input/gmail_credentials.json `
  --token private-output/gmail/token.json `
  --max-results 200 `
  --evidence-dir private-output/evidence `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

## Default alert coverage

The default read-only query searches recent messages that resemble alerts from:

- LinkedIn
- Naukri
- Indeed
- Bayt
- GulfTalent
- recruiter and employer alerts with job-alert subjects

Override the query without changing code:

```powershell
job-intel --db data/database/jobs.db import-gmail `
  --query 'newer_than:14d (subject:(piping) OR subject:(E3D) OR subject:(PDMS))'
```

## Daily combined operation

```powershell
.\scripts\run_worldwide_daily.ps1
```

If the credentials file does not exist, the worldwide runner skips Gmail and still
completes the verified official-source workbook. Once credentials exist, Gmail alerts
are included before the final workbook export.

## Failure handling

- One malformed email does not discard valid imports.
- Exact email bytes are deduplicated by SHA-256.
- Inferred title or company fields are routed to manual review.
- Original Gmail message IDs are not stored in Git.
- OAuth credentials and tokens are never committed.
