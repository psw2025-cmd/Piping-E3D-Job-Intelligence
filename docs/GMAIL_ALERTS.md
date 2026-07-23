# Gmail Job Alert Import

Gmail import runs only on the user's local computer with the read-only scope
`https://www.googleapis.com/auth/gmail.readonly`. It does not mark messages read,
archive, delete, label or send mail.

## Setup

1. Enable the Gmail API in a Google Cloud project.
2. Create a Desktop application OAuth client.
3. Save the downloaded JSON as `private-input/gmail_credentials.json`.
4. Install support with `pip install -e ".[gmail]"`.

The first run opens a browser for consent. The local token is stored at
`private-output/gmail/token.json`. Both paths are ignored by Git.

## Run

```powershell
.\.venv\Scripts\python.exe scripts\import_gmail_alerts.py `
  --db data/database/jobs.db `
  --credentials private-input/gmail_credentials.json `
  --token private-output/gmail/token.json `
  --evidence-dir private-output/evidence `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

The default query covers recent LinkedIn, Naukri, Indeed, Bayt, GulfTalent and generic
job-alert messages. Exact message bytes are deduplicated by SHA-256 and uncertain fields
remain in manual review.
