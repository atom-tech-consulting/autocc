"""Unit tests for src/autocc/hooks/autocc-hooks-codex.py.

Each test runs the Codex hook as a subprocess with synthetic stdin and asserts
the parsed stdout JSON. This matches how Codex invokes the hook in production:
the codex binary spawns the configured ``command`` with the event name as a
positional argv and pipes the hook input JSON on stdin.

The Codex wire format is intentionally different from Claude's
(``permissionDecision: allow`` vs ``hookSpecificOutput.decision.behavior:
allow``); these tests pin the Codex shape so the script can't silently
regress to Claude's shape — the Codex binary rejects unsupported variants
by string match (`PermissionRequest hook returned unsupported …` per
docs/codex-mapping.md §2a), which would break the autopilot loop.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "autocc"
    / "hooks"
    / "autocc-hooks-codex.py"
)

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
    """Invoke autocc-hooks-codex.py and parse the JSON output.

    The script reads ``cwd`` from the stdin payload as one of its fallbacks
    for locating the project root (after PLUGIN_ROOT / CLAUDE_PLUGIN_ROOT env
    vars, which we deliberately leave unset here so the cwd-on-stdin path is
    exercised — that's the contract Codex itself uses when spawning hooks
    in a project context).
    """
    enriched = {"cwd": str(project_dir), **payload}
    # Scrub the plugin env vars to avoid bleed-through from a real Codex
    # session run under the same shell — the test wants the cwd fallback.
    env = {k: v for k, v in os.environ.items() if k not in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")}
    result = subprocess.run(
        [sys.executable, str(HOOK), event],
        input=json.dumps(enriched),
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
# Flag absent → no-op (every event must safely no-op)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "event,payload",
    [
        ("pre_tool_use", {"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        ("pre_tool_use", {"tool_name": "AskUserQuestion", "tool_input": {"question": "q?"}}),
        ("permission_request", {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}),
        ("elicitation", {"input": "something"}),
        ("post_compact", {}),
    ],
)
def test_flag_absent_returns_noop(project, event, payload):
    """Without the autopilot flag, every event must return ``{}`` — no
    decision, no log write, no crash."""
    assert _run_hook(event, payload, project) == {}


def test_stop_flag_absent_returns_noop(project):
    """Stop hook with no flag — let Codex stop naturally."""
    assert _run_hook("stop", {"stop_hook_active": False}, project) == {}


# ---------------------------------------------------------------------------
# pre_tool_use — Codex has no AskUserQuestion/EnterPlanMode tool; always no-op
# ---------------------------------------------------------------------------


def test_pretooluse_under_autopilot_is_noop(autopilot_project):
    """Codex doesn't ship AskUserQuestion / EnterPlanMode tools — the matcher
    autocc wires never fires in practice. Even when the script IS invoked
    (e.g. from a defensive matcher-less install), it must no-op cleanly."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    assert _run_hook("pre_tool_use", payload, autopilot_project) == {}


def test_pretooluse_with_askuserquestion_is_noop(autopilot_project):
    """Defensive: even if some future Codex tool surface a tool named
    AskUserQuestion and the matcher does fire, the script just no-ops —
    matches the briefing's 'must still handle the pre_tool_use event JSON
    without crashing' contract."""
    payload = {"tool_name": "AskUserQuestion", "tool_input": {"question": "Pick a color"}}
    assert _run_hook("pre_tool_use", payload, autopilot_project) == {}


