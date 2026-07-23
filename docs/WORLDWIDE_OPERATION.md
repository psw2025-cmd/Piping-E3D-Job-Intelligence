# Worldwide Operation

The system combines verified official sources, staged ATS sources, authorized Gmail
alerts, private files and recruiter coverage into one daily workbook.

## One-command run

```powershell
.\scripts\run_worldwide_daily.ps1
```

The runner collects enabled official sources, imports Gmail alerts when credentials
exist, exports the worldwide workbook and verifies database, evidence and output.

## Source states

- `active_supported`: enabled for daily collection.
- `staged_source`: configured but disabled until live proof passes.
- `connector_planned`: official portal recorded; source-specific work remains.
- `email_alert_ingestion_ready`: supported through local read-only Gmail OAuth.

A staged source must prove public accessibility, bounded pagination, correct detail
parsing, profile filtering, evidence hashing and visible failure behavior before enablement.

## Duplicate handling

SQLite keeps strict identity aliases and canonical URLs. Excel adds a non-destructive
cross-source group based on normalized role, company, location and posting evidence.
`Worldwide_Dedup` keeps the strongest row and `Duplicate_Variants` keeps every source
row and application URL.

GitHub Actions processes public sources only. Gmail credentials, CVs, private evidence
and application records remain local.
