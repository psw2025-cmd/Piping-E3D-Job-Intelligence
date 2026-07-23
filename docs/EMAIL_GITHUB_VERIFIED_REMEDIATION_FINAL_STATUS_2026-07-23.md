# Final Status — Gmail and GitHub Verified Remediation

**Repository:** `psw2025-cmd/Piping-E3D-Job-Intelligence`  
**Date:** 2026-07-23  
**Detailed audit:** `docs/EMAIL_GITHUB_VERIFIED_REMEDIATION_2026-07-23.md`

## Final result

The email-derived issue audit and verified remediation are complete.

- Matching Gmail messages inspected in full: **269**
- Search used: `subject:"psw2025-cmd/Piping-E3D-Job-Intelligence"`
- Detailed findings were deduplicated by PR, workflow, commit, review thread and source file.
- Historical intermediate failures were not treated as current defects.
- PR #43 was corrected and merged at `7e86c913b62001621511b019ea465a7c2519d05d`.
- PR #44 was merged at `d7181ffe67611afde636ba998b39d0a2d107472b`.

## Verified defects resolved by PR #44

1. Oracle location filtering now uses phrase boundaries and no longer treats `Indiana` as `india` or `Romania` as `oman`.
2. HTTP and public-HTML redirects cannot leave a source's configured allowed-domain boundary.
3. Explicit scoring profiles no longer silently combine with another environment taxonomy.
4. Every configured target role has an explicit canonical role-family mapping.
5. Rescored reimports can clear obsolete derived role, location, software, sector, employment-type and closing-date fields.
6. Live notice proof and production collection use the same collector and source-domain controls.
7. A permanent live Oracle contract workflow verifies McDermott and Wood source health and evidence.

## Exact tested PR #44 head

```text
0ba973afe03f48547e9974d897055aeac9fe3193
```

The following exact-head gates passed before merge:

- Ruff
- full pytest
- CLI smoke test
- cloud daily workbook and coverage-bundle proof
- live Workday contract proof
- live GAIL public-notice proof
- live NPCIL public-notice proof
- live McDermott and Wood Oracle contract proof
- review-thread inspection: no unresolved threads
- branch divergence: ahead of `main`, behind by zero

## Claims rejected as stale or unsupported

The following broad claims from the Gemini summary were not accepted as current defects:

- PR #12 is still blocked;
- duplicate private imports and evidence recovery remain unresolved;
- duplicate database exports are proven current defects;
- all GitHub Actions or agents are blocked by resource exhaustion;
- PR #42 and PR #43 are stalled indefinitely;
- old `No jobs were run` messages prove a current employer-registry outage;
- removing a temporary proof workflow broke the permanent daily pipeline;
- all Airswift, NES Fircroft and Brunel validation is currently broken; and
- generic job-count logic requires an unbounded rewrite.

Current regression tests already protect the corrected private-import, URL-less identity, pagination, sitemap-cap and daily-bundle truth behavior.

## Cursor quota truth

Cursor Bugbot usage/spend limits are real and may prevent optional Bugbot review or autofix.

They do **not** block:

- GitHub Actions;
- repository changes;
- pull-request creation;
- independent review-thread inspection; or
- merging after successful GitHub proof.

No repository-side quota bypass was attempted. Only the user or Cursor team administrator can change Cursor billing or usage limits.

## Safety decisions retained

- No robots.txt bypass
- No CAPTCHA bypass
- No login or access-control bypass
- EIL remains on Gmail/private-import fallback because direct crawling is disallowed by robots rules.
- IndianOil remains on Gmail/private-import fallback because its public listing presents a JavaScript/Sucuri challenge.
- GAIL remains staged until a separate production-activation decision.
- NPCIL remains the verified active India public-notice source.

## Final authoritative state

The verified email remediation is merged and complete. Remaining open feature PRs and source expansions are separate work items and must be evaluated on their own current code and live proof; they are not automatically defects merely because historical email notifications exist.
