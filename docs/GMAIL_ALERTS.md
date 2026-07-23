# User-Authorized Gmail Job Alerts

This feature reads job-alert emails from the user's own Gmail account through the official Gmail API with the read-only scope.

It is intended for portals where direct collection is restricted or unreliable, including LinkedIn, Naukri, Indeed, Glassdoor, Foundit, GulfTalent, Bayt, Naukrigulf, Rigzone, Energy Jobline and recruiter alerts.

## Privacy boundary

- Gmail access is read-only.
- OAuth credentials and tokens stay under `private-config` on the Windows computer.
- Raw email evidence stays under `private-output/gmail-evidence`.
- Email content, OAuth files, databases and workbooks are ignored by Git.
- The system does not delete, label, archive, forward or send email.
- It does not submit job applications.

## Google setup

Google requires a Google Cloud project, Gmail API enablement and a Desktop app OAuth client.

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable **Gmail API**.
4. Configure the Google Auth consent screen for your account.
5. Create an OAuth client with application type **Desktop app**.
6. Download the JSON credential file.
7. Create this local folder in the repository:

```powershell
New-Item -ItemType Directory -Force private-config
```

8. Save the downloaded file as:

```text
private-config\gmail_credentials.json
```

Do not upload or commit this file.

## First authorization

From PowerShell in the repository:

```powershell
.\.venv\Scripts\python.exe -m job_intelligence.cli gmail-auth `
  --credentials private-config\gmail_credentials.json `
  --token private-config\gmail_token.json
```

A Google browser window opens. Select the Gmail account and grant read-only access. The refresh token is stored locally in `private-config\gmail_token.json`.

## Import alerts now

```powershell
.\scripts\run_gmail_alerts.ps1
```

The default Gmail query scans the last 30 days for messages containing job, vacancy, hiring or career terms. A custom query can be supplied:

```powershell
.\scripts\run_gmail_alerts.ps1 `
  -Query 'newer_than:14d (from:linkedin.com OR from:naukri.com OR from:indeed.com)'
```

## Daily Windows task

```powershell
.\scripts\install_gmail_alert_task.ps1 -DailyTime "09:15"
```

The task runs while the Windows user is logged in. The GitHub public-source workflow remains separate and runs at 09:00 IST.

## What is extracted

For every matching email, the importer:

- stores the raw `.eml` evidence with a SHA-256 hash;
- tracks the Gmail message ID so the same email is not processed repeatedly;
- extracts multiple job links from HTML and plain-text alerts;
- rejects unsubscribe, settings, profile, login and privacy links;
- creates one job record per distinct job URL;
- maps job title, company and location when explicitly present;
- marks missing employer information as `Unknown employer` and `review_required`;
- marks contact addresses found in the alert as `ALERT_SUPPLIED`, not verified;
- deduplicates against official employer and recruiter sources through canonical URLs and identity aliases.

## Workbook proof

The daily workbook includes:

- `Gmail_Alerts` — one row per processed Gmail message;
- `Gmail_Alert_Jobs` — message-to-job evidence links;
- `Manual_Review` — uncertain employer/title/contact records;
- `All_Active`, `New_Today`, `High_Priority` and application-tracking sheets;
- `Daily_Summary` — Gmail and source totals.

## Verification

```powershell
.\.venv\Scripts\python.exe -m job_intelligence.cli `
  --db data\database\jobs.db `
  verify `
  --output data\exports\Piping_E3D_Jobs.xlsx
```

Verification checks Gmail evidence existence and hashes, staged imports and orphan message-to-job links.

## Limitations

- Gmail authorization must be completed by the account owner on the Windows computer.
- Portal alert formats can change; uncertain results remain in `Manual_Review`.
- A job-alert email does not prove the vacancy is still open. The direct link and official employer page should be checked before applying.
- The importer never invents salary, employer, location, experience or recruiter verification.
