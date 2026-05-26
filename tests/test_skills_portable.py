"""Portability checks for the `afk`, `reflector`, and `commit-changes` skills.

These three skills used to bake in Claude-Code-only assumptions
(`$CLAUDE_PROJECT_DIR`, a hard-coded `Co-Authored-By: Claude
<noreply@anthropic.com>` trailer). TB-4 decoupled them via a
provider-neutral fallback chain
(`${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`)
and two trailer env vars (`AUTOCC_AGENT_NAME` / `AUTOCC_AGENT_EMAIL`).

These tests grep the skill bodies to pin the contract so a future edit
that re-introduces a Claude-only literal trips CI instead of shipping a
Codex-side regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"

AFK = SKILLS_ROOT / "afk" / "SKILL.md"
REFLECTOR = SKILLS_ROOT / "reflector" / "SKILL.md"
COMMIT_CHANGES = SKILLS_ROOT / "commit-changes" / "SKILL.md"

# Matches "$CLAUDE_PROJECT_DIR" as a bare shell variable reference, i.e. not
# followed by a word char (so `$CLAUDE_PROJECT_DIRECTORY` would NOT match) and
# not preceded by `{`/`-` (so `${... :-${CLAUDE_PROJECT_DIR:-...}}` is the
# fallback chain, not a bare reference). The intent is to catch resurrected
# Claude-only `mkdir -p "$CLAUDE_PROJECT_DIR/..."`-style snippets.
_BARE_CLAUDE_PROJECT_DIR = re.compile(r"(?<![{:-])\$CLAUDE_PROJECT_DIR(?![A-Za-z_0-9])")

# The fallback chain we expect to see wherever the skill resolves a project
# root. Whitespace-tolerant — the chain may be wrapped or rendered in a
# fenced block.
_FALLBACK_CHAIN = re.compile(
    r"\$\{AUTOCC_PROJECT_DIR:-\$\{CLAUDE_PROJECT_DIR:-\$\{CODEX_PROJECT_DIR:-\$PWD\}\}\}"
)

# The exact Claude-only trailer line that the commit-changes skill used to
# hard-code. The new contract requires the parameterized form; this literal
# must not survive as a stand-alone line.
_HARDCODED_TRAILER = re.compile(
    r"^Co-Authored-By: Claude <noreply@anthropic\.com>\s*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# afk
# ---------------------------------------------------------------------------

def test_afk_uses_fallback_chain_not_bare_claude_project_dir():
    body = AFK.read_text()
    bare = _BARE_CLAUDE_PROJECT_DIR.findall(body)
    assert not bare, (
        f"skills/afk/SKILL.md still has bare $CLAUDE_PROJECT_DIR references "
        f"outside the fallback chain: {bare}"
    )


def test_afk_cites_autocc_project_dir():
    body = AFK.read_text()
    assert "AUTOCC_PROJECT_DIR" in body, (
        "skills/afk/SKILL.md must mention AUTOCC_PROJECT_DIR (the portable "
        "project-root override)"
    )
    assert _FALLBACK_CHAIN.search(body), (
        "skills/afk/SKILL.md must contain the full fallback chain "
        "${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}"
    )


# ---------------------------------------------------------------------------
# reflector
# ---------------------------------------------------------------------------

def test_reflector_uses_fallback_chain_not_bare_claude_project_dir():
    body = REFLECTOR.read_text()
    bare = _BARE_CLAUDE_PROJECT_DIR.findall(body)
    assert not bare, (
        f"skills/reflector/SKILL.md still has bare $CLAUDE_PROJECT_DIR "
        f"references outside the fallback chain: {bare}"
    )


def test_reflector_cites_autocc_project_dir():
    body = REFLECTOR.read_text()
    assert "AUTOCC_PROJECT_DIR" in body, (
        "skills/reflector/SKILL.md must mention AUTOCC_PROJECT_DIR (the "
        "portable project-root override)"
    )
    assert _FALLBACK_CHAIN.search(body), (
        "skills/reflector/SKILL.md must contain the full fallback chain "
        "${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}"
    )


# ---------------------------------------------------------------------------
# commit-changes
# ---------------------------------------------------------------------------

def test_commit_changes_parameterizes_trailer_name():
    body = COMMIT_CHANGES.read_text()
    assert "AUTOCC_AGENT_NAME" in body, (
        "skills/commit-changes/SKILL.md must reference AUTOCC_AGENT_NAME so "
        "the Co-Authored-By trailer's name is provider-overridable"
    )


def test_commit_changes_parameterizes_trailer_email():
    body = COMMIT_CHANGES.read_text()
    assert "AUTOCC_AGENT_EMAIL" in body, (
        "skills/commit-changes/SKILL.md must reference AUTOCC_AGENT_EMAIL so "
        "the Co-Authored-By trailer's email is provider-overridable"
    )


def test_commit_changes_has_no_hardcoded_claude_trailer():
    body = COMMIT_CHANGES.read_text()
    matches = _HARDCODED_TRAILER.findall(body)
    assert not matches, (
        "skills/commit-changes/SKILL.md must NOT contain a stand-alone "
        "'Co-Authored-By: Claude <noreply@anthropic.com>' line. The name and "
        "email must appear only as defaults inside the "
        "${AUTOCC_AGENT_NAME:-Claude} / ${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com} "
        "fallback expressions."
    )


def test_commit_changes_trailer_uses_fallback_default_form():
    """Spot-check that the parameterized trailer template is the form the
    skill instructs the agent to use (catches half-finished edits that drop
    the default-value `:-...` syntax).

    TB-8 made the default-when-unset provider-aware via a `$CODEX_PROJECT_DIR`
    sniff inside the `:-` branches, so the test pins the surrounding
    `${AUTOCC_AGENT_NAME:-...}` / `${AUTOCC_AGENT_EMAIL:-...}` shape and
    checks both provider's literals appear as default candidates. The
    actual end-to-end runtime behavior is exercised by
    `tests/test_commit_changes_defaults.py`.
    """
    body = COMMIT_CHANGES.read_text()
    # The trailer expression must still have a `${AUTOCC_AGENT_NAME:-...}`
    # default branch (not bare `$AUTOCC_AGENT_NAME`), so an unset env var
    # falls through to a default rather than expanding to empty.
    assert re.search(r"\$\{AUTOCC_AGENT_NAME:-", body), (
        "commit-changes trailer must use the `${AUTOCC_AGENT_NAME:-<default>}` "
        "form so an unset env var falls through to the provider-aware default"
    )
    assert re.search(r"\$\{AUTOCC_AGENT_EMAIL:-", body), (
        "commit-changes trailer must use the `${AUTOCC_AGENT_EMAIL:-<default>}` "
        "form so an unset env var falls through to the provider-aware default"
    )
    # Both providers' literals appear as candidates inside the trailer
    # template — Claude is the historical default, Codex is the
    # provider-sniff branch.
    assert "Claude" in body, "Claude default still expected somewhere in the trailer template"
    assert "noreply@anthropic.com" in body, (
        "noreply@anthropic.com default still expected somewhere in the trailer template"
    )
    assert "Codex" in body, (
        "Codex default expected as the provider-sniff branch in the trailer template"
    )
    assert "noreply@openai.com" in body, (
        "noreply@openai.com default expected as the provider-sniff branch "
        "in the trailer template"
    )
    assert "CODEX_PROJECT_DIR" in body, (
        "commit-changes trailer must sniff $CODEX_PROJECT_DIR to pick the "
        "provider-aware default when AUTOCC_AGENT_NAME / AUTOCC_AGENT_EMAIL "
        "is unset"
    )


# ---------------------------------------------------------------------------
# sanity: the files actually exist (catches a moved-skill regression)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [AFK, REFLECTOR, COMMIT_CHANGES])
def test_skill_file_exists(path: Path):
    assert path.is_file(), f"expected skill file at {path}"
