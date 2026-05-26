"""End-to-end Codex smoke against the taskflow fixture.

Skipped by default — set ``AUTOCC_REAL_SDK=1`` to run (the same env var
gates the Claude-side smoke at ``tests/smoke/test_reflector_e2e.py``, so a
single opt-in flips both providers' smokes on).

This smoke complements the Claude-side reflector smoke: TB-2 / TB-3 / TB-4
landed the Codex installer, the Codex-shaped autopilot hook script, and the
provider-portable skill bodies — all green against synthetic fixtures only.
This file is the first end-to-end run against the real `codex` CLI: it
installs autocc into a sandboxed ``HOME`` as a Codex plugin, launches
``codex exec`` against a copy of ``examples/taskflow``, and asserts that
the Codex-side hook script (``autocc-hooks-codex.py``) actually fired —
which proves the install → marketplace discovery → plugin-hooks dispatch
path works end-to-end against the real binary.

Mandatory assertion: at least one entry in the taskflow workspace's
``.autocc/decisions.log`` written by ``autocc-hooks-codex.py``.  A single
hook firing is sufficient evidence that install/discovery/wire-shape is
correct; the full reflector loop is already exercised under Claude in
``tests/smoke/test_reflector_e2e.py`` and duplicating that expectation
under Codex would be fragile (codex rate limits, auth-flow quirks,
slash-command invocation differences that aren't autocc bugs).

Stretch assertion (soft — does not fail the test): the seeded backlog
task moved to ``## Complete`` AND a commit with a matching subject prefix
landed on the taskflow branch. If the stretch fails but the mandatory
passes, the test still passes; the stretch outcome is captured with
capsys for inspection.

Observations from implementation (closes "verify before depending on it"
items in ``docs/codex-mapping.md``):

- **Plugin hooks feature flag.** ``docs/codex-mapping.md`` §1c noted
  ``plugin_hooks`` ships as "under development, false" on codex-cli
  0.128.0.  The test passes ``--enable plugin_hooks`` (equivalent to
  ``-c features.plugin_hooks=true``) on the ``codex exec`` invocation
  so plugin-bundled hooks (autocc's ``hooks.json``) are merged into the
  dispatcher.  Without this flag the install is fine but the hooks
  never fire — i.e. the plugin loads, marketplace discovery succeeds,
  the skills become invocable, but ``PermissionRequest`` / ``Stop``
  never reach the Codex-shaped script.
- **Sandboxed HOME via ``HOME`` + ``CODEX_HOME``.** Codex resolves
  ``~`` via ``$HOME`` for the marketplace path (``~/.agents/plugins/
  marketplace.json``) and via ``$CODEX_HOME`` (falling back to
  ``$HOME/.codex``) for auth + config.  Setting both lets the test
  point at an isolated sandboxed home without modifying the operator's
  live ``~/.codex/`` state.  The fixture copies ``~/.codex/auth.json``
  and ``~/.codex/config.toml`` from the operator's home into the
  sandbox so codex can authenticate without a fresh ``codex login``.
- **Project-trust prompt.** Codex's ``[projects."<path>"].trust_level``
  table in ``config.toml`` is per-absolute-path; on a fresh sandboxed
  workspace the path is new, so codex would prompt for trust mid-run
  if we didn't pre-seed it.  The test writes a ``trust_level =
  "trusted"`` entry for the taskflow tempdir into the sandboxed
  ``config.toml`` before launching.
- **Approval / sandbox bypass.** ``codex exec`` in this smoke uses
  ``--dangerously-bypass-approvals-and-sandbox`` because the test is
  itself running inside an OS-level sandbox (the autocc agent harness)
  and we want the inner codex to behave the way a real autopilot
  session would: no interactive approval prompts.  This is also the
  closest-to-Claude-Code's ``--dangerously-skip-permissions`` shape.
- **Slash-command invocation.** ``docs/codex-mapping.md`` §3 predicted
  that "Codex's TUI accepts ``/<skill-name>`` to trigger a skill" and
  the same call style holds for ``codex exec`` — the prompt body
  ``/reflector`` triggers the reflector skill when the plugin manifest
  exposes a skill of that name.  No prompt-shape divergence observed
  vs the Claude-side smoke's ``-p /reflector`` invocation.
"""

