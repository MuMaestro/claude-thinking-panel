#!/usr/bin/env bash
# claude-think — opens Claude Code with a thinking side pane (claude-watch),
# inside a 100% isolated tmux.
#
# Isolation: its own socket (-L claude-think) + its own config (-f), so this
# tmux neither sees nor affects any other tmux usage, has no status bar and
# does not exist beyond the duration of this command.
#
# Lifecycle: the main pane runs `claude <args>` and, when claude exits
# (/exit, crash, close), kills the whole tmux session — viewer included — and
# you are back at your normal prompt. Ctrl+Z suspends the tmux CLIENT (bound
# in the config), so `fg` restores claude + pane intact. F9 toggles the
# viewer pane.
#
# Usage: claude-think [claude args...]
set -euo pipefail

if ! command -v tmux >/dev/null 2>&1; then
  echo "claude-think: tmux not found; opening claude without the panel." >&2
  exec claude "$@"
fi

conf="$HOME/.claude/claude-think.tmux.conf"
sock="claude-think"
sess="ct$$"

rundir="${XDG_RUNTIME_DIR:-/tmp}/claude-think"
mkdir -p "$rundir"
runner=$(mktemp "$rundir/runner-XXXXXX.sh")

# Runner serialized to a file to preserve arg quoting through tmux's internal
# `sh -c`. kill-session is the last line: when claude exits, the session (and
# the viewer pane) dies with it.
{
  printf '#!/usr/bin/env bash\n'
  printf 'claude'
  printf ' %q' "$@"
  printf '\nrm -f -- %q\n' "$runner"
  printf 'exec tmux -L %q kill-session -t %q\n' "$sock" "$sess"
} >"$runner"
chmod +x "$runner"

# env -u TMUX: allows opening even if you are already inside another tmux
# (different sockets, nesting is safe here).
exec env -u TMUX tmux -L "$sock" -f "$conf" \
  new-session -s "$sess" "bash $runner" \; \
  split-window -h -l 38% "claude-watch" \; \
  select-pane -t 0
