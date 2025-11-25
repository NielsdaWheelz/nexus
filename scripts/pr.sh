#!/bin/bash
# PR workflow shortcut
# Usage: ./scripts/pr.sh "PR description" [branch-name]
#
# Examples:
#   ./scripts/pr.sh "Add database models"              # Uses current branch
#   ./scripts/pr.sh "Add auth" "feature/auth"          # Specifies branch
#   ./scripts/pr.sh "Implement search" "pr1.5/search"
#
# What it does:
#   1. Stages all changes (git add .)
#   2. Creates commit with your message (git commit -m ...)
#   3. Pushes to origin (git push origin branch)
#   4. Creates GitHub PR (gh pr create)
#   5. Merges PR with auto-merge flag (gh pr merge)
#
# Requirements:
#   - git installed and configured
#   - gh (GitHub CLI) installed and authenticated
#   - You must be on the target branch before running

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_error() {
    echo -e "${RED}✗ Error: $1${NC}" >&2
    exit 1
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_info() {
    echo -e "${BLUE}→ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    if ! command -v git &> /dev/null; then
        print_error "git not found. Please install git."
    fi
    if ! command -v gh &> /dev/null; then
        print_error "gh (GitHub CLI) not found. Please install it: https://cli.github.com/"
    fi
}

# Get current branch if not specified
get_branch() {
    if [ -n "${2:-}" ]; then
        echo "$2"
    else
        git rev-parse --abbrev-ref HEAD
    fi
}

# Validate inputs
validate_inputs() {
    if [ -z "${1:-}" ]; then
        print_error "No PR description provided. Usage: ./scripts/pr.sh \"Your PR description\" [branch-name]"
    fi
}

# Stage changes
stage_changes() {
    print_info "Staging changes..."
    git add .
    print_success "Changes staged"
}

# Create commit
create_commit() {
    local message="$1"

    print_info "Creating commit..."

    git commit -m "$(cat <<EOF
$message

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)" || print_error "Failed to create commit. Maybe nothing changed?"

    print_success "Commit created"
}

# Push to origin
push_to_origin() {
    local branch="$1"

    print_info "Pushing to origin/$branch..."
    git push origin "$branch" || print_error "Failed to push to origin"
    print_success "Pushed to origin/$branch"
}

# Create PR
create_pr() {
    local branch="$1"
    local title="$2"

    print_info "Creating GitHub PR..."

    # Extract PR title (first line of message)
    local pr_title="${title}"

    # Create PR and capture URL
    local pr_url
    pr_url=$(gh pr create \
        --title "$pr_title" \
        --body "Auto-created with pr.sh script" \
        --head "$branch" 2>&1 | grep "^https://" || echo "")

    if [ -z "$pr_url" ]; then
        print_warning "Could not capture PR URL, but PR should be created"
        return 0
    fi

    print_success "PR created: $pr_url"
    echo "$pr_url"
}

# Merge PR
merge_pr() {
    local pr_number="$1"

    print_info "Merging PR #$pr_number..."

    gh pr merge "$pr_number" --merge --auto 2>&1 || print_error "Failed to merge PR"
    print_success "PR #$pr_number merged"
}

# Get PR number from URL
get_pr_number() {
    local url="$1"
    echo "$url" | grep -oP 'pull/\K[0-9]+' || print_error "Could not extract PR number from URL"
}

# Main
main() {
    check_prerequisites
    validate_inputs "${1:-}"

    local message="${1:-}"
    local branch
    branch=$(get_branch "${1:-}" "${2:-}")

    echo ""
    print_info "PR Workflow for Branch: $branch"
    echo ""

    # Confirm branch
    echo "Current git status:"
    git status --short | head -10 || true
    echo ""
    print_warning "About to commit to branch: $branch"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_error "Aborted by user"
    fi

    echo ""

    # Execute workflow
    stage_changes
    create_commit "$message"
    push_to_origin "$branch"

    # Create and merge PR
    pr_output=$(create_pr "$branch" "$message")

    if [ -n "$pr_output" ]; then
        pr_number=$(get_pr_number "$pr_output")
        sleep 2  # Wait for PR to be fully available
        merge_pr "$pr_number"
    else
        print_warning "Skipping auto-merge (no PR URL captured)"
    fi

    echo ""
    print_success "PR workflow complete!"
    echo ""
}

# Run
main "$@"
