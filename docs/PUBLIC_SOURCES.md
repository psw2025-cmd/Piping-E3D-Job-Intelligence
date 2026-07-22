# Public Source Collection

The collector layer reads only sources explicitly enabled in `config/sources.yaml`.
All examples remain disabled until their public identifiers and access are verified.

## Supported source types

- **Greenhouse:** public Job Board API using a board token.
- **Lever:** public Postings API using a site name and global or EU region.
- **SmartRecruiters:** public Posting API using a company identifier.
- **RSS/Atom:** public feed URL.
- **Sitemap:** public XML sitemap; job pages must expose `JobPosting` JSON-LD.

## Safety rules

- HTTP(S) only; embedded URL credentials and literal private or local IP addresses are rejected.
- CAPTCHA bypass, rotating proxies and login-required sources are prohibited.
- Per-source request rates, timeouts, maximum items and allowed sitemap domains are enforced.
- Sitemap pages are checked against `robots.txt`; the default is to skip when robots cannot be checked.
- One source failure does not discard successful sources.
- Raw public responses are written below `data/raw/`, hashed and registered in the database.
- API keys, CV files, application records and recruiter lists remain local and ignored by Git.

## Configure a source

Copy the matching disabled example in `config/sources.yaml`, replace only its public identifier or URL, and then set `enabled: true`.

Do not enable a source until all of these are confirmed:

1. The endpoint or feed is publicly accessible without login.
2. The source permits public automated access.
3. The configured company name is correct.
4. The source identifier or URL belongs to the intended employer.
5. The interval and rate limit are conservative.

Validate configuration before collecting:

```powershell
job-intel validate-sources --sources config/sources.yaml
```

## Collect, export and verify

```powershell
job-intel --db data/database/jobs.db collect `
  --sources config/sources.yaml `
  --evidence-dir data/raw `
  --output data/exports/Piping_E3D_Jobs.xlsx

job-intel --db data/database/jobs.db verify `
  --output data/exports/Piping_E3D_Jobs.xlsx
```

A collection run returns:

- exit `0`: all selected sources passed, or no source was enabled;
- exit `1`: partial success; at least one source passed and one failed;
- exit `2`: all selected sources failed or Excel export failed.

Use `--only <source-id>` one or more times to test selected sources without running the complete registry.

The `Source_Health`, `Source_Evidence`, and `Run_Proof` Excel sheets provide the audit trail.
