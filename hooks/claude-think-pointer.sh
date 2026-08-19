#!/usr/bin/env bash
# Maintains a per-directory pointer file with the active Claude Code session,
# so claude-watch discovers which transcript to follow without mtime
# heuristics.
#
# Registered by install.sh in ~/.claude/settings.json under SessionStart /
# SessionEnd / UserPromptSubmit. Receives the hook's JSON payload on stdin
# (session_id, transcript_path, cwd, ...) and writes/updates:
#   ~/.claude/run/active-session-<cwd-hash>.json
#
# Usage: claude-think-pointer.sh start|update|end
#
# IMPORTANT: write NOTHING to stdout — on UserPromptSubmit the hook's stdout
# becomes context injected into the conversation.
set -euo pipefail

mode="${1:-update}"
payload=$(cat)

cwd=$(jq -r '.cwd // empty' <<<"$payload" 2>/dev/null) || exit 0
[ -n "$cwd" ] || exit 0

hash=$(printf '%s' "$cwd" | md5sum | cut -c1-8)
dir="$HOME/.claude/run"
mkdir -p "$dir"
ptr="$dir/active-session-$hash.json"

case "$mode" in
  end)
    # Only mark ended if the pointer still points at THIS session: another
    # session in the same directory may have taken over the pointer meanwhile.
    [ -f "$ptr" ] || exit 0
    current=$(jq -r '.session_id // empty' "$ptr" 2>/dev/null) || exit 0
    this=$(jq -r '.session_id // empty' <<<"$payload" 2>/dev/null) || exit 0
    if [ -n "$this" ] && [ "$current" = "$this" ]; then
      jq -c '. + {ended: true}' <<<"$payload" >"$ptr.tmp" && mv "$ptr.tmp" "$ptr"
    fi
    ;;
  *)
    jq -c '. + {ended: false}' <<<"$payload" >"$ptr.tmp" && mv "$ptr.tmp" "$ptr"
    ;;
esac
