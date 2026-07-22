# Post-merge Bugbot fix

This branch addresses delayed Cursor Bugbot findings raised after PR #2 was merged.

## Fixed

- `upsert_job` now reports update vs create correctly even when alias lookup misses but the allocated key already exists.
- Fingerprint alias matching no longer treats an existing empty canonical URL as compatible with any incoming apply URL. Exact field-key URL enrichment remains supported, while distinct later URLs can create separate records.
- Scoring configuration tolerates YAML `null` for `weights`, `thresholds`, `terms` and `recent_days`, falling back to defaults instead of crashing.

## Tests added

- Regression for URL enrichment followed by a distinct URL.
- Regression for update reporting when aliases are missing.
- Regression for null scoring YAML fallback.

## Safety

No live web collection, secrets, CV data, recruiter list, job database or export artifacts were added.
