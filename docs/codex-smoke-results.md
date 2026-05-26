# Codex live-smoke results — TB-9

Tracks the actual on-disk outcome of running the opt-in real-SDK Codex
smoke (`tests/smoke/test_reflector_e2e_codex.py`) against the operator's
locally-installed `codex` CLI. This is the artifact required by TB-9's
verification gate: it records that the live validation was attempted,
what the run actually exercised, which `docs/codex-mapping.md`
"verify before depending on it" items resolved, and where the install
path stands vs. the smoke's mandatory hook-fired assertion.

## Environment

- **Date:** 2026-05-21
- **codex binary:** `codex-cli 0.132.0` (from `codex --version`),
  resolved at `/opt/homebrew/bin/codex` →
  `/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/codex/codex`
- **Host:** macOS, arm64 (operator's primary dev machine)
- **Codex auth:** ChatGPT Pro account, seeded into sandbox HOME via
  `~/.codex/auth.json` + `~/.codex/config.toml` copy (see fixture
  `_seed_codex_auth`).
- **Command run:**
  `bash -c 'AUTOCC_REAL_SDK=1 AUTOCC_SMOKE_WORKSPACE=/tmp/tb9-smoke/ws-2
  uv run pytest -q tests/smoke/test_reflector_e2e_codex.py -s'`

The smoke installs autocc as a Codex plugin into a sandboxed `HOME`,
registers the local marketplace + plugin via
`codex plugin marketplace add` + `codex plugin add`, mirrors the
plugin's hooks into `config.toml`'s stable `[hooks]` table as a
workaround for codex 0.132's incomplete `plugin_hooks` dispatcher
(see §Bugs found below), and then launches a non-interactive
`codex exec --enable plugin_hooks --dangerously-bypass-approvals-and-sandbox
--dangerously-bypass-hook-trust --skip-git-repo-check -C <project>`
against an `examples/taskflow` copy with `.autocc/flag` set and one
seeded backlog task (`TB-99: Add autopilot smoke marker to README`).

## Outcome

| Bar | Result | Evidence |
|---|---|---|
| Plugin install (`autocc install --agent codex`) | **pass** | Plugin manifest + hooks.json + skills/ landed at `<HOME>/plugins/autocc/`; `marketplace.json` at `<HOME>/.agents/plugins/`. |
| Marketplace registration (`codex plugin marketplace add`) | **pass** | `[marketplaces.autocc]` block written to sandboxed `config.toml`. |
| Plugin install via codex (`codex plugin add autocc@autocc`) | **pass** | `[plugins."autocc@autocc"] enabled = true` written; plugin cached at `<HOME>/.codex/plugins/cache/autocc/autocc/0.1.0/`. |
| Skills discoverable to codex | **pass** | Codex's session log (`<HOME>/.codex/sessions/.../*.jsonl`) shows the developer message listing `autocc:afk`, `autocc:commit-changes`, `autocc:housekeeping`, `autocc:reflector`, `autocc:taskboard`, `autocc:tb` under `### Available skills`, each resolved to the cached plugin path. |
| Reflector workflow runs end-to-end | **pass** | Codex completed `TB-99`: appended `<!-- autocc-smoke-marker -->` to `README.md`, wrote the briefing, moved the task Backlog → Complete, committed locally with subject `Complete TB-99 smoke marker`. |
| **Mandatory assertion — `autocc-hooks-codex.py` fired at least once** | **FAIL** | `.autocc/decisions.log` is absent (not just empty — never created) in the post-run workspace. No `HookStarted` / `HookCompleted` rows in the codex session JSONL either. The hook script was never spawned. |
| Stretch — Backlog → Complete cycle + commit subject references seed task | **n/a (mandatory failed)** | Would have passed: `TB-99` is in `## Complete`, absent from `## Backlog`, and HEAD subject is `Complete TB-99 smoke marker`. But this is a soft assertion the smoke only checks after the mandatory one. |

**Net:** install + discovery + skill-dispatch work end-to-end against
real codex; **hooks do not fire**. The smoke's mandatory assertion
cannot be made to pass on codex-cli 0.132 in `codex exec` mode without
either (a) a TUI-only step the test cannot drive non-interactively, or
(b) a fix that ships in a future codex release.

## Bugs found (and which were fixable)

### 1. `autocc-hooks-codex.py` resolved `project_dir` to the *plugin install dir*, not the project root — **fixed**

The pre-TB-9 hook script's project-root chain was:

    PLUGIN_ROOT → CLAUDE_PLUGIN_ROOT → hook_input.cwd → os.getcwd()

Codex's `PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` env vars (per
`docs/codex-mapping.md` §1c) point at the plugin's *install directory*
(e.g. `$CODEX_HOME/plugins/cache/autocc/autocc/0.1.0/`), **not** the
project root. So even if codex had been firing the hook, the script
would have resolved `.autocc/flag` to
`$CODEX_HOME/plugins/cache/.../0.1.0/.autocc/flag` — which doesn't
exist — and silently no-op'd. The unit tests in
`tests/test_autocc_hook_codex.py` had codified this same wrong
assumption (they passed `PLUGIN_ROOT` as the project anchor and
asserted it overrode `cwd`), masking the latent bug.

