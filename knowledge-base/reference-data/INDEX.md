# Index — reference-data

Structured lookup data — permission matrices, configuration exports, test-data catalogues.

**Read this index before opening anything in this folder.** For a file queried often, run the owning skill's script rather than reading the file into context.

| File | Covers | How to read it |
|---|---|---|

*Empty. Add one row per file as you add it, and say whether a script reads it or it is read directly.*

## Rule of thumb

If a file here gets queried more than a couple of times, it should have a **script** in the owning skill rather than being parsed ad hoc each run. A script's source never enters the context window — only its output does — and tested code beats code regenerated from scratch every time.

The permission matrix is the worked example: put yours here as `permissions-matrix.csv` and `.claude/skills/qa-permission-testing/scripts/lookup_permission.py` will query it. See that skill's `references/matrix-guide.md` for the expected columns.

## Keeping this current

Exports go stale silently. Record the export date next to each file, and re-export before a release cycle rather than trusting last quarter's copy.
