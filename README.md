# claude-thinking-panel

A live side panel for [Claude Code](https://claude.com/claude-code) that shows what the official TUI hides: **thinking blocks, tool calls as they happen, tool results, and subagent activity** — all in a second pane next to your normal Claude Code session.

```
┌────────────────────────────────┬──────────────────────────────┐
│                                │ ▸ 12:00:01 💭 thinking        │
│   your normal Claude Code      │ ▸ 12:00:02 ⚙ Bash  run tests │
│   session, untouched           │ ▸ 12:00:05 ✔ 42 passed       │
│                                │ ▸ 12:00:09 [MAIN] 🗣 Done —…  │
│                                │ ▸ 12:00:11 [explore] ⚙ Grep  │
└────────────────────────────────┴──────────────────────────────┘
```

Why: to *see the AI working* — catch it stuck on a command, drifting from the plan, or watch what a subagent is actually doing — without giving up the interactive TUI.

## How it works

- **No wrappers around the model, no API keys, no patching Claude Code.** The viewer tails the session transcript (`~/.claude/projects/<project>/<session>.jsonl`), which Claude Code writes block-by-block as the conversation advances. Subagent transcripts (`<session>/subagents/*.jsonl`) are merged in chronologically.
- **Session discovery is deterministic, not heuristic.** Three tiny Claude Code hooks (SessionStart / UserPromptSubmit / SessionEnd) maintain a pointer file per directory in `~/.claude/run/`. New session, `/clear`, resume, exit — the panel follows along automatically.
- **The tmux is 100% self-contained.** Own socket (`-L claude-think`), own config file, no status bar, no prefix key. It cannot see or affect any other tmux usage on your machine, and it dies when Claude Code exits. `Ctrl+Z` suspends the whole thing like a normal job (`fg` brings it back intact).

## Install

Dependencies: `tmux`, `jq`, `python3` (stdlib only), and Claude Code itself. Linux; macOS untested.

```sh
git clone https://github.com/MuMaestro/claude-thinking-panel.git
cd claude-thinking-panel
./install.sh
```

The installer copies the two scripts to `~/.local/bin` (as `claude-watch` and `claude-think`), the tmux config and pointer hook into `~/.claude/`, and registers the hooks in `~/.claude/settings.json` (a backup is made; `./uninstall.sh` reverts everything).

Everything here is plain source — `claude_watch.py` is stdlib-only Python (curses), the rest is bash and a tmux config. No build step, nothing compiled.

## Use

```sh
claude-think            # opens claude + the side panel
claude-think --resume   # any claude args pass through
claude-watch [dir]      # just the viewer, in any terminal (default: $PWD)
```

Inside the panel:

| key | action |
|---|---|
| click | expand / collapse an event |
| wheel · ↑↓ · j/k · PgUp/PgDn | scroll |
| `f` | follow the tail again (auto-scroll) |
| `s` | cycle view: everything → main only → each subagent |
| `e` / `c` | expand all / collapse all (thinking stays open) |
| `+` / `-` | widen / narrow the panel |
| `F9` | toggle the panel without leaving the session |
| `?` | shortcut legend |
| `q` / Esc | quit the viewer |

Thinking blocks are always expanded (they're the point); everything else starts collapsed to one line, since you already see it in the main terminal. Timestamps are shown in your local timezone. When subagents appear, every line is tagged and colored by its agent (`[MAIN]`, `[explore the repo]`, …).

## Good to know

- **Latency is block-level, not token-level.** Claude Code writes the transcript asynchronously per content block — a long thinking block appears when it finishes, not while it streams. That's inherent to observing from outside.
- **Sometimes thinking arrives empty.** On the Claude 5 model family the API only returns thinking text (a summary) when the request asks for it; otherwise the block comes with a signature and empty text. The panel marks those as `💭 thought (summary not exposed by the API in this mode)` — there is genuinely nothing to show, for any tool. Enabling `"alwaysThinkingEnabled": true` in your settings maximizes what you do get.

## License & a small ask

MIT — free and open source, use it however you like.

The only thing I ask: **if this project inspired you or you built on it, leave a comment** (an issue or discussion saying hi is perfect) and consider starring the repo. That's it.
