# Phase 1 Scope

## Goal

Establish a local-first, testable foundation for collecting and tracking relevant piping, E3D and EPC job opportunities without claiming unrestricted global coverage.

## Included in this branch

- SQLite schema for jobs, source health and run proof
- Deterministic duplicate detection
- Explainable profile-match scoring
- Manual UTF-8 vacancy-text import
- Public email extraction marked `PUBLIC_UNVERIFIED`
- Multi-sheet Excel export
- Database and workbook verification
- Windows install and daily-run scripts
- GitHub Actions lint, unit, end-to-end and CLI smoke tests
- Configuration for target roles, locations, scoring and collection policy

## Not yet implemented

- Production RSS and sitemap collection
- Greenhouse, Lever, SmartRecruiters or Workday connectors
- OCR for PDF/image imports
- Gmail/LinkedIn alert-email parsing
- Telegram/email notifications
- Web dashboard
- Cloud scheduling
- Automated CV parsing

## Acceptance gates

A phase is not accepted because a command merely exits successfully. Evidence must show:

1. Tests pass.
2. Re-importing the same vacancy does not create a second row.
3. Every job retains source fields.
4. Excel exists, is non-empty and contains all required sheets.
5. Missing title/company records are blocked.
6. No secrets, CVs, databases, exported spreadsheets or vacancy evidence are tracked by Git.
7. Failures are visible rather than silently ignored.

## Source policy

- Public, permitted sources only.
- Respect robots.txt and per-domain rate limits.
- No CAPTCHA bypass, proxy evasion or login-wall circumvention.
- Restricted platforms should be integrated through user-owned alerts or manual import rather than scraping.
