# Worldwide Operation

The system combines official public sources, staged ATS sources, authorized Gmail
alerts, private files and recruiter coverage into one daily workbook.

## One-command run

```powershell
.\scripts\run_worldwide_daily.ps1
```

The runner collects enabled official sources, imports Gmail alerts when local OAuth
credentials exist, exports the worldwide workbook and verifies database/evidence/output.

## Source states

- `active_supported`: enabled for daily collection.
- `staged_source`: fully configured but disabled until live proof passes.
- `connector_planned`: official portal recorded; source-specific configuration remains.
- `email_alert_ingestion_ready`: supported through local read-only Gmail OAuth.

A staged source must prove public accessibility, bounded pagination, correct job detail
parsing, profile filtering, evidence hashing and visible failure behavior before enabling.

## Duplicate handling

SQLite keeps strict identity aliases and canonical URLs. Excel adds a non-destructive
cross-source group based on normalized role, company, location and posting evidence.
`Worldwide_Dedup` keeps the strongest representative row. `Duplicate_Variants` keeps
every source row and URL.

## GitHub versus local operation

GitHub Actions processes only public sources and uploads a verified artifact. Gmail
credentials, CVs, private vacancy evidence, application status and recruiter records
remain on the local computer.
