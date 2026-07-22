# Public Source Collection

The collector layer reads only sources explicitly enabled in `config/sources.yaml`. Production sources must be tied to an official employer careers page and recorded in `config/employer_registry.yaml`.

## Configuration files

- `config/sources.yaml` contains verified production sources.
- `config/sources.example.yaml` contains disabled templates.
- `config/sources.ci.yaml` contains no enabled source and keeps GitHub Actions network-free.
- `config/employer_registry.yaml` records official employer URLs, status and remaining connector work.

## Supported source types

- **Greenhouse:** public Job Board API using a board token.
- **Lever:** public Postings API using a site name and global or EU region.
- **SmartRecruiters:** public Posting API using a company identifier.
- **RSS/Atom:** public feed URL.
- **Sitemap:** public XML sitemap; job pages must expose `JobPosting` JSON-LD.
- **Public HTML:** official employer search pages with strict pagination, domain allowlists, job-link patterns, role filters, required location markers and optional detail-page parsing.

## Public HTML controls

A `public_html` source must define:

- `url` and optionally a `page_url_template` containing `{page}`;
- `allowed_domains` for both the employer page and its public job-detail host;
- `job_link_patterns` that identify job-detail URLs;
- `anchor_text_patterns` for relevant roles;
- `required_anchor_text_patterns` for location or other mandatory markers;
- optional `exclude_anchor_text_patterns` for promotional or unrelated links;
- conservative `max_pages`, `max_items`, request rate and response-size limits.

The collector scans every configured listing page even when an earlier page has no relevant roles. It fetches a detail page only when the link host, path, role text and all required markers pass.

## Safety rules

- HTTP(S) only; embedded credentials, literal private addresses and DNS-resolved private targets are rejected.
- Every redirect destination is validated before a request is made.
- Environment proxies are disabled.
- CAPTCHA bypass, rotating proxies and login-required sources are prohibited.
- Per-source request rates, timeouts, response sizes, redirects, maximum items and allowed domains are enforced.
- Sitemap and public-HTML pages are checked against `robots.txt`; the default is to skip when robots cannot be checked.
- One source failure does not discard successful sources.
- Raw public responses are written below `data/raw/`, hashed and registered in the database before job upserts.
- Untrusted text is neutralized before Excel export so it cannot be interpreted as a formula.
- API keys, CV files, application records and recruiter lists remain local and ignored by Git.

## Active production sources

The initial production registry contains official McDermott location searches for:

- Chennai, Tamil Nadu, India
- Dubai, United Arab Emirates
- Doha, Qatar

Only links containing relevant piping/layout/mechanical role terms and the configured location markers are eligible for detail retrieval.

## Add or change a source

Start from `config/sources.example.yaml`. Do not enable a source until all of these are confirmed:

1. The page or feed is publicly accessible without login.
2. Employer ownership and the public job-detail host are verified.
3. Public automated access is permitted.
4. The configured company and location are correct.
5. Link, role and location filters have fixture tests.
6. Request rate, maximum pages and maximum items are conservative.
7. The employer registry records the source and verification date.

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
