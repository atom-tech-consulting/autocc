# Tasks

## Active


## Ready


## Backlog

- [ ] **TB-8** **Make commit-changes' trailer identity default to "Codex" under the Codex install** `#codex` `#skills` `#commit-changes` — Have the Codex installer export AUTOCC_AGENT_NAME=Codex / AUTOCC_AGENT_EMAIL=noreply@openai.com (or document the user-set override) so commit-changes' Co-Authored-By trailer reads "Codex" under the Codex install path rather than the Claude default. [→ brief](.cc-autopilot/tasks/make-commit-changes-trailer-identity-def.md)
- [ ] **TB-7** **Document the Codex install path in README and ARCHITECTURE** `#codex` `#docs` — Add Codex install + hook documentation to README and ARCHITECTURE alongside the existing Claude Code coverage, closing goal.md Done-when bullet #4. [→ brief](.cc-autopilot/tasks/document-the-codex-install-path-in-readm.md)

## Pipeline Pending


## Complete

- [x] **TB-1** **Map Codex extension points to autocc hook + skill requirements** `#codex` `#discovery` `#docs` [→ brief](.cc-autopilot/tasks/map-codex-extension-points-to-autocc-hoo.md)
- [x] **TB-2** **Add `--agent codex` install branch to autocc installer** `#codex` `#installer` — Add `--agent codex` install branch to autocc installer [→ brief](.cc-autopilot/tasks/add-agent-codex-install-branch-to-autocc.md)
- [x] **TB-3** **Write Codex-side autocc hook script with Codex JSON wire shapes** `#codex` `#hooks` — Write Codex-side autocc hook script with Codex JSON wire shapes [→ brief](.cc-autopilot/tasks/write-codex-side-autocc-hook-script-with.md)
- [x] **TB-4** **Decouple afk / reflector / commit-changes skills from Claude-only assumptions** `#codex` `#skills` — Decouple afk / reflector / commit-changes skills from Claude-only assumptions [→ brief](.cc-autopilot/tasks/decouple-afk-reflector-commit-changes-sk.md)
- [x] **TB-6** **Fix TB-5 briefing: move live-codex AUTOCC_REAL_SDK bullet out of Verification** `#codex` `#fix-briefing` `#smoke` — Fix TB-5 briefing: relocate the live-codex smoke invocation from ## Verification to ## Out of scope so the daemon can re-verify the task; the implementation already landed at commit e0d1b66. [→ brief](.cc-autopilot/tasks/fix-tb-5-briefing-move-live-codex-autocc.md)
- [x] **TB-5** **Add Codex real-SDK smoke test against examples/taskflow** `#codex` `#smoke` `#tests` [→ brief](.cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md)

## Frozen
