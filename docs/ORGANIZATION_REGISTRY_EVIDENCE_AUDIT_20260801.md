# Organization Registry Evidence Audit

Audit date: 2026-08-01

## Exact repository counts

- Imported organization rows: **746**
- Rows labelled employer: **522**
- Rows labelled recruiter: **224**
- Exact normalized name labels: **740**
- Unique employer labels: **517**
- Unique recruiter labels: **223**
- Exact duplicate rows removed by name normalization: **6**

These are exact counts of repository data, not a claim that every identity, category, parent relationship, careers URL, or automation permission has been independently verified.

## Unsupported historical totals

The source file itself warns that earlier totals of **1,200**, **3,327**, and **3,340** were claims in imported chat content and that only partial lists were supplied. Those totals must not be published as verified counts.

## Canonical-identity integrity failure

The audit found **22 canonical collision groups**. Several contain unrelated organizations incorrectly merged under one parent. Therefore the stored 583 canonical keys are not a reliable unique-organization total.

## Google spot-check evidence

| Stored incorrect merge | Google result evidence | Finding |
|---|---|---|
| BP Singapore → Wood | https://www.bp.com/about-us/what-we-do/bp-worldwide/bp-in-singapore | BP Singapore belongs to BP, not Wood. |
| Morson International → Brunel | https://www.morson.com/ | Morson has its own official organization and domain. |
| Suncor Energy → NMDC Energy | https://www.suncor.com/ | Suncor has its own official organization and domain. |
| CPCL → BPCL | https://cpcl.co.in/ | CPCL is Chennai Petroleum Corporation Limited and has its own official domain. |
| TechnipFMC → Technip Energies | https://www.technipfmc.com/en/ | TechnipFMC has its own official organization and domain. |

## Current defensible display

**740 unique imported organization labels: 517 employer-labelled and 223 recruiter-labelled. External identity verification is incomplete.**

No larger “verified company” total is supported by the current evidence. Each label must be independently checked against Google results and the resulting official website before it can be promoted to verified status or enabled as a job source.