**Fix (this commit):**

- `src/autocc/hooks/autocc-hooks-codex.py`: switched the resolution
  chain to
  `AUTOCC_PROJECT_DIR → CLAUDE_PROJECT_DIR → CODEX_PROJECT_DIR →
  hook_input.cwd → PLUGIN_ROOT → CLAUDE_PLUGIN_ROOT → os.getcwd()`.
  `PLUGIN_ROOT` is kept as a low-priority fallback purely for
  backwards compat with synthetic unit-test contexts that use it as a
  project-root stand-in.
- `tests/test_autocc_hook_codex.py`: removed the two tests that
  encoded the wrong precedence
  (`test_plugin_root_env_overrides_stdin_cwd`,
  `test_claude_plugin_root_env_alias_honored`) and added four new
  tests that pin the correct chain
  (`test_autocc_project_dir_env_overrides_stdin_cwd`,
  `test_claude_project_dir_env_honored_for_parity`,
  `test_stdin_cwd_wins_over_plugin_root_env`,
  `test_plugin_root_env_used_as_legacy_fallback`,
  `test_claude_plugin_root_env_alias_used_as_legacy_fallback`).

This resolves the `docs/codex-mapping.md` §1c "verify before depending
on it" item about `PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` semantics. Their
documented role is "locate plugin assets" — which is consistent with
codex's actual behavior — and the binary does **not** repurpose them
as the project anchor. The Claude Code parity claim in the mapping
doc was about the env-var *name*, not about what the value points at,
and the hook script had read past that distinction.

### 2. The live smoke missed two non-interactive setup steps — **fixed**

The smoke as authored under TB-5 only ran the installer + flipped
`--enable plugin_hooks`. That's enough on a fresh codex install where
the marketplace was already registered, but a sandboxed `HOME` is
empty. `codex exec` then doesn't discover the plugin at all.

**Fix:** the test fixture now calls
`codex plugin marketplace add <HOME>` and
`codex plugin add autocc@autocc` between install and launch, with
`HOME` / `CODEX_HOME` pointed at the sandbox so the writes stay
isolated. It also passes `--dangerously-bypass-hook-trust` on the
`codex exec` invocation — codex 0.132 surfaces hook-trust review in
the TUI (binary strings: `Hooks need review`, `New hook - review
required`, `1 hook needs review before it can run`, source file
`startup_hooks_review.rs`); `codex exec` has no UI to confirm the
review, so without the bypass any enabled hooks would be silently
gated even if `plugin_hooks` were wired through.

