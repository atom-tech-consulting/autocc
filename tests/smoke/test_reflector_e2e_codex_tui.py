"""End-to-end tmux-driven Codex TUI smoke against an empty taskboard.

Skipped by default — set ``AUTOCC_REAL_SDK=1`` to run. Also skipped if
``tmux`` isn't on ``$PATH`` or the operator hasn't completed the one-time
``autocc install --agent codex`` + TUI ``/hooks`` trust ritual (see
"Operator setup" below).

Why TUI (not ``codex exec``)
============================

TB-9 / TB-10 established (see ``docs/codex-smoke-results.md``) that
``codex exec`` on codex-cli 0.132 / 0.133 does NOT fire hooks — upstream
issue openai/codex#16430 (plugin manifest parser ignores ``hooks``) plus
the dispatcher gap captured under the ``plugin_hooks`` "under development"
flag. The interactive TUI is a different code path and DOES fire hooks
once the operator has trusted them via ``/hooks``. This smoke exercises
the working path; the exec-based smoke it replaces encoded an
impossible expectation and is removed.

Operator setup (one-time per host)
==================================

1. ``autocc install --agent codex`` — writes the marker-bounded
   ``[[hooks.*]]`` block into ``${CODEX_HOME:-~/.codex}/config.toml`` so
   codex can discover the autocc handlers.
2. Launch ``codex`` once interactively, type ``/hooks``, and trust the
   three autocc entries (``PreToolUse``, ``PermissionRequest``,
   ``Stop``). This causes codex to persist ``trusted_hash`` values under
   ``[hooks.state."<config>:<event>:0:0"]`` in ``config.toml``. Without
   this step codex refuses to spawn the hook script.
3. ``AUTOCC_REAL_SDK=1 uv run pytest tests/smoke/test_reflector_e2e_codex_tui.py``.

The skip gates print the specific next command if any of the three are
missing, so a fresh operator gets a precise fix rather than a red test.

What this test asserts
======================

With an empty 5-section ``TASKS.md`` and ``.autocc/flag`` set, the
autocc Stop hook resolves to "board empty; flag dropped" and appends
``Stop -> stop | board empty; flag dropped`` to
``<workspace>/.autocc/decisions.log``. Presence of a ``Stop -> stop``
entry is the mandatory hook-fired evidence — the same audit row
captured in the live TUI validation on codex 0.132 documented in
``docs/codex-smoke-results.md``.

What this test deliberately does NOT do
=======================================

- It does NOT install autocc into a sandboxed ``HOME``. The earlier
  exec-based smoke did that, and the pattern produced a unit-test
  leakage bug that mutated the operator's real ``~/.codex/config.toml``
  with pytest-tmp paths (see TB-11 "Out of scope"). Instead this smoke
  exercises the operator's actual install and skips cleanly if the
  install hasn't been done.
- It does NOT write to ``[hooks]`` in ``~/.codex/config.toml`` — the
  operator's hook install is treated as read-only.
- It does NOT use ``codex exec`` (see "Why TUI" above).
- It does NOT gate on a full Backlog → Complete cycle. One Stop-hook
  firing is sufficient evidence; the full reflector loop is covered by
  the Claude smoke at ``tests/smoke/test_reflector_e2e.py``.

The only persistent write into ``~/.codex/`` is an optional
marker-bounded ``[projects."<tmp_path>"]`` trust entry, stripped on
teardown so nothing leaks between runs.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

import pytest

REAL_CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
REAL_CODEX_CONFIG = REAL_CODEX_HOME / "config.toml"

# Must match src/autocc/installer.py::CODEX_HOOKS_BEGIN_MARKER.
HOOKS_BEGIN_MARKER = "# >>> autocc managed hooks (do not edit) >>>"

# Separate markers for the per-test project-trust block so teardown can
# strip our writes without disturbing the operator's hook install or any
# other [projects.*] entries the operator has trusted.
TRUST_BEGIN_MARKER = "# >>> autocc-smoke-tui project trust (do not edit) >>>"
TRUST_END_MARKER = "# <<< autocc-smoke-tui project trust <<<"

# Detects at least one persisted Stop-hook trust entry. Codex writes these
# only after the operator confirms via /hooks in the TUI; the regex matches
# the shape `[hooks.state."<config-path>:stop:0:0"] ... trusted_hash = "..."`.
STOP_TRUST_RE = re.compile(
    r'\[hooks\.state\."[^"]+:stop:\d+:\d+"\][^\[]*?trusted_hash\s*=',
    re.DOTALL,
)

TMUX_SESSION = "autocc-smoke-tui"
DECISIONS_LOG_TIMEOUT_S = 60
BANNER_TIMEOUT_S = 30


def _skip_reason() -> str | None:
    """Return the first unmet precondition's actionable message, or None.

    Three logical gates per TB-11 verification: AUTOCC_REAL_SDK opt-in,
    tmux availability, and operator config-layer install + persisted
    ``/hooks`` trust. Each message names the exact command an operator
    should run to fix the gap.
    """
    if not os.environ.get("AUTOCC_REAL_SDK"):
        return (
            "opt-in real-SDK smoke; set AUTOCC_REAL_SDK=1 to run."
        )
    if shutil.which("tmux") is None:
        return (
            "tmux not found on $PATH; install with `brew install tmux` "
            "(macOS) or your distro's equivalent before re-running."
        )
    if not REAL_CODEX_CONFIG.exists():
        return (
            f"{REAL_CODEX_CONFIG} does not exist; run "
            "`autocc install --agent codex` first to write the autocc "
            "hook block into config.toml."
        )
    cfg_text = REAL_CODEX_CONFIG.read_text()
    if HOOKS_BEGIN_MARKER not in cfg_text:
        return (
            f"{REAL_CODEX_CONFIG} is missing the autocc marker block "
            f"`{HOOKS_BEGIN_MARKER}`; run `autocc install --agent codex` "
            "to write it."
        )
    if not STOP_TRUST_RE.search(cfg_text):
        return (
            f"{REAL_CODEX_CONFIG} has no persisted `trusted_hash` under "
            "`[hooks.state.\"...:stop:0:0\"]`; launch `codex` interactively, "
            "run the `/hooks` slash command, and trust the three autocc "
            "entries (PreToolUse, PermissionRequest, Stop). Codex persists "
            "the trust state inline in config.toml; without it the Stop "
            "hook will not spawn."
        )
    return None


_SKIP_REASON = _skip_reason()
pytestmark = pytest.mark.skipif(
    _SKIP_REASON is not None,
    reason=_SKIP_REASON or "preconditions met",
)


# ---------------------------------------------------------------------------
# Workspace + project-trust fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal taskboard workspace + autopilot flag.

    All writes are confined to ``tmp_path`` (see ``project_trusted`` for the
    single optional, marker-guarded mutation under ``~/.codex/``).
    """
    project = tmp_path / "autopilot-workspace"
    project.mkdir()
    (project / ".autocc").mkdir()
    (project / ".autocc" / "flag").touch()
    (project / "TASKS.md").write_text(
        "# Tasks\n\n"
        "## Active\n\n"
        "## Ready\n\n"
        "## Backlog\n\n"
        "## Complete\n\n"
        "## Frozen\n"
    )
    return project


