#!/usr/bin/env python3
"""Autopilot hook for OpenAI Codex.

Codex-side counterpart to ``autocc-hooks.py``. Kept as a separate file (rather
than sharing helpers via import) so each provider's wire format stays legible
in one place — the helpers are duplicated verbatim. Per ``goal.md`` the
non-goal explicitly rules out a generic plugin SDK that would let a 3rd
provider tap in.

When ``.autocc/flag`` exists in the project root, this script auto-decides on
the three Codex hook events that have analogs in autocc's Claude wire-up:

- ``pre_tool_use``      — no-op (Codex has no ``AskUserQuestion`` /
                          ``EnterPlanMode`` tool to match against; the
                          matcher pattern never fires on Codex).
- ``permission_request`` — auto-allow via Codex's wire shape:
                          ``{"permissionDecision":"allow",
                            "permissionDecisionReason": "AUTOPILOT: …"}``.
                          The Codex binary rejects unsupported variants by
                          string match (``PermissionRequest hook returned
                          unsupported …`` per ``docs/codex-mapping.md`` §2a),
                          so the shape is load-bearing.
- ``stop``              — block idle to keep Codex working; respects
                          ``stop_hook_active`` to avoid loops. Always emits
                          a non-empty ``reason`` when blocking (Codex rejects
                          ``decision:block`` without a non-empty reason).

The two Claude hook events with no Codex analog (``elicitation``,
``post_compact``) are accepted defensively as argv values and emit ``{}`` —
if the installer accidentally wires them, the dispatcher gets a clean no-op
rather than a crash.

PermissionRequest decisions are logged to ``.autocc/decisions.log``.

Usage (in plugin ``hooks.json``)::

  python3 ${PLUGIN_ROOT}/hooks/autocc-hooks-codex.py <hook_type>

Where ``hook_type`` is the CamelCase event name Codex passes through (e.g.
``PreToolUse``, ``PermissionRequest``, ``Stop``). The script also accepts
snake_case (``pre_tool_use`` etc.) — Codex's own ``HookEventName`` enum is
snake_case internally, and tests pipe the snake_case form to verify the
script tolerates both.
"""

import json
import os
import re
import sys
from datetime import datetime

AUTOPILOT_DIR = ".autocc"
FLAG_FILE = "flag"
LOG_FILE = "decisions.log"


def main():
    hook_input = json.load(sys.stdin)
    # Project-root resolution chain. Codex's binary passes ``PLUGIN_ROOT`` /
    # ``CLAUDE_PLUGIN_ROOT`` to hook processes, but those point at the
    # **plugin install directory** (``$CODEX_HOME/plugins/cache/<mp>/<name>/
    # <version>/``), NOT the project root — TB-9's live smoke surfaced this:
    # codex fired ``Stop`` against autocc, the hook resolved
    # ``project_dir`` to the plugin install dir, found no
    # ``.autocc/flag`` there, and silently no-op'd. So PLUGIN_ROOT is
    # demoted to a low-priority fallback (kept for synthetic-test
    # compatibility) and the real anchors come first:
    #
    #   AUTOCC_PROJECT_DIR  — autocc's own override, honored across hooks +
    #                         skills (see skills/*/SKILL.md's PWD chain).
    #   CLAUDE_PROJECT_DIR  — Claude Code's project-dir env var; honored for
    #                         parity with autocc-hooks.py.
    #   CODEX_PROJECT_DIR   — Codex's planned project-dir env var (not yet
    #                         set by the 0.132 binary, but read defensively).
    #   hook_input["cwd"]   — Codex puts the session cwd on stdin; this is
    #                         the project root when codex was launched with
    #                         ``-C <project>``.
    #   PLUGIN_ROOT / CLAUDE_PLUGIN_ROOT — legacy fallbacks (incorrect for
    #                         real codex but synthetic unit tests rely on
    #                         them as a project-root stand-in).
    #   os.getcwd()         — last-resort default.
    project_dir = (
        os.environ.get("AUTOCC_PROJECT_DIR")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("CODEX_PROJECT_DIR")
        or hook_input.get("cwd")
        or os.environ.get("PLUGIN_ROOT")
        or os.environ.get("CLAUDE_PLUGIN_ROOT")
        or os.getcwd()
    )
    hook_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    # Normalize the event name. Codex's binary uses snake_case internally
    # (HookEventName::PreToolUse → "pre_tool_use") but the hooks.json
    # convention is CamelCase. Strip the difference so the dispatch table
    # matches either form.
    norm = hook_type.replace("_", "").lower()

    if norm == "stop":
        handle_stop(project_dir, hook_input)
        return

    if norm == "pretooluse":
        # Codex doesn't ship an AskUserQuestion or EnterPlanMode tool, so the
        # matcher autocc wires (mirroring the Claude install) never fires on
        # Codex. The handler still has to parse stdin without crashing — the
        # dispatcher may invoke it anyway depending on how the matcher is
        # interpreted on a future Codex version. Always no-op.
        output({})
        return

    if norm == "permissionrequest":
        handle_permission_request(project_dir, hook_input)
        return

    if norm in ("elicitation", "postcompact"):
        # Codex emits no such hook event (HookEventName enum has no
        # Elicitation / PostCompact variant — docs/codex-mapping.md §2a).
        # Accept defensively: if the installer wires them by accident, no-op
        # cleanly instead of crashing the session. Do NOT attempt the
        # Claude-shape additionalContext injection — Codex's
        # PreToolUse/etc. binary rejects unsupported additionalContext.
        output({})
        return

    # Unknown event — no-op.
    output({})


