# Codex extension surface ↔ autocc requirements

Discovery output for TB-1. The goal: name, for each Claude-Code-side
behavior autocc currently relies on, the equivalent OpenAI Codex
extension point — or, where none exists, record the gap so downstream
installer / hook tasks can plan a polyfill, a documented skip, or an
accepted limitation.

Findings here are pinned to **codex-cli 0.132.0** as installed by
Homebrew at `/opt/homebrew/bin/codex` (npm package `@openai/codex`,
shipping a precompiled Rust binary under
`@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/codex/codex`).
TB-9 / TB-10 re-validated against 0.132.0 (homebrew) and 0.133.0
(user-local `npm install -g`); the hook-discovery + dispatcher
findings hold across both. Where the codex binary's `--help` text
doesn't surface a behavior, I cite the strings table extracted from
that binary — most internal type names, hook event identifiers, and
JSON wire shapes are reachable that way, even though they aren't in
the CLI help. Where a claim depends on a shape that wasn't directly
verifiable (e.g. specific JSON-RPC method names), I say so explicitly
rather than asserting.

Out-of-scope surfaces (Codex Cloud, the desktop app, the remote
exec-server, multi-agent v2 features) are not covered — autocc v1 is
a local-CLI tool and the installer's blast radius is local CLI files.

---

## 1. Codex config + extension surface

### 1a. On-disk config directory

Codex reads its config from a single home directory chosen at startup
via the `CODEX_HOME` env var, defaulting to **`~/.codex/`**. The
files inside that the autocc installer cares about:

