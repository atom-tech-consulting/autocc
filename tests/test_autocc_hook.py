"""Unit tests for src/autocc/hooks/autocc-hooks.py.

Each test runs the hook as a subprocess with synthetic stdin and asserts the
parsed stdout JSON. This matches how Claude Code invokes the hook in
production, and covers the decision logic for all five registered events
under both flag-present and flag-absent conditions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "src" / "autocc" / "hooks" / "autocc-hooks.py"
TASKBOARD_FULL = """# Tasks

## Active

## Ready
- [ ] **TB-1** **Some task** — desc

## Backlog

## Complete

## Frozen
"""

TASKBOARD_EMPTY = """# Tasks

## Active

## Ready

## Backlog

## Complete
- [x] **TB-1** **Done task** — desc

## Frozen
"""


def _run_hook(event: str, payload: dict, project_dir: Path) -> dict:
    """Invoke autocc-hooks.py and parse the JSON output."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    result = subprocess.run(
        [sys.executable, str(HOOK), event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, f"hook exited {result.returncode}\n{result.stderr}"
    return json.loads(result.stdout) if result.stdout.strip() else {}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Empty project directory — no .autocc/, no flag, no TASKS.md."""
    return tmp_path


@pytest.fixture
def autopilot_project(tmp_path: Path) -> Path:
    """Project with .autocc/flag set + a TASKS.md that has open work."""
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    (tmp_path / "TASKS.md").write_text(TASKBOARD_FULL)
    return tmp_path


# ---------------------------------------------------------------------------
# Flag absent → all events return no-op {}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("event,payload", [
    ("PreToolUse", {"tool_name": "AskUserQuestion", "tool_input": {"question": "q?"}}),
    ("PreToolUse", {"tool_name": "EnterPlanMode", "tool_input": {}}),
    ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}),
    ("PermissionRequest", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
    ("Elicitation", {"input": "something"}),
])
def test_flag_absent_returns_noop(project, event, payload):
    assert _run_hook(event, payload, project) == {}


def test_stop_flag_absent_returns_noop(project):
    """Stop hook with no flag — let Claude stop naturally."""
    assert _run_hook("Stop", {"stop_hook_active": False}, project) == {}


def test_postcompact_flag_absent_returns_noop(project):
    assert _run_hook("PostCompact", {}, project) == {}


# ---------------------------------------------------------------------------
# PreToolUse(AskUserQuestion) — deny + log when flag is set
# ---------------------------------------------------------------------------

def test_ask_user_question_denied_under_autopilot(autopilot_project):
    payload = {"tool_name": "AskUserQuestion", "tool_input": {"question": "Pick a color"}}
    out = _run_hook("PreToolUse", payload, autopilot_project)
    assert out["decision"] == "deny"
    assert "best judgment" in out["reason"]
    assert "decisions.log" in out["reason"]
    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "AskUserQuestion -> deny" in log
    assert "Pick a color" in log


def test_enter_plan_mode_denied_under_autopilot(autopilot_project):
    payload = {"tool_name": "EnterPlanMode", "tool_input": {"plan": "step 1..."}}
    out = _run_hook("PreToolUse", payload, autopilot_project)
    assert out["decision"] == "deny"
    assert "plan mode" in out["reason"].lower()
    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "EnterPlanMode -> deny" in log


def test_other_pretool_use_under_autopilot_is_noop(autopilot_project):
    """The PreToolUse matcher only targets AskUserQuestion + EnterPlanMode.
    Other tools (Bash, Edit, Write, ...) should pass through unchanged."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    assert _run_hook("PreToolUse", payload, autopilot_project) == {}


# ---------------------------------------------------------------------------
# Elicitation — deny + log when flag is set
# ---------------------------------------------------------------------------

def test_elicitation_denied_under_autopilot(autopilot_project):
    payload = {"input": "what's your favorite letter?"}
    out = _run_hook("Elicitation", payload, autopilot_project)
    assert out["decision"] == "deny"
    assert "safe defaults" in out["reason"]
    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "Elicitation -> deny" in log


# ---------------------------------------------------------------------------
# PermissionRequest — auto-allow when flag is set
# ---------------------------------------------------------------------------

def test_permission_request_auto_allowed_under_autopilot(autopilot_project):
    payload = {"tool_name": "Bash", "tool_input": {"command": "uv run pytest -q"}}
    out = _run_hook("PermissionRequest", payload, autopilot_project)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PermissionRequest"
    assert spec["decision"] == {"behavior": "allow"}
    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "PermissionRequest(Bash) -> allow" in log
    assert "uv run pytest -q" in log


def test_permission_request_logs_edit_path(autopilot_project):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/foo.py"}}
    _run_hook("PermissionRequest", payload, autopilot_project)
    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "PermissionRequest(Edit) -> allow" in log
    assert "/tmp/foo.py" in log


# ---------------------------------------------------------------------------
# Stop — block when work remains, allow when board empty or already nudged
# ---------------------------------------------------------------------------

def test_stop_blocks_when_board_has_open_work(autopilot_project):
    out = _run_hook("Stop", {"stop_hook_active": False}, autopilot_project)
    assert out["decision"] == "block"
    assert "/reflector" in out["reason"]
    # Flag should NOT be removed — agent has more work to do
    assert (autopilot_project / ".autocc" / "flag").exists()


def test_stop_allows_when_already_nudged(autopilot_project):
    """If we already returned block once (stop_hook_active=True), give up
    and let the agent stop. Otherwise we'd loop forever."""
    out = _run_hook("Stop", {"stop_hook_active": True}, autopilot_project)
    assert out == {}
    # Flag IS removed — autopilot terminates
    assert not (autopilot_project / ".autocc" / "flag").exists()


def test_stop_allows_when_board_is_empty(tmp_path: Path):
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    (tmp_path / "TASKS.md").write_text(TASKBOARD_EMPTY)
    out = _run_hook("Stop", {"stop_hook_active": False}, tmp_path)
    assert out == {}
    # Empty board → autopilot terminates, flag removed
    assert not (tmp_path / ".autocc" / "flag").exists()


def test_stop_allows_when_tasks_md_missing(tmp_path: Path):
    """No TASKS.md → treat as empty board, allow stop."""
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    out = _run_hook("Stop", {"stop_hook_active": False}, tmp_path)
    assert out == {}
    assert not (tmp_path / ".autocc" / "flag").exists()


def test_stop_resolves_task_list_path_from_claude_md(tmp_path: Path):
    """If CLAUDE.md ## Autopilot points to a custom path, the hook follows it."""
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    (tmp_path / "CLAUDE.md").write_text(
        "## Autopilot\n- Task list: `docs/board.md`\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "board.md").write_text(TASKBOARD_FULL)
    out = _run_hook("Stop", {"stop_hook_active": False}, tmp_path)
    assert out["decision"] == "block"
    # And work is found, so flag remains
    assert (tmp_path / ".autocc" / "flag").exists()


# ---------------------------------------------------------------------------
# PostCompact — inject latest checkpoint as additionalContext
# ---------------------------------------------------------------------------

def test_postcompact_with_checkpoint_injects_content(autopilot_project):
    checkpoints = autopilot_project / ".autocc" / "checkpoints"
    checkpoints.mkdir()
    # Filenames are ISO timestamps; lex sort = chronological.
    (checkpoints / "2026-05-12T10-00-00.md").write_text("# older checkpoint")
    (checkpoints / "2026-05-12T12-00-00.md").write_text("# Latest state\n- TB-3 done")
    out = _run_hook("PostCompact", {}, autopilot_project)
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == "PostCompact"
    ctx = spec["additionalContext"]
    assert "AUTOPILOT RESUME" in ctx
    assert "Latest state" in ctx
    assert "TB-3 done" in ctx
    assert "Resume /reflector" in ctx


def test_postcompact_without_checkpoint_still_resumes(autopilot_project):
    out = _run_hook("PostCompact", {}, autopilot_project)
    spec = out["hookSpecificOutput"]
    ctx = spec["additionalContext"]
    assert "AUTOPILOT RESUME" in ctx
    assert "No checkpoint found" in ctx


# ---------------------------------------------------------------------------
# CLAUDE_PROJECT_DIR is honored over cwd
# ---------------------------------------------------------------------------

def test_hook_uses_claude_project_dir_not_cwd(tmp_path: Path, autopilot_project):
    """Even when called from an unrelated cwd, the hook looks at
    $CLAUDE_PROJECT_DIR for the flag — this is how it survives the agent
    cd-ing into subdirs."""
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(autopilot_project)}
    result = subprocess.run(
        [sys.executable, str(HOOK), "PreToolUse"],
        input=json.dumps({"tool_name": "AskUserQuestion", "tool_input": {"question": "?"}}),
        capture_output=True,
        text=True,
        env=env,
        cwd=other_cwd,
        timeout=10,
    )
    assert result.returncode == 0
    out = json.loads(result.stdout)
    assert out["decision"] == "deny"
