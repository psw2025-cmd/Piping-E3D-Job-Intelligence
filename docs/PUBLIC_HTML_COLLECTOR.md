# Public HTML Collector

The `public_html` collector is available for official career pages that do not have a verified supported API. All production HTML sources remain disabled until a source-specific live proof passes.

Controls include exact domain and link allowlists, bounded pagination and item counts, robots checks using the crawler identity, role/location anchor filters, schema.org parsing, constrained HTML fallback, local raw evidence with SHA-256 verification, and `pass_with_warnings` when a safe listing-only fallback is retained.

The verified production sources remain the McDermott and Wood Oracle connectors in `config/sources.yaml`. Disabled examples belong in `config/sources.example.yaml`; CI uses `config/sources.ci.yaml` and performs no live collection.