| Path | Role | Equivalent in Claude Code |
|---|---|---|
| `~/.codex/config.toml` | Single-file user config. TOML. Holds model selection, sandbox, MCP servers, **and a top-level `[hooks]` table** (the codex binary's `HookEventsToml` deserializer accepts `PreToolUse`, `PermissionRequest`, `PostToolUse`, `SessionStart`, and the other CamelCase hook event names directly as table keys). **This is the working hook surface on 0.132 / 0.133** — see §1c for why plugin-bundled `hooks.json` is silently dropped by the dispatcher. The per-handler `state.trusted_hash` field is also written here by codex's TUI `/hooks` review (TB-10). | `~/.claude/settings.json` |
| `~/.codex/skills/` | User-installed skills (peer of the `~/.codex/skills/.system/` directory codex ships preinstalled — `skill-creator`, `plugin-creator`, `skill-installer`, `imagegen`, `openai-docs`). The `skill-installer` skill defaults its dest path to `${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>`. Each skill is `<skill>/SKILL.md` with YAML frontmatter `name:` and `description:`. | `~/.claude/skills/<skill>/SKILL.md` |
| `~/plugins/<name>/` (home-rooted) or `<repo-root>/plugins/<name>/` (repo-rooted) | Plugins. A plugin is a directory with `.codex-plugin/plugin.json` plus optional `skills/`, `hooks.json`, `.mcp.json`, `.app.json`, `assets/`. **Discovery is marketplace-driven, not filesystem-scan** — codex's `core-plugins/src/loader.rs` reads plugins from marketplaces, so the plugin folder can technically live anywhere the marketplace's `source.path` points. `~/plugins/<name>/` is the documented convention (from `plugin-creator/SKILL.md`); `~/.codex/plugins/` is NOT a Codex convention and is not referenced anywhere in the plugin-creator or skill-installer documentation. | n/a (Claude Code's nearest analog is shipping a skill + hook + statusline bundle as separate files under `~/.claude/`) |
| `~/.agents/plugins/marketplace.json` (or `<repo>/.agents/plugins/marketplace.json`) | Marketplace index listing plugin entries with `source.path`, `policy.installation`, `policy.authentication`, `category`. Codex's plugin-creator skill documents the exact shape. | n/a |
| `~/.codex/sessions/` | Per-session rollout state. Read-only from an installer's perspective. | `~/.claude/projects/` rollout |
| `~/.codex/memories/` | Persistent memory store (gated on `features.memories`, currently `experimental, false`). | `~/.claude/CLAUDE.md` + per-project `CLAUDE.md` |

`autocc install --agent codex` writes the plugin folder at
`~/plugins/autocc/` (the home-rooted convention from
`plugin-creator/SKILL.md`) and registers it via a marketplace entry
in `~/.agents/plugins/marketplace.json` with
`source.path: ./plugins/autocc` (which resolves relative to the
marketplace's home anchor — per `plugin-creator/SKILL.md`'s
worked example, "with `~/.agents/plugins/marketplace.json`,
`./plugins/<plugin-name>` resolves to `~/plugins/<plugin-name>`",
NOT to `~/.agents/plugins/<name>/` as a naive relative resolution
would suggest). Skills live inside the plugin folder.

**TB-10 update:** The hook *registration*, however, no longer lives
solely inside the plugin folder. The installer also writes a
marker-bounded `[[hooks.<Event>]]` block into
`${CODEX_HOME:-~/.codex}/config.toml`, because the plugin-bundled
`hooks.json` is silently dropped by codex 0.132 / 0.133's dispatcher
(upstream issue openai/codex#16430: `codex-rs/core/src/plugins/
manifest.rs` parses `skills`, `mcpServers`, `apps` but NOT `hooks`,
and hook discovery only scans config folders, never plugin roots).
The config-layer entry is the working hook surface today. The plugin
manifest still references `hooks: "./hooks.json"` and the hook script
still lives under `~/plugins/autocc/hooks/` so the absolute command
path stays under one install root; when codex eventually merges
plugin hooks into the dispatcher, both surfaces will fire, and the
binary's normalized hook identity (command + matcher + event)
collapses the duplicate.

That config-layer write does "leak" install state outside the plugin
folder, but only into a single delimited block bounded by sentinel
comments (`# >>> autocc managed hooks (do not edit) >>>` /
`# <<< autocc managed hooks <<<`). `autocc uninstall --agent codex`
strips the block idempotently, preserving any unrelated user content
(including the user's own `[[hooks.<Event>]]` entries placed outside
our markers).

Alternative install paths exist — because discovery is
marketplace-driven, the installer could put the plugin folder under
`~/.codex/plugins/autocc/` (or anywhere else) and point the
marketplace there. That's a TB-2-time call; recommend the canonical
`~/plugins/autocc/` unless there's a specific reason to colocate
with `CODEX_HOME`.

### 1b. Migration is a first-class concern for the codex binary

Codex has an external-config-migration capability, surfaced via the
`external_migration` feature flag (described in `codex features
list` as "Show a startup prompt when Codex detects migratable
external agent config for this machine or project"). The binary
contains `ExternalConfigMigrationPrompts` config types, a
`HookMigration` item type, and `import external agent config
migration items` log strings — confirming migration is implemented
and includes a hook-migration item path. Exact JSON-RPC method
names and the full item-type enum are NOT surfaced in the binary's
string table at 0.128.0 (`grep externalAgentConfig` on the binary
returns nothing); treat the migration API as "capability exists,
surface area not nailed down — verify against Codex's source or
runtime behavior before depending on it." Implication for autocc:
a clean install path is in scope, and *opportunistically* leaning
on Codex's importer for pre-existing Claude artifacts is plausible,
but the installer should not assume specific method names without
a runtime probe.

### 1c. Extension points the binary exposes

The runnable extension surface, in the order autocc cares about:

1. **Hooks.** First-class — but the working surface is `[hooks]` in
   `config.toml`, NOT plugin-bundled `hooks.json`. Hook events are
   listed in §2 below. Implementation lives in `codex-rs/hooks/`,
   dispatched by `engine::dispatcher` via `engine::command_runner`.
   Hook handlers can be `Command` (spawn a process, give it JSON on
   stdin, parse JSON on stdout) with fields `command`, `timeout`,
   `async`, `statusMessage`, `agent`, plus a `matcher` regex
   (PreToolUse-only).
   - **The plugin hooks gap (TB-10).** Plugin-bundled `hooks.json`
     **does not fire** on codex 0.132 / 0.133. Upstream issue
     openai/codex#16430 (confirmed against the local 0.132 + 0.133
     binaries): `codex-rs/core/src/plugins/manifest.rs` parses
     `skills`, `mcpServers`, and `apps` from the plugin manifest but
     NOT `hooks`, and hook discovery only scans config folders, never
     plugin roots. Even with `--enable plugin_hooks` and
     `--dangerously-bypass-hook-trust`, `codex exec` does not spawn
     plugin hook commands. The supported, working path is `[hooks]`
     in `${CODEX_HOME:-~/.codex}/config.toml` — per the official
     Codex hooks docs and issue #16430's own reporter, hooks placed
     there "work immediately."
   - **Feature flag:** `codex_hooks` is `stable, true`. A
     newer `plugin_hooks` flag graduated to `stable, true` on
     0.133.0 (it was `under development, false` on 0.128.0 when this
     doc was first written), but the dispatcher behavior is unchanged
     — flag-on does not actually fire plugin hooks. Don't take the
     stable-flag label as evidence the path works; verify against
     #16430 / TB-10's `docs/codex-smoke-results.md`.
   - **Hook trust gate.** Non-managed command hooks must be reviewed
     and trusted before they run; the review is TUI-only via the
     `/hooks` slash command (binary strings: `Hooks need review`,
     `New hook - review required`, `1 hook needs review before it can
     run`, `Modified since last trusted - review required`, source
     file `startup_hooks_review.rs`). Trust state persists in
     `config.toml` itself — alongside each `[[hooks.<Event>]]` entry,
     codex's TUI review writes a `state = { enabled = true,
     trusted_hash = "..." }` sub-table (binary's `HookStateToml`
     deserializer + `MatcherGroup` with `state` + `matcher` +
     `hooks` fields). The hash algorithm + canonical input are NOT
     surfaced in the binary's strings table at 0.132 / 0.133, so
     pre-seeding `trusted_hash` non-interactively is impractical
     (would require reverse-engineering the hash inputs). The
     `--dangerously-bypass-hook-trust` flag is the documented
     non-interactive bypass, but TB-9's live smoke confirmed it does
     NOT cause `codex exec` to actually spawn hook commands on
     0.132 / 0.133 — the dispatcher gap is independent of the trust
     state. The autocc-managed "managed hooks" pathway
     (`/etc/codex/managed_config.toml` + `allow_managed_hooks_only`
     requirements flag) is auto-trusted because installation requires
     root, but is therefore not reachable from a user-mode autocc
     install.
   - **Hook env vars:** the binary passes `PLUGIN_ROOT`,
     `CLAUDE_PLUGIN_ROOT`, `PLUGIN_DATA`, `CLAUDE_PLUGIN_DATA` to hook
     commands. The Claude-prefixed aliases are deliberate — Codex
     mirrors the Claude Code env-var contract so a hook written for
     Claude Code mostly Just Works. **Caveat (per TB-9):** these env
     vars point at the *plugin install directory*
     (`$CODEX_HOME/plugins/cache/<mp>/<name>/<version>/`), NOT the
     project root. autocc's hook script uses
     `AUTOCC_PROJECT_DIR → CLAUDE_PROJECT_DIR → CODEX_PROJECT_DIR →
     hook_input.cwd` and treats PLUGIN_ROOT only as a synthetic-test
     fallback.
2. **Skills.** Match Claude Code's skill model closely. YAML
   frontmatter requires `name`, `description`. Codex additionally
   recognizes an optional `metadata` block (e.g. `short-description`).
   The `aliases:` frontmatter key autocc uses on the `taskboard` skill
   is not in the codex skill-creator spec — likely tolerated (extra
   keys are ignored) but should be verified before relying on it.
   Skills are auto-discovered from `${CODEX_HOME}/skills/`. Restart of
   codex is required to pick up new skills (per skill-installer SKILL.md).
3. **MCP servers.** `codex mcp add | list | get | remove | login |
   logout` + `~/.codex/config.toml`'s `mcp_servers` table. Identical
   contract to Claude Code's MCP support; not autocc-relevant for v1.
4. **Plugins.** Manifest at `<plugin>/.codex-plugin/plugin.json`.
   Manifest fields the installer would set: `name`, `version`,
   `description`, `skills` (default `./skills/`), `hooks` (e.g.
   `./hooks.json`), `mcpServers`, optional `apps`, and an `interface`
   block with `displayName`, `category`, etc. for UI surfacing.
5. **Statusline.** Codex has a `status_line` TUI config key and a
   `/statusline` slash command (binary string: *"Use /statusline to
   configure which items appear in the status line."*), plus
   internal `StatusLineSetup` / `StatusLineSetupCancelled` /
   `StatusLineBranchUpdated` events. But the `status_line` config
   is a **widget list** (branch, tokens, model, etc.) that the codex
   TUI renders itself, **not** a shell-out point — there's no
   analog to Claude Code's `statusLine.command =
   "/path/to/script.sh"` that spawns an external process per
   refresh. autocc's statusline-shell-script mechanism therefore
   has no Codex equivalent. See §4 for what this breaks for the
   `.autocc/context.json` side effect.
6. **Features flags.** `codex features list | enable | disable`. Many
   are gated; the relevant ones for autocc are `codex_hooks` (already
   stable+on), `plugin_hooks` (under development), `memories`
   (experimental, off), `personality` (stable+on).

---

## 2. Hook event mapping

Codex's hook event vocabulary, taken from the binary's
`HookEventName` enum (`pre-tool-use|permission-request|post-tool-use|session-start|user-prompt-submit|stop` as a single token in the strings table) and the matching `events/<name>.rs` source paths.
**Six events total — no `notification`, `elicitation`, `post_compact`, `ask_user_question`, or `enter_plan_mode` variants exist in 0.128.0.**

| Wire name (snake_case) | CamelCase (JSON `hookEventName`) | Source file referenced in binary |
|---|---|---|
| `pre_tool_use` | `PreToolUse` | `codex-rs/hooks/src/events/pre_tool_use.rs` |
| `post_tool_use` | `PostToolUse` | `codex-rs/hooks/src/events/post_tool_use.rs` |
| `permission_request` | `PermissionRequest` | `codex-rs/hooks/src/events/permission_request.rs` |
| `session_start` | `SessionStart` | `codex-rs/hooks/src/events/session_start.rs` |
| `user_prompt_submit` | `UserPromptSubmit` | `codex-rs/hooks/src/events/user_prompt_submit.rs` |
| `stop` | `Stop` | `codex-rs/hooks/src/events/stop.rs` |

Per-event JSON contract resembles Claude Code's closely. Hook input
fields the binary parses from stdin include `session_id`, `turn_id`,
`transcript_path`, `hook_event_name`, `cwd`, `model`,
`permission_mode`, `prompt`, `tool_name`, `tool_input`, `tool_use_id`,
`source`, `last_assistant_message` (subset depends on event). Hook
output fields the binary parses from stdout include `decision`
(`approve` / `block` / `allow`), `reason`, `hookSpecificOutput`,
`permissionDecision` (`allow` / `deny` / `ask`),
`permissionDecisionReason`, `additionalContext`, `updatedInput`,
`updatedPermissions`, `interrupt`, `stopReason`, `suppressOutput`,
`systemMessage`, `tool_response`, `continue`, `updatedMCPToolOutput`.
PreToolUse handler entries also accept a `matcher` regex against
`tool_name`. The binary explicitly rejects a handful of fields it
doesn't yet implement (e.g. `PreToolUse hook returned unsupported
permissionDecision:allow`, `…unsupported additionalContext`,
`…unsupported updatedInput`); the installer should not depend on
those.

### 2a. autocc → Codex hook mapping

| # | autocc event (matcher) | Codex equivalent | Impedance notes |
|---|---|---|---|
| 1 | `PreToolUse` (`AskUserQuestion`) | `pre_tool_use` with matcher, but **no built-in `AskUserQuestion` tool to match against** | Codex doesn't ship an `AskUserQuestion` tool. The model asks the user via the `ElicitationRequest` / `RequestUserInput` events (`item/tool/requestUserInput`), which fire through a different code path than tool calls and are not dispatched to `pre_tool_use`. A `pre_tool_use` matcher set to `AskUserQuestion` would simply never fire. To enforce "make your best judgment, log it" semantics on Codex, autocc has to intercept user-input requests elsewhere — see Elicitation row. |
| 2 | `PreToolUse` (`EnterPlanMode`) | **no analog** | Codex has no plan-mode tool. The closest construct is the `-a/--ask-for-approval` startup policy (`untrusted` / `on-request` / `never`), which is set once at session start, not invoked per-call. There is no `EnterPlanMode`-equivalent tool to match in `pre_tool_use`. |
| 3 | `PermissionRequest` (all) | `permission_request` | 1:1 mapping. Same `permissionDecision: allow` JSON shape (codex literally rejects unsupported variants by string match: `PermissionRequest hook returned unsupported …`). autocc's current `{"behavior":"allow"}` shape under Claude Code's `hookSpecificOutput.decision` is slightly different from Codex's `permissionDecision: allow` field — installer must emit the codex shape, not the claude shape. |
| 4 | `Elicitation` (all) | **no hook event analog** | Codex emits `elicitation_request` as an Event (sent to the client over the app-server JSON-RPC channel) but does **not** expose a hook event named `elicitation`. The codex binary's `HookEventName` enum has no `Elicitation` variant. autocc cannot intercept elicitation via the hook surface; the model just receives the user-input request and either the human answers it or the run stalls. See Gap list. |
| 5 | `Stop` (all) | `stop` | 1:1 mapping. Codex's stop hook supports the same continuation contract — `decision: "block"` plus `reason` text re-prompts the model. The binary even rejects a malformed reuse: `Stop hook returned decision:block without a non-empty reason`, `Stop hook requested continuation without a prompt; ignoring the block.` There is also an `after_agent` legacy notification mechanism in the binary (`legacy notify payload is only supported for after_agent`); it predates the `stop` hook event and the installer should not target it. |
| 6 | `PostCompact` (all) | **no analog** | Codex performs auto-compaction (the binary has `compact.rs`, `compact_remote.rs`, `core/src/tasks/compact.rs`, a `context_compacted` Event, and a `thread/compact/start` JSON-RPC request) but does NOT fire a hook event after compaction completes. The `HookEventName` enum has no PostCompact variant. autocc's checkpoint-injection mechanism has no place to attach on Codex. See Gap list. |

### 2b. Codex hooks autocc could opportunistically use

Not requirements, just available surface autocc might exploit in
follow-up work:

- `session_start` — fires once per session. Useful for autocc to
  detect "this session was launched while the flag is set" and inject
  the resume nudge as `additionalContext`. Could partially polyfill
  the PostCompact gap (every compaction in codex eventually surfaces
  as a new turn; a session_start handler is not the same trigger, but
  a UserPromptSubmit handler after `context_compacted` Event might be).
- `user_prompt_submit` — fires every time the user submits a turn.
  Could be the channel through which autocc detects "the human came
  back and typed something" without needing a Stop-hook detour.
- `post_tool_use` — fires after each tool returns. Currently autocc
  doesn't need this on Claude Code, but it's the right place to hang
  cross-cutting per-tool logging if a future task wants it.

---

## 3. Skill portability

Each of autocc's six skills, against Codex's skill loader behavior:

| Skill | Claude-Code-specific assumptions | Codex portability | Required glue |
|---|---|---|---|
| `afk` | Reads `$CLAUDE_PROJECT_DIR` env var to locate session root; creates `.autocc/flag`; invokes `/reflector` as a sibling skill. | **needs-provider-specific-glue** | Codex does not set `CLAUDE_PROJECT_DIR`. The skill body must fall back to `${CODEX_PROJECT_DIR:-$PWD}` (or read codex's project root from `$PWD`, since `codex -C/--cd` rewrites cwd). Slash-command invocation (`/reflector`) works in both — Codex's TUI accepts `/<skill-name>` to trigger a skill — so the skill-to-skill call is fine. |
| `reflector` | Reads `$CLAUDE_PROJECT_DIR`; reads `CLAUDE.md`'s `## Autopilot` section; depends on the Stop hook re-blocking idle to keep the loop alive; reads `.autocc/context.json` (statusline-written) for the 70%-context CHECKPOINT trigger. | **needs-provider-specific-glue** | Same env-var fallback as `afk`. The skill's `CLAUDE.md` parse works regardless of provider because it's done via the agent's shell tool (`cat CLAUDE.md` / file read), not a provider-injected system-prompt mechanism — both Claude Code and Codex expose shell access, so the `## Autopilot` parse is portable as-is. (Codex's own native agent-instructions file is `AGENTS.md`, which the external-config-migration prompt converts `CLAUDE.md` into; this is independent of the skill's parse path.) The Stop-hook loop wiring works as-is (codex's `stop` hook implements the same `decision:block` contract). The 70%-CHECKPOINT trigger is the load-bearing break: Codex has no statusline shell-out (§4), so `context.json` is never written — the CHECKPOINT logic must instead read context usage from the session's own state. Codex emits `ThreadTokenUsageUpdated` / `token_count` Events that carry token-usage deltas, but those don't reach a skill's prompt context the way a statusline-written file does. Polyfill candidates: (a) parse the most recent `~/.codex/sessions/<id>.jsonl` rollout for token-usage events, (b) accept "checkpoint every N completed tasks" instead of "checkpoint at N% context," (c) accept the degradation and document it. |
| `taskboard` | Reads/writes `TASKS.md`; reads `CLAUDE.md` `## Autopilot` paths; references `.autocc/tasks/`, `.autocc/progress.md`. No env-var dependence. | **portable-as-is** | None. Codex reads `CLAUDE.md` (and `AGENTS.md`) natively. The skill body's `aliases:` frontmatter key is not in the codex skill-creator spec; codex skill loaders appear to ignore unknown keys, but if a future codex version validates frontmatter strictly the `aliases:` line would need to move into `metadata:`. |
| `tb` | Pure alias for `/taskboard` (one body line). | **portable-as-is** | None. The alias mechanism in autocc is just a separately-installed skill that re-invokes `/taskboard`; codex handles that fine. |
| `housekeeping` | Detects project tooling via `pyproject.toml` / `package.json` / `Makefile` / `Cargo.toml` etc. and runs the project's linter/tests. No Claude-specific surface. | **portable-as-is** | None. |
| `commit-changes` | Pure prompt; reads `TASKS.md` + `.autocc/progress.md`; writes git commits with a `Co-Authored-By: Claude <noreply@anthropic.com>` trailer. | **needs-provider-specific-glue** | The hardcoded `Co-Authored-By: Claude <noreply@anthropic.com>` trailer is wrong under Codex — should be `Co-Authored-By: Codex <noreply@openai.com>` or parameterized by the active provider. Otherwise the skill is pure markdown protocol. TB-4 parameterized the trailer on `AUTOCC_AGENT_NAME` / `AUTOCC_AGENT_EMAIL`; TB-8 then made the default-when-unset provider-aware via a `$CODEX_PROJECT_DIR` sniff inside the `:-` branches so Codex sessions don't need any explicit env wiring to get the right trailer. |

No skill in autocc is classified `no-codex-analog` — every one of them
can run under Codex, three of them as-is and three with cosmetic /
env-var glue.

### 3a. Provider-portable skills — env-var contract

TB-4 closed the three `needs-provider-specific-glue` rows above by
decoupling the skill bodies from Claude-only env vars. The contract
the skills now follow (and the installer Codex branch wires to
match):

| Env var | Default | Used by | Set by |
|---|---|---|---|
| `AUTOCC_PROJECT_DIR` | _(unset)_ | `afk`, `reflector` — resolved via the chain `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}` to locate the session root (`.autocc/flag`, `CLAUDE.md`, `TASKS.md`, etc.) | Operator override only — the skills walk to `CLAUDE_PROJECT_DIR` then `CODEX_PROJECT_DIR` then `$PWD` automatically. Sets this when the operator wants to pin a non-default project root regardless of which harness is running. |
| `CLAUDE_PROJECT_DIR` | _(unset)_ | Same as above; second in the chain | Claude Code CLI sets this for every session. |
| `CODEX_PROJECT_DIR` | _(unset)_ | Same as above; third in the chain | Codex CLI (when present); the autocc Codex plugin's `hooks.json` `env` block can also set it explicitly for environments where Codex doesn't export it natively. |
| `AUTOCC_AGENT_NAME` | `Claude` (Claude session) / `Codex` (Codex session) | `commit-changes` — interpolated into the `Co-Authored-By` trailer as `${AUTOCC_AGENT_NAME:-$([ -n "$CODEX_PROJECT_DIR" ] && echo Codex || echo Claude)}` | Operator override only. When unset, the trailer sniffs `$CODEX_PROJECT_DIR` and picks `Codex` if it is set, `Claude` otherwise — see TB-8. The Codex CLI exports `CODEX_PROJECT_DIR` natively, so no installer-side env wiring is required. |
| `AUTOCC_AGENT_EMAIL` | `noreply@anthropic.com` (Claude session) / `noreply@openai.com` (Codex session) | `commit-changes` — interpolated into the `Co-Authored-By` trailer as `${AUTOCC_AGENT_EMAIL:-$([ -n "$CODEX_PROJECT_DIR" ] && echo noreply@openai.com || echo noreply@anthropic.com)}` | Same provider-sniff fallback as `AUTOCC_AGENT_NAME`, with the matching email for each provider. |

The fallback chain's ordering — `AUTOCC_*` first, then each provider's
native var, then `$PWD` — keeps the skill bodies provider-neutral
without a runtime branch. A future third provider can opt in just by
exporting `AUTOCC_PROJECT_DIR` (and, optionally, `AUTOCC_AGENT_NAME`
/ `AUTOCC_AGENT_EMAIL`) at session start; no skill edit needed.

The `commit-changes` trailer defaults take the same shape, but with the
sniff folded directly into the `${...:-default}` expansion rather than
a multi-level chain — there are only two concrete providers (Claude
and Codex), so a single `[ -n "$CODEX_PROJECT_DIR" ]` test suffices and
avoids growing a generic provider-detection layer (Non-goal: "Generic
provider plugin SDK"). The override surface is unchanged: operators
who set `AUTOCC_AGENT_NAME` / `AUTOCC_AGENT_EMAIL` explicitly always
win, under both providers.

The reflector skill's `## 5 CHECKPOINT` branch still reads
`.autocc/context.json`, which today is only written by the Claude Code
statusline; on Codex the read returns empty and the branch no-ops.
That's an intentionally-deferred polyfill — see the Statusline
shell-out row in §4 below.

---

## 4. Gap list

Five Claude-Code-side behaviors autocc relies on that have no clean
Codex 0.128.0 analog. Each is tagged with the recommended disposition
(polyfill candidate / document-and-skip / accept-as-limitation) and a
one-line rationale.

- **PreToolUse(AskUserQuestion) — accept-as-limitation.** Codex has
  no `AskUserQuestion` tool to intercept; the "ask the human"
  pathway flows through `ElicitationRequest`/`RequestUserInput`
  events that the hook surface doesn't expose. Without an
  intercept point the autopilot constraint becomes "the model
  shouldn't ask in the first place" — enforce via the autopilot
  skill prompt, not the hook.

- **PreToolUse(EnterPlanMode) — accept-as-limitation.** Codex has no
  plan-mode tool. The `-a/--ask-for-approval=never` startup flag is
  the closest behavior (skip interactive approval prompts entirely),
  but it's set at session-launch not per-event, so autocc's installer
  should set it as part of the autopilot bootstrap rather than
  trying to intercept per-call.

- **Elicitation hook — polyfill candidate.** Codex emits
  `elicitation_request` Events but has no `Elicitation` hook event,
  so autocc can't auto-deny them. Polyfill option: an MCP server
  registered under `mcp_servers` that proxies `elicit/create` and
  auto-denies; Codex's `tool_call_mcp_elicitation` stable feature
  flag routes MCP elicitation through a path the model already
  understands.

- **PostCompact hook — polyfill candidate.** Codex auto-compacts
  (the `context_compacted` Event fires) but exposes no PostCompact
  hook for autocc to inject the latest checkpoint as
  `additionalContext`. Polyfill option: hang the resume nudge off
  the `user_prompt_submit` hook conditioned on "the most recent
  rollout entry was a compaction" — adds a turn of latency vs
  Claude Code's immediate inject, but preserves the loop-resume
  contract.

- **Statusline shell-out — document-and-skip.** Codex has a
  `status_line` TUI config but only as a widget list — there's no
  shell-command hook (no analog to Claude Code's `statusLine.command`).
  The autocc statusline script's primary side effect — writing
  `.autocc/context.json` for the reflector's 70%-context CHECKPOINT
  trigger — has no home on Codex. Recommend the Codex-side reflector
  skill drop the 70%-context branch entirely and rely on either
  (a) the existing per-task CHECKPOINT-on-completion pass, or
  (b) post-hoc parsing of `~/.codex/sessions/<id>.jsonl` for
  `ThreadTokenUsageUpdated` events if a smarter cadence is needed.

The pattern: Codex's hook surface is broadly a strict superset of
Claude Code's for the events we share names with, but two of autocc's
six hook events (`Elicitation`, `PostCompact`) have no direct binding,
and two of the matchers autocc relies on (`AskUserQuestion`,
`EnterPlanMode`) don't exist as Codex tools — so even though
`pre_tool_use` is available, those matchers never fire. The
installer task can proceed; the polyfill / accept decisions above
are inputs to its briefing.
