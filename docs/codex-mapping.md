# Codex extension surface ↔ autocc requirements

Discovery output for TB-1. The goal: name, for each Claude-Code-side
behavior autocc currently relies on, the equivalent OpenAI Codex
extension point — or, where none exists, record the gap so downstream
installer / hook tasks can plan a polyfill, a documented skip, or an
accepted limitation.

Findings here are pinned to **codex-cli 0.128.0** as installed by
Homebrew at `/opt/homebrew/bin/codex` (npm package `@openai/codex`,
shipping a precompiled Rust binary under
`@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/codex/codex`).
Where the codex binary's `--help` text doesn't surface a behavior,
I cite the strings table extracted from that binary — most internal
type names, hook event identifiers, and JSON wire shapes are reachable
that way, even though they aren't in the CLI help.

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
| `~/.codex/config.toml` | Single-file user config. TOML. Holds model selection, sandbox, MCP servers, **and a top-level `[hooks]` table** (the codex binary's `HookStateToml` deserializer accepts `PreToolUse`, `PermissionRequest`, `PostToolUse`, `SessionStart`, and the other CamelCase hook event names directly as table keys). | `~/.claude/settings.json` |
| `~/.codex/skills/` | User-installed skills (peer of the `~/.codex/skills/.system/` directory codex ships preinstalled — `skill-creator`, `plugin-creator`, `skill-installer`, `imagegen`, `openai-docs`). The `skill-installer` skill defaults its dest path to `${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>`. Each skill is `<skill>/SKILL.md` with YAML frontmatter `name:` and `description:`. | `~/.claude/skills/<skill>/SKILL.md` |
| `~/.codex/plugins/` (or repo-rooted `<repo>/plugins/`) | Plugins. A plugin is a directory with `.codex-plugin/plugin.json` plus optional `skills/`, `hooks.json`, `.mcp.json`, `.app.json`, `assets/`. Plugin manifests are surfaced to codex via a marketplace file. | n/a (Claude Code's nearest analog is shipping a skill + hook + statusline bundle as separate files under `~/.claude/`) |
| `~/.agents/plugins/marketplace.json` (or `<repo>/.agents/plugins/marketplace.json`) | Marketplace index listing plugin entries with `source.path`, `policy.installation`, `policy.authentication`, `category`. Codex's plugin-creator skill documents the exact shape. | n/a |
| `~/.codex/sessions/` | Per-session rollout state. Read-only from an installer's perspective. | `~/.claude/projects/` rollout |
| `~/.codex/memories/` | Persistent memory store (gated on `features.memories`, currently `experimental, false`). | `~/.claude/CLAUDE.md` + per-project `CLAUDE.md` |

`autocc install --agent codex` should write under `~/.codex/` (skills
and, for the hook script, a plugin folder under
`~/.codex/plugins/autocc/`), and either inject hook entries into
`~/.codex/config.toml`'s `[hooks]` table or ship them inside the
plugin's `hooks.json`. The plugin-shaped install is the more idiomatic
choice — Codex has explicit infrastructure for plugins (marketplace,
plugin/install request, `PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` env vars
that the binary exposes to hook commands), and uninstall reduces to
deleting one directory plus one marketplace entry.

### 1b. Migration is a first-class concern for the codex binary

The codex binary contains an `externalAgentConfig/detect` +
`externalAgentConfig/import` JSON-RPC API explicitly designed to
detect a `~/.claude` / `CLAUDE.md` / `settings.json` / `hooks.json`
/ `AGENTS.md` / `.agents/` install and migrate it into the codex
equivalents. The migration item types the binary serializes include
`AGENTS_MD`, `CONFIG`, `SKILLS`, `PLUGINS`, `MCP_SERVER_CONFIG`,
`SUBAGENTS`, `HOOKS`. Implication for autocc: a clean Codex install
path is in scope, but the installer can lean on Codex's own importer
for the *user's* pre-existing claude artifacts rather than reinventing
that work.

### 1c. Extension points the binary exposes

The runnable extension surface, in the order autocc cares about:

1. **Hooks.** First-class. Configured under `[hooks]` in
   `config.toml` (per-user) or under a plugin's `hooks.json` (sharable).
   Hook events are listed in §2 below. Implementation lives in
   `codex-rs/hooks/`, dispatched by `engine::dispatcher` via
   `engine::command_runner`. Hook handlers can be `Command` (spawn a
   process, give it JSON on stdin, parse JSON on stdout) with fields
   `command`, `timeout`, `async`, `statusMessage`, `agent`, plus a
   `matcher` regex (PreToolUse-only).
   - **Feature flag:** `codex_hooks` is `stable, true`. A
     newer `plugin_hooks` flag is `under development, false` and
     reportedly controls whether plugin-bundled hooks merge into the
     dispatcher; if the install path goes plugin-only, the installer
     should explicitly enable it via `codex --enable plugin_hooks` or
     `-c features.plugin_hooks=true` when running on a build where it
     defaults off.
   - **Hook env vars:** the binary passes `PLUGIN_ROOT`,
     `CLAUDE_PLUGIN_ROOT`, `PLUGIN_DATA`, `CLAUDE_PLUGIN_DATA` to hook
     commands. The Claude-prefixed aliases are deliberate — Codex
     mirrors the Claude Code env-var contract so a hook written for
     Claude Code mostly Just Works.
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
5. **Statusline.** No analog. `codex --help` and the binary strings
   table contain no `statusLine` / `statusline` configuration knob.
   See §4 for what this breaks.
6. **Features flags.** `codex features list | enable | disable`. Many
   are gated; the relevant ones for autocc are `codex_hooks` (already
   stable+on), `plugin_hooks` (under development), `memories`
   (experimental, off), `personality` (stable+on).

---

## 2. Hook event mapping

Codex's hook event vocabulary, taken from the binary's
`HookEventName` enum and the matching `events/<name>.rs` source paths:

| Wire name (snake_case) | CamelCase (JSON `hookEventName`) | Source file referenced in binary |
|---|---|---|
| `pre_tool_use` | `PreToolUse` | `codex-rs/hooks/src/events/pre_tool_use.rs` |
| `post_tool_use` | `PostToolUse` | `codex-rs/hooks/src/events/post_tool_use.rs` |
| `permission_request` | `PermissionRequest` | `codex-rs/hooks/src/events/permission_request.rs` |
| `session_start` | `SessionStart` | `codex-rs/hooks/src/events/session_start.rs` |
| `user_prompt_submit` | `UserPromptSubmit` | `codex-rs/hooks/src/events/user_prompt_submit.rs` |
| `stop` | `Stop` | `codex-rs/hooks/src/events/stop.rs` |
| `notification` | `Notification` | (no dedicated events file string surfaced, but the name appears in the `HookEventName` enum) |

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
- `notification` — present in `HookEventName` but underdocumented in
  the strings table; useful surface area to investigate before
  building any polyfill.

---

## 3. Skill portability

Each of autocc's six skills, against Codex's skill loader behavior:

| Skill | Claude-Code-specific assumptions | Codex portability | Required glue |
|---|---|---|---|
| `afk` | Reads `$CLAUDE_PROJECT_DIR` env var to locate session root; creates `.autocc/flag`; invokes `/reflector` as a sibling skill. | **needs-provider-specific-glue** | Codex does not set `CLAUDE_PROJECT_DIR`. The skill body must fall back to `${CODEX_PROJECT_DIR:-$PWD}` (or read codex's project root from `$PWD`, since `codex -C/--cd` rewrites cwd). Slash-command invocation (`/reflector`) works in both — Codex's TUI accepts `/<skill-name>` to trigger a skill — so the skill-to-skill call is fine. |
| `reflector` | Reads `$CLAUDE_PROJECT_DIR`; reads `CLAUDE.md`'s `## Autopilot` section; depends on the Stop hook re-blocking idle to keep the loop alive; reads `.autocc/context.json` (statusline-written) for the 70%-context CHECKPOINT trigger. | **needs-provider-specific-glue** | Same env-var fallback as `afk`. Codex reads `CLAUDE.md` natively (the externalAgentConfig migration path proves this), so the `## Autopilot` section parse works as-is. The Stop-hook loop wiring works as-is (codex's `stop` hook implements the same `decision:block` contract). The 70%-CHECKPOINT trigger is the load-bearing break: Codex has no statusline (§4), so `context.json` is never written — the CHECKPOINT logic must instead read context usage from the session's own state. Codex emits `ThreadTokenUsageUpdated` / `token_count` Events that carry token-usage deltas, but those don't reach a skill's prompt context the way a statusline-written file does. Polyfill candidates: (a) parse the most recent `~/.codex/sessions/<id>.jsonl` rollout for token-usage events, (b) accept "checkpoint every N completed tasks" instead of "checkpoint at N% context," (c) accept the degradation and document it. |
| `taskboard` | Reads/writes `TASKS.md`; reads `CLAUDE.md` `## Autopilot` paths; references `.autocc/tasks/`, `.autocc/progress.md`. No env-var dependence. | **portable-as-is** | None. Codex reads `CLAUDE.md` (and `AGENTS.md`) natively. The skill body's `aliases:` frontmatter key is not in the codex skill-creator spec; codex skill loaders appear to ignore unknown keys, but if a future codex version validates frontmatter strictly the `aliases:` line would need to move into `metadata:`. |
| `tb` | Pure alias for `/taskboard` (one body line). | **portable-as-is** | None. The alias mechanism in autocc is just a separately-installed skill that re-invokes `/taskboard`; codex handles that fine. |
| `housekeeping` | Detects project tooling via `pyproject.toml` / `package.json` / `Makefile` / `Cargo.toml` etc. and runs the project's linter/tests. No Claude-specific surface. | **portable-as-is** | None. |
| `commit-changes` | Pure prompt; reads `TASKS.md` + `.autocc/progress.md`; writes git commits with a `Co-Authored-By: Claude <noreply@anthropic.com>` trailer. | **needs-provider-specific-glue** | The hardcoded `Co-Authored-By: Claude <noreply@anthropic.com>` trailer is wrong under Codex — should be `Co-Authored-By: Codex <noreply@openai.com>` or parameterized by the active provider. Otherwise the skill is pure markdown protocol. |

No skill in autocc is classified `no-codex-analog` — every one of them
can run under Codex, three of them as-is and three with cosmetic /
env-var glue.

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

- **Statusline — document-and-skip.** Codex has no statusline
  config. The autocc statusline's primary side effect — writing
  `.autocc/context.json` for the reflector's 70%-context CHECKPOINT
  trigger — has no home. Recommend the Codex-side reflector skill
  drop the 70%-context branch entirely and rely on either
  (a) the existing per-task CHECKPOINT-on-completion pass, or
  (b) post-hoc parsing of `~/.codex/sessions/<id>.jsonl` for
  `ThreadTokenUsageUpdated` events if a smarter cadence is needed.

The pattern: Codex's hook surface is broadly a strict superset of
Claude Code's for the events we share names with, but two of autocc's
six hook events (`Elicitation`, `PostCompact`) and one tool matcher
(`EnterPlanMode`) have no direct binding. The installer task can
proceed; the polyfill / accept decisions above are inputs to its
briefing.
