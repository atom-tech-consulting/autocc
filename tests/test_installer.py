"""Smoke tests for autocc.installer.

These run install/uninstall against a tmp CLAUDE_HOME (claude branch) or a tmp
AUTOCC_CODEX_PLUGIN_ROOT + marketplace path (codex branch) and verify the
on-disk result. They do NOT touch the user's real ~/.claude or ~/plugins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autocc.installer import (
    CODEX_HOOK_BASENAME,
    CODEX_HOOK_EVENTS,
    CODEX_PLUGIN_NAME,
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


# ---------------------------------------------------------------------------
# Codex provider branch
# ---------------------------------------------------------------------------


@pytest.fixture
def codex_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Return (plugin_root, marketplace_path) anchored under tmp_path."""
    plugin_root = tmp_path / "codex_plugins"
    plugin_root.mkdir()
    marketplace_path = tmp_path / "agents" / "plugins" / "marketplace.json"
    # don't pre-create the parent dir — installer should mkdir as needed
    return plugin_root, marketplace_path


def test_codex_install_creates_plugin_tree_and_marketplace_entry(
    codex_paths: tuple[Path, Path],
):
    plugin_root, marketplace_path = codex_paths
    rc = install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    assert rc == 0

    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    # 1. plugin manifest
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    assert manifest_path.is_file(), f"missing {manifest_path}"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == CODEX_PLUGIN_NAME
    assert manifest["skills"] == "./skills/"
    assert manifest["hooks"] == "./hooks.json"
    assert "version" in manifest
    assert "description" in manifest

    # 2. Skills tree
    for name in SKILL_NAMES:
        skill_md = plugin_dir / "skills" / name / "SKILL.md"
        assert skill_md.is_file(), f"missing {skill_md}"

    # 3. Stub hook script
    hook_script = plugin_dir / "hooks" / CODEX_HOOK_BASENAME
    assert hook_script.is_file()
    assert hook_script.stat().st_mode & 0o100, "stub hook should be executable"

    # 4. hooks.json registering each Codex-supported event
    hooks_json_path = plugin_dir / "hooks.json"
    assert hooks_json_path.is_file()
    hooks_payload = json.loads(hooks_json_path.read_text())
    for event in CODEX_HOOK_EVENTS:
        assert event in hooks_payload["hooks"], f"hooks.json missing {event}"
        entries = hooks_payload["hooks"][event]
        assert entries, f"{event} has no handler entries"
        cmd = entries[0]["hooks"][0]["command"]
        assert CODEX_HOOK_BASENAME in cmd
        assert event in cmd  # hook script receives the event name as arg

    # 5. Marketplace entry
    assert marketplace_path.is_file()
    marketplace = json.loads(marketplace_path.read_text())
    assert "plugins" in marketplace
    matching = [
        p for p in marketplace["plugins"]
        if isinstance(p, dict) and p.get("name") == CODEX_PLUGIN_NAME
    ]
    assert len(matching) == 1, f"expected one autocc entry, got {matching}"
    entry = matching[0]
    assert entry["source"] == {
        "source": "local",
        "path": f"./plugins/{CODEX_PLUGIN_NAME}",
    }
    assert entry["policy"]["installation"] == "AVAILABLE"
    assert entry["policy"]["authentication"] == "ON_INSTALL"
    assert entry["category"]


def test_codex_install_is_idempotent(codex_paths: tuple[Path, Path]):
    plugin_root, marketplace_path = codex_paths
    install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    before = marketplace_path.read_text()
    install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    after = marketplace_path.read_text()
    assert before == after, "second install should be a no-op against marketplace"

    # plugins[] should still have exactly one autocc entry
    payload = json.loads(after)
    matching = [
        p for p in payload["plugins"]
        if isinstance(p, dict) and p.get("name") == CODEX_PLUGIN_NAME
    ]
    assert len(matching) == 1


def test_codex_install_preserves_existing_marketplace_entries(
    codex_paths: tuple[Path, Path],
):
    plugin_root, marketplace_path = codex_paths
    # Pre-existing user marketplace with another plugin and a custom display name
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_path.write_text(json.dumps({
        "name": "my-marketplace",
        "interface": {"displayName": "My Marketplace"},
        "plugins": [
            {
                "name": "other-plugin",
                "source": {"source": "local", "path": "./plugins/other-plugin"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            },
        ],
    }))

    install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)

    payload = json.loads(marketplace_path.read_text())
    # top-level metadata preserved
    assert payload["name"] == "my-marketplace"
    assert payload["interface"]["displayName"] == "My Marketplace"
    # other plugin preserved
    names = [p["name"] for p in payload["plugins"]]
    assert "other-plugin" in names
    assert CODEX_PLUGIN_NAME in names


def test_codex_uninstall_removes_plugin_and_marketplace_entry(
    codex_paths: tuple[Path, Path],
):
    plugin_root, marketplace_path = codex_paths
    install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    assert plugin_dir.is_dir()
    assert json.loads(marketplace_path.read_text())["plugins"]

    rc = uninstall(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    assert rc == 0
    assert not plugin_dir.exists(), "plugin directory should be removed"

    payload = json.loads(marketplace_path.read_text())
    matching = [
        p for p in payload["plugins"]
        if isinstance(p, dict) and p.get("name") == CODEX_PLUGIN_NAME
    ]
    assert matching == [], "autocc entry should be stripped from marketplace"


def test_codex_uninstall_preserves_other_marketplace_entries(
    codex_paths: tuple[Path, Path],
):
    plugin_root, marketplace_path = codex_paths
    install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    # Add an unrelated user entry after install
    payload = json.loads(marketplace_path.read_text())
    payload["plugins"].append({
        "name": "other-plugin",
        "source": {"source": "local", "path": "./plugins/other-plugin"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    })
    marketplace_path.write_text(json.dumps(payload, indent=2) + "\n")

    uninstall(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)

    after = json.loads(marketplace_path.read_text())
    names = [p["name"] for p in after["plugins"]]
    assert CODEX_PLUGIN_NAME not in names
    assert "other-plugin" in names


def test_codex_dry_run_writes_nothing(codex_paths: tuple[Path, Path]):
    plugin_root, marketplace_path = codex_paths
    rc = install(
        agent="codex",
        dry_run=True,
        plugin_root=plugin_root,
        marketplace_path=marketplace_path,
    )
    assert rc == 0
    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    assert not plugin_dir.exists()
    assert not marketplace_path.exists()


def test_codex_status_reports_unwired(codex_paths: tuple[Path, Path], capsys):
    plugin_root, marketplace_path = codex_paths
    rc = status(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "✗" in out


def test_codex_status_reports_wired_after_install(
    codex_paths: tuple[Path, Path], capsys
):
    plugin_root, marketplace_path = codex_paths
    install(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    status(agent="codex", plugin_root=plugin_root, marketplace_path=marketplace_path)
    out = capsys.readouterr().out
    assert "✓" in out
    assert "autocc plugin entry registered" in out


def test_unknown_agent_returns_error(tmp_path: Path, capsys):
    rc = install(agent="bogus")
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown agent" in err
