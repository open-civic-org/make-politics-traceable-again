# ECI collectors

## Status

**Fixture mode only.** Live Election Commission of India HTTP requests are not implemented.

## Package layout

```text
collectors/eci/
  collector.py          Election-results fixture pipeline
  ...
  affidavits/           Form-26 affidavit fixture pipeline (Milestone 3)
    collector.py
    extract.py
    parser.py
    normalize.py
    validation.py
    currency.py
    schemas.py
    persist.py
    cli.py
```

## Run (fixture)

```bash
uv run python scripts/run_eci_fixture_import.py
uv run python scripts/run_eci_affidavit_fixture_import.py
```

## Identity policy

- Exact `normalized_name` match reuses a person **only when exactly one** person exists with that name.
- Ambiguous names always create a new person (no fuzzy merge).
- Later: candidates enter `identity_match_review` for admin MERGE / DO_NOT_MERGE.

## Archive layout

```text
data/raw/eci/election_results/{year}/{artifact_id}/
  payload.json
  metadata.json
```

Identical SHA-256 content is not rewritten; a new observation may point at the existing payload.