from __future__ import annotations

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
REAL_CODEX_HOME = Path.home() / ".codex"

# The mandatory assertion is "hook fired at least once" rather than "full
# reflector cycle completed" (the loop is exercised under Claude in the
# sibling smoke). One hook event is enough to validate install + discovery
# + dispatch; the stretch assertion catches the loop-level happy path.
# Cap turns generously — codex exec doesn't expose a turn cap flag at
# 0.128.0, so the wall-clock TIMEOUT_S below is the real bound.
TIMEOUT_S = 300
SEED_TASK_ID = "TB-99"
SEED_TASK_TITLE = "Add autopilot smoke marker to README"


def _run(
    cmd: list[str],
    cwd: Path,
    env: dict | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
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
    """Mirror the Claude smoke's resolver — pytest's tmp_path by default,
    or ``$AUTOCC_SMOKE_WORKSPACE`` for a persistent inspectable location."""
    custom = os.environ.get("AUTOCC_SMOKE_WORKSPACE")
    if not custom:
        return tmp_path
    root = Path(custom).expanduser().resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    return root


def _seed_codex_auth(sandbox_home: Path) -> None:
    """Copy the operator's ``~/.codex/auth.json`` and ``~/.codex/config.toml``
    into the sandboxed ``HOME`` so codex authenticates without inheriting the
    real home or triggering a fresh login flow.

    This is deliberately scoped to auth + config only — sessions, caches,
    memories, etc. stay isolated in the sandbox.
    """
    dest = sandbox_home / ".codex"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("auth.json", "config.toml"):
        src = REAL_CODEX_HOME / name
        if src.is_file():
            shutil.copy2(src, dest / name)


def _trust_project_in_sandbox(sandbox_home: Path, project: Path) -> None:
    """Append a ``[projects."<abs path>"].trust_level = "trusted"`` block to
    the sandboxed ``config.toml`` so codex doesn't prompt for trust on the
    fresh tempdir mid-run."""
    cfg = sandbox_home / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    existing = cfg.read_text() if cfg.exists() else ""
    block = (
        f'\n[projects."{project}"]\n'
        f'trust_level = "trusted"\n'
    )
    if block not in existing:
        cfg.write_text(existing + block)


@pytest.fixture
def workspace(tmp_path: Path) -> dict:
    root = _resolve_workspace_root(tmp_path)
    sandbox_home = root / "codex_home"
    sandbox_home.mkdir()
    _seed_codex_auth(sandbox_home)

    project = root / "taskflow"
    shutil.copytree(FIXTURE_SRC, project)
    _git_init_project(project)
    _trust_project_in_sandbox(sandbox_home, project)
    return {"home": sandbox_home, "project": project, "root": root}


def _section(tasks_md: str, header: str) -> str:
    """Extract a single ``## <header>`` section's body from TASKS.md."""
    start = tasks_md.find(f"## {header}")
    if start == -1:
        return ""
    end = tasks_md.find("\n## ", start + len(f"## {header}"))
    return tasks_md[start:end] if end != -1 else tasks_md[start:]


def _seed_backlog_task(project: Path) -> None:
    """Replace the fixture's TASKS.md with a single, trivial backlog task.

    The fixture ships with TB-3/4/5 in Ready/Backlog (intended for the
    Claude smoke's full-cycle assertion); for the Codex smoke we don't need
    the loop to grind through all of them. A single trivial task lowers the
    blast radius for the stretch assertion — if the reflector loop does
    cooperate, the task completes in a couple of turns and we get the
    Backlog→Complete signal cheaply; if it doesn't cooperate, the mandatory
    hook-fired assertion still passes.
    """
    tasks_md = (
        "# Tasks\n\n"
        "## Active\n\n"
        "## Ready\n\n"
        "## Backlog\n\n"
        f"- [ ] **{SEED_TASK_ID}** **{SEED_TASK_TITLE}** `#docs` — "
        "Append a single line `<!-- autocc-smoke-marker -->` to the end "
        "of README.md. No tests required.\n\n"
        "## Complete\n\n"
        "## Frozen\n"
    )
    (project / "TASKS.md").write_text(tasks_md)
    # Commit the reset so a clean git log makes the stretch assertion's
    # commit-detection unambiguous (only post-baseline commits matter).
    _run(["git", "add", "TASKS.md"], cwd=project)
    _run(
        [
            "git",
            "-c", "user.name=autocc-smoke",
            "-c", "user.email=smoke@autocc.test",
            "-c", "commit.gpgsign=false",
            "commit", "-q", "-m", "seed: single backlog task for codex smoke",
        ],
        cwd=project,
    )


def _decisions_log_text(project: Path) -> str:
    log_path = project / ".autocc" / "decisions.log"
    if not log_path.exists():
        return ""
    return log_path.read_text()


def _head_commit_subject(project: Path) -> str:
    res = _run(["git", "log", "-1", "--pretty=%s"], cwd=project, timeout=10)
    return (res.stdout or "").strip()


def _all_commit_subjects_since_baseline(project: Path) -> list[str]:
    res = _run(
        ["git", "log", "--pretty=%s"],
        cwd=project,
        timeout=10,
    )
    return [line for line in (res.stdout or "").splitlines() if line.strip()]


def test_codex_reflector_hook_fires(workspace, capsys):
    """Install autocc as a Codex plugin, run codex exec against taskflow,
    and verify ``autocc-hooks-codex.py`` actually fired at least once.

    The mandatory invariant is the hook-fired evidence on disk
    (``.autocc/decisions.log``). The stretch invariants (Backlog→Complete
    + commit landed) are soft-failed with capsys notes so a partially-
    cooperating codex session still passes the test as long as the
    install/discovery/wire-shape path is exercised end-to-end.
    """
    # 1. Install autocc as a Codex plugin into the sandboxed HOME.
    from autocc.installer import (
        CODEX_HOOK_BASENAME,
        CODEX_PLUGIN_NAME,
        install,
    )

    plugin_root = workspace["home"] / "plugins"
    marketplace_path = workspace["home"] / ".agents" / "plugins" / "marketplace.json"

    rc = install(
        agent="codex",
        plugin_root=plugin_root,
        marketplace_path=marketplace_path,
    )
    assert rc == 0, "autocc install --agent codex failed"

    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    assert manifest_path.is_file(), f"plugin manifest missing: {manifest_path}"
    assert marketplace_path.is_file(), f"marketplace missing: {marketplace_path}"
    hook_script = plugin_dir / "hooks" / CODEX_HOOK_BASENAME
    assert hook_script.is_file(), f"Codex hook script missing: {hook_script}"

    # 2. Seed the taskflow workspace: autopilot flag + one trivial backlog task.
    flag = workspace["project"] / ".autocc" / "flag"
    flag.parent.mkdir(exist_ok=True)
    flag.touch()
    _seed_backlog_task(workspace["project"])
    baseline_head = _head_commit_subject(workspace["project"])

    # 3. Launch codex exec non-interactively. Key env:
    #    - HOME / CODEX_HOME: sandboxed home (auth + marketplace discovery)
    #    - AUTOCC_PROJECT_DIR: pin the project root for the hook + skills
    #      (the hook chain is AUTOCC_PROJECT_DIR > CLAUDE_PROJECT_DIR >
    #      CODEX_PROJECT_DIR > cwd > getcwd)
    env = {
        "HOME": str(workspace["home"]),
        "CODEX_HOME": str(workspace["home"] / ".codex"),
        "AUTOCC_PROJECT_DIR": str(workspace["project"]),
    }
    # Trim PATH-affecting vars only if needed; we want the operator's codex
    # binary on PATH, so leave PATH alone.
    cmd = [
        "codex", "exec",
        "--enable", "plugin_hooks",  # surface the plugin's hooks.json to the dispatcher
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-C", str(workspace["project"]),
        (
            "Invoke the /reflector skill against this project. Work on "
            f"task {SEED_TASK_ID} from the Backlog section of TASKS.md, "
            "then update TASKS.md and commit. Do not ask any questions — "
            "this is an autopilot session."
        ),
    ]

    try:
        result = _run(cmd, cwd=workspace["project"], env=env, timeout=TIMEOUT_S)
        rc_codex = result.returncode
        stdout_tail = result.stdout[-2000:] if result.stdout else ""
        stderr_tail = result.stderr[-2000:] if result.stderr else ""
    except subprocess.TimeoutExpired as exc:
        rc_codex = -1
        stdout_tail = (exc.stdout or b"")[-2000:].decode("utf-8", errors="replace")
        stderr_tail = (exc.stderr or b"")[-2000:].decode("utf-8", errors="replace")

    with capsys.disabled():
        print(f"\n[codex-smoke] returncode={rc_codex}")
        print(f"[codex-smoke] workspace: {workspace['root']}")
        print(f"[codex-smoke] sandbox HOME: {workspace['home']}")
        if stdout_tail:
            print(f"[codex-smoke] stdout tail:\n{stdout_tail}")
        if stderr_tail:
            print(f"[codex-smoke] stderr tail:\n{stderr_tail}")

    # 4. Mandatory: the Codex-side hook fired at least once. Evidence:
    #    .autocc/decisions.log written by autocc-hooks-codex.py. The Codex
    #    hook only writes to decisions.log on PermissionRequest (per the
    #    hook script's log_decision call); a single line proves the
    #    install → marketplace discovery → plugin_hooks dispatch chain
    #    works end-to-end.
    log_text = _decisions_log_text(workspace["project"])
    assert log_text.strip(), (
        "decisions.log is empty — Codex-side hook never fired.\n"
        "Hook script path: "
        f"{plugin_dir / 'hooks' / CODEX_HOOK_BASENAME}\n"
        "Check: did the plugin_hooks feature flag take effect? "
        "Does marketplace.json point at the right plugin folder? "
        "Did codex actually load the plugin (look for 'autocc' in stderr)?\n"
        f"--- stdout tail ---\n{stdout_tail}\n"
        f"--- stderr tail ---\n{stderr_tail}"
    )
    assert "PermissionRequest" in log_text, (
        "decisions.log exists but has no PermissionRequest entries — the "
        "hook ran but on a non-decisions-logged event. The Codex hook "
        "only logs PermissionRequest decisions; if Stop or PreToolUse "
        "fired instead, the install path is fine but PermissionRequest "
        "specifically wasn't exercised this run.\n"
        f"--- decisions.log ---\n{log_text}"
    )

    # 5. Stretch (soft): the seeded task moved Backlog → Complete AND a
    #    commit whose subject references SEED_TASK_ID landed. If this fails
    #    we capture the reason but don't fail the test — the loop-level
    #    happy path under Codex is fragile (auth flow, rate limits,
    #    slash-command invocation differences) and the mandatory hook
    #    assertion is the real install-correctness signal.
    tasks_md = (workspace["project"] / "TASKS.md").read_text()
    complete_section = _section(tasks_md, "Complete")
    backlog_section = _section(tasks_md, "Backlog")
    moved_to_complete = (
        SEED_TASK_ID in complete_section
        and SEED_TASK_ID not in backlog_section
    )

    subjects = _all_commit_subjects_since_baseline(workspace["project"])
    new_subjects = []
    for s in subjects:
        if s == baseline_head:
            break
        new_subjects.append(s)
    commit_landed = any(SEED_TASK_ID in s for s in new_subjects)

    with capsys.disabled():
        print(
            f"[codex-smoke] stretch: moved_to_complete={moved_to_complete} "
            f"commit_landed={commit_landed}"
        )
        if not moved_to_complete:
            print(
                "[codex-smoke] stretch.note: TASKS.md did not show "
                f"{SEED_TASK_ID} in Complete (and absent from Backlog). "
                "Possible causes: codex hit timeout mid-task, slash-command "
                "invocation didn't trigger the reflector skill, or the "
                "reflector skill body didn't recognize the seeded task. "
                "Mandatory hook-fired assertion still holds, so the "
                "install/discovery/wire-shape path is fine."
            )
        if not commit_landed:
            print(
                "[codex-smoke] stretch.note: no commit subject referenced "
                f"{SEED_TASK_ID}. Reflector may have edited files without "
                "calling /commit-changes, or the commit-changes skill "
                "may have run with a different subject convention under "
                "Codex (AUTOCC_AGENT_NAME interpolation, etc.)."
            )
