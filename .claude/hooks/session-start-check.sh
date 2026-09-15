#!/usr/bin/env bash
# SessionStart hook — primes a session with the environment facts the agent would
# otherwise have to ask for, and warns about setup that is not finished.
#
# Whatever this prints on stdout is added to the conversation, which makes it the right
# place for the "state of the world" that changes between machines and between days.
#
# Two matchers matter (see settings.json.example):
#   startup  - fresh session only
#   compact  - AFTER compaction. This is how you re-inject context that compaction
#              dropped. PostCompact does NOT get its output back into the conversation;
#              this is the one that does. It is the single most common hook mistake.

set -uo pipefail

ENV_FILE=".claude/qa-test-env.md"
EXAMPLE_FILE=".claude/qa-test-env.example.md"

echo "QA workspace session"
echo ""

# --- environment file ---------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  echo "SETUP INCOMPLETE: $ENV_FILE does not exist."
  echo "  Copy it from $EXAMPLE_FILE and fill in your own values."
  echo "  Until then, ask the user for URLs and logins per run."
else
  placeholders="$(grep -c '<PLACEHOLDER>' "$ENV_FILE" 2>/dev/null || echo 0)"
  if [ "$placeholders" -gt 0 ]; then
    echo "Environment file present, with $placeholders unfilled <PLACEHOLDER> value(s)."
    echo "  Ask the user for those specific values when a run needs them."
  else
    echo "Environment file present and fully populated."
  fi
fi

# --- knowledge base -----------------------------------------------------------
if [ -d "knowledge-base" ]; then
  docs=$(find knowledge-base -type f ! -name "INDEX.md" ! -name "README.md" ! -name ".gitkeep" ! -name "sync-config.json" ! -name "SYNC_LOG.md" ! -name ".sync-*" 2>/dev/null | wc -l | tr -d ' ')
  echo "Knowledge base: $docs source document(s)."
  if [ "$docs" -gt 0 ]; then
    echo "  Read the folder INDEX.md files before opening any source document."
  else
    echo "  Empty. Answer from documents only once they are added; do not fill gaps by guessing."
  fi
fi

# --- knowledge-base sync ------------------------------------------------------
if [ -f "knowledge-base/sync-config.json" ]; then
  # Count only folder entries ("name": "https://drive.google.com/..."), never the
  # example URL in the _comment block - that made an unconfigured file look linked.
  # grep -c prints 0 and exits 1 when nothing matches, so `|| echo 0` would append
  # a second zero, and the numeric test below would then break on that two-line value.
  configured="$(grep -cE '^[[:space:]]*"[a-z-]+":[[:space:]]*"https://drive\.google\.com' knowledge-base/sync-config.json 2>/dev/null || true)"
  configured="${configured:-0}"
  if [ "$configured" -eq 0 ]; then
    echo "Drive sync: no folder links set yet in knowledge-base/sync-config.json."
  else
    # Trim the surrounding spaces only - `tr -d ' '` also ate the one between
    # the date and the time, printing 2026-09-1413:42.
    last="$(grep -E '^\| [0-9]{4}-' knowledge-base/SYNC_LOG.md 2>/dev/null | tail -1 | cut -d'|' -f2 | sed 's/^ *//; s/ *$//')"
    if [ -n "${last:-}" ]; then
      echo "Drive sync: $configured folder(s) linked, last run $last."
    else
      echo "Drive sync: $configured folder(s) linked, never run here — say \"sync the knowledge base\"."
    fi
  fi
fi

# --- git document guard -------------------------------------------------------
if [ -d ".githooks" ] && [ "$(git config core.hooksPath 2>/dev/null)" != ".githooks" ]; then
  echo ""
  echo "WARNING: git hooks are not active on this clone — project documents are not fully protected."
  echo "  Run once:  git config core.hooksPath .githooks"
fi

# --- reminders that survive compaction ---------------------------------------
echo ""
echo "Standing rules: draft test cases and defects in chat before writing them anywhere;"
echo "never put credentials in reports, screenshots, the tracker, or committed files."

exit 0
