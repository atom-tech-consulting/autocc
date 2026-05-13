#!/usr/bin/env bash
# Claude Code statusLine command for autocc.
#
# Extras beyond a standard prompt-style status line:
# - Saves the full JSON to $project_dir/.autocc/context.json so the agent can
#   read its own context level during autopilot (reflector uses this for its
#   70%-checkpoint trigger).
# - When .autocc/flag is set, appends the active task ID + Ready task count.

input=$(cat)

# --- Save JSON to autocc folder if it exists ---
project_dir=$(echo "$input" | jq -r '.workspace.project_dir // empty')
if [ -n "$project_dir" ] && [ -d "$project_dir/.autocc" ]; then
  echo "$input" > "$project_dir/.autocc/context.json"
fi

# --- Path: up to 3 levels between pwd and project_dir ---
current_dir=$(echo "$input" | jq -r '.workspace.current_dir // empty')
[ -z "$current_dir" ] && current_dir=$(pwd)

if [ -n "$project_dir" ] && [ "$current_dir" != "$project_dir" ]; then
  rel="${current_dir#"$project_dir"/}"
  parts=$(echo "$rel" | tr '/' '\n' | tail -3 | tr '\n' '/' | sed 's|/$||')
  full_parts=$(echo "$rel" | tr '/' '\n' | wc -l | tr -d ' ')
  [ "$full_parts" -gt 3 ] && parts="…/$parts"
  dir_display="$(basename "$project_dir")/$parts"
else
  dir_display=$(basename "$project_dir")
fi

# --- Shell-prompt components ---
user=$(whoami)
host=$(hostname -s)

# Git branch (skip optional locks)
git_branch=""
if git -C "$current_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  branch=$(GIT_OPTIONAL_LOCKS=0 git -C "$current_dir" symbolic-ref --short HEAD 2>/dev/null \
           || GIT_OPTIONAL_LOCKS=0 git -C "$current_dir" rev-parse --short HEAD 2>/dev/null)
  [ -n "$branch" ] && git_branch=" ($branch)"
fi

# --- Claude-specific info ---
model=$(echo "$input" | jq -r '.model.display_name // empty')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)

ctx_info=""
[ -n "$used_pct" ] && ctx_info=" ctx:${used_pct}%"

model_info=""
[ -n "$model" ] && model_info=" $model"

# --- Autopilot task info (only when flag is set) ---
task_info=""
if [ -n "$project_dir" ] && [ -f "$project_dir/.autocc/flag" ] && [ -f "$project_dir/TASKS.md" ]; then
  active_id=$(awk '/^## Active/{found=1;next} /^## /{found=0} found && /\*\*TB-[0-9]+\*\*/{match($0,/\*\*TB-[0-9]+\*\*/); id=substr($0,RSTART+2,RLENGTH-4); print id; exit}' "$project_dir/TASKS.md")
  ready_count=$(awk '/^## Ready/{found=1;next} /^## /{found=0} found && /^- \[/{c++} END{print c+0}' "$project_dir/TASKS.md")
  if [ -n "$active_id" ]; then
    task_info=" [$active_id]"
  fi
  if [ "$ready_count" -gt 0 ] 2>/dev/null; then
    task_info="${task_info} R:${ready_count}"
  fi
fi

# --- Assemble ---
printf "[%s@%s %s%s]%s%s%s" \
  "$user" "$host" "$dir_display" "$git_branch" \
  "$model_info" \
  "$ctx_info" \
  "$task_info"
