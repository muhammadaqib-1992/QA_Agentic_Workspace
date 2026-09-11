# Index — technical-design

Technical design (TDD) — the implementation spec for the same features the solution documents describe functionally. Reach for it when a defect might be a **configuration** root cause rather than a functional gap, or when a defect report needs a script or field identifier.

**Read this index before opening anything in this folder.** Only open a source document when a row below says it is the one you need.

| Document | Covers | Notes |
|---|---|---|

*Empty. Add one row per document as you add it.*

## What QA usually needs from here

- **Configuration navigation path** — where a toggle actually lives, so "is it enabled?" can be answered rather than assumed.
- **Script / deployment identifiers** — a defect citing the script id gets triaged faster than one describing only the symptom.
- **Custom field and record identifiers** — needed to query the backend and verify what the UI displays.
- **Data flow** — which records are read and written, so you know what to check after an action.
- **Prerequisites** — a feature that silently depends on a custom field fails confusingly where that field is missing.

## Cross-referencing rule

Cross-reference the solution document and the TDD **by feature number, not by title** — titles drift apart between the two while numbers stay stable.

## Known gaps

List features present in the solution document with no TDD section. A missing TDD section is not permission to guess a config path — say it isn't documented.
