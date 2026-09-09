# Coverage Maximization Plan — 2026-09-09

## Objective
Maximize verified worldwide piping/E3D/PDMS/SP3D/S3D/Plant3D/layout/stress/site/EPC job coverage while preserving source truth, deduplication, bounded crawling, and one authoritative recurring workflow per source lane.

## Immediate P0
1. Correct Oracle HCM pagination so active McDermott and Wood sources traverse distinct pages using Oracle Candidate Experience finder pagination.
2. Validate returned Offset/Limit/TotalJobsCount metadata and fail closed on contradictory or repeated pages.
3. Prove bounded traversal with deterministic tests before merge.

## Coverage expansion priorities
### Tier 1 — activate or prove already staged/high-priority employers
- Worley
- Technip Energies
- Fluor
- Jacobs
- L&T Energy Hydrocarbon
- Saipem
- MAIRE Tecnimont
- Black & Veatch
- Hatch
- Aker Solutions
- Kent
- Penspen
- Samsung E&A
- JGC
- Chiyoda
- NPCC
- Bilfinger
- Burns & McDonnell
- Ramboll

### Tier 2 — add major EPC/EPCM/process/offshore employers
- Techint Engineering & Construction
- Tata Consulting Engineers
- Aarvi Encon
- PM Group
- Veolia
- Swayam
- RCAD
- KBR regional entities where distinct official ATS inventories exist
- Petrofac regional channels where distinct official inventory exists
- McDermott regional/discipline views only when they add unique requisitions
- Bechtel regional/discipline views only when they add unique requisitions
- Samsung E&A regional recruitment channels
- JGC regional companies
- Chiyoda regional companies
- L&T Energy Hydrocarbon / Offshore / Heavy Engineering relevant official channels

## Required source evidence per employer
For each employer retain: official careers URL, public job host, ATS/platform type, source IDs, verified date, active/staged status, pagination method, detail-page method, robots/access behavior, max pages/items, evidence path, last successful live proof, unique requisition count, and failure reason when disabled.

## Coverage governance
- No source becomes active without bounded live proof.
- No source may claim exhaustive/worldwide coverage unless pagination termination is independently verified.
- Deduplicate by exact requisition ID first, then canonical source URL/company/title/location fallback.
- Preserve constrained/junior/degree/work-right/date-unproven roles rather than silently dropping them.
- One recurring workflow owner per source to prevent duplicate crawls and duplicate alerts.
- Historical/superseded PRs remain audit evidence but must not remain parallel authorities after their useful changes are salvaged.
- Every scheduled run should report employers attempted, employers healthy, employers failed, pages scanned, unique requisitions seen, matching piping roles, duplicate count, and source freshness.

## Definition of maximum practical coverage
100% cannot truthfully mean every job on the internet. The measurable target is 100% of the maintained verified employer/source universe attempted according to policy, with every enabled source either PASS or explicitly FAIL with evidence, and continuous expansion toward 2,000+ legitimate employers/sources and 1,000+ public recruitment-contact resources in auditable batches.
