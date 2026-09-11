# Shared by .githooks/pre-commit and .claude/hooks/block-secret-commit.sh.
#
# The ONLY paths under knowledge-base/ that may ever be committed. Everything else there is
# a project document (solution docs, TDD, BRD, SOW, call recordings, client data) synced
# locally from Google Drive — and project documents never go to GitHub.
#
# To allow a new kind of committed file, change it here, in this one place.
KB_ALLOWED_RE='^knowledge-base/(README\.md|sync-config\.json|[^/]+/INDEX\.md|[^/]+/\.gitkeep)$'
