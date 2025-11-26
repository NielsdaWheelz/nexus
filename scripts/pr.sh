#!/bin/bash
# PR workflow shortcut
# Usage: gpr "branch-name" "commit-message"
#
# Example:
#   gpr "pr4.2/documents-list" "Implement GET /documents endpoint
#
#   - Add pagination support
#   - Add ACL enforcement"
#
# What it does:
#   1. Creates and checks out branch (git checkout -b branch)
#   2. Stages all changes (git add .)
#   3. Commits with message (git commit -m ...)
#   4. Pushes to origin (git push origin branch)
#   5. Creates GitHub PR (gh pr create --base main)
#   6. Squash merges and deletes branch (gh pr merge --squash --delete-branch)
#
# Setup (add to ~/.zshrc):
#   alias gpr='/Users/nnandal/Documents/code/nexus/scripts/pr.sh'

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

die() { echo -e "${RED}✗ $1${NC}" >&2; exit 1; }
ok() { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "${BLUE}→ $1${NC}"; }

# Validate
[[ $# -ge 2 ]] || die "Usage: gpr \"branch-name\" \"commit-message\""
command -v git &>/dev/null || die "git not found"
command -v gh &>/dev/null || die "gh not found"

BRANCH="$1"
MESSAGE="$2"

# Extract first line as PR title, rest as body
TITLE=$(echo "$MESSAGE" | head -n1)
BODY=$(echo "$MESSAGE" | tail -n +2)

info "Branch: $BRANCH"
info "Title: $TITLE"
echo ""

# 1. Create and checkout branch
info "Creating branch..."
git checkout -b "$BRANCH" || die "Failed to create branch (maybe it exists?)"
ok "Branch created"

# 2. Stage all changes
info "Staging changes..."
git add .
ok "Staged"

# 3. Commit (multiline message preserved)
info "Committing..."
git commit -m "$MESSAGE" || die "Nothing to commit"
ok "Committed"

# 4. Push
info "Pushing..."
git push origin "$BRANCH" || die "Push failed"
ok "Pushed"

# 5. Create PR (title = first line, body = rest)
info "Creating PR..."
PR_URL=$(gh pr create --base main --head "$BRANCH" --title "$TITLE" --body "$BODY" 2>&1 | grep "^https://" || echo "")
[[ -n "$PR_URL" ]] || die "Failed to create PR"
ok "PR: $PR_URL"

# 6. Squash merge + delete branch
info "Merging..."
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')
sleep 1
gh pr merge "$PR_NUM" --squash --delete-branch || die "Merge failed"
ok "Merged and branch deleted"

echo ""
ok "Done!"
