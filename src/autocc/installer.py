"""Install autocc skills + hooks into ~/.claude/ and wire up settings.json."""

from __future__ import annotations

import difflib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

SKILL_NAMES = ("afk", "reflector", "taskboard", "tb", "housekeeping", "commit-changes")
HOOK_BASENAMES = ("autocc-hooks.py",)
STATUSLINE_BASENAME = "statusline.sh"

# Hook config injected into ~/.claude/settings.json. Each entry is tagged with
# `autoccManaged: true` so uninstall can find + remove just our additions
# without touching the user's other hooks.
HOOK_MARKER = "autoccManaged"
STATUSLINE_DEST = "statusline-command.sh"  # name in ~/.claude/


def _claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_HOME", str(Path.home() / ".claude")))


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


def install(*, dry_run: bool = False, assume_yes: bool = False, claude_home: Path | None = None) -> int:
    """Install skills, hooks, statusline, and patch settings.json.

    Returns process exit code.
    """
    home = claude_home or _claude_home()
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


def uninstall(*, dry_run: bool = False, assume_yes: bool = False, claude_home: Path | None = None) -> int:
    """Remove skills + hooks + revert settings.json autocc entries."""
    home = claude_home or _claude_home()
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


def status(claude_home: Path | None = None) -> int:
    """Show which autocc artifacts are currently installed."""
    home = claude_home or _claude_home()
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
