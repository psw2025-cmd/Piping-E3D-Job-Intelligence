# Private Import Recovery Patch 0.4.1

This corrective patch addresses delayed review findings reported after the private import pipeline merged.

## Corrected behavior

- Re-importing a file repairs missing or corrupted stored evidence instead of returning a false duplicate.
- Supported symbolic-link files discovered during folder import are recorded as failed inputs rather than silently skipped.
- A failed staged-ledger insert removes any newly copied evidence that is not referenced by a ledger row.
- Symbolic-link source folders are rejected before path resolution.

## Verification gate

The patch must pass installation, Ruff, the complete test suite, public-source configuration validation, private-import CLI proof, Excel/database/evidence verification, cloud daily runner proof and delayed automated review before merge.
