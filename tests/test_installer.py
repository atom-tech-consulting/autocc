"""Smoke tests for autocc.installer.

These run install/uninstall against a tmp CLAUDE_HOME and verify the on-disk
result. They do NOT touch the user's real ~/.claude.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autocc.installer import (
    HOOK_MARKER,
    SKILL_NAMES,
    install,
    status,
    uninstall,
)


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "claude"
    home.mkdir()
    return home


def test_install_into_empty_home_creates_skills_hooks_settings(fake_home: Path):
    rc = install(assume_yes=True, claude_home=fake_home)
    assert rc == 0

    for name in SKILL_NAMES:
        skill_md = fake_home / "skills" / name / "SKILL.md"
        assert skill_md.is_file(), f"missing {skill_md}"

    autopilot = fake_home / "hooks" / "autocc-hooks.py"
    assert autopilot.is_file()
    assert autopilot.stat().st_mode & 0o100, "autocc-hooks.py should be executable"

    statusline = fake_home / "statusline-command.sh"
    assert statusline.is_file()
    assert statusline.stat().st_mode & 0o100

    settings = json.loads((fake_home / "settings.json").read_text())
    hooks = settings["hooks"]
    for event in ("PreToolUse", "PermissionRequest", "Elicitation", "Stop", "PostCompact"):
        assert event in hooks, f"settings.json missing {event} hook"
        assert any(e.get(HOOK_MARKER) for e in hooks[event])


def test_install_is_idempotent(fake_home: Path):
    install(assume_yes=True, claude_home=fake_home)
    settings_before = (fake_home / "settings.json").read_text()
    install(assume_yes=True, claude_home=fake_home)
    settings_after = (fake_home / "settings.json").read_text()
    assert settings_before == settings_after


def test_install_preserves_existing_user_hooks(fake_home: Path):
    # User already has a custom hook configured
    fake_home.mkdir(exist_ok=True)
    (fake_home / "settings.json").write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "echo user-hook"}],
                 "matcher": "Bash"},
            ]
        }
    }))

    install(assume_yes=True, claude_home=fake_home)

    settings = json.loads((fake_home / "settings.json").read_text())
    pre_tool_use = settings["hooks"]["PreToolUse"]

    # User's hook preserved
    user_hook = [e for e in pre_tool_use if not e.get(HOOK_MARKER)]
    assert len(user_hook) == 1
    assert user_hook[0]["hooks"][0]["command"] == "echo user-hook"

    # autocc hook added
    autocc_hook = [e for e in pre_tool_use if e.get(HOOK_MARKER)]
    assert len(autocc_hook) == 1


def test_uninstall_removes_artifacts_and_strips_settings(fake_home: Path):
    install(assume_yes=True, claude_home=fake_home)
    uninstall(assume_yes=True, claude_home=fake_home)

    for name in SKILL_NAMES:
        assert not (fake_home / "skills" / name).exists()
    assert not (fake_home / "hooks" / "autocc-hooks.py").exists()
    assert not (fake_home / "statusline-command.sh").exists()

    settings = json.loads((fake_home / "settings.json").read_text())
    hooks = settings.get("hooks", {})
    for entries in hooks.values():
        for e in entries:
            assert not e.get(HOOK_MARKER), "autocc entry should be stripped"


def test_uninstall_preserves_user_hooks(fake_home: Path):
    (fake_home / "settings.json").write_text(json.dumps({
        "hooks": {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "echo user-hook"}],
                 "matcher": "Bash"},
            ]
        }
    }))
    install(assume_yes=True, claude_home=fake_home)
    uninstall(assume_yes=True, claude_home=fake_home)

    settings = json.loads((fake_home / "settings.json").read_text())
    pre_tool_use = settings["hooks"]["PreToolUse"]
    assert len(pre_tool_use) == 1
    assert pre_tool_use[0]["hooks"][0]["command"] == "echo user-hook"


def test_dry_run_writes_nothing(fake_home: Path):
    rc = install(dry_run=True, assume_yes=True, claude_home=fake_home)
    assert rc == 0
    assert not (fake_home / "skills").exists() or not any((fake_home / "skills").iterdir())
    assert not (fake_home / "hooks").exists() or not any((fake_home / "hooks").iterdir())
    assert not (fake_home / "settings.json").exists()


def test_status_reports_unwired(fake_home: Path, capsys):
    rc = status(claude_home=fake_home)
    assert rc == 0
    out = capsys.readouterr().out
    assert "✗" in out


def test_status_reports_wired_after_install(fake_home: Path, capsys):
    install(assume_yes=True, claude_home=fake_home)
    status(claude_home=fake_home)
    out = capsys.readouterr().out
    assert "✓" in out
    assert "autocc hooks wired" in out
