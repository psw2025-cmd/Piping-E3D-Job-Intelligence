# Daily Automation

The repository runs `daily-live-job-intelligence` every day at **09:00 Asia/Kolkata**. It can also be started manually from the GitHub **Actions** tab with **Run workflow**.

## What the run does

1. Installs the committed Python package in a clean GitHub runner.
2. Validates `config/sources.yaml` and its public-source safety policy.
3. Collects only enabled official sources.
4. Stores raw public evidence locally and records SHA-256 hashes in SQLite.
5. Scores and deduplicates filtered piping/E3D jobs.
6. Exports `Piping_E3D_Jobs.xlsx`.
7. Verifies SQLite identity integrity, evidence files and hashes, and workbook structure.
8. Publishes a readable run summary.
9. Uploads a 14-day artifact named `piping-e3d-jobs-<run-id>-<attempt>`.

## Artifact contents

The GitHub artifact contains:

- `SUMMARY.md`
- `status.json`
- `run.log`
- `Piping_E3D_Daily_Bundle.zip`

Extract `Piping_E3D_Daily_Bundle.zip` to obtain the portable `output/daily` folder containing:

- the verified Excel tracker;
- the SQLite ledger and proof tables;
- retained public source evidence;
- the same summary, status, and log files.

The bundle preserves the relative evidence paths stored in SQLite.

## Status behavior

- **PASS:** all enabled sources passed and database, evidence, and workbook verification passed.
- **FAIL:** any source failed or returned a partial run, export failed, evidence verification failed, or workbook verification failed.

Artifacts are uploaded even for failed runs so the failure can be inspected. A failed or partial collection still leaves the GitHub workflow visibly failed; it cannot be mistaken for a verified successful day.

## Safety boundaries

- Repository permission is read-only during the permanent daily workflow.
- No credentials, cookies, CV files, recruiter lists, application data, databases, workbooks, or raw evidence are committed to Git.
- Concurrent daily runs do not overlap.
- `public_html` example sources remain disabled until a source-specific live proof passes.
- Production currently uses only the enabled official sources in `config/sources.yaml`.
