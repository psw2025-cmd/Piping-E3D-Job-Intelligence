# Security and Privacy

This repository may process personal job-search information locally. Do not commit any of the following:

- `.env` or API credentials
- CVs, cover letters or identity documents
- SQLite databases
- Excel exports
- downloaded vacancy pages, images or PDFs
- recruiter/contact lists
- email messages or application histories

Use `.env.example` only as a variable-name template. Store real values in a local `.env` or approved GitHub repository secrets.

## Contact classifications

- `PUBLIC_VERIFIED`: explicitly published and independently confirmed by an approved process
- `PUBLIC_UNVERIFIED`: present in supplied public evidence but not independently verified
- `ENRICHMENT_VERIFIED`: returned by an approved business-contact provider
- `PATTERN_SUGGESTION`: generated possibility; never present as confirmed
- `GENERIC_COMPANY_CONTACT`: public generic company address

Do not perform SMTP probing, credential testing, access-control bypass, CAPTCHA bypass or collection from private groups without authorization.

## Reporting

Do not open a public issue containing secrets or personal records. Remove sensitive values and provide only the minimum reproducible technical details.