def _strip_trust_block(text: str) -> str:
    """Idempotently remove the marker-bounded smoke trust block.

    Preserves all other content (including the autocc hook block and any
    other operator-trusted projects) byte-for-byte.
    """
    b = text.find(TRUST_BEGIN_MARKER)
    if b == -1:
        return text
    e = text.find(TRUST_END_MARKER, b)
    if e == -1:
        return text
    end = e + len(TRUST_END_MARKER)
    # Consume the trailing newline we appended.
    if end < len(text) and text[end] == "\n":
        end += 1
    # And the leading separator newlines we added (one or two blank lines).
    start = b
    while start > 0 and text[start - 1] == "\n":
        start -= 1
    # Re-introduce a single trailing newline if the rest of the file expects it.
    tail = text[end:]
    head = text[:start]
    if head and not head.endswith("\n"):
        head = head + "\n"
    return head + tail


@pytest.fixture
def project_trusted(workspace: Path) -> Path:
    """Pre-seed a marker-bounded ``[projects."<tmp_path>"]`` trust entry
    into the operator's real ``~/.codex/config.toml`` so codex doesn't
    prompt for trust on the fresh tempdir mid-run.

    Teardown strips the marker block. No other persistent mutation of
    ``~/.codex/`` is performed by this smoke.
    """
    cfg_text = REAL_CODEX_CONFIG.read_text()
    # Strip any leftover block from a previously crashed run before writing.
    cfg_text = _strip_trust_block(cfg_text)
    block = (
        f"{TRUST_BEGIN_MARKER}\n"
        f'[projects."{workspace}"]\n'
        f'trust_level = "trusted"\n'
        f"{TRUST_END_MARKER}\n"
    )
    sep = "" if cfg_text == "" or cfg_text.endswith("\n\n") else (
        "\n" if cfg_text.endswith("\n") else "\n\n"
    )
    REAL_CODEX_CONFIG.write_text(cfg_text + sep + block)
    try:
        yield workspace
    finally:
        current = REAL_CODEX_CONFIG.read_text()
        REAL_CODEX_CONFIG.write_text(_strip_trust_block(current))


# ---------------------------------------------------------------------------
# tmux helpers
# ---------------------------------------------------------------------------


def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    if check and res.returncode != 0:
        raise RuntimeError(
            f"tmux {' '.join(args)} failed (rc={res.returncode})\n"
            f"stdout: {res.stdout}\nstderr: {res.stderr}"
        )
    return res


def _capture_pane() -> str:
    return _tmux("capture-pane", "-t", TMUX_SESSION, "-p").stdout


def _send_keys(*keys: str) -> None:
    _tmux("send-keys", "-t", TMUX_SESSION, *keys)


