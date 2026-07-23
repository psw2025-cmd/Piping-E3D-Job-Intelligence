# India Public Recruitment Notices

Indian public-sector employers frequently publish recruitment through HTML tables, PDF advertisements, corrigenda, deadline extensions and separate application links instead of a commercial ATS.

The `public_notice` collector provides a bounded, read-only path for those sources.

## Supported evidence

- official recruitment listing page
- advertisement PDF
- HTML notice or detail page
- corrigendum
- addendum
- application deadline extension
- walk-in recruitment notice

All fetched listing and document responses are retained through the existing source-evidence SHA-256 proof system.

## Default exclusions

The collector excludes follow-up content that does not represent a new or corrected vacancy:

- results
- selected or shortlisted candidate lists
- admit cards
- call letters
- scorecards
- interview schedules
- medical-examination lists
- document-verification lists

A source can explicitly opt into follow-up notices, but the default remains false.

## Extracted fields

Each accepted notice can populate:

- exact notice or advertisement title
- employer
- country and location
- official notice/application URL
- listing and document source evidence
- published date when explicitly labelled
- closing date when explicitly labelled
- notice kind: advertisement, corrigendum, addendum, deadline extension or walk-in
- extracted PDF or HTML text for role and profile matching

No date, role, employer, salary or experience value is invented.

## Safety limits

Every source requires:

- an official public listing URL
- an exact domain allowlist containing the listing host
- explicit notice-link URL patterns
- bounded maximum notices
- bounded maximum PDF pages
- conservative request rate and response-size limits
- fail-closed robots.txt handling

The collector does not bypass login, CAPTCHA, JavaScript access controls or restricted application portals.

## Staged sources

`config/sources.india-notices.yaml` currently stages:

- NPCIL official opportunities
- IndianOil official latest job openings

Both remain `enabled: false` until their bounded live-contract workflow proves listing extraction, document evidence, role filtering and source health.

Validate configuration locally:

```powershell
job-intel validate-sources --sources config/sources.india-notices.yaml
```

A later activation PR must include the live proof result and update the worldwide company registry from staged to proven only after a successful scheduled run.
