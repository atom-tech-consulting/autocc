"""Install autocc skills + hooks for Claude Code or OpenAI Codex.

The installer has two provider branches:

- ``claude`` (default) — writes ``~/.claude/{skills,hooks}/`` and patches
  ``~/.claude/settings.json``. Honors ``CLAUDE_HOME``.
- ``codex`` — writes a plugin folder at ``${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/``
  (``.codex-plugin/plugin.json`` + ``skills/`` + ``hooks.json`` + the
  Codex-shaped autopilot hook script ``autocc-hooks-codex.py``) and adds a
  ``source.path: ./plugins/autocc`` entry to
  ``~/.agents/plugins/marketplace.json`` so Codex discovers the plugin via
  its marketplace loader.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

from . import __version__

SKILL_NAMES = ("afk", "reflector", "taskboard", "tb", "housekeeping", "commit-changes")
HOOK_BASENAMES = ("autocc-hooks.py",)
STATUSLINE_BASENAME = "statusline.sh"

# Hook config injected into ~/.claude/settings.json. Each entry is tagged with
# `autoccManaged: true` so uninstall can find + remove just our additions
# without touching the user's other hooks.
HOOK_MARKER = "autoccManaged"
STATUSLINE_DEST = "statusline-command.sh"  # name in ~/.claude/

VALID_AGENTS = ("claude", "codex")

# --- Codex provider constants ----------------------------------------------
CODEX_PLUGIN_NAME = "autocc"
# The Codex-shaped autopilot hook script, separate from the Claude script so
# each provider's wire format stays legible. Lives in src/autocc/hooks/ and
# is copied into the plugin's hooks/ subdir at install time. Per the
# discovery doc (docs/codex-mapping.md §2a), the Codex binary parses
# `permissionDecision: allow` (not Claude's
# `hookSpecificOutput.decision.behavior: allow`), so the wire shape is
# load-bearing — install must wire this script, not the Claude script.
CODEX_HOOK_BASENAME = "autocc-hooks-codex.py"
# Codex hook events autocc wires (CamelCase, as accepted by codex's
# HookStateToml deserializer + plugin hooks.json `hooks` table). Per the
# discovery doc (docs/codex-mapping.md §2a), only PreToolUse,
# PermissionRequest, and Stop have direct analogs — Elicitation / PostCompact
# / ask-user-question / enter-plan-mode are deferred to follow-ups.
CODEX_HOOK_EVENTS = ("PreToolUse", "PermissionRequest", "Stop")
CODEX_MARKETPLACE_DEFAULT_NAME = "autocc"
CODEX_MARKETPLACE_DEFAULT_DISPLAY_NAME = "autocc"
CODEX_MARKETPLACE_DEFAULT_CATEGORY = "Productivity"


def _claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))


def _codex_plugin_root() -> Path:
    """Default parent dir for the Codex plugin folder. Plugin lives at
    ``<root>/autocc/``."""
    return Path(os.environ.get("AUTOCC_CODEX_PLUGIN_ROOT", str(Path.home() / "plugins")))


def _codex_marketplace_path() -> Path:
    """Default location of the home-rooted Codex marketplace index."""
    return Path.home() / ".agents" / "plugins" / "marketplace.json"


def _package_root() -> Path:
    """Locate skill + hook payloads bundled with the package.

    When installed via pip/uv, payloads live at autocc/_skills and
    autocc/hooks inside the wheel. In editable / source layouts they sit at
    the repo root.
    """
    here = Path(__file__).resolve().parent
    # Wheel layout: src/autocc/_skills + src/autocc/hooks
    if (here / "_skills").is_dir():
        return here
    # Source layout: repo root has skills/ and src/autocc/hooks
    repo_root = here.parent.parent
    return repo_root


def _payload_paths() -> tuple[Path, Path]:
    """Return (skills_dir, hooks_dir) regardless of install layout."""
    here = Path(__file__).resolve().parent
    if (here / "_skills").is_dir():
        return here / "_skills", here / "hooks"
    repo_root = here.parent.parent
    return repo_root / "skills", here / "hooks"


def _copy_tree(src: Path, dest: Path) -> list[Path]:
    """Copy src → dest, replacing dest contents. Returns list of dest paths written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return [p for p in dest.rglob("*") if p.is_file()]


