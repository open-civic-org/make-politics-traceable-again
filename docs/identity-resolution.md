# Identity resolution

## Internal vs external identifiers

Internal canonical IDs are allocated by MPTA:

```text
IND-PER-...   Person
IND-CND-...   Candidacy
IND-ELC-...   Election
```

External Election Commission of India (ECI) identifiers are **evidence attached to a candidacy**, never Person primary keys.

## `candidacy_source_identifier`

Table uniqueness (exactly one candidacy per scoped key):

```text
(source_authority, source_system, identifier_type, external_value_raw, election_id)
```

ECI IDs are **not** assumed globally permanent across elections; `election_id` is part of the unique key.

| Field | Example |
|-------|---------|
| `source_authority` | `Election Commission of India` |
| `source_system` | `RESULTS_PORTAL`, `AFFIDAVIT_PORTAL` |
| `identifier_type` | `CANDIDATE_ID`, `CANDIDATE_LOCATOR`, `NOMINATION_ID` |
| `external_value_raw` | `ECI-DEMO-CAND-001` (synthetic) or a real portal value |

Never invent fake ECI IDs such as `ECI-CAND-<NAME>`. If the source only provides a page URL, store it as `CANDIDATE_LOCATOR`, not `CANDIDATE_ID`.

## Affidavit linkage

Preferred:

```text
external ECI identifier
  → candidacy_source_identifier
  → Candidacy → Election → Person
```

Fallback (exact only):

```text
normalized candidate name + election year + election type + constituency
```

Ambiguous or incomplete → `IDENTITY_REVIEW_REQUIRED`. No fuzzy matching.

Values that look like internal person IDs (`IND-PER-*`) are rejected as `source_candidate_id`.

## Extraction confidence

`SourceDocument.extraction_confidence` is reserved and currently **unset (`NULL`)**.

Objective provenance fields remain: `extraction_method`, content SHA-256, collector/parser versions, git SHA.

## Statistical report staging identity

Report 33 staging rows may set a **read-only** `identity_candidacy_id` when exactly one candidacy matches:

```text
normalized candidate name + election year + election type + constituency name
```

Statuses: `EXACT_LINKED` / `AMBIGUOUS` / `UNRESOLVED` / `CONFLICT` / `NEEDS_REVIEW`.
Statistical import never creates `Person`, `Candidacy`, or `ElectionResult`.
