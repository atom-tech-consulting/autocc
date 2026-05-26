## Goal

Current focus: OpenAI Codex provider support. The `commit-changes`
skill currently uses the trailer

    Co-Authored-By: ${AUTOCC_AGENT_NAME:-Claude} <${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com}>

The hard-coded defaults `Claude` / `noreply@anthropic.com` are
correct under `autocc install --agent claude` but misleading
under `autocc install --agent codex` — every Codex-authored
commit ends up trailing `Co-Authored-By: Claude
<noreply@anthropic.com>` unless the operator manually exports
the override env vars. This task makes the trailer identity
provider-aware so the default-when-unset reflects the install
branch.

Why now: The `--agent codex` install branch is live and shipping
commits authored by Codex sessions, but every such commit
attributes co-authorship to "Claude" by default. That is a
user-visible correctness bug on every Codex commit: the trailer
is a permanent git-log artifact, so the gap accumulates fast.
Fixing it now — before any production Codex run lands a mass of
mis-attributed commits — is much cheaper than rewriting commit
history later. This closes a small but cumulative gap inside
the "Skills are portable across providers" Done-when bullet.

## Scope

Pick ONE of the following two designs at implementation time
(whichever lands cleaner against the existing installer
shape) and document the choice in the commit message:

Option A — installer-set env exports:
- In `src/autocc/installer.py`'s Codex branch, write
  `AUTOCC_AGENT_NAME=Codex` and
  `AUTOCC_AGENT_EMAIL=noreply@openai.com` into the Codex
  plugin's environment-bootstrap file (whichever Codex
  config surface the installer already writes; if none,
  add a small `env.sh` or equivalent the plugin sources).
- The Claude install branch is unchanged; its existing
  no-export behavior keeps the current `Claude` /
  `noreply@anthropic.com` defaults in `commit-changes`.

Option B — provider-aware skill default:
- In `skills/commit-changes/SKILL.md`, replace the
  hard-coded `:-Claude` / `:-noreply@anthropic.com`
  defaults with a chain that prefers `$AUTOCC_AGENT_NAME`,
  then a provider sniff (e.g. `[ -n "$CODEX_PROJECT_DIR" ]
  && echo Codex || echo Claude`), with the same pattern
  for the email default.
- The installer is unchanged; the skill text alone makes
  the default provider-aware at commit time.

Option B is preferred (no installer churn, no new file on
disk under `~/plugins/autocc/`), but Option A is acceptable
if the skill-only approach can't be expressed in pure
shell parameter expansion without breaking POSIX. Document
the chosen option's tradeoff in the commit message.

In either case:
- Add `tests/test_commit_changes_defaults.py` (or extend
  `tests/test_skills_portable.py`) with cases pinning:
  (1) `AUTOCC_AGENT_NAME=` unset under a Codex-style
      env → trailer reads `Codex` / `noreply@openai.com`.
  (2) `AUTOCC_AGENT_NAME=` unset under a Claude-style
      env → trailer reads `Claude` / `noreply@anthropic.com`
      (regression check; no behavior change for the
      Claude path).
  (3) `AUTOCC_AGENT_NAME=Alice AUTOCC_AGENT_EMAIL=a@b`
      always wins over the default (override still works
      under both providers).
- Update `docs/codex-mapping.md` §3a's env-var contract
  paragraph to document the new provider-aware default.
- Update the README/ARCHITECTURE Codex coverage IF AND
  ONLY IF the parallel docs task hasn't landed yet —
  otherwise leave docs to that task and don't conflict
  on the file.

## Design

Keep the `$AUTOCC_AGENT_NAME` / `$AUTOCC_AGENT_EMAIL`
override surface intact — operators who set them
explicitly get exactly what they set, under both
providers. Only the "neither env var is set" default
changes branch-aware.

No new abstraction layer (matches goal.md Non-goal:
"Generic provider plugin SDK"). No new MCP server. No
PyPI work. Pure additive parameterization on the existing
env-var fallback pattern that `commit-changes` already uses.

## Verification

- `uv run pytest -q tests/test_commit_changes_defaults.py` — new test file (or extended `tests/test_skills_portable.py`) passes the three default-trailer cases.
- `uv run pytest -q` — full pytest suite passes (regression gate; no other test broken).
- `grep -qE "Codex|CODEX_PROJECT_DIR|noreply@openai" skills/commit-changes/SKILL.md src/autocc/installer.py` — Codex-side default identity (or the provider-sniff branch) appears in either the skill or the installer.
- `grep -q "AUTOCC_AGENT_NAME" docs/codex-mapping.md` — the env-var contract paragraph still documents the override surface.
- `bash -c 'cd $(mktemp -d) && AUTOCC_AGENT_NAME=Override AUTOCC_AGENT_EMAIL=o@v.test bash -c "echo \"Co-Authored-By: \${AUTOCC_AGENT_NAME:-Claude} <\${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com}>\"" | grep -q "Co-Authored-By: Override <o@v.test>"'` — basic shell-expansion sanity check that the override path still beats any default.
- Prose: `git log -1 --format=%B` on the commit produced by this task includes a one-line note saying whether Option A or Option B was chosen and why (judge confirms by reading the commit message).

## Out of scope

- Rewriting historical commits to retroactively fix the trailer (one-way; not worth it).
- Adding a `--co-author` CLI flag to `autocc install` (env-var override is the existing surface; don't grow a second one).
- Generalizing to N providers' trailer identities (Non-goals: no generic provider SDK; only Claude + Codex are concrete today).
- Touching the `afk` / `reflector` env-var fallback chain — only the `commit-changes` trailer identity changes here.
- Updating README/ARCHITECTURE if the parallel docs task has already landed those Codex sections — let that task own the file.
- Changing the override semantics: `AUTOCC_AGENT_NAME=` set to empty string vs unset is out of scope; the existing `${VAR:-default}` semantics carry forward.
