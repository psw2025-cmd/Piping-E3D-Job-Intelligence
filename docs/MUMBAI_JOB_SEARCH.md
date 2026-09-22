# Mumbai, Thane and Navi Mumbai job search

## What changed

The worldwide collector remains enabled. Each daily run now puts a dedicated local shortlist at the top of SUMMARY.md and exports MUMBAI_THANE_NAVI_MUMBAI.md and .json in the daily artifact and ZIP bundle. No new schedule is created; the existing daily workflow generates these outputs.

Local matching uses the job's location field, with normalized city as a fallback only when location is absent. Company addresses in descriptions cannot qualify a Chennai vacancy as Mumbai. New Mumbai, New Bombay and Navi-Mumbai map to Navi Mumbai. Supported local areas include Airoli, Ghansoli, Rabale, Mahape, Vashi, Sanpada, Juinagar, Nerul, CBD Belapur, Kopar Khairane, Turbhe, Kharghar, Vikhroli, Powai, Andheri, Goregaon, Bhandup, Mulund, Chembur, Wagle Estate and Ghodbunder. Thane/Pune roles retain both locations in the report.

The shortlist requires relevant role wording in the title, rejects unrelated disciplines, omits explicit closed/expired notices and past parseable deadlines, and deduplicates application URLs. Posting date, last-seen date and collection status remain separate. Unknown/older dates do not become newly posted dates. A listed vacancy is not a guarantee that the employer is still accepting candidates.

## Run locally

```sh
job-intel --db data/database/mumbai.db collect --sources config/sources.mumbai.yaml --evidence-dir data/raw/mumbai --no-export
python -m job_intelligence.local_shortlist --db data/database/mumbai.db --output private-output/mumbai
```

The targeted configuration currently covers Technosoft only; the normal daily configuration covers the existing worldwide sources plus that verified addition. This is bounded coverage, not all employers in the region. A failed/partial collection is explicitly labelled, even if useful rows were collected.

## Source proof observed 23 September 2026

The actual repository collector fetched Technosoft with robots checks enabled, retained source evidence, and returned PASS, 1/1 sources, 2 jobs. Locations were extracted as `Thane / Pune` and `Pune / Thane`. The local proof run ID was `54f29eecf75f4c3a870fde1d6dd3f275`. Raw evidence and the database remain local, not committed.

## Relevant listings checked during this review

These are source-page observations, not applications or promises of hiring. Publication dates are unknown unless stated.

| Area | Role | Source and fit notes |
|---|---|---|
| Thane / Pune | Sr. Piping Engineer (AVEVA E3D), Technosoft | [Official role](https://technosoft.gmbh/careers/openings-india/sr-piping-engineer-aveva-e3d/): 8–12 years, E3D mandatory, mechanical bachelor's degree; confirm Thane assignment. |
| Thane / Pune | Piping Engineer, Technosoft | [Official role](https://technosoft.gmbh/careers/openings-india/piping-engineer/); location is shared with Pune. |
| Mumbai, Vikhroli | Staff Engineer – Piping, Black & Veatch | [Official role](https://careers.bv.com/job/Vikhroli%2C-West-Mumbai-Staff-Engineer-Piping-MH/1434643933/): dated 8 September 2026, 10–20+ years piping/layout experience; degree required. |
| Mumbai | Piping Designer, SSOE | [Official role](https://indcareers-ssoe.icims.com/jobs/3763/piping-designer/job?in_iframe=1): 3–5 years, diploma, AutoCAD/Plant3D; evening coordination with US teams. More junior than the senior target profile. |
| Navi Mumbai, CBD Belapur | Piping Engineer, Damodhartech | [Official careers page](https://www.damodhartech.com/careers/): 8–10 years, BE/B.Tech Mechanical plus Diploma in Piping Engineering; layout, isometrics, BOQ/MTO and supports. Undated listing; confirm current availability. |

## Excluded or needs renewed confirmation

- [ANI Piping Design Engineer – 3D Modelling](https://anione.in/careers/piping-design-engineer-3d-modelling): detailed page explicitly says **Deadline passed** and **Apply by 05 Jul 2026**. The date is an application deadline, not a publication date. This corrects the earlier recommendation based on the careers listing. The local filter now rejects this closure wording even when an application form remains.
- [Egis E3D Aveva Admin – Nuclear](https://jobs.egis-group.com/job/e3d-aveva-admin-nuclear-in-navi-mumbai-jid-3220): page explicitly says expired.
- [Worley Senior Piping Stress Engineer](https://worleyparsons.referrals.selectminds.com/jobs/senior-piping-stress-engineer-24213): explicitly closed.
- [Proton Navi Mumbai Piping Design Engineer](https://www.protonengineering.in/jobs/piping-design-engineer/): application form remains, but page displays 2021 dates. Do not present as a fresh vacancy.

The web-reviewed Black & Veatch, SSOE and Damodhartech pages are research leads, not newly enabled automated connectors. Future agents should verify extraction, location, dates and robots compliance before adding them to the daily sources.

### Black & Veatch extraction probe

On 23 September 2026, a robots-aware collector probe of the official Mumbai piping search returned seven relevant titles and job links (run `667eceb13c1b4feaaf2788ea27456c60`, PASS 1/1). However, every extracted location and publication date was empty. The source remains disabled: fetch success alone does not establish usable local coverage. Before enabling it, implement and validate location/date extraction against saved official-page evidence. Do not infer a job location solely from its URL or company address.
