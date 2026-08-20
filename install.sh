#!/usr/bin/env bash
# Installs claude-think:
#   ~/.local/bin/claude-think, ~/.local/bin/claude-watch
#   ~/.claude/claude-think.tmux.conf
#   ~/.claude/hooks/claude-think-pointer.sh
# and registers the pointer hooks in ~/.claude/settings.json (with a backup).
set -euo pipefail
cd "$(dirname "$0")"

for dep in tmux jq python3; do
  command -v "$dep" >/dev/null 2>&1 || {
    echo "error: missing dependency: $dep" >&2
    exit 1
  }
done

BIN="$HOME/.local/bin"
CLAUDE="$HOME/.claude"
mkdir -p "$BIN" "$CLAUDE/hooks" "$CLAUDE/run"

install -m 755 claude_watch.py "$BIN/claude-watch"
install -m 755 claude-think.sh "$BIN/claude-think"
install -m 755 hooks/claude-think-pointer.sh "$CLAUDE/hooks/"
install -m 644 claude-think.tmux.conf "$CLAUDE/claude-think.tmux.conf"

SETTINGS="$CLAUDE/settings.json"
[ -f "$SETTINGS" ] || echo '{}' >"$SETTINGS"

if grep -q 'claude-think-pointer' "$SETTINGS"; then
  echo "hooks already registered in $SETTINGS — nothing to do."
else
  cp "$SETTINGS" "$SETTINGS.bak-claude-think"
  jq '
    def entry($mode): {hooks: [{type: "command",
      command: ("bash ~/.claude/hooks/claude-think-pointer.sh " + $mode),
      timeout: 5}]};
    .hooks //= {} |
    .hooks.SessionStart      = ((.hooks.SessionStart      // []) + [entry("start")]) |
    .hooks.UserPromptSubmit  = ((.hooks.UserPromptSubmit  // []) + [entry("update")]) |
    .hooks.SessionEnd        = ((.hooks.SessionEnd        // []) + [entry("end")])
  ' "$SETTINGS" >"$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  echo "hooks registered in $SETTINGS (backup at $SETTINGS.bak-claude-think)."
fi

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) echo "warning: $BIN is not on your PATH — add it in your shell config." ;;
esac

echo "done! new Claude Code sessions will maintain the pointer."
echo "open with:  claude-think"
