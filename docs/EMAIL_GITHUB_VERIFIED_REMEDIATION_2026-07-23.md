# Gmail and GitHub Verified Remediation Audit

**Repository:** `psw2025-cmd/Piping-E3D-Job-Intelligence`  
**Audit date:** 2026-07-23  
**Audit branch:** `agent/verified-email-remediation`  
**Authoritative baseline after PR #43:** `7e86c913b62001621511b019ea465a7c2519d05d`

## 1. Purpose

This document replaces the unverified Gemini-generated task brief with a repository-grounded audit.

The instruction was not to treat every failure email or AI summary as a current defect. Every claim was checked against:

1. the matching Gmail notifications;
2. current GitHub pull-request state;
3. current `main` source code;
4. Bugbot review threads;
5. regression tests already present on `main`;
6. exact GitHub Actions runs; and
7. current branch differences.

No issue was patched merely because it appeared in an email. Only defects still reproducible or visible in current code were included in remediation.

## 2. Mailbox scope and method

Gmail was searched with the exact subject filter:

```text
subject:"psw2025-cmd/Piping-E3D-Job-Intelligence"
```

The search returned **269 matching messages across three result pages**. The full body of every matching message was read.

The messages were then deduplicated by:

- pull-request number;
- workflow name;
- commit SHA;
- Bugbot review thread;
- source file and line-level finding; and
- repeated push-run versus pull-request-run notifications.

Most messages were not independent defects. They were repeated notifications for intermediate commits, duplicated workflow triggers, WIP correction commits, or already superseded pull requests.

## 3. Executive conclusion

The Gemini summary was not reliable as a current execution plan. It mixed four different categories:

1. **real current defects**;
2. **historical defects already fixed by later PRs**;
3. **temporary branch/workflow failures that were expected during development**; and
4. **unsupported conclusions**, such as all CI being broken or Cursor quota blocking GitHub Actions.

### Verified current defects

The audit confirmed these current defects:

1. PR #43 live proof called the old public-notice collector while production used the adaptive collector.
2. Oracle location terms used substring matching, allowing `india` to match `Indiana` and `oman` to match `Romania`.
3. Public HTML redirects could escape the configured domain allowlist after the initial URL check.
4. A prebuilt/custom scoring profile could still auto-load a different environment taxonomy.
5. Several configured target roles normalized to a broader or blank role because canonical aliases were missing.
6. Rescored reimports could retain obsolete derived profile fields when the newly computed value became blank.

### Verified external notification

Cursor Bugbot usage/spend limits were genuinely reached on several PRs. This affects optional Cursor review and autofix only. It does **not** block:

- GitHub Actions;
- direct GitHub repository changes;
- pull-request creation;
- GitHub review-thread inspection; or
- merging after independent proof.

There is no safe or legitimate repository-side quota bypass. Only the user or Cursor team administrator can change Cursor spending or usage settings.

## 4. Claim-by-claim adjudication

| Claim from email/Gemini brief | Current verdict | Evidence-based conclusion |
|---|---|---|
| Cursor/Bugbot quota is exhausted | **True, external** | Cursor review/autofix may not run. GitHub CI and repository work continue independently. No bypass was implemented. |
| PR #42 and PR #43 are stalled indefinitely | **False/stale** | PR #42 was already merged. PR #43 was corrected, passed three exact-head gates, and was merged during this audit. |
| PR #12 is blocked by duplicate private imports | **False/stale** | PR #12 was merged and its post-merge findings were corrected by PR #13. Current tests cover missing/corrupt evidence, folder symlinks and orphan cleanup. |
| Duplicate database exports remain unresolved | **Unsupported** | No current reproducible defect or authoritative open review finding supports this broad claim. |
| Private evidence recovery remains broken | **False/stale** | Current post-merge tests verify evidence repair and cleanup behavior. |
| All agents and CI are failing from resource exhaustion | **Unsupported** | Recent exact-head GitHub Actions passed. Cursor quota messages were incorrectly generalized to GitHub infrastructure. |
| Employer-registry workflows report “No jobs were run” | **Historical branch event** | These notifications came from temporary integration workflow states on old PR #9 branch commits. They are not a current `main` production failure. |
| Removing the temporary daily proof workflow broke dependencies | **False** | Removal was intentional after proof work. Permanent daily and test workflows remained and later passed. |
| Daily verification currently fails for Airswift, NES and Brunel | **Unsupported as current state** | Historical failures exist, but no current evidence proves all recruiter validation is broken. Their open feature PRs remain separate decisions. |
| Job counts are generally inaccurate | **Unsupported as stated** | No precise current counting defect was identified from the emails. Identity and URL-less dedup defects were fixed by PR #3 and later integrity tests. |
| Role normalization is flawed | **True** | Four PR #22 review findings remained applicable to current `main`; they are addressed on this branch. |
| Oracle location filter has false positives | **True** | Current code used substring matching. A phrase-boundary fix and regression test were added. |
| Public HTML redirects bypass domain allowlist | **True** | Current collector checked requested links but not every final redirected response. HTTP-level and collector-level guards were added. |
| Lever/SmartRecruiters can loop forever | **Historical, fixed** | Current `tests/test_collector_limits.py` proves repeated-page hard stops. |
| Sitemap `max_items` can overrun job count | **Historical, fixed** | Corrective PR and current cap regression tests exist. |
| URL-less imports create duplicates or unrelated URLs merge | **Historical, fixed** | Current `tests/test_database_integrity.py` covers these cases. |
| Symlink validation bypass remains in private import | **Historical, fixed** | Post-merge private-import tests prove symlink reporting and containment behavior. |

