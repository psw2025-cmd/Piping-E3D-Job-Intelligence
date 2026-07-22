# Delayed Bugbot Fixes for PR 2

This branch fixes delayed Cursor Bugbot findings raised after PR #2 was already merged.

## Fixes

- Corrects `upsert_job` create/update reporting when alias lookup misses but the allocated `job_key` already exists.
- Prevents fingerprint-alias matching from treating an existing empty `canonical_url` as compatible with every incoming URL, while preserving first-time URL enrichment for the same field-based key.
- Makes scoring configuration tolerate YAML `null` values for `weights`, `thresholds`, `terms`, and `recent_days` by falling back to defaults.

## Tests

- Regression test for URL enrichment followed by a distinct URL.
- Regression test for create/update reporting when identity aliases are missing.
- Regression test for null scoring YAML fallback.

## Safety

No live web collectors, CV files, secrets, recruiter contacts, databases, Excel exports, or personal application data are included.