def _wait_for_text(needle: str, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if needle in _capture_pane():
            return True
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# The smoke
# ---------------------------------------------------------------------------


def test_codex_tui_stop_hook_fires(project_trusted: Path, capsys):
    """Drive an interactive ``codex`` TUI through tmux; assert the autocc
    Stop hook writes a ``Stop -> stop`` entry to
    ``<workspace>/.autocc/decisions.log`` when codex finishes responding
    on an empty taskboard.

    The mandatory evidence is the on-disk decisions.log entry: a Stop
    hook firing is the universal "autocc install + trust + dispatcher
    are wired" signal an operator can grep for.
    """
    workspace = project_trusted
    decisions_log = workspace / ".autocc" / "decisions.log"
    assert not decisions_log.exists(), (
        "decisions.log already exists at workspace start — fixture bug?"
    )

    # Always start with a clean slate. A leftover session from a prior
    # crashed run would foul send-keys (tmux would attach to the stale pane).
    _tmux("kill-session", "-t", TMUX_SESSION, check=False)

    try:
        # 1. Launch codex inside a fresh tmux pane. -d detaches immediately;
        #    -x/-y set a generous pane size so codex's TUI doesn't reflow
        #    awkwardly. The shell command cd's into the workspace then
        #    execs codex, so codex's cwd is the project root and our
        #    [projects."<workspace>"] trust entry matches.
        launch_cmd = f"cd {shlex.quote(str(workspace))} && codex"
        _tmux(
            "new-session", "-d",
            "-s", TMUX_SESSION,
            "-x", "200", "-y", "50",
            launch_cmd,
        )

        # 2. Wait for the codex banner. The bottom hint bar always shows
        #    `/help` on 0.132+, which is a robust marker that the TUI is
        #    interactive and ready to accept input.
        if not _wait_for_text("/help", timeout_s=BANNER_TIMEOUT_S):
            pane = _capture_pane()
            pytest.fail(
                f"codex TUI banner not seen within {BANNER_TIMEOUT_S}s. "
                "Possible causes: codex binary missing from $PATH inside "
                "the tmux pane's login shell, codex needs reauth, or the "
                "operator's `~/.codex/config.toml` has a syntax error.\n"
                f"--- tmux pane ---\n{pane}"
            )

        # 3. If codex's update-available prompt appears, choose Skip (2)
        #    so the test doesn't block on operator interaction. The prompt
        #    only shows when `codex doctor` has a pending minor-version
        #    upgrade for the local install.
        pane = _capture_pane().lower()
        if "update" in pane and ("skip" in pane or "later" in pane):
            _send_keys("2")
            time.sleep(0.3)
            _send_keys("Enter")
            time.sleep(1.0)

        # 4. Send a tiny prompt body, then submit with a single Enter.
        #    codex 0.132's TUI submit key is plain Enter; Ctrl+J inserts a
        #    newline instead, so we deliberately use Enter (not C-j). The
        #    -l flag tells tmux to type the string literally so any "/" /
        #    "$" / "." chars aren't interpreted as tmux key names.
        _send_keys("-l", "Say the word hello and stop.")
        time.sleep(0.5)
        _send_keys("Enter")

        # 5. Poll for the decisions.log file. When codex emits its Stop
        #    event (model finished responding), the autocc Stop hook
        #    runs, sees an empty board, drops the flag, and appends
        #    `Stop -> stop | board empty; flag dropped` to decisions.log.
        deadline = time.time() + DECISIONS_LOG_TIMEOUT_S
        matched = False
        while time.time() < deadline:
            if decisions_log.exists():
                txt = decisions_log.read_text()
                if "Stop -> stop" in txt:
                    matched = True
                    break
            time.sleep(1.0)

        if not matched:
            pane = _capture_pane()
            log_text = (
                decisions_log.read_text()
                if decisions_log.exists()
                else "(decisions.log does not exist)"
            )
            pytest.fail(
                f"decisions.log did not contain `Stop -> stop` within "
                f"{DECISIONS_LOG_TIMEOUT_S}s. The autocc Stop hook either "
                "didn't fire, or fired against a different workspace.\n"
                f"--- decisions.log ---\n{log_text}\n"
                f"--- tmux pane (last frame) ---\n{pane}"
            )

        log_text = decisions_log.read_text()
        with capsys.disabled():
            print(f"\n[codex-tui-smoke] decisions.log entries:\n{log_text}")

        assert "Stop -> stop" in log_text

    finally:
        # 6. Best-effort shutdown: Ctrl+C twice triggers codex's quit-confirm
        #    flow, then kill the tmux session regardless of whether the
        #    quit-confirm landed. project_trusted's teardown strips the
        #    config.toml trust block.
        try:
            _send_keys("C-c")
            time.sleep(0.2)
            _send_keys("C-c")
            time.sleep(0.3)
        except Exception:
            pass
        _tmux("kill-session", "-t", TMUX_SESSION, check=False)