## 5. Unique issue ledger extracted from all matching mail

### PR #2 and PR #3 — identity and deduplication

Historical findings included:

- URL-less records could be mishandled;
- empty canonical URLs could merge unrelated records;
- create/update reporting could be incorrect; and
- identity transitions needed stable aliases.

**Current status:** fixed by the corrective PR chain and locked by `tests/test_database_integrity.py`.

### PR #4 and PR #5 — collector bounds and atomicity

Historical findings included:

- sitemap cap semantics;
- pagination termination;
- evidence/upsert consistency; and
- verification ordering after collection failures.

**Current status:** superseded by corrective PR #5 and current collector-limit/integrity tests.

### PR #6 — Oracle location substring matching

Bugbot correctly reported that plain substring matching could admit unrelated locations such as Indiana for `india` or Romania for `oman`.

**Current status before this audit:** still present as a generic latent defect, even though current production Oracle entries use empty location-term lists.

**Remediation:** phrase-boundary matching added in commit `ebf49227ca0ca3bff1266febe61bbdb8e237685d`.

### PR #8 — missing `public_html` registration

The original PR omitted production dispatch for the new source type.

**Current status:** historical and fixed before current `main`.

### PR #9 — redirect allowlist bypass

Bugbot reported that requested listing/detail URLs were checked, but the final URL after redirects could be on another public host and still be parsed and stored as evidence.

**Current status before this audit:** still applicable.

**Remediation:** 

- `SafeHttpClient` now accepts source domain boundaries and validates every redirect target;
- the production collection runner supplies each source's allowed domains;
- the live-notice proof runner supplies the same boundary; and
- a collector-level wrapper rejects disallowed final URLs even with injected/custom clients.

Commits:

- `5e08cb1af8da3892e5561572359593efbd33c080`
- `58e35d2d165bc58079f5391505492839482c0601`
- `de79f32063c25802304c22b0da07c55a61420743`
- `138e083b0652908e657f7d38d9d85695e7393897`
- `1cffe8c5226529201763ad619086908db4d279e9`

### PR #10 and PR #11 — daily proof truth

PR #10 emails reported:

- partial/failing collection could still show `verified: true`; and
- `status.json`/summary could be written before bundle creation completed.

**Current status:** historical. PR #11 and later workflow changes corrected these truth-ordering issues. Current cloud daily bundle tests run successfully.

The email saying a temporary proof workflow was removed is not evidence that the permanent daily pipeline was broken.

### PR #12 and PR #13 — private import pipeline

Email findings covered:

- symlink containment;
- duplicate evidence integrity;
- stale staged rows;
- folder symlink reporting;
- rollback consistency; and
- orphan evidence cleanup.

**Current status:** corrected by PR #13 and locked by `tests/test_private_import_postmerge.py` and integrity tests.

The Gemini phrase “duplicate database exports” was not supported by a current code-level finding.

### PR #22 — scoring and role normalization

Four review findings remained applicable:

1. A supplied `ScoringProfile` could be mixed with taxonomy auto-resolved from another directory.
2. `Piping Design Checker` could normalize as `Piping Design Engineer`.
3. Several configured target titles lacked explicit aliases and could normalize blank or to the wrong family.
4. Reimports could retain stale normalized role, location, software, sector, employment type or closing date.

