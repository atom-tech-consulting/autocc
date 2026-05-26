"""End-to-end checks for the `commit-changes` `Co-Authored-By` trailer.

TB-4 parameterized the trailer on two env vars (`AUTOCC_AGENT_NAME` /
`AUTOCC_AGENT_EMAIL`) but kept the hard-coded `:-Claude` /
`:-noreply@anthropic.com` defaults — under the Codex install branch
every commit without explicit overrides still trailed
`Co-Authored-By: Claude <noreply@anthropic.com>`, which is a
user-visible mis-attribution.

TB-8 makes the default-when-unset provider-aware: the trailer sniffs
`$CODEX_PROJECT_DIR` and picks `Codex` / `noreply@openai.com` when it
is set, `Claude` / `noreply@anthropic.com` otherwise. Explicit
`AUTOCC_AGENT_NAME` / `AUTOCC_AGENT_EMAIL` overrides still win under
both providers.

These tests pin that contract by extracting the trailer template from
`skills/commit-changes/SKILL.md` and evaluating it under each
provider-shaped env via `bash`. If the skill body's trailer expression
regresses (drops the sniff, hard-codes one side, breaks POSIX), one
of these cases trips.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

COMMIT_CHANGES = (
    Path(__file__).resolve().parents[1] / "skills" / "commit-changes" / "SKILL.md"
)


def _extract_trailer_template() -> str:
    """Return the literal `Co-Authored-By: ...` template line from
    `commit-changes/SKILL.md`.

    Picks the first such line in the file; the skill body's worked-example
    code block is the canonical instance the agent will copy. Other prose
    references mention the line in the abstract and don't start with
    `Co-Authored-By:` at column 0.
    """
    body = COMMIT_CHANGES.read_text()
    m = re.search(r"^Co-Authored-By: .+$", body, re.MULTILINE)
    assert m, (
        "expected a `Co-Authored-By: ...` template line in "
        f"{COMMIT_CHANGES} — has it been moved or renamed?"
    )
    return m.group(0)


def _expand(template: str, env: dict[str, str]) -> str:
    """Evaluate `template` under `bash` with the given env and return the
    expanded line (trailing newline stripped).

    Runs in a near-empty env so leftover `AUTOCC_*` / `CODEX_*` exports
    in the test runner's environment don't perturb the result. The
    template is interpolated inside a double-quoted `echo` argument —
    semantically equivalent to its use inside an unquoted heredoc, which
    is how the skill instructs the agent to invoke `git commit`.
    """
    base_env = {"PATH": "/usr/bin:/bin"}
    base_env.update(env)
    proc = subprocess.run(
        ["bash", "-c", f'echo "{template}"'],
        env=base_env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.rstrip("\n")


# ---------------------------------------------------------------------------
# Default-when-unset cases (the bug TB-8 fixes)
# ---------------------------------------------------------------------------


def test_default_under_codex_session_reads_codex():
    """No `AUTOCC_*` overrides set + `CODEX_PROJECT_DIR` set
    (Codex-style env) → trailer reads `Codex <noreply@openai.com>`."""
    out = _expand(
        _extract_trailer_template(),
        {"CODEX_PROJECT_DIR": "/tmp/some-codex-project"},
    )
    assert out == "Co-Authored-By: Codex <noreply@openai.com>", (
        f"under a Codex-style env the unset-default must read "
        f"`Codex <noreply@openai.com>`, got: {out!r}"
    )


def test_default_under_claude_session_reads_claude():
    """No `AUTOCC_*` overrides set + `CODEX_PROJECT_DIR` unset
    (Claude-style env) → trailer reads `Claude <noreply@anthropic.com>`.

    Regression check: the Claude-side default is preserved exactly,
    no behavior change for the Claude install branch."""
    out = _expand(_extract_trailer_template(), {})
    assert out == "Co-Authored-By: Claude <noreply@anthropic.com>", (
        f"under a Claude-style env (no CODEX_PROJECT_DIR) the "
        f"unset-default must read `Claude <noreply@anthropic.com>`, "
        f"got: {out!r}"
    )


# ---------------------------------------------------------------------------
# Override-wins cases (the override surface that TB-4 preserved)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_extra,label",
    [
        ({}, "claude-style"),
        ({"CODEX_PROJECT_DIR": "/tmp/some-codex-project"}, "codex-style"),
    ],
)
def test_explicit_override_wins_under_both_providers(
    env_extra: dict[str, str], label: str
):
    """`AUTOCC_AGENT_NAME` / `AUTOCC_AGENT_EMAIL` set explicitly always
    wins over the provider-sniff default — under both Claude-style and
    Codex-style envs."""
    env = {
        "AUTOCC_AGENT_NAME": "Alice",
        "AUTOCC_AGENT_EMAIL": "alice@example.test",
        **env_extra,
    }
    out = _expand(_extract_trailer_template(), env)
    assert out == "Co-Authored-By: Alice <alice@example.test>", (
        f"under {label} env, explicit AUTOCC_AGENT_NAME / "
        f"AUTOCC_AGENT_EMAIL must override the provider-sniff "
        f"default, got: {out!r}"
    )


def test_partial_override_name_only_under_codex():
    """`AUTOCC_AGENT_NAME` set + `AUTOCC_AGENT_EMAIL` unset under a
    Codex-style env → name is the override; email falls through to the
    Codex-side default. Sanity check that the two env vars are
    independent (a half-override doesn't leak the other side back to
    the Claude default)."""
    out = _expand(
        _extract_trailer_template(),
        {
            "AUTOCC_AGENT_NAME": "Alice",
            "CODEX_PROJECT_DIR": "/tmp/some-codex-project",
        },
    )
    assert out == "Co-Authored-By: Alice <noreply@openai.com>", (
        f"with only AUTOCC_AGENT_NAME set under a Codex env, "
        f"the email must still default to `noreply@openai.com`, "
        f"got: {out!r}"
    )


def test_partial_override_email_only_under_claude():
    """`AUTOCC_AGENT_EMAIL` set + `AUTOCC_AGENT_NAME` unset under a
    Claude-style env → email is the override; name falls through to the
    Claude-side default."""
    out = _expand(
        _extract_trailer_template(),
        {"AUTOCC_AGENT_EMAIL": "alice@example.test"},
    )
    assert out == "Co-Authored-By: Claude <alice@example.test>", (
        f"with only AUTOCC_AGENT_EMAIL set under a Claude env, "
        f"the name must still default to `Claude`, got: {out!r}"
    )