This resolves the `docs/codex-mapping.md` §1 "Plugins → discovery is
marketplace-driven, not filesystem-scan" caveat in the concrete:
yes, `[marketplaces.<name>]` and `[plugins."<id>@<mp>"]` blocks in
`config.toml` are mandatory for `codex exec` to see the plugin, and
the `codex plugin marketplace add` / `codex plugin add` subcommands
are the only non-interactive way to write them.

### 3. The Codex hook script never logged `Stop` decisions, only `PermissionRequest` — **fixed**

The pre-TB-9 hook script only called `log_decision(...)` from
`handle_permission_request`. The smoke's mandatory assertion is
"hook fired at least once", but under
`--dangerously-bypass-approvals-and-sandbox` codex never issues a
permission request (the docstring on that flag — and the binary's
behavior — is "no interactive approval prompts"), so even if hooks
were dispatching correctly, only `Stop` would fire, and `Stop`
wouldn't write `decisions.log`. The smoke would fail with hook-fired
evidence that the hook *had* run but on an event the script chose
not to log.

**Fix:** `handle_stop` now writes a `decisions.log` entry on each
of its three terminal paths (`stop_hook_active=true`, board empty,
or board-has-work). The decision values are
`Stop -> stop|stop|block` respectively, with substantive `reason`
strings so they're distinguishable in the log.

This makes `Stop` the universal "hook fired" signal an operator or
smoke can grep for, which is what the mandatory assertion needs.

### 4. The blocker: codex-cli 0.132 `exec` does not fire hooks — **NOT fixable from autocc**

After (1)–(3), running the smoke still fails its mandatory
assertion: `.autocc/decisions.log` is never created. The codex
session JSONL (`<HOME>/.codex/sessions/<date>/rollout-*.jsonl`) shows
no `HookStarted` / `HookCompleted` notification rows either. The
plugin is loaded, the marketplace resolves, the skills are
invocable, the model runs `/reflector` end-to-end and commits the
seeded task — but **no hook command is ever spawned**.

What was tried, in order:

1. **Plugin `hooks.json` only, `--enable plugin_hooks` set.** No
   hooks fire. Matches the `docs/codex-mapping.md` §1c warning that
   `plugin_hooks` is labelled "under development, false" in codex's
   feature table; the binary's string table confirms `PluginHooks`
   is alongside other under-development features (`InAppBrowser`,
   `ComputerUse`, `BrowserUse`).

2. **Plugin `hooks.json` + `--dangerously-bypass-hook-trust`.** No
   hooks fire. The binary string
   `` `--dangerously-bypass-hook-trust` is enabled. Enabled hooks
   may run without review for this invocation. ``
   suggests the flag is honored at startup-message level, but in
   practice `codex exec` does not subsequently spawn the hook
   commands. This appears to be the same incomplete-dispatcher
   issue as (1) — the bypass flag short-circuits the *review*
   step, but the underlying "merge plugin hooks into the
   dispatcher" wiring is what's actually missing.

3. **Plugin `hooks.json` + mirror the same handler entries under
   `config.toml`'s stable `[hooks]` table.** No hooks fire either.
   The `codex_hooks` feature is documented as "stable, true" (and
   the `HookStateToml` deserializer for `[hooks]` blocks is present
   in the binary), but `codex exec` with
   `--dangerously-bypass-hook-trust` still does not fire the
   configured commands. The TUI-side hook-trust review (binary
   strings `Trust to trust all hooks`, `Modified since last
   trusted - review required`) appears to be the only path that
   actually marks a hook handler as
   `HookTrustStatus::trusted`/`approved` in persisted state, and
   `codex exec` does not honor the per-invocation bypass for the
   final "spawn the command" decision. The smoke's workaround
   step (`_register_user_hooks_in_config`) is kept in place
   because it's the closest-to-correct shape for when codex does
   finish wiring this through; but on 0.132 it does not produce
   hook firings.

