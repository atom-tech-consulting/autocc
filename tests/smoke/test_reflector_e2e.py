"""End-to-end reflector smoke against the taskflow fixture.

Skipped by default — set AUTOCC_REAL_SDK=1 to run. See `tests/smoke/README.md`.

Success is measured by **on-disk state**, not by the SDK exit code:

- TB-3/4/5 land in TASKS.md's `## Complete` section
- `.autocc/progress.md` has entries for each
- `uv run pytest` is green in the fixture

The SDK loop legitimately may hit `--max-turns` *after* finishing the target
tasks, because the reflector skill runs `/housekeeping` on an empty board and
will keep finding more work. We tolerate `terminal_reason == "max_turns"` as
long as the target invariants hold.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("AUTOCC_REAL_SDK"),
    reason="opt-in real-SDK smoke; set AUTOCC_REAL_SDK=1 to run",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SRC = REPO_ROOT / "examples" / "taskflow"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# The fixture has 3 workable tasks. The reflector's per-task cost is ~15-25
# turns (read briefing → explore → edit → test → commit → update board +
# progress). 100 turns gives headroom for all three plus the post-board
# housekeeping scan that the skill triggers on an empty Backlog.
#
# Note: this smoke covers the reflector skill end-to-end, but does NOT
# directly exercise autocc's installed autocc-hooks.py — the claude CLI
# reads ~/.claude/ regardless of CLAUDE_HOME, so it ends up using whatever
# hook the user has deployed system-wide. Hook decision logic is covered
# by `tests/test_autocc_hook.py` (pure-Python, deterministic, no API).
MAX_TURNS = "100"
MAX_BUDGET_USD = "5.00"
TIMEOUT_S = 1500


def _run(cmd: list[str], cwd: Path, env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _git_init_project(project: Path) -> None:
    """Init the fixture copy as a git repo so the reflector can commit."""
    _run(["git", "init", "-b", "main", "-q"], cwd=project)
    _run(["git", "add", "-A"], cwd=project)
    _run(
        [
            "git",
            "-c", "user.name=autocc-smoke",
            "-c", "user.email=smoke@autocc.test",
            "-c", "commit.gpgsign=false",
            "commit", "-q", "-m", "fixture baseline",
        ],
        cwd=project,
    )


def _resolve_workspace_root(tmp_path: Path) -> Path:
    """Pick the workspace root.

    If ``AUTOCC_SMOKE_WORKSPACE`` is set, use that path (cleaning any prior
    contents) so the agent's run artifacts persist for inspection. Otherwise
    use pytest's tmp_path, which gets garbage-collected on the next run.
    """
    custom = os.environ.get("AUTOCC_SMOKE_WORKSPACE")
    if not custom:
        return tmp_path
    root = Path(custom).expanduser().resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


@pytest.fixture
def workspace(tmp_path: Path) -> dict:
    root = _resolve_workspace_root(tmp_path)
    fake_home = root / "claude_home"
    fake_home.mkdir()
    project = root / "taskflow"
    shutil.copytree(FIXTURE_SRC, project)
    _git_init_project(project)
    return {"home": fake_home, "project": project, "root": root}


def _slug_for(project: Path) -> str:
    """Match claude CLI's project-slug derivation: leading '-' then '/' → '-'."""
    return "-" + str(project).strip("/").replace("/", "-")


def _locate_session_jsonl(project: Path, session_id: str) -> Path | None:
    if not session_id:
        return None
    for candidate_path in {project, project.resolve()}:
        candidate = CLAUDE_PROJECTS_DIR / _slug_for(candidate_path) / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    # Last resort: scan all project dirs for this session id.
    for f in CLAUDE_PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        return f
    return None


def _complete_section(tasks_md: str) -> str:
    """Extract the ## Complete section content from TASKS.md."""
    start = tasks_md.find("## Complete")
    if start == -1:
        return ""
    end = tasks_md.find("\n## ", start + len("## Complete"))
    return tasks_md[start:end] if end != -1 else tasks_md[start:]


def test_reflector_completes_remaining_tasks(workspace, capsys):
    """Run /reflector against taskflow; verify TB-3/4/5 end up Complete + tests green."""
    from autocc.installer import install

    rc = install(assume_yes=True, claude_home=workspace["home"])
    assert rc == 0, "autocc install failed"

    flag = workspace["project"] / ".autocc" / "flag"
    flag.parent.mkdir(exist_ok=True)
    flag.touch()

    env = {
        "CLAUDE_HOME": str(workspace["home"]),
        "CLAUDE_PROJECT_DIR": str(workspace["project"]),
    }
    result = _run(
        [
            "claude", "-p", "/reflector",
            "--dangerously-skip-permissions",
            "--max-turns", MAX_TURNS,
            "--max-budget-usd", MAX_BUDGET_USD,
            "--output-format", "json",
        ],
        cwd=workspace["project"],
        env=env,
        timeout=TIMEOUT_S,
    )

    # Parse the SDK's JSON result for visibility. The exit code itself is
    # not a success signal: the reflector legitimately keeps looping after
    # the target board is done, so hitting --max-turns is fine.
    sdk_summary: dict = {}
    if result.stdout.strip():
        try:
            sdk_summary = json.loads(result.stdout)
        except json.JSONDecodeError:
            sdk_summary = {"_unparsed_stdout": result.stdout[:500]}
    terminal_reason = sdk_summary.get("terminal_reason")
    cost = sdk_summary.get("total_cost_usd")
    turns = sdk_summary.get("num_turns")
    session_id = sdk_summary.get("session_id")

    # Persist the session trajectory next to the workspace for easy inspection.
    session_src = _locate_session_jsonl(workspace["project"], session_id) if session_id else None
    session_dest = workspace["root"] / "session.jsonl"
    if session_src:
        shutil.copy2(session_src, session_dest)

    with capsys.disabled():
        print(
            f"\n[smoke] terminal_reason={terminal_reason} "
            f"turns={turns} cost=${cost} returncode={result.returncode}"
        )
        print(f"[smoke] workspace: {workspace['root']}")
        print(f"[smoke] session_id: {session_id}")
        if session_src:
            print(f"[smoke] session trajectory (origin): {session_src}")
            print(f"[smoke] session trajectory (copy):   {session_dest}")
        else:
            print("[smoke] session trajectory: not located under ~/.claude/projects/")

    # We deliberately don't gate on terminal_reason or returncode. The SDK
    # legitimately reports several "fine" terminations (`completed`,
    # `max_turns`, `end_turn`) depending on whether the agent stops by
    # exhausting the board, hits the turn cap mid-housekeeping, or returns
    # `end_turn` mid-loop. The authoritative success signal is the on-disk
    # state below.

    tasks_md = (workspace["project"] / "TASKS.md").read_text()
    complete = _complete_section(tasks_md)
    for tb in ("TB-3", "TB-4", "TB-5"):
        assert tb in complete, (
            f"{tb} not in Complete section after reflector run.\n"
            f"--- TASKS.md ---\n{tasks_md}"
        )

    progress = workspace["project"] / ".autocc" / "progress.md"
    assert progress.exists(), "progress.md should have been updated"
    progress_text = progress.read_text()
    for tb in ("TB-3", "TB-4", "TB-5"):
        assert tb in progress_text, f"{tb} missing from progress.md"

    pytest_result = _run(
        ["uv", "run", "pytest", "-q"],
        cwd=workspace["project"],
        timeout=180,
    )
    assert pytest_result.returncode == 0, (
        f"pytest failed after reflector run:\n{pytest_result.stdout[-2000:]}"
    )