def test_pretooluse_camelcase_is_noop(autopilot_project):
    """The hooks.json convention is CamelCase; the script accepts both
    casings."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    assert _run_hook("PreToolUse", payload, autopilot_project) == {}


# ---------------------------------------------------------------------------
# permission_request — Codex wire shape: permissionDecision: allow
# ---------------------------------------------------------------------------


def test_permission_request_emits_codex_allow_shape(autopilot_project):
    """The Codex binary parses ``permissionDecision: allow`` from stdout.
    The Claude shape (``hookSpecificOutput.decision.behavior: allow``) would
    surface as ``PermissionRequest hook returned unsupported …`` and break
    the autopilot loop. Pin the Codex shape."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "uv run pytest -q"}}
    out = _run_hook("permission_request", payload, autopilot_project)
    assert out["permissionDecision"] == "allow"
    assert "AUTOPILOT" in out["permissionDecisionReason"]
    # Explicitly assert we did NOT emit the Claude shape.
    assert "hookSpecificOutput" not in out

    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "PermissionRequest(Bash) -> allow" in log
    assert "uv run pytest -q" in log


def test_permission_request_flag_absent_returns_empty(project):
    """Without the autopilot flag, even permission_request must return ``{}``
    so Codex falls through to its normal approval flow."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert _run_hook("permission_request", payload, project) == {}


def test_permission_request_camelcase_accepted(autopilot_project):
    """Codex's hooks.json convention passes CamelCase argv (e.g.
    ``PermissionRequest``). Script accepts either casing."""
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/foo.py"}}
    out = _run_hook("PermissionRequest", payload, autopilot_project)
    assert out["permissionDecision"] == "allow"


def test_permission_request_logs_edit_path(autopilot_project):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/foo.py"}}
    _run_hook("permission_request", payload, autopilot_project)
    log = (autopilot_project / ".autocc" / "decisions.log").read_text()
    assert "PermissionRequest(Edit) -> allow" in log
    assert "/tmp/foo.py" in log


# ---------------------------------------------------------------------------
# stop — block when work remains, allow when board empty or already nudged
# ---------------------------------------------------------------------------


def test_stop_blocks_when_board_has_open_work(autopilot_project):
    """Stop with flag set + non-empty board → ``decision: block`` with a
    non-empty ``reason``. Codex's binary explicitly rejects ``block``
    without a reason (`Stop hook returned decision:block without a
    non-empty reason`)."""
    out = _run_hook("stop", {"stop_hook_active": False}, autopilot_project)
    assert out["decision"] == "block"
    assert out["reason"], "Codex rejects decision:block without a non-empty reason"
    assert "/reflector" in out["reason"]
    # Flag must NOT be removed — agent has more work to do.
    assert (autopilot_project / ".autocc" / "flag").exists()


def test_stop_with_stop_hook_active_drops_flag_and_emits_empty(autopilot_project):
    """If Codex was already nudged (stop_hook_active=True) and stopped again,
    give up and let it stop. The flag is removed so future stops are
    natural; the response is ``{}`` so Codex doesn't loop forever.

    (This is the exact case the briefing's prose verification calls out.)
    """
    out = _run_hook("stop", {"stop_hook_active": True}, autopilot_project)
    assert out == {}
    assert not (autopilot_project / ".autocc" / "flag").exists(), (
        "stop_hook_active=True must drop the autopilot flag so the next "
        "Stop returns naturally"
    )


def test_stop_allows_when_board_is_empty(tmp_path: Path):
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    (tmp_path / "TASKS.md").write_text(TASKBOARD_EMPTY)
    out = _run_hook("stop", {"stop_hook_active": False}, tmp_path)
    assert out == {}
    assert not (tmp_path / ".autocc" / "flag").exists()


def test_stop_allows_when_tasks_md_missing(tmp_path: Path):
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    out = _run_hook("stop", {"stop_hook_active": False}, tmp_path)
    assert out == {}
    assert not (tmp_path / ".autocc" / "flag").exists()


def test_stop_resolves_task_list_path_from_claude_md(tmp_path: Path):
    """If CLAUDE.md ## Autopilot points to a custom path, the hook follows it.
    Codex sessions may still keep CLAUDE.md alongside the Codex-native
    AGENTS.md; the parse path is shared."""
    (tmp_path / ".autocc").mkdir()
    (tmp_path / ".autocc" / "flag").touch()
    (tmp_path / "CLAUDE.md").write_text(
        "## Autopilot\n- Task list: `docs/board.md`\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "board.md").write_text(TASKBOARD_FULL)
    out = _run_hook("stop", {"stop_hook_active": False}, tmp_path)
    assert out["decision"] == "block"
    assert (tmp_path / ".autocc" / "flag").exists()


def test_stop_camelcase_argv_accepted(autopilot_project):
    """``Stop`` (CamelCase) and ``stop`` (snake) both route to the stop
    handler."""
    out = _run_hook("Stop", {"stop_hook_active": False}, autopilot_project)
    assert out["decision"] == "block"


# ---------------------------------------------------------------------------
# elicitation / post_compact — defensive no-op (Codex has no such event)
# ---------------------------------------------------------------------------


def test_elicitation_under_autopilot_is_noop(autopilot_project):
    """Codex's HookEventName enum has no ``Elicitation`` variant
    (docs/codex-mapping.md §2a). The script accepts the argv name
    defensively in case an installer wires it by accident, and must emit
    ``{}`` without crashing — do NOT use the Claude deny/log shape, which
    Codex would reject."""
    out = _run_hook("elicitation", {"input": "what's your favorite letter?"}, autopilot_project)
    assert out == {}


def test_post_compact_under_autopilot_is_noop(autopilot_project):
    """Codex auto-compacts but exposes no PostCompact hook event
    (docs/codex-mapping.md §2a). Script accepts the argv name defensively
    and emits ``{}`` — must not attempt the Claude-shape
    ``additionalContext`` injection, which Codex's binary rejects."""
    out = _run_hook("post_compact", {}, autopilot_project)
    assert out == {}


def test_post_compact_camelcase_is_noop(autopilot_project):
    out = _run_hook("PostCompact", {}, autopilot_project)
    assert out == {}


# ---------------------------------------------------------------------------
# Env vars — project-root resolution chain
#
# Real codex sets PLUGIN_ROOT / CLAUDE_PLUGIN_ROOT to the *plugin install
# directory*, NOT the project root (TB-9 surfaced this — the hook fired on
# Stop, resolved project_dir to the plugin install dir, found no flag, and
# silently no-op'd). The correct project anchor is one of the explicit
# ``*_PROJECT_DIR`` env vars or the cwd that codex puts on stdin. PLUGIN_ROOT
# / CLAUDE_PLUGIN_ROOT remain as low-priority fallbacks for synthetic
# contexts that set them as a project-root stand-in.
# ---------------------------------------------------------------------------


def _hook_subprocess(hook_input: dict, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    """Spawn the hook with a known env + stdin shape. Used by the resolution
    chain tests below to keep each test focused on one env-var precedence
    decision rather than re-spelling the subprocess plumbing."""
    return subprocess.run(
        [sys.executable, str(HOOK), "permission_request"],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=10,
    )


def test_autocc_project_dir_env_overrides_stdin_cwd(tmp_path: Path, autopilot_project: Path):
    """``AUTOCC_PROJECT_DIR`` is autocc's own project-anchor override and
    sits at the top of the hook's resolution chain — set by callers that
    want to pin the project root regardless of what the agent harness puts
    on stdin (e.g. the live Codex smoke at
    ``tests/smoke/test_reflector_e2e_codex.py``)."""
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR")
    }
    env["AUTOCC_PROJECT_DIR"] = str(autopilot_project)
    result = _hook_subprocess(
        {"cwd": str(other_cwd), "tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        env=env,
        cwd=other_cwd,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["permissionDecision"] == "allow"
    # Log written under autopilot_project's .autocc/, NOT other_cwd's.
    assert (autopilot_project / ".autocc" / "decisions.log").is_file()
    assert not (other_cwd / ".autocc").exists()


def test_claude_project_dir_env_honored_for_parity(tmp_path: Path, autopilot_project: Path):
    """``CLAUDE_PROJECT_DIR`` is the Claude Code project-anchor env var; the
    Codex hook honors it for parity with ``autocc-hooks.py`` so a hook
    invoked from a Claude-style harness still resolves the right
    project root."""
    other_cwd = tmp_path / "elsewhere2"
    other_cwd.mkdir()
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "AUTOCC_PROJECT_DIR", "CODEX_PROJECT_DIR")
    }
    env["CLAUDE_PROJECT_DIR"] = str(autopilot_project)
    result = _hook_subprocess(
        {"cwd": str(other_cwd), "tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        env=env,
        cwd=other_cwd,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["permissionDecision"] == "allow"
    assert (autopilot_project / ".autocc" / "decisions.log").is_file()


def test_stdin_cwd_wins_over_plugin_root_env(tmp_path: Path, autopilot_project: Path):
    """Codex sets ``PLUGIN_ROOT`` to the **plugin install directory** (e.g.
    ``$CODEX_HOME/plugins/cache/autocc/autocc/0.1.0/``), not the project
    root — this is the bug TB-9 surfaced. The hook must prefer the cwd
    Codex puts on stdin (which IS the project root when codex was launched
    with ``-C <project>``) over PLUGIN_ROOT, which would otherwise route
    flag-resolution / log-writing into the plugin's install dir and silently
    no-op the autopilot loop."""
    plugin_install_like = tmp_path / "plugin_install"
    plugin_install_like.mkdir()
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("CLAUDE_PLUGIN_ROOT", "AUTOCC_PROJECT_DIR", "CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR")
    }
    # PLUGIN_ROOT points at a NON-project dir (the plugin install) — this
    # mirrors the real-codex shape where PLUGIN_ROOT and the project root
    # diverge.
    env["PLUGIN_ROOT"] = str(plugin_install_like)
    result = _hook_subprocess(
        {"cwd": str(autopilot_project), "tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        env=env,
        cwd=autopilot_project,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["permissionDecision"] == "allow"
    # Log written under the project root from stdin, NOT under PLUGIN_ROOT.
    assert (autopilot_project / ".autocc" / "decisions.log").is_file()
    assert not (plugin_install_like / ".autocc").exists()


def test_plugin_root_env_used_as_legacy_fallback(tmp_path: Path, autopilot_project: Path):
    """When no higher-priority project-dir env var is set AND no ``cwd`` is
    on stdin, the hook falls through to ``PLUGIN_ROOT`` before ``os.getcwd``.
    This preserves backwards-compat with the synthetic contexts that set
    ``PLUGIN_ROOT`` as a project-root stand-in (and exercises the
    pre-TB-9 unit-test entry point)."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("CLAUDE_PLUGIN_ROOT", "AUTOCC_PROJECT_DIR", "CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR")
    }
    env["PLUGIN_ROOT"] = str(autopilot_project)
    other_cwd = tmp_path / "elsewhere3"
    other_cwd.mkdir()
    # No "cwd" key on stdin — forces the fallthrough to PLUGIN_ROOT.
    result = _hook_subprocess(
        {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        env=env,
        cwd=other_cwd,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["permissionDecision"] == "allow"
    assert (autopilot_project / ".autocc" / "decisions.log").is_file()


def test_claude_plugin_root_env_alias_used_as_legacy_fallback(tmp_path: Path, autopilot_project: Path):
    """``CLAUDE_PLUGIN_ROOT`` is Codex's Claude-prefixed alias for
    ``PLUGIN_ROOT`` (docs/codex-mapping.md §1c). Same legacy-fallback
    semantics as the previous test."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("PLUGIN_ROOT", "AUTOCC_PROJECT_DIR", "CLAUDE_PROJECT_DIR", "CODEX_PROJECT_DIR")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(autopilot_project)
    other_cwd = tmp_path / "elsewhere4"
    other_cwd.mkdir()
    result = _hook_subprocess(
        {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        env=env,
        cwd=other_cwd,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["permissionDecision"] == "allow"
    assert (autopilot_project / ".autocc" / "decisions.log").is_file()
