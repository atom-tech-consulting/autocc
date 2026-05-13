---
name: commit-changes
description: "Commit current work, update TASKS.md and progress.md. Use after completing a unit of work."
user_invocable: true
---

<command-name>commit-changes</command-name>

# Commit Changes

Wrap up a unit of work: commit, update project docs. Run this when you've finished a task or the user asks to commit.

## Steps

Execute these in order. Do NOT skip steps.

### 1. Survey changes

Run in parallel:
- `git status -u` (never use `-uall`)
- `git diff` (staged + unstaged)
- `git log --oneline -5` (for commit message style)

Review the output. Identify:
- What files changed and why
- Whether any files should NOT be committed (secrets, large binaries, `.env`)
- Which task(s) this work relates to

### 2. Update TASKS.md

Read `TASKS.md` (or the path from CLAUDE.md `## Autopilot` section).

- Move completed tasks from Active → Complete (change `- [ ]` to `- [x]`)
- If the next task is obvious, move it from Ready → Active
- If new tasks were discovered during work, append them to Backlog
- Do not touch Frozen

### 3. Update progress.md

Read `.autocc/progress.md` (or the path from CLAUDE.md `## Autopilot` section).

Append an entry for this work. Format:

```markdown
## [YYYY-MM-DD] <Short description of work>

### <Category> (e.g., "Bug fixes", "New feature", "Infrastructure")
- **<What>** — <1-2 sentence description of what was done and why>

### Files changed
- `path/to/file` — <what changed>
```

Keep it concise — this is an audit trail, not a novel. Only document what's not obvious from the diff.

### 4. Stage and commit

Stage the work files, TASKS.md, and progress.md together in one commit:

```
git add <changed files> TASKS.md .autocc/progress.md
```

Commit using heredoc syntax:

```bash
git commit -m "$(cat <<'EOF'
<first line: imperative summary>

- <bullet point for each logical change>

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

**Commit message guidelines:**
- First line: imperative, under 72 chars, summarizes the change
- Body (after blank line): bullet points for each logical change
- Always end with the `Co-Authored-By` trailer
- Match the style of recent commits in the repo

### 5. Confirm

Tell the user:
- Commit hash and message
- What was updated in TASKS.md (tasks moved)

## Rules

- **One commit per invocation.** Bundle all related changes (code + docs) into a single commit.
- **Always update both TASKS.md and progress.md.** Even if changes are minor, the audit trail matters.
- **Never commit secrets.** Skip `.env`, credentials, tokens. Warn the user if they're in the diff.
- **Do not push.** Reflector/autopilot work is local-only by convention. The human decides when to push.
- **Co-author trailer is mandatory.** Always include it.
