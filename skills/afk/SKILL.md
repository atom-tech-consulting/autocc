---
description: "Turn on autopilot and start autonomous work. Use when going AFK — enables auto-approval of permissions and kicks off /reflector."
user_invocable: true
---

# AFK

One-command setup for unattended operation. Enables autopilot (auto-approves permissions, skips questions/plan mode) and starts the reflector work loop.

## Project-root resolution

This skill writes the autopilot flag at the project root. Resolve the
root with this provider-neutral fallback chain (first set wins):

    PROJECT_DIR="${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}"

`AUTOCC_PROJECT_DIR` is the portable override; `CLAUDE_PROJECT_DIR`
covers Claude Code (set by the harness, stable across subdirectory
`cd`s); `CODEX_PROJECT_DIR` covers Codex (set by the autocc Codex
plugin); `$PWD` is the last-resort fallback when neither harness
exports a project-root variable.

## Steps

When this skill is invoked:

1. **Enable autopilot** — create the flag at the session root:
   ```bash
   PROJECT_DIR="${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}"
   mkdir -p "$PROJECT_DIR/.autocc" && touch "$PROJECT_DIR/.autocc/flag"
   ```
2. **Confirm** — briefly tell the user: "Autopilot on. Starting reflector. `rm .autocc/flag` or send a message to stop."
3. **Start reflector** — invoke `/reflector` (with any arguments passed to `/afk`, e.g. `/afk tests` becomes `/reflector tests`)

That's it. Do NOT ask for confirmation. The user invoked `/afk` — they want to leave.

## Returning from AFK

When the user sends any message while reflector is running:
- Respond to their message
- If they say "back", "stop", or similar:
  1. Resolve `PROJECT_DIR` via the same fallback chain above, then run
     `rm "$PROJECT_DIR/.autocc/flag"` to turn off autopilot
  2. Stop the reflector loop (do not call GO TO 1 after the current task)
- Otherwise, answer their question and resume the loop
