#!/usr/bin/env bash
# Undoes install.sh: removes binaries, hook, tmux conf and the pointer hook
# entries from ~/.claude/settings.json.
set -euo pipefail

rm -f "$HOME/.local/bin/claude-think" "$HOME/.local/bin/claude-watch" \
      "$HOME/.claude/hooks/claude-think-pointer.sh" \
      "$HOME/.claude/claude-think.tmux.conf"
rm -rf "$HOME/.claude/run"

SETTINGS="$HOME/.claude/settings.json"
if [ -f "$SETTINGS" ] && command -v jq >/dev/null 2>&1; then
  jq '
    if .hooks then
      .hooks |= with_entries(
        .value |= map(select(
          ((.hooks // []) | map(.command // "") | join(" "))
          | contains("claude-think-pointer") | not
        ))
      )
    else . end
  ' "$SETTINGS" >"$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
fi

echo "claude-think removed."
