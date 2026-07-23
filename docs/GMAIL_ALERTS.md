# Gmail Job Alert Import

Gmail import runs only on the user's local computer with the read-only scope:

```text
https://www.googleapis.com/auth/gmail.readonly
```

It does not mark messages read, archive, delete, label or send mail. Matching messages
are downloaded as RFC822 evidence, hashed and imported through the existing private
import ledger.

## Setup

1. Create or select a Google Cloud project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create a Desktop application OAuth client.
5. Save the downloaded JSON as `private-input/gmail_credentials.json`.
6. Install support with `pip install -e ".[gmail]"`.

The first run opens a browser for consent. The local token is stored at
`private-output/gmail/token.json`. Both locations are ignored by Git.

## Run

```powershell
.\.venv\Scripts\python.exe scripts\import_gmail_alerts.py `
  --db data/database/jobs.db `
  --credentials private-input/gmail_credentials.json `
  --token private-output/gmail/token.json `
  --max-results 200 `
  --evidence-dir private-output/evidence `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

The default query covers recent LinkedIn, Naukri, Indeed, Bayt, GulfTalent and generic
job-alert messages. Override `--query` for employer or recruiter alerts.

One malformed message does not discard valid imports. Exact message bytes are
deduplicated by SHA-256, and inferred fields remain in manual review.