def handle_permission_request(project_dir, hook_input):
    """Auto-allow tool permissions when autopilot is on, using Codex's wire shape.

    Codex's permission_request handler parses ``permissionDecision`` (one of
    ``allow`` / ``deny`` / ``ask``) and ``permissionDecisionReason`` from
    stdout. The Claude-shape ``hookSpecificOutput.decision.behavior`` field is
    NOT recognized — emitting it would surface as
    ``PermissionRequest hook returned unsupported …`` in the Codex log and
    fall through to interactive approval, killing the autopilot loop.
    """
    flag_path = os.path.join(project_dir, AUTOPILOT_DIR, FLAG_FILE)
    if not os.path.exists(flag_path):
        output({})
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    summary = format_tool_summary(tool_name, tool_input)
    log_decision(project_dir, f"PermissionRequest({tool_name})", summary, "allow")
    output({
        "permissionDecision": "allow",
        "permissionDecisionReason": (
            "AUTOPILOT: Human is away. Auto-allowing tool call. "
            "See .autocc/decisions.log for the audit trail."
        ),
    })


def _find_tasks_file(project_dir):
    """Find the task file path by reading CLAUDE.md Autopilot section, fallback to TASKS.md."""
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if os.path.exists(claude_md):
        try:
            with open(claude_md) as f:
                content = f.read()
            m = re.search(r"[Tt]ask list:\s*`([^`]+)`", content)
            if m:
                return os.path.join(project_dir, m.group(1))
        except OSError:
            pass
    return os.path.join(project_dir, "TASKS.md")


def _board_is_empty(project_dir):
    """Check if TASKS.md Active/Ready/Backlog sections are all empty."""
    tasks_path = _find_tasks_file(project_dir)
    if not os.path.exists(tasks_path):
        return True
    try:
        with open(tasks_path) as f:
            content = f.read()
        for section in ("## Active", "## Ready", "## Backlog"):
            idx = content.find(section)
            if idx == -1:
                continue
            next_idx = content.find("\n## ", idx + len(section))
            block = content[idx:next_idx] if next_idx != -1 else content[idx:]
            if "- [ ]" in block:
                return False
        return True
    except OSError:
        return True


def _remove_flag(flag_path):
    try:
        os.unlink(flag_path)
    except OSError:
        pass


def handle_stop(project_dir, hook_input):
    """Block idle when autopilot is on, to keep Codex working.

    The Codex binary rejects ``decision:block`` with an empty / missing
    ``reason`` (per ``docs/codex-mapping.md`` §2a: ``Stop hook returned
    decision:block without a non-empty reason``). Always emit a substantive
    reason when blocking; on the terminal paths (already nudged, or board
    empty) drop the flag and emit ``{}`` so Codex stops naturally.

    Every Stop decision is logged to ``.autocc/decisions.log`` so the
    audit trail captures hook firings beyond just PermissionRequest — under
    ``--dangerously-bypass-approvals-and-sandbox`` codex never issues
    permission requests, so Stop is the universal "hook fired" signal a
    live smoke or operator can grep for.
    """
    flag_path = os.path.join(project_dir, AUTOPILOT_DIR, FLAG_FILE)
    if not os.path.exists(flag_path):
        output({})
        return

    if hook_input.get("stop_hook_active", False):
        # Codex was already nudged and stopped again — genuinely nothing to do.
        _remove_flag(flag_path)
        log_decision(project_dir, "Stop", "stop_hook_active=true; flag dropped", "stop")
        output({})
        return

    if _board_is_empty(project_dir):
        _remove_flag(flag_path)
        log_decision(project_dir, "Stop", "board empty; flag dropped", "stop")
        output({})
        return

    log_decision(project_dir, "Stop", "board has work; nudging to /reflector", "block")
    output({
        "decision": "block",
        "reason": (
            "AUTOPILOT: Human is away. Do not stop — invoke /reflector to find and "
            "work on the next task. If you have genuinely exhausted all tasks after "
            "two full passes, you may stop."
        ),
    })


def format_tool_summary(tool_name, tool_input):
    if tool_name == "Bash":
        return tool_input.get("command", str(tool_input))
    elif tool_name in ("Edit", "Write", "Read"):
        return tool_input.get("file_path", str(tool_input))
    elif tool_name == "Agent":
        return tool_input.get("description", str(tool_input))
    else:
        return str(tool_input)[:200]


def log_decision(cwd, hook_type, detail, decision):
    log_path = os.path.join(cwd, AUTOPILOT_DIR, LOG_FILE)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detail_clean = detail.replace("\n", " ")[:300]
    entry = f"[{timestamp}] {hook_type} -> {decision} | {detail_clean}\n"
    try:
        with open(log_path, "a") as f:
            f.write(entry)
    except OSError:
        pass


def output(data):
    json.dump(data, sys.stdout)


if __name__ == "__main__":
    main()