def _copy_file(src: Path, dest: Path, executable: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    if executable:
        dest.chmod(0o755)
    return dest


def _planned_hooks_block(autocc_hook_path: Path) -> dict:
    """Return the hooks object to merge into ~/.claude/settings.json."""
    cmd = f"python3 {autocc_hook_path}"
    entry = lambda hook_type: {
        "hooks": [{"type": "command", "command": f"{cmd} {hook_type}"}],
        HOOK_MARKER: True,
    }
    return {
        "PreToolUse": [
            {**entry("PreToolUse"), "matcher": "AskUserQuestion|EnterPlanMode"},
        ],
        "PermissionRequest": [entry("PermissionRequest")],
        "Elicitation": [entry("Elicitation")],
        "Stop": [entry("Stop")],
        "PostCompact": [entry("PostCompact")],
    }


def _merge_hooks(existing: dict, planned: dict) -> dict:
    """Idempotently merge planned hook entries into existing config.

    Removes any pre-existing autocc-managed entries first, then appends ours.
    Preserves the user's other hook entries unchanged.
    """
    merged = dict(existing or {})
    hooks = dict(merged.get("hooks", {}))
    for event, planned_entries in planned.items():
        current = list(hooks.get(event, []))
        # Drop our prior entries, keep the rest
        current = [e for e in current if not e.get(HOOK_MARKER)]
        current.extend(planned_entries)
        hooks[event] = current
    merged["hooks"] = hooks
    return merged


def _diff(before: str, after: str, label: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"{label} (before)",
        tofile=f"{label} (after)",
        n=3,
    )
    return "".join(diff)


def _prompt_yes(question: str, *, default_yes: bool = False) -> bool:
    suffix = " [Y/n] " if default_yes else " [y/N] "
    if not sys.stdin.isatty():
        # Non-interactive: assume the caller knows what they're doing
        return default_yes
    try:
        ans = input(question + suffix).strip().lower()
    except EOFError:
        return default_yes
    if not ans:
        return default_yes
    return ans in {"y", "yes"}


def install(
    *,
    agent: str = "claude",
    dry_run: bool = False,
    assume_yes: bool = False,
    claude_home: Path | None = None,
    plugin_root: Path | None = None,
    marketplace_path: Path | None = None,
) -> int:
    """Top-level install entry-point.

    Dispatches to the Claude or Codex provider per ``agent``. The
    ``claude_home`` arg is honored only when ``agent == "claude"``;
    ``plugin_root`` / ``marketplace_path`` are honored only when
    ``agent == "codex"``.
    """
    if agent not in VALID_AGENTS:
        print(f"error: unknown agent: {agent!r} (expected one of {VALID_AGENTS})", file=sys.stderr)
        return 2
    if agent == "codex":
        return _codex_install(
            dry_run=dry_run,
            plugin_root=plugin_root or _codex_plugin_root(),
            marketplace_path=marketplace_path or _codex_marketplace_path(),
        )
    return _claude_install(
        dry_run=dry_run,
        assume_yes=assume_yes,
        claude_home=claude_home or _claude_home(),
    )


def _claude_install(*, dry_run: bool, assume_yes: bool, claude_home: Path) -> int:
    """Install skills, hooks, statusline, and patch settings.json.

    Returns process exit code.
    """
    home = claude_home
    skills_src, hooks_src = _payload_paths()

    if not skills_src.is_dir() or not hooks_src.is_dir():
        print(f"error: payloads missing (skills={skills_src}, hooks={hooks_src})", file=sys.stderr)
        return 2

    print(f"autocc install → {home}")
    print()

    # 1. Skills
    skills_dest = home / "skills"
    skill_count = 0
    for name in SKILL_NAMES:
        src = skills_src / name
        if not src.is_dir():
            print(f"  warn: skill source missing: {src}", file=sys.stderr)
            continue
        dest = skills_dest / name
        if dry_run:
            print(f"  [dry-run] would install skill: {dest}")
        else:
            _copy_tree(src, dest)
            print(f"  installed skill: {dest}")
        skill_count += 1

    # 2. Hooks
    hook_dest_dir = home / "hooks"
    autocc_hook_dest = hook_dest_dir / "autocc-hooks.py"
    for name in HOOK_BASENAMES:
        src = hooks_src / name
        dest = hook_dest_dir / name
        if dry_run:
            print(f"  [dry-run] would install hook: {dest}")
        else:
            _copy_file(src, dest, executable=True)
            print(f"  installed hook: {dest}")

    # 3. Statusline (lives at ~/.claude/statusline-command.sh)
    statusline_dest = home / STATUSLINE_DEST
    statusline_src = hooks_src / STATUSLINE_BASENAME
    if dry_run:
        print(f"  [dry-run] would install statusline: {statusline_dest}")
    else:
        _copy_file(statusline_src, statusline_dest, executable=True)
        print(f"  installed statusline: {statusline_dest}")

    # 4. settings.json — show diff, prompt, then merge
    settings_path = home / "settings.json"
    existing: dict = {}
    before_text = ""
    if settings_path.exists():
        before_text = settings_path.read_text()
        try:
            existing = json.loads(before_text) if before_text.strip() else {}
        except json.JSONDecodeError as e:
            print(f"error: {settings_path} is not valid JSON ({e})", file=sys.stderr)
            return 3

    planned = _planned_hooks_block(autocc_hook_dest)
    merged = _merge_hooks(existing, planned)
    after_text = json.dumps(merged, indent=2) + "\n"

    if before_text.strip() == after_text.strip():
        print()
        print(f"  settings.json: already up to date")
    else:
        print()
        print(f"  settings.json patch ({settings_path}):")
        print()
        diff_text = _diff(before_text or "{}\n", after_text, settings_path.name)
        for line in diff_text.splitlines():
            print(f"    {line}")
        print()
        proceed = assume_yes or _prompt_yes(
            "Apply this patch to settings.json?", default_yes=True
        )
        if not proceed:
            print("  skipped settings.json patch.")
        elif dry_run:
            print("  [dry-run] skipped writing settings.json")
        else:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(after_text)
            print(f"  wrote {settings_path}")

    print()
    print(f"Done. {skill_count} skills, {len(HOOK_BASENAMES)} hook(s), 1 statusline.")
    print()
    print("Next: in any project where you want to enable autopilot, run `/afk` —")
    print("that creates .autocc/flag and starts the reflector loop. To configure")
    print("a task board first, run `/taskboard init`.")
    return 0


def uninstall(
    *,
    agent: str = "claude",
    dry_run: bool = False,
    assume_yes: bool = False,
    claude_home: Path | None = None,
    plugin_root: Path | None = None,
    marketplace_path: Path | None = None,
) -> int:
    """Top-level uninstall entry-point; dispatches per ``agent``."""
    if agent not in VALID_AGENTS:
        print(f"error: unknown agent: {agent!r} (expected one of {VALID_AGENTS})", file=sys.stderr)
        return 2
    if agent == "codex":
        return _codex_uninstall(
            dry_run=dry_run,
            plugin_root=plugin_root or _codex_plugin_root(),
            marketplace_path=marketplace_path or _codex_marketplace_path(),
        )
    return _claude_uninstall(
        dry_run=dry_run,
        assume_yes=assume_yes,
        claude_home=claude_home or _claude_home(),
    )


def _claude_uninstall(*, dry_run: bool, assume_yes: bool, claude_home: Path) -> int:
    """Remove skills + hooks + revert settings.json autocc entries."""
    home = claude_home
    print(f"autocc uninstall ← {home}")
    print()

    # Skills
    skills_dir = home / "skills"
    for name in SKILL_NAMES:
        dest = skills_dir / name
        if dest.exists():
            if dry_run:
                print(f"  [dry-run] would remove skill: {dest}")
            else:
                shutil.rmtree(dest)
                print(f"  removed skill: {dest}")

    # Hooks
    for name in HOOK_BASENAMES:
        dest = home / "hooks" / name
        if dest.exists():
            if dry_run:
                print(f"  [dry-run] would remove hook: {dest}")
            else:
                dest.unlink()
                print(f"  removed hook: {dest}")

    # Statusline
    statusline_dest = home / STATUSLINE_DEST
    if statusline_dest.exists():
        if dry_run:
            print(f"  [dry-run] would remove statusline: {statusline_dest}")
        else:
            statusline_dest.unlink()
            print(f"  removed statusline: {statusline_dest}")

    # settings.json — strip our entries
    settings_path = home / "settings.json"
    if settings_path.exists():
        before_text = settings_path.read_text()
        try:
            existing = json.loads(before_text) if before_text.strip() else {}
        except json.JSONDecodeError:
            print(f"  warn: {settings_path} not valid JSON, leaving as-is", file=sys.stderr)
            existing = None

        if existing is not None:
            hooks = dict(existing.get("hooks", {}))
            changed = False
            for event in list(hooks.keys()):
                kept = [e for e in hooks[event] if not e.get(HOOK_MARKER)]
                if len(kept) != len(hooks[event]):
                    changed = True
                if kept:
                    hooks[event] = kept
                else:
                    del hooks[event]
            if changed:
                if hooks:
                    existing["hooks"] = hooks
                else:
                    existing.pop("hooks", None)
                after_text = json.dumps(existing, indent=2) + "\n"
                if dry_run:
                    print(f"  [dry-run] would strip autocc entries from {settings_path}")
                else:
                    settings_path.write_text(after_text)
                    print(f"  stripped autocc entries from {settings_path}")

    print()
    print("Done.")
    return 0


def status(
    *,
    agent: str = "claude",
    claude_home: Path | None = None,
    plugin_root: Path | None = None,
    marketplace_path: Path | None = None,
) -> int:
    """Top-level status entry-point; dispatches per ``agent``."""
    if agent not in VALID_AGENTS:
        print(f"error: unknown agent: {agent!r} (expected one of {VALID_AGENTS})", file=sys.stderr)
        return 2
    if agent == "codex":
        return _codex_status(
            plugin_root=plugin_root or _codex_plugin_root(),
            marketplace_path=marketplace_path or _codex_marketplace_path(),
        )
    return _claude_status(claude_home=claude_home or _claude_home())


def _claude_status(*, claude_home: Path) -> int:
    """Show which autocc artifacts are currently installed."""
    home = claude_home
    print(f"autocc status @ {home}")
    print()

    print("Skills:")
    for name in SKILL_NAMES:
        dest = home / "skills" / name
        mark = "✓" if dest.is_dir() else "✗"
        print(f"  {mark} {name}")

    print()
    print("Hooks:")
    for name in HOOK_BASENAMES:
        dest = home / "hooks" / name
        mark = "✓" if dest.is_file() else "✗"
        print(f"  {mark} {name}")
    statusline_dest = home / STATUSLINE_DEST
    mark = "✓" if statusline_dest.is_file() else "✗"
    print(f"  {mark} {STATUSLINE_DEST}")

    print()
    print("settings.json:")
    settings_path = home / "settings.json"
    if not settings_path.exists():
        print("  ✗ not present")
    else:
        try:
            data = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            print("  ! invalid JSON")
            return 0
        hooks = data.get("hooks", {})
        managed_events: list[str] = []
        for event, entries in hooks.items():
            if any(e.get(HOOK_MARKER) for e in entries):
                managed_events.append(event)
        if managed_events:
            print(f"  ✓ autocc hooks wired for: {', '.join(managed_events)}")
        else:
            print("  ✗ no autocc hooks wired")
    return 0


# ===========================================================================
# Codex provider
# ===========================================================================
#
# Codex discovers plugins via marketplaces (not by scanning CODEX_HOME), so
# autocc installs as a self-contained plugin folder plus a single marketplace
# entry. The plugin folder shape (per ~/.codex/skills/.system/plugin-creator):
#
#   <plugin_root>/autocc/
#     .codex-plugin/plugin.json        — manifest (name, version, skills, hooks)
#     skills/<name>/SKILL.md           — copied from the shared payload
#     hooks.json                       — registers PreToolUse /
#                                        PermissionRequest / Stop, pointing
#                                        at the Codex hook script
#     hooks/autocc-hooks-codex.py      — Codex-shaped autopilot hook script
#                                        (TB-3 replaced the prior stub with
#                                        the real implementation)
#
# The marketplace entry lives at ~/.agents/plugins/marketplace.json with
# `source.path: ./plugins/autocc`, which Codex resolves to ~/plugins/autocc/
# per the plugin-creator skill's documented convention.


def _codex_plugin_manifest(plugin_name: str, version: str) -> dict:
    """Build the `.codex-plugin/plugin.json` manifest.

    Keeps to the minimal field set the loader needs to surface skills + hooks:
    `name`, `version`, `description`, `skills` path, `hooks` path. The fuller
    `interface` block (display name, brand color, screenshots, etc.) is
    optional and omitted here — autocc is a CLI bundle, not a UI plugin.
    """
    return {
        "name": plugin_name,
        "version": version,
        "description": "autopilot for Claude Code / Codex — skills + hooks for unattended sessions",
        "skills": "./skills/",
        "hooks": "./hooks.json",
    }


def _codex_hooks_json(hook_script_relpath: str) -> dict:
    """Build the plugin-level `hooks.json` registering autocc's three events.

    Shape matches Codex's hooks.json convention (see e.g. the bundled `figma`
    plugin): top-level `hooks` object keyed by CamelCase event name, each
    value an array of `{matcher?, hooks: [{type, command}]}` entries. The
    command path is relative to the plugin root — Codex sets `PLUGIN_ROOT`
    / `CLAUDE_PLUGIN_ROOT` env vars when invoking hook commands, but
    relative paths are also resolved against the plugin root by the
    dispatcher.

    The hook script is invoked with ``python3 ...`` rather than relying on
    the shebang so the plugin loads cleanly on systems where ``python3``
    isn't on ``PATH`` for shebang resolution (e.g. some homebrew setups
    where the script's mode bit is dropped on copy).
    """
    cmd = f"python3 {hook_script_relpath}"

    def entry(event: str) -> dict:
        return {
            "hooks": [
                {"type": "command", "command": f"{cmd} {event}"},
            ],
        }

    # Mirror the Claude install's PreToolUse matcher — the AskUserQuestion /
    # EnterPlanMode tools don't exist on Codex, so this matcher never fires
    # in practice, but pinning the matcher documents intent and avoids
    # invoking the hook on every Bash/Edit/Write call.
    hooks: dict = {}
    for event in CODEX_HOOK_EVENTS:
        if event == "PreToolUse":
            hooks[event] = [{**entry(event), "matcher": "AskUserQuestion|EnterPlanMode"}]
        else:
            hooks[event] = [entry(event)]
    return {"hooks": hooks}


def _codex_marketplace_entry(plugin_name: str) -> dict:
    """Build a single `plugins[]` entry per the plugin-creator skill spec."""
    return {
        "name": plugin_name,
        "source": {
            "source": "local",
            "path": f"./plugins/{plugin_name}",
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": CODEX_MARKETPLACE_DEFAULT_CATEGORY,
    }


def _seed_marketplace_payload() -> dict:
    """Top-level shape the plugin-creator skill writes for a brand-new
    marketplace.json: `name`, `interface.displayName`, empty `plugins`."""
    return {
        "name": CODEX_MARKETPLACE_DEFAULT_NAME,
        "interface": {"displayName": CODEX_MARKETPLACE_DEFAULT_DISPLAY_NAME},
        "plugins": [],
    }


def _merge_marketplace_entry(existing: dict | None, entry: dict) -> dict:
    """Idempotent merge: replace any prior `plugins[]` entry with the same
    `name`, or append. Preserves top-level `name`, `interface`, and any
    other plugin entries the user / other tools added."""
    merged = dict(existing) if isinstance(existing, dict) else _seed_marketplace_payload()
    # Backfill missing top-level fields rather than overwriting existing ones.
    merged.setdefault("name", CODEX_MARKETPLACE_DEFAULT_NAME)
    iface = merged.get("interface")
    if not isinstance(iface, dict):
        merged["interface"] = {"displayName": CODEX_MARKETPLACE_DEFAULT_DISPLAY_NAME}
    elif "displayName" not in iface:
        iface["displayName"] = CODEX_MARKETPLACE_DEFAULT_DISPLAY_NAME

    plugins = list(merged.get("plugins") or [])
    replaced = False
    for i, p in enumerate(plugins):
        if isinstance(p, dict) and p.get("name") == entry["name"]:
            plugins[i] = entry
            replaced = True
            break
    if not replaced:
        plugins.append(entry)
    merged["plugins"] = plugins
    return merged


def _strip_marketplace_entry(existing: dict, plugin_name: str) -> tuple[dict, bool]:
    """Return (payload-with-entry-removed, changed?)."""
    plugins = list(existing.get("plugins") or [])
    new_plugins = [
        p for p in plugins
        if not (isinstance(p, dict) and p.get("name") == plugin_name)
    ]
    changed = len(new_plugins) != len(plugins)
    out = dict(existing)
    out["plugins"] = new_plugins
    return out, changed


def _codex_install(*, dry_run: bool, plugin_root: Path, marketplace_path: Path) -> int:
    """Install autocc as a Codex plugin at ``<plugin_root>/autocc/``.

    Returns process exit code.
    """
    skills_src, hooks_src = _payload_paths()
    if not skills_src.is_dir():
        print(f"error: skill payloads missing at {skills_src}", file=sys.stderr)
        return 2
    hook_src_path = hooks_src / CODEX_HOOK_BASENAME
    if not hook_src_path.is_file():
        print(
            f"error: Codex hook script missing at {hook_src_path}",
            file=sys.stderr,
        )
        return 2

    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    print(f"autocc install (codex) → {plugin_dir}")
    print()

    # 1. plugin manifest
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    manifest = _codex_plugin_manifest(CODEX_PLUGIN_NAME, __version__)
    manifest_text = json.dumps(manifest, indent=2) + "\n"
    if dry_run:
        print(f"  [dry-run] would write manifest: {manifest_path}")
    else:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest_text)
        print(f"  wrote manifest: {manifest_path}")

    # 2. Skills (copy from shared payload)
    skills_dest = plugin_dir / "skills"
    skill_count = 0
    for name in SKILL_NAMES:
        src = skills_src / name
        if not src.is_dir():
            print(f"  warn: skill source missing: {src}", file=sys.stderr)
            continue
        dest = skills_dest / name
        if dry_run:
            print(f"  [dry-run] would install skill: {dest}")
        else:
            _copy_tree(src, dest)
            print(f"  installed skill: {dest}")
        skill_count += 1

    # 3. Codex-shaped hook script + hooks.json registration
    hook_script_path = plugin_dir / "hooks" / CODEX_HOOK_BASENAME
    if dry_run:
        print(f"  [dry-run] would install hook script: {hook_script_path}")
    else:
        hook_script_path.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(hook_src_path, hook_script_path, executable=True)
        print(f"  installed hook script: {hook_script_path}")

    hooks_json_path = plugin_dir / "hooks.json"
    hooks_payload = _codex_hooks_json(f"./hooks/{CODEX_HOOK_BASENAME}")
    hooks_text = json.dumps(hooks_payload, indent=2) + "\n"
    if dry_run:
        print(f"  [dry-run] would write hooks.json: {hooks_json_path}")
    else:
        hooks_json_path.write_text(hooks_text)
        print(f"  wrote hooks.json: {hooks_json_path}")

    # 4. Marketplace entry (idempotent merge)
    before_text = ""
    existing: dict | None = None
    if marketplace_path.exists():
        before_text = marketplace_path.read_text()
        try:
            existing = json.loads(before_text) if before_text.strip() else None
        except json.JSONDecodeError as e:
            print(f"error: {marketplace_path} is not valid JSON ({e})", file=sys.stderr)
            return 3

    entry = _codex_marketplace_entry(CODEX_PLUGIN_NAME)
    merged = _merge_marketplace_entry(existing, entry)
    after_text = json.dumps(merged, indent=2) + "\n"

    if before_text.strip() == after_text.strip():
        print(f"  marketplace.json: already up to date ({marketplace_path})")
    elif dry_run:
        print(f"  [dry-run] would update marketplace.json: {marketplace_path}")
    else:
        marketplace_path.parent.mkdir(parents=True, exist_ok=True)
        marketplace_path.write_text(after_text)
        print(f"  wrote marketplace entry: {marketplace_path}")

    print()
    print(f"Done. {skill_count} skills, {len(CODEX_HOOK_EVENTS)} hook event(s), 1 plugin.")
    print()
    print("Next: start codex; the plugin loads via the marketplace entry.")
    return 0


def _codex_uninstall(*, dry_run: bool, plugin_root: Path, marketplace_path: Path) -> int:
    """Remove the Codex plugin folder + strip the marketplace entry."""
    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    print(f"autocc uninstall (codex) ← {plugin_dir}")
    print()

    if plugin_dir.exists():
        if dry_run:
            print(f"  [dry-run] would remove plugin folder: {plugin_dir}")
        else:
            shutil.rmtree(plugin_dir)
            print(f"  removed plugin folder: {plugin_dir}")
    else:
        print(f"  plugin folder not present: {plugin_dir}")

    if marketplace_path.exists():
        before_text = marketplace_path.read_text()
        try:
            existing = json.loads(before_text) if before_text.strip() else {}
        except json.JSONDecodeError:
            print(
                f"  warn: {marketplace_path} not valid JSON, leaving as-is",
                file=sys.stderr,
            )
            existing = None

        if isinstance(existing, dict):
            stripped, changed = _strip_marketplace_entry(existing, CODEX_PLUGIN_NAME)
            if changed:
                after_text = json.dumps(stripped, indent=2) + "\n"
                if dry_run:
                    print(
                        f"  [dry-run] would strip autocc entry from {marketplace_path}"
                    )
                else:
                    marketplace_path.write_text(after_text)
                    print(f"  stripped autocc entry from {marketplace_path}")

    print()
    print("Done.")
    return 0


def _codex_status(*, plugin_root: Path, marketplace_path: Path) -> int:
    """Show which Codex plugin artifacts are currently installed."""
    plugin_dir = plugin_root / CODEX_PLUGIN_NAME
    print(f"autocc status (codex) @ {plugin_dir}")
    print()

    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    mark = "✓" if manifest_path.is_file() else "✗"
    print(f"Manifest: {mark} {manifest_path}")

    print()
    print("Skills:")
    for name in SKILL_NAMES:
        dest = plugin_dir / "skills" / name / "SKILL.md"
        mark = "✓" if dest.is_file() else "✗"
        print(f"  {mark} {name}")

    print()
    print("Hooks:")
    hooks_json = plugin_dir / "hooks.json"
    mark = "✓" if hooks_json.is_file() else "✗"
    print(f"  {mark} hooks.json")
    hook_stub = plugin_dir / "hooks" / CODEX_HOOK_BASENAME
    mark = "✓" if hook_stub.is_file() else "✗"
    print(f"  {mark} {CODEX_HOOK_BASENAME}")

    print()
    print(f"Marketplace ({marketplace_path}):")
    if not marketplace_path.exists():
        print("  ✗ not present")
        return 0
    try:
        data = json.loads(marketplace_path.read_text())
    except json.JSONDecodeError:
        print("  ! invalid JSON")
        return 0
    plugins = data.get("plugins") or []
    wired = any(
        isinstance(p, dict) and p.get("name") == CODEX_PLUGIN_NAME
        for p in plugins
    )
    mark = "✓" if wired else "✗"
    print(f"  {mark} autocc plugin entry registered")
    return 0
