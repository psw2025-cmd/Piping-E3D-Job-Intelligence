# Gemini Execution Contract

This document is the execution contract for Gemini when working on `Piping-E3D-Job-Intelligence`.

## Purpose

The goal is to improve this repository into the best practical maximum-coverage, self-extending, self-learning job intelligence system possible for piping, E3D, PDMS, SP3D, offshore, refinery, nuclear, energy, and EPC opportunities, while preserving the repository’s documented architecture and safety model.

Gemini must remain aligned with these pillars:

1. Coverage maximization.
2. Discovery of additional legitimate public sources.
3. Better extraction, normalization, deduplication, scoring, and proof.
4. Better reliability, automation, validation, and maintainability.

## Repo reality to respect

Before making changes, Gemini must re-scan the repository and act from actual repo state, not assumptions.

The repository already includes and/or documents:

- `docs/`, `tests/`, `.github/workflows`, `scripts/`, `config/`, `src/job_intelligence/`
- `.env.example`
- `.gitignore`
- `pyproject.toml`
- `requirements.txt`
- SQLite as strict source of truth
- Excel workbook as operating review output
- Gmail read-only alert ingestion
- Private local import flow
- evidence-backed, non-destructive collection and verification
- explicit safety boundaries

Gemini must not confuse current repo constraints with defects.

## Safety boundaries

Gemini must obey the repository’s documented safety boundaries:

- Use only public, permitted APIs, feeds, sitemaps, and employer career pages unless the repo explicitly supports another allowed path.
- Respect robots.txt, conservative request limits, and platform terms.
- Never bypass CAPTCHAs, login walls, or access controls.
- Never commit CVs, application records, recruiter lists, databases, evidence, or credentials.
- Keep public-source automation and private/local imports separated.
- Respect Gmail’s read-only model where Gmail support is involved.

## Execution style

Gemini must work end-to-end, not partially.

### Phase 0 — Understand first

Before implementation:

1. Scan the repo tree.
2. Read major Markdown/docs files first.
3. Read relevant source modules.
4. Build a system-level understanding of current data flow and architecture.
5. Identify actual limitations before proposing or changing anything.

### Phase 1 — Pre-flight

Before changing code:

- Check Python version and virtual environment.
- Check install method from `pyproject.toml` / `requirements.txt`.
- Check test runner availability.
- Check current git status.
- Check local git identity.
- Check whether docs/examples/config need sync.

If required packages or tools are missing, Gemini should install or configure them on the laptop environment before continuing.

### Phase 2 — Implement fully

Gemini must not leave half-integrated features.

If a feature requires touching multiple layers, Gemini should update all relevant layers, including:

- config and registries
- collectors or extractors
- models and schema
- DB logic
- scoring and normalization
- CLI commands
- export/workbook/reporting logic
- tests
- docs
- scripts/workflows where required

### Phase 3 — Validate and repair

After implementation, Gemini must:

1. Run targeted tests.
2. Run broader regression checks.
3. Run formatter/linter/type checks if configured.
4. Execute representative CLI flows where safe.
5. Fix failures.
6. Re-run validation until stable.

Gemini must not stop after reporting the first error if it can reasonably fix it.

### Phase 4 — Final verification

Before completion, Gemini must verify:

- the feature is integrated and callable
- the repo still installs cleanly
- touched tests pass
- docs match behavior
- `.env.example` reflects new environment needs
- `.env` remains ignored
- no secrets were committed
- no junk artifacts remain
- git diff is coherent and reviewable
- the work meaningfully improves the repo toward the stated goal

## Strict Definition of Done

Before marking any task complete, Gemini must satisfy all of the following:

1. **Schema safety** — if adding or modifying SQLite tables, use safe, idempotent, non-destructive behavior.
2. **Non-blocking validation** — if adding any listener/daemon, do not validate it by running an endless live loop; use dry-run, single-pass, or mocked validation.
3. **Environment hygiene** — if new environment variables are required, mirror them into `.env.example` with placeholder values and confirm `.env` remains ignored.
4. **Dependency sync** — if adding packages, update the correct dependency files and update lockfiles only if lockfiles actually exist.
5. **1:1 tests for new modules** — every new module added under `src/` must have a corresponding test file under `tests/`.
6. **Git identity safeguard** — if git identity is missing in the environment, configure a local placeholder identity before commit operations.
7. **Docs sync** — update README/docs/scripts/examples when user-facing behavior changes.
8. **Installability** — the repo must still install and run after changes.
9. **Proof of execution** — final output must clearly state what was inspected, changed, installed, tested, fixed, and any remaining limitations.

## MRI scan of execution traps

Gemini must actively avoid these failure modes:

### Trap A — Wrong CLI assumptions

Do not assume a command, subcommand, or flag exists. Check source or `--help` before using it.

### Trap B — Flaky network validation

If validation depends on unstable network behavior, prefer mocking, fixtures, dry-runs, or deterministic checks where practical.

### Trap C — Artifact pollution

Do not leave temporary files, caches, exports, tokens, private evidence, or junk tracked in git.

### Trap D — Import/module collisions

Validate package structure, imports, `__init__` behavior, and test discovery when adding modules.

### Trap E — Context drift

At every major step, re-anchor to the core goal and repo architecture. Do not get distracted by unrelated refactors.

### Trap F — Fake completion

Do not claim success just because code was written. Success requires verification, integration, docs sync, and stable operation.

## Dependency and installation rule

Gemini is expected to discover what needs to be installed on the laptop environment for the requested task.

That includes, when needed:

- Python packages
- test dependencies
- formatter/linter/type-check tools already implied by repo configuration
- browser/runtime dependencies only if actually required by an allowed feature
- any missing local execution prerequisites

Gemini should:

1. Detect what is missing.
2. Install it correctly.
3. Update dependency files where appropriate.
4. Verify imports and commands.
5. Continue only after environment readiness is confirmed.

## Output standard

Gemini’s final response for any execution must include:

1. What was inspected.
2. What was found.
3. What was changed.
4. What was installed or configured.
5. What was tested.
6. What failed and how it was fixed.
7. Final validation status.
8. Remaining limitations or consciously deferred items.

## Mindset

Gemini must behave like a disciplined engineering executor:

- Understand first.
- Change carefully.
- Validate deeply.
- Fix issues.
- Re-validate.
- Finish cleanly.

No partial delivery. No drift. No unsupported claims of completion.