# ECI candidate affidavits (Form 26) — fixture mode

## Status

**Fixture mode only.** No live ECI Affidavit Portal crawling. No OCR platform.

Parser version: `ECI_AFFIDAVIT_PARSER_V1`

## Pipeline

```text
Affidavit fixture
        ↓
Immutable raw archive
        ↓
Document extraction
        ↓
Structured parser
        ↓
Normalization
        ↓
Validation
        ↓
Candidate linkage
        ↓
Canonical database
        ↓
SourceDocument provenance
```

## Package

```text
collectors/eci/affidavits/
  collector.py    Fixture-mode Collector
  extract.py      PDF/text → ExtractedDocument (no OCR)
  parser.py       ExtractedDocument → ParsedAffidavit
  normalize.py    Parsed → NormalizedAffidavit
  validation.py   Business rules
  currency.py     Indian amount / NIL parser (Decimal)
  schemas.py      Intermediate typed structures
  persist.py      Normalized → PostgreSQL + review queue
  cli.py          Offline import CLI
```

## Run

```bash
# Requires persons/elections already present (e.g. election-results fixture import)
uv run python -m collectors.eci.affidavits.cli --fixture tests/fixtures/eci/affidavits/asha_verma_form26.txt
```

Or:

```bash
uv run python scripts/run_eci_affidavit_fixture_import.py
```

## Extraction statuses

| Status | Meaning |
|--------|---------|
| `TEXT_EXTRACTED` | Machine-readable text available (plaintext or **pypdf** text layer) |
| `OCR_REQUIRED` | Image / PDF with no extractable text — review queued |
| `EXTRACTION_FAILED` | Read/decode failure — review queued |

PDF classification is by extraction result, not filename. Image extensions (`.png`, `.jpg`, …) imply `OCR_REQUIRED`. Unreadable documents **never** produce empty asset/education/case rows.

Dependency: `pypdf` (declared in `pyproject.toml`).

## Linkage

Preferred: `Source Candidate Id` matching an existing `person_id`.

Fallback: exactly one person with the same `normalized_name`, optionally narrowed by election year + constituency. Ambiguous → `IDENTITY_REVIEW_REQUIRED` (no guess).

## Publication policy (privacy boundary)

Archived raw affidavits may retain the full public Form 26 when lawfully published by ECI.

The **public API and UI must not expose** normalized fields for:

- full residential address
- phone number / personal email
- PAN / Aadhaar / government ID numbers
- bank account numbers
- signatures
- unnecessary dependent identifiers

Declared education, assets, liabilities, and criminal-case disclosures that appear on Form 26 may be shown with:

- wording **Declared …** / **Self-declared in election affidavit**
- `verification_status = SELF_DECLARED`
- a `source_id` link to provenance

Never present self-declared education or finances as independently verified.

## Money values

Amounts use `Decimal` / PostgreSQL `NUMERIC`. JSON APIs return amount strings to avoid float precision loss. Explicit `NIL` → zero; `Not Applicable` / `-` → null (`NOT_APPLICABLE`); blank → `MISSING`; garbage → `PARSE_FAILED` (never silent zero).
