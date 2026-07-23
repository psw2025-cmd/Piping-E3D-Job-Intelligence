# Worldwide Coverage Operating Model

The worldwide system uses a measurable company registry rather than claiming that every job on the internet can be collected.

## Company status model

Every target company in `config/worldwide_companies.yaml` has exactly one status:

- `ACTIVE_DIRECT` — a verified public collector is enabled.
- `ACTIVE_GMAIL_ALERT` — official or portal alerts are imported through user-authorized Gmail.
- `ACTIVE_PUBLIC_NOTICE` — official recruitment notices, advertisements, corrigenda and PDFs are monitored.
- `ACTIVE_MANUAL_IMPORT` — official vacancy files can be imported from PDF, Word, EML, text or images.
- `STAGED_NEEDS_LIVE_PROOF` — a source is known but remains disabled until bounded live proof passes.
- `BLOCKED_RESTRICTED` — safe automation is unavailable; no login, CAPTCHA or access-control bypass is permitted.
- `NO_SOURCE_FOUND` — source discovery remains open.

A company cannot silently disappear from coverage. The workbook reports every active, staged, blocked and missing entry.

## India priority batch

The first India batch contains 25 employers covering:

- EPC and engineering consultancies
- refinery, petrochemical, LNG and pipeline owner/operators
- nuclear and power organizations
- public-sector recruitment notices
- water and process-plant engineering companies

The registry includes Engineers India, Tata Consulting Engineers, Tata Projects, Reliance Industries, Toyo Engineering India, Nuberg EPC, WABAG, ONGC, IndianOil, BPCL, HPCL, GAIL, Petronet LNG, NPCIL, NTPC, BHEL, Assystem India, AECOM India, Mott MacDonald India, Tractebel India, Thermax, Praj, PDIL, MECON and Egis India.

## Gmail query groups

`config/gmail_query_groups.yaml` separates authorized read-only Gmail collection into:

1. India job portals
2. Gulf and Middle East portals
3. India PSU recruitment notices
4. India EPC and engineering employers
5. Worldwide official employers
6. Energy and engineering recruiters
7. Nuclear and ITER opportunities

Run every enabled group after local Google authorization:

```powershell
.\scripts\run_gmail_query_groups.ps1
```

OAuth credentials, tokens, raw emails, databases and workbooks remain local and ignored by Git.

## Daily workbook proof

The verified daily cloud workflow appends these sheets after public collection:

- `Company_Registry`
- `Country_Coverage`
- `Missing_Companies`
- `Employer_Source_Status`
- `ATS_Coverage`
- `Portal_Alert_Coverage`
- `Recruiter_Source_Status`
- `PSU_Notices`
- `Source_Discovery`
- `Stale_Sources`
- `Blocked_Sources`
- `Coverage_Gaps`
- `Company_Aliases`
- `Country_Company_Matrix`

The workflow updates `status.json`, appends a coverage section to `SUMMARY.md`, verifies the sheets, and rebuilds the downloadable ZIP bundle. The workflow fails if coverage proof is absent.

## Coverage percentage

Country coverage counts these modes as covered:

- active direct
- active Gmail alert
- active public notice
- active manual import

Staged, blocked and no-source entries remain visible as gaps. Coverage percentage therefore measures operational reach across the target registry; it is not a claim that every vacancy in a country was found.

## Next batches

1. Implement bounded HTML/PDF notice collection for Indian PSUs.
2. Prove and enable Reliance, TCE, Nuberg, WABAG, Thermax and Praj public sources.
3. Add GCC operators, EPC contractors and public recruitment portals.
4. Add offshore/subsea companies and international engineering consultancies.
5. Expand to North America, Asia-Pacific, Africa and Latin America.
6. Run scheduled source-health and stale-source recovery checks.
