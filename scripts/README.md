# Scripts

Helpful scripts for development and CI/CD.

## pr.sh – Automated PR Workflow

Shortcut to commit, push, create, and merge a PR in one command.

### Usage

```bash
./scripts/pr.sh "Your PR description"              # Uses current branch
./scripts/pr.sh "Your PR description" "pr1.2/name"  # Specify target branch
```

### What It Does

1. Stages all changes (`git add .`)
2. Creates commit with your message + Claude Code footer
3. Pushes to origin
4. Creates GitHub PR
5. Automatically merges PR

### Examples

```bash
# Current branch
./scripts/pr.sh "Add health endpoint"

# Specific branch
./scripts/pr.sh "Implement chunking pipeline" "pr3.2/chunking"

# Multi-line description (use quotes)
./scripts/pr.sh "Add RAG pipeline

Integrates retrieval into LLM prompts"
```

### Requirements

- `git` installed and configured
- `gh` (GitHub CLI) installed and authenticated
- Current branch should be the target for the PR

### What Happens

The script will:
1. Show `git status` with pending changes
2. Ask for confirmation before proceeding
3. Create commit, push, and create/merge PR
4. Print success message with PR number

### Undo

If you need to undo after running this script:

```bash
# Undo the merge (goes back to before PR was created)
git reset --hard HEAD~1
git push -f origin your-branch
```

Or manually use GitHub UI if already merged to main.