**Remediation:**

- explicit custom profiles remain isolated unless a matching `config_dir` is deliberately supplied;
- every configured target role now has a canonical role-family entry;
- checker, layout, site, field, construction, CAD, E3D and PDMS roles are separated; and
- rescored records replace computed profile fields, including clearing obsolete values.

Commits:

- `b412c16757fd9f4e33d506dd14dd21a41a9cc11e`
- `8bf07fc8cb6aa424c166bb12e735530bd5035215`
- `d2cb9bb45e65c55018b7d8c7548f60d2f24ccebc`

### PR #38 through PR #42 — registry and public-notice expansion

These PRs generated many repeated Actions and Bugbot notifications. Their existence does not mean the final merged state failed.

Verified outcomes:

- worldwide/India coverage registry merged;
- configured coverage and proven operational coverage are separate;
- NPCIL live proof and production activation merged;
- IndianOil remains on Gmail/private-import fallback because direct automation encountered a JavaScript/Sucuri challenge;
- EIL remains on Gmail/private-import fallback because robots rules prohibit the crawler; and
- no CAPTCHA, robots or access-control bypass was implemented.

### PR #43 — GAIL proof mismatch

The branch's production dispatcher used `collect_public_notice_adaptive`, while the live-proof script imported and called the original collector directly. The workflow also did not watch proof-script changes.

**Remediation completed and merged:**

- proof uses the production `COLLECTORS` mapping;
- workflow paths and Ruff checks include the proof script;
- a regression test locks adaptive production dispatch;
- exact-head full CI passed;
- live GAIL proof passed;
- live NPCIL regression passed; and
- there were no unresolved review threads.

PR #43 was squash-merged as:

```text
7e86c913b62001621511b019ea465a7c2519d05d
```

GAIL remains staged until a separate production-activation decision. EIL remains on safe authorized fallback.

## 6. Changes on `agent/verified-email-remediation`

The branch contains only fixes justified by current code and the verified emails.

| Area | Change |
|---|---|
| Oracle filters | Phrase-boundary term matching prevents location substring false positives. |
| Scoring profiles | Explicit profiles no longer silently mix with another auto-resolved taxonomy. |
| Role taxonomy | Every configured target title maps to an explicit canonical role. |
| Reimport integrity | Rescored jobs can clear obsolete derived fields. |
| HTTP redirects | Every redirect target is checked against source allowed domains. |
| Public HTML defense | Final listing/detail response URLs are checked before parsing or evidence storage. |
| Proof parity | Live notice proof uses the same production collector mapping and source-domain boundary. |
| Regression suite | Added focused tests for all verified current findings. |

The consolidated regression suite is:

```text
tests/test_verified_email_remediation.py
```

## 7. Items intentionally not changed

The following were not changed because the audit did not prove a current defect or because they require a separate product decision:

- Cursor billing or spend limits;
- attempts to bypass Cursor quota;
- EIL robots restrictions;
- IndianOil JavaScript/Sucuri restrictions;
- CAPTCHA or login automation;
- automatic merging of open recruiter/source PRs #31, #34 and #36;
- the separate live-worldwide audit draft PR #33;
- generic “job count” rewrites without a reproducible failing case; and
- reopening private-import defects already covered by passing regression tests.

## 8. Merge gate for this remediation

This branch must not merge until the exact latest head passes:

1. Ruff;
2. complete pytest;
3. CLI smoke tests;
4. cloud daily workbook and coverage bundle proof;
5. live Oracle contract proof;
6. live Workday regression where triggered;
7. live recruiter contracts where triggered;
8. live NPCIL and GAIL notice regression where triggered;
9. review-thread inspection; and
10. branch-divergence verification.

No test or workflow should be weakened to obtain a green result. A failure must be corrected at its exact cause or the affected source must remain disabled.

## 9. Final operational truth

- Cursor quota is a real optional-review limitation, not a GitHub infrastructure outage.
- PR #43 is resolved and merged.
- Historical CI emails are not current defects merely because they remain in Gmail.
- Private-import and identity defects cited by Gemini are already protected by current tests.
- The remaining verified defects are addressed on `agent/verified-email-remediation` and require exact-head CI before merge.
- No restricted-source bypass has been added.
