# Contributing

Thanks for your interest in improving claude-thinking-panel!

## Before you start

- **Bug fixes and small improvements**: open a pull request directly. No need to ask first.
- **New features or behavior changes**: please **open an issue first** describing what you want to do and why. This avoids you spending time on something that may not fit the project's scope. Wait for a 👍 before writing code.

## Ground rules

- Keep the Python side (`claude_watch.py`) **standard-library only** — no third-party dependencies.
- Shell scripts must pass `shellcheck`; Python must pass `ruff check`. CI enforces both on every pull request.
- Keep changes focused: one topic per pull request.

## Pull request process

1. Fork the repo and create a branch from `main`.
2. Make your change. Run the linters locally if you can:
   ```sh
   shellcheck claude-think.sh install.sh uninstall.sh hooks/*.sh
   ruff check claude_watch.py
   ```
3. Use [Conventional Commits](https://www.conventionalcommits.org/) messages (`feat:`, `fix:`, `docs:`, `chore:`), matching the existing history.
4. Open the pull request. CI must be green before it can be merged. Note that CI runs for first-time contributors require maintainer approval, so there may be a short delay.
5. Pull requests are **squash-merged**, so your PR title becomes the commit message — write it accordingly.

## Reporting bugs

Open an issue with:

- What you did, what you expected, and what happened instead.
- Your environment: OS, tmux version, Python version, and Claude Code version.
- If relevant, the panel output or a screenshot.

## Code of conduct

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
