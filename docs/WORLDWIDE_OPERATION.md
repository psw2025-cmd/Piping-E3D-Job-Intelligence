# Worldwide Operation

The system combines verified official public sources, configured staged ATS sources,
user-authorized Gmail alerts, private files and recruiter coverage into one daily workbook.

## One-command Windows run

```powershell
.\scripts\run_worldwide_daily.ps1
```

The runner performs these steps:

1. Collect every enabled official public source.
2. Import Gmail alerts when the local OAuth credential exists.
3. Export one worldwide deduplicated workbook.
4. Verify the database, public/private/Gmail evidence and workbook contract.

The GitHub daily workflow is strict: a partial source run, failed source, cancelled scan,
missing evidence, invalid workbook or missing coverage proof is a failed run. The
--allow-partial escape hatch is intentionally not available to the cloud runner.
The global 48-hour workflow runs official-source discovery and collection as separate
jobs, transfers the verified runtime registry as an artifact, then applies the same
zero-failure gate. This prevents a long discovery phase from consuming the collection
job timeout and ensures discovered official company sources are actually collected.

Install the recurring local task:

```powershell
.\scripts\install_worldwide_daily_task.ps1
```

## Source states

- `active_supported`: enabled for daily public collection.
- `staged_source`: fully configured but disabled until exact live proof passes.
- `official_site_verified`: official career entry recorded; connector research remains.
- `connector_planned`: public portal recorded; source-specific configuration remains.
- `email_alert_ingestion_ready`: covered through local read-only Gmail OAuth.

A staged source must prove:

1. Public listing access without authentication bypass.
2. Bounded pagination that terminates and does not repeat pages.
3. Correct title, company, location and official application URL extraction.
4. Global role-profile filtering that rejects unrelated jobs.
5. Evidence retention with SHA-256 verification.
6. Visible failed or partial status when any source fails.
7. Full Ruff, pytest, CLI smoke, workbook and offline daily-bundle gates.

## ATS strategy

The connector registry covers Oracle HCM, Workday, Greenhouse, Lever, SmartRecruiters,
SuccessFactors, SelectMinds, Eightfold, iCIMS, Taleo, Teamtailor, Workable and Ashby.

The safe fallback order is:

1. Documented public API.
2. Official RSS, XML or sitemap.
3. Bounded official public HTML.
4. User-authorized Gmail alerts.
5. Private PDF, Word, EML, text or image import.

## Duplicate handling

SQLite keeps strict identity aliases, canonical URLs and source evidence. Excel adds a
second non-destructive grouping layer based on normalized role, company, location and
posting evidence.

- `Worldwide_Dedup` keeps the strongest representative row.
- `All_Source_Rows` retains every active database row.
- `Duplicate_Variants` retains every row from groups found through multiple sources.
- `all_apply_urls` preserves all known application links.

This avoids losing distinct requisitions while reducing repeated official, recruiter and
email-alert representations in the operating view.

## GitHub versus local operation

GitHub Actions processes only public sources and uploads a verified artifact. Gmail OAuth
credentials, CVs, private vacancy files, application status and local recruiter records
remain on the user's Windows computer.
## Current strict source contract

The repository-managed baseline currently enables nine official source entries across McDermott, Wood, KBR, AtkinsRealis, Bechtel, three Petrofac feeds, and NPCIL. Workday sources use the provider-compatible page size of 20; if a provider repeats a page, the collector stops only that search term and records the warning so other terms and sources continue. The all-source contract verifies every enabled source's health and retained evidence. Staged sources are not silently enabled until they have live official-source proof.
