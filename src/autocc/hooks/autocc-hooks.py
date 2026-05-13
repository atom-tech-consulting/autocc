#!/usr/bin/env python3
"""Autopilot hook for Claude Code.

When .autocc/flag exists in the project root, auto-decides on:
- PermissionRequest: auto-allow
- PreToolUse(AskUserQuestion): deny with "decide yourself"
- PreToolUse(EnterPlanMode): deny with "skip plan mode"
- Elicitation: deny with "skip, proceed without input"
- Stop: block idle — keep Claude working; respects stop_hook_active to avoid loops
- PostCompact: inject latest checkpoint as additionalContext + resume instructions

All decisions (except PostCompact/Stop) logged to .autocc/decisions.log.

Usage (in settings.json hooks):
  python3 ~/.claude/hooks/autocc-hooks.py <hook_type>

Where hook_type is: PermissionRequest, PreToolUse, Elicitation, Stop, PostCompact
"""

import json
import os
import re
import sys
from datetime import datetime

AUTOPILOT_DIR = ".autocc"
FLAG_FILE = "flag"
LOG_FILE = "decisions.log"
CHECKPOINTS_DIR = "checkpoints"


def main():
    hook_input = json.load(sys.stdin)
    # CLAUDE_PROJECT_DIR is set by Claude Code to the session root — stable
    # regardless of which subdirectory the agent navigates to during the session.
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", hook_input.get("cwd", os.getcwd()))
    hook_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    if hook_type == "PostCompact":
        handle_post_compact(project_dir)
        return

    if hook_type == "Stop":
        handle_stop(project_dir, hook_input)
        return

    # Check autopilot flag
    flag_path = os.path.join(project_dir, AUTOPILOT_DIR, FLAG_FILE)
    if not os.path.exists(flag_path):
        output({})
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    if tool_name == "AskUserQuestion":
        question = tool_input.get("question", str(tool_input))
        decision = "deny"
        reason = (
            "AUTOPILOT: Human is away. Make your best judgment and proceed. "
            "Document your decision and reasoning by appending to "
            ".autocc/decisions.log."
        )
        log_decision(project_dir, "AskUserQuestion", question, decision)

    elif tool_name == "EnterPlanMode":
        decision = "deny"
        reason = (
            "AUTOPILOT: Human is away. Skip plan mode and proceed directly "
            "with implementation. Document your approach by appending to "
            ".autocc/decisions.log."
        )
        log_decision(project_dir, "EnterPlanMode", str(tool_input)[:200], decision)

    elif hook_type == "Elicitation":
        decision = "deny"
        reason = (
            "AUTOPILOT: Human is away. Skip this input request and proceed "
            "with safe defaults. Document what was skipped by appending to "
            ".autocc/decisions.log."
        )
        log_decision(project_dir, "Elicitation", str(tool_input)[:200], decision)

    elif hook_type == "PermissionRequest":
        summary = format_tool_summary(tool_name, tool_input)
        log_decision(project_dir, f"PermissionRequest({tool_name})", summary, "allow")
        output({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "allow"
                }
            }
        })
        return

    else:
        output({})
        return

    output({"decision": decision, "reason": reason})


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
    """Block idle when autopilot is on, to keep Claude working."""
    flag_path = os.path.join(project_dir, AUTOPILOT_DIR, FLAG_FILE)
    if not os.path.exists(flag_path):
        output({})
        return

    if hook_input.get("stop_hook_active", False):
        # Claude was already nudged and stopped again — genuinely nothing to do.
        _remove_flag(flag_path)
        output({})
        return

    if _board_is_empty(project_dir):
        _remove_flag(flag_path)
        output({})
        return

    output({
        "decision": "block",
        "reason": (
            "AUTOPILOT: Human is away. Do not stop — invoke /reflector to find and "
            "work on the next task. If you have genuinely exhausted all tasks after "
            "two full passes, you may stop."
        ),
    })


def handle_post_compact(project_dir):
    """Inject latest checkpoint as additionalContext if autopilot is on."""
    flag_path = os.path.join(project_dir, AUTOPILOT_DIR, FLAG_FILE)
    if not os.path.exists(flag_path):
        output({})
        return

    checkpoints_dir = os.path.join(project_dir, AUTOPILOT_DIR, CHECKPOINTS_DIR)
    checkpoint_content = None

    if os.path.isdir(checkpoints_dir):
        files = sorted(
            [f for f in os.listdir(checkpoints_dir) if f.endswith(".md")],
            reverse=True,
        )
        if files:
            try:
                with open(os.path.join(checkpoints_dir, files[0])) as f:
                    checkpoint_content = f.read()
            except OSError:
                pass

    if checkpoint_content:
        context_msg = (
            f"AUTOPILOT RESUME: Compaction complete. Latest checkpoint:\n\n"
            f"{checkpoint_content}\n\n"
            f"Resume /reflector immediately."
        )
    else:
        context_msg = (
            "AUTOPILOT RESUME: Compaction complete. No checkpoint found — "
            "check progress.md and resume /reflector."
        )

    output({
        "hookSpecificOutput": {
            "hookEventName": "PostCompact",
            "additionalContext": context_msg,
        }
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