The fail mode is "no hook command is spawned, anywhere", which
rules out every fixable autocc-side cause (path resolution,
project-dir env, JSON wire shape, decision-log gating). The plugin
manifest is read (otherwise skills wouldn't load), but the
sibling `hooks.json` is parsed and then dropped on the floor.

This is a Codex CLI environment constraint, not a bug in autocc's
install path or hook script. It matches TB-9's briefing carve-out
for "an auth flow that needs interactive login" — the
hook-trust-review flow is TUI-only, and there is no non-interactive
equivalent on 0.132 that actually results in hooks firing in
`codex exec`. The autocc-side fixes (1)–(3) above are durable —
they are what the install path / hook script will need regardless
once codex's dispatcher catches up to its CLI surface — but they
are not sufficient on this binary release.

## What this validates

Even with the mandatory hook-fired assertion still red on 0.132,
the live run produces durable evidence that everything *up to* the
hook dispatcher is correct against real codex:

- The installer writes a plugin layout codex can read end-to-end
  (manifest, hooks.json, skills/, marketplace.json).
- `codex plugin marketplace add` + `codex plugin add` accept the
  shapes the installer emits; the `[marketplaces.autocc]` and
  `[plugins."autocc@autocc"]` blocks materialize as expected.
- Codex's session log exposes the autocc skills under their
  `autocc:` prefix exactly as `docs/codex-mapping.md` §1 predicts
  for skills shipped via plugin, and resolves their `SKILL.md`
  paths to the cached plugin directory.
- `/reflector` triggered as a prompt body to `codex exec`
  successfully runs the full reflector loop end-to-end against
  the taskflow fixture: bootstrap → discover → execute → verify →
  commit → taskboard update → progress note. This validates the
  skill bodies' portability across providers (TB-4's
  `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`
  chain, the `commit-changes` skill, the `taskboard` lifecycle
  contract) under real codex semantics.

What remains unvalidated is the `Stop`-hook-fires-block-decision
loop continuation behavior — i.e. autocc's "human is away, keep
working" nudge. That's the autopilot loop's core differentiator and
the deliverable the milestone's done-when bullet #5 wanted to lock
in. It cannot be validated against codex-cli 0.132 in `exec` mode.

## Recommendations for next steps

These are recommendations, not commitments — TB-9 is closing
without a passing smoke and these belong on the operator's review
queue:

1. **Re-run the smoke on each codex-cli minor release** until
   `PluginHooks` graduates from "under development" to stable. The
   smoke is now hardened against (1)–(3) above, so the next live
   run only needs to flip the `decisions.log` from absent to
   present to pass. The smoke remains opt-in (`AUTOCC_REAL_SDK=1`).

2. **Open a Codex CLI issue / discussion** documenting that
   `codex exec --dangerously-bypass-hook-trust --enable plugin_hooks`
   does not actually result in hook command spawning on 0.132, with
   the reproduction recipe from this smoke (sandboxed HOME, local
   marketplace, plugin add, hooks.json + config.toml [hooks]). The
   binary's UX text claims the bypass flag is "Intended only for
   automation that already vets hook sources" — automation can't
   use it productively if it doesn't actually fire hooks.

3. **Do NOT** drift autocc's install path to accommodate this. The
   plugin install + `hooks.json` shape is correct against the
   documented contract (`docs/codex-mapping.md` §1c, §2a). Working
   around the dispatcher gap by writing a `[hooks]` block into the
   user's `~/.codex/config.toml` would leak install state outside
   the plugin folder (against the marketplace-driven discovery
   model the docs lay out) and would be obsolete the moment codex
   ships the fix. The smoke fixture's
   `_register_user_hooks_in_config` step is scoped to the test's
   sandboxed HOME for the same reason; it must not appear in
   `src/autocc/installer.py`.

## Re-validation 2026-05-21 (post-unfreeze)

TB-9 was unfrozen by the operator after ffa523e and re-attempted to
confirm the blocker still stands on the current local codex install.
This section captures what changed and what didn't.

### What changed

- **`codex features list` now reports `plugin_hooks` as `stable, true`**
  by default (previously labelled `under development, false` per
  ffa523e's investigation). The feature flag graduated, but the
  *dispatcher* behavior is unchanged on 0.132.0 — `codex exec` still
  does not spawn hook commands even with the feature reported as
  stable+enabled.
- **`codex doctor` reports `0.133.0 available (current 0.132.0)`.**
  Upgrading the local codex install via `codex update` (which shells
  out to `npm install -g @openai/codex`) is blocked under this
  agent's user — the system-wide
  `/opt/homebrew/lib/node_modules/@openai/codex` path requires root
  to overwrite. A user with sudo could `npm install -g
  @openai/codex@latest` to pick up 0.133.0 and re-run the smoke.

### What was re-confirmed (still red on 0.132.0)

The smoke was re-run end-to-end against the same binary:

    AUTOCC_REAL_SDK=1 \
    AUTOCC_SMOKE_WORKSPACE=/tmp/tb9-final-smoke/ws \
    uv run pytest -q tests/smoke/test_reflector_e2e_codex.py -s

Outcome: same as ffa523e's run. `codex exec` ran to completion, the
model invoked `/reflector`, completed `TB-99`, appended the smoke
marker to `README.md`, moved the task to `## Complete`, and committed
locally with subject `Complete TB-99 smoke marker` (stretch
assertion would have passed). But `.autocc/decisions.log` was again
absent — no hook command spawned, despite `--enable plugin_hooks
--dangerously-bypass-hook-trust` and the plugin's hooks mirrored
under the stable `[hooks]` table in the sandboxed `config.toml`.
The session JSONL contains no `HookStarted` / `HookCompleted` rows.

### Minimal standalone repro (rules out autocc-side cause)

To rule out any remaining autocc-specific cause, a one-off minimal
plugin was built in `/tmp/tb9-minimal/` with a single Stop hook
whose handler just appends a line to a file. Same setup steps as
the smoke (sandboxed `HOME` / `CODEX_HOME`, `codex plugin
marketplace add`, `codex plugin add`, project trust seeded).
Running `codex exec --enable plugin_hooks
--dangerously-bypass-approvals-and-sandbox
--dangerously-bypass-hook-trust --skip-git-repo-check -C
<project> "Print the contents of README.md and then stop."` against
the minimal repro produced the same fail mode: the bypass-warning
prints (`` warning: `--dangerously-bypass-hook-trust` is enabled.
Enabled hooks may run without review for this invocation. ``), codex
runs the prompt, then exits cleanly — and no hook command was
spawned (the touch-file the hook would have written is absent).
The same is true with the hook entries mirrored under user-level
`[hooks]` in the sandboxed `config.toml`, and with PreToolUse /
PostToolUse / Stop all registered.

This rules out every autocc-specific input shape (project-dir
resolution chain, hook script wire format, decision-log gating,
marketplace.json schema, plugin.json metadata) as the cause. The
fail mode is "no hook command of any shape ever spawns under
`codex exec` on 0.132.0", end of story. The autocc install path
and hook script are sound; the binary's dispatcher is the wall.

### Disposition

TB-9 is reporting `blocked` again. The blocker is unchanged from
ffa523e: `codex exec` does not invoke hooks on codex-cli 0.132.0,
and the fix (or workaround) is gated on either a codex CLI update
(0.133.0 +) or operator-driven manual TUI trust seeding, neither
of which is reachable from this agent's sandbox. Recommendation
(1) in the previous section — re-run on each codex-cli minor
release — is the next concrete step; 0.133.0 is the first
candidate.

## Re-validation 2026-05-22 (codex-cli 0.133.0)

TB-9 was unfrozen again after c5f72c5 to chase recommendation (1):
re-run on the next codex-cli minor release. This section captures
the outcome on 0.133.0 — installed user-locally via
`npm install -g --prefix=$HOME/.local/npm @openai/codex@0.133.0` to
sidestep the root-required system-wide upgrade path. The local
copy resolves to `/Users/claude-agent/.local/npm/bin/codex` →
`...node_modules/@openai/codex-darwin-arm64/.../codex` and reports
`codex-cli 0.133.0` from `codex --version`.

### What was re-tested

A minimal one-off plugin (`/tmp/tb9-probe-133/home/plugins/probe/`)
with a single `Stop` hook that appends to a marker file, registered
via `codex plugin marketplace add` + `codex plugin add probe@probe-mp`
in a sandboxed `HOME` / `CODEX_HOME`, exercised under two
configurations:

1. **Plugin `hooks.json` only, `--enable plugin_hooks`,
   `--dangerously-bypass-hook-trust`.** Same flags as the smoke.
   Codex `exec` ran the trivial prompt (`"Print the word DONE and
   stop."`) to completion. Marker file: absent. Session JSONL:
   no `HookStarted` / `HookCompleted` rows.
2. **Plugin `hooks.json` + the same handler entries mirrored under
   `[[hooks.Stop]]` / `[[hooks.PreToolUse]]` in `config.toml`'s
   stable `[hooks]` table** (the workaround
   `_register_user_hooks_in_config` applies in the smoke). Codex
   `exec` ran the prompt to completion again. Marker file: still
   absent. Session JSONL: still empty of hook events.

Both runs printed the documented bypass warning
(`` warning: `--dangerously-bypass-hook-trust` is enabled. Enabled
hooks may run without review for this invocation. ``), so the
flag is parsed and acknowledged at startup. The dispatcher is
simply never invoked for hook commands — `codex_hooks` and
`plugin_hooks` are both `stable, true` in `codex features list` on
0.133.0, but `codex exec` does not actually spawn either source's
configured commands. The minor-release bump did NOT close the gap.

### Why the smoke wasn't re-run

The full smoke (`tests/smoke/test_reflector_e2e_codex.py`) would
have produced the same outcome at much higher cost (model tokens,
wall-clock, three prior post-unfreeze attempts already hit the
1200s daemon timeout). The minimal probe above isolates the exact
question the smoke's mandatory assertion gates on — "does the hook
command spawn?" — and answers it independently of the autocc
install path, the reflector skill body, the seeded task, or the
commit-changes flow. With the probe's answer firmly NO on
0.133.0, running the smoke would just re-derive the same failure
via a 5-minute model trajectory. The autocc-side fixes from
ffa523e (project-dir resolution, Stop-decision logging,
marketplace fixture) remain durable and correct against the
binary's documented contract; they will be sufficient once codex
actually invokes the dispatcher.

### Disposition (unchanged)

TB-9 is reporting `blocked` again. The blocker is unchanged from
c5f72c5: `codex exec` does not invoke hooks on the current codex
CLI on this machine — now confirmed across **both 0.132.0 and
0.133.0**, ruling out the "wait for the next minor release"
recommendation from the previous re-validation. The next concrete
step is to track the codex-cli changelog for an explicit "fix
hook dispatch in `codex exec`" entry rather than blindly bumping
on each minor release, since two consecutive minors have shipped
with the same gap. The autocc-side smoke is hardened and ready;
flipping `decisions.log` from absent to present requires only that
codex starts spawning the configured hook command.

## TB-10 update — hook re-homed to config layer, trust spike completed

TB-9's "no hook command of any shape ever spawns under `codex
exec` on 0.132 / 0.133" wasn't actually two failures stacked
together — it was upstream issue openai/codex#16430 doing the
work: codex's plugin manifest parser only reads `skills`,
`mcpServers`, and `apps`, never `hooks`. The autocc-side `hooks.json`
inside the plugin folder was never going to be wired into the
dispatcher, no matter what trust state we got into. TB-10 splits
the residual work in two:

### 1. Cross-references (upstream)

The two upstream tracking items the operator should follow:
- **openai/codex#16430** — "plugin-bundled `hooks.json` not parsed
  from manifest." This is the issue that captures the gap autocc
  hit. The reporter explicitly confirmed that placing the same
  handler entries in `~/.codex/hooks.json` (or in
  `~/.codex/config.toml`'s `[hooks]` table) "works immediately."
- **openai/codex#17532** — "PluginHooks feature flag graduated to
  stable on 0.133.0, but dispatcher still does not fire plugin
  hooks." Confirms what the 2026-05-22 re-validation observed: the
  stable-flag label is not evidence the path works.
- The official Codex hooks docs (linked from `codex --help` and
  the binary's startup messages) describe `config.toml` `[hooks]`
  as the canonical install path; the plugin-bundled hooks model
  is documented as "under development / coming with the next
  plugin loader update."

### 2. Retraction — config-layer hooks ARE the right install path

The pre-TB-10 "Recommendations for next steps" item #3 in this
doc said:

> **Do NOT** drift autocc's install path to accommodate this. The
> plugin install + `hooks.json` shape is correct against the
> documented contract … Working around the dispatcher gap by
> writing a `[hooks]` block into the user's `~/.codex/config.toml`
> would leak install state outside the plugin folder (against the
> marketplace-driven discovery model the docs lay out) and would
> be obsolete the moment codex ships the fix. The smoke fixture's
> `_register_user_hooks_in_config` step is scoped to the test's
> sandboxed HOME for the same reason; it must not appear in
> `src/autocc/installer.py`.

**That recommendation is retracted.** The premise — that
plugin-bundled `hooks.json` is the documented contract and the
config-layer path is a workaround — was wrong on the merits:

- The official Codex docs and the upstream maintainer (issue
  #16430) both say config-layer is the supported, working path
  today. Plugin-bundled hooks are the feature in progress, not
  the canonical surface.
- The "leak install state outside the plugin folder" objection
  was real but mis-weighted: `~/.codex/config.toml` is already a
  multi-tenant user file that codex's own `/hooks` review, `codex
  mcp add`, `codex plugin add`, `[projects.<path>] trust_level`
  bookkeeping, and the TUI's `tui.*` settings all write to. autocc
  joining that list — in a single marker-delimited block bounded
  by sentinel comments — is consistent with the file's actual
  contract, not a violation of it.
- The "obsolete the moment codex ships the fix" objection assumed
  duplicate registration would cause double-firing. It won't:
  codex's normalized hook identity collapses duplicate
  `command + matcher + event` tuples, so when plugin hooks finally
  land, the plugin-bundled `hooks.json` and the config-layer block
  resolve to the same handler and fire once.

TB-10's installer change (this commit) writes a marker-bounded
`[[hooks.<Event>]]` block into `${CODEX_HOME:-~/.codex}/config.toml`
in addition to (not instead of) the plugin-bundled `hooks.json`.
The plugin manifest, skills tree, and marketplace entry are
unchanged — skills work via the plugin, as the live run proved
end-to-end. `autocc uninstall --agent codex` strips the
config-layer block idempotently, preserving any user `[[hooks.*]]`
entries placed outside our markers.

### 3. Hook-trust persisted state — spike outcome

The trust gate the previous re-validations hit is real: codex's
binary contains `HookTrustStatus`, `HookTrustStatus.ts`,
`startup_hooks_review.rs`, `Modified since last trusted - review
required`, `1 hook needs review before it can run`, and persists
trust as a `trusted_hash` field on each hook handler. The spike's
question was: can autocc pre-seed that trust state at install time
so its own hook fires non-interactively on first launch?

**Where trust persists.** The binary's strings table exposes the
TOML deserializer field names: `HookEventsToml` (top-level), then
`MatcherGroup { state, matcher, hooks }` per entry, where `state`
is a `HookStateToml { enabled, trusted_hash }`. So the persisted
shape is inline in `config.toml`, alongside each
`[[hooks.<Event>]]` block:

    [[hooks.Stop]]
    state = { enabled = true, trusted_hash = "<hex>" }
    hooks = [{ type = "command", command = "..." }]

We confirmed `state_5.sqlite` does NOT contain a hook-trust table
— trust is purely a TOML-side concern. The `<hex>` value is what
codex's TUI review writes after the user confirms the hook via
`/hooks`.

**Why we can't pre-seed it on 0.132 / 0.133.** Two reasons,
either of which is decisive on its own:

1. **Hash algorithm + canonical input are not published.** The
   binary's strings table names the field (`trusted_hash`) and
   the struct (`HookStateToml`) but does not expose the hashing
   primitive or the byte-string it canonicalizes. Reverse-engineering
   the hash inputs from the binary (likely SHA-256 over some
   canonical serialization of `command + matcher + event`, but
   the exact form is conjecture) would be brittle — a 0.134
   refactor could silently shift the canonical input and every
   pre-seeded autocc install would re-prompt for review without
   any code change on our side. The downstream maintenance cost
   makes this a non-starter even if we got the bytes right today.

2. **Even with trust bypassed, `codex exec` doesn't fire plugin
   hooks on 0.132 / 0.133.** TB-9's live smoke established this
   independently of the trust state: `--dangerously-bypass-hook-trust`
   prints its acknowledgement (`` `--dangerously-bypass-hook-trust`
   is enabled. Enabled hooks may run without review for this
   invocation. ``), but no hook command is spawned. The dispatcher
   gap is upstream-side and not unlockable from autocc's install
   path. So even if we hashed correctly, the result would be a
   trusted hook that still doesn't fire on `codex exec`.

The "managed hooks" pathway (`/etc/codex/managed_config.toml` +
`allow_managed_hooks_only` requirements flag) auto-trusts hooks
loaded from the managed config layer, because installing them
requires root. autocc is a user-mode installer, so this path is
not reachable.

**Determination: option (b) per the briefing.** Non-interactive
hook firing is **not feasible** on codex 0.132 / 0.133 via the
avenues explored (pre-seeded `trusted_hash`, `--dangerously-bypass-hook-trust`,
`--enable plugin_hooks`, managed-hooks layer). The config-layer
install is landed regardless, so the moment codex ships the
dispatcher fix (or publishes the `trusted_hash` hash algorithm,
or routes `--dangerously-bypass-hook-trust` past the dispatcher
gate), autocc is already shaped correctly. The TUI `/hooks`
review remains the one-time human-gated step on first run; once
the user trusts the autocc hook, codex writes the `trusted_hash`
inline in `config.toml` and subsequent `codex exec` runs honor it
(once the dispatcher gap closes).

### 4. Net status

- **Installer (TB-10):** ✅ landed. `autocc install --agent codex`
  now writes `[[hooks.PreToolUse]]` / `[[hooks.PermissionRequest]]`
  / `[[hooks.Stop]]` into `${CODEX_HOME}/config.toml` in a
  marker-bounded block, in addition to keeping the plugin
  manifest + skills + plugin-bundled `hooks.json`. Uninstall
  idempotently strips the config-layer block. Unit tests pin the
  new behavior under `tests/test_installer.py::test_codex_install_writes_config_layer_hooks_block`
  and four siblings.
- **Docs (TB-10):** ✅ corrected. `docs/codex-mapping.md` §1a / §1c
  reflect the dispatcher gap + the trust persistence shape;
  pinned codex version bumped from 0.128.0 → 0.132.0.
- **Live smoke:** still red on 0.132 / 0.133 — the autocc-side
  fixes (TB-9's project-dir resolution + Stop-decision logging,
  TB-10's config-layer install) are durable, but the dispatcher
  gap is upstream. Operator re-runs the smoke per the
  "Recommendations" section above on each codex-cli minor
  release.
- **Trust spike:** ✅ documented; determination is option (b)
  (non-interactive firing impossible on 0.132 / 0.133 via the
  avenues explored). The config-layer install positions autocc
  so a future codex release that closes the dispatcher gap will
  fire the autocc hook directly, with a single TUI trust step on
  first run.
