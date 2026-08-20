#!/usr/bin/env python3
"""claude-watch — TUI that follows the active Claude Code session and shows
what the official TUI hides, with THINKING as the protagonist:

- thinking blocks: always expanded, full text;
- tool calls, results, assistant text and user prompts: collapsed to one line
  (you already see them in the main terminal) — click to expand.

Interaction: click toggles expand/collapse · mouse wheel / ↑↓ PgUp PgDn
scroll · f resumes following the tail · e/c expand/collapse all · q quits.

Session discovery: reads the pointer file that the hooks
(claude-think-pointer.sh) maintain in ~/.claude/run/active-session-<cwd-hash>.json.
A new session or a resume switches transcripts automatically; SessionEnd goes
back to "waiting". Subagents (<session>/subagents/*.jsonl) join the same
stream, labeled.

Latency: Claude Code writes the transcript per block, asynchronously — never
token by token; that is the best an outside observer can get.

Usage: claude-watch [directory]   (default: $PWD)
"""

import curses
import hashlib
import json
import os
import sys
import textwrap
import time

POLL = 0.4          # seconds between file scans
BACKLOG_BYTES = 200_000  # when picking up a session mid-flight, read only the file tail

HOME = os.path.expanduser("~")


def pointer_path(watch_dir):
    h = hashlib.md5(watch_dir.encode()).hexdigest()[:8]
    return os.path.join(HOME, ".claude", "run", f"active-session-{h}.json")


def clip(s, n):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


class Event:
    __slots__ = ("kind", "ts", "title", "body", "expanded", "src")

    def __init__(self, kind, ts, title, body, expanded, src=""):
        self.kind = kind
        self.ts = ts
        self.title = title
        self.body = body.rstrip("\n")
        self.expanded = expanded
        self.src = src


def tool_result_text(block):
    content = block.get("content", "")
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content)


def parse_line(raw, src):
    """One JSONL line -> list of Events (possibly empty)."""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(obj, dict):
        return []
    ts = (obj.get("timestamp") or "")[11:19] or "--:--:--"
    events = []
    msg = obj.get("message") or {}
    if obj.get("type") == "assistant":
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            ct = c.get("type")
            if ct == "thinking":
                body = c.get("thinking") or ""
                if body.strip():
                    events.append(Event("thinking", ts, "💭 thinking", body, True, src))
            elif ct == "tool_use":
                inp = c.get("input", {}) or {}
                # Collapsed line: the INTENT of the call, not the JSON. Order:
                # description (Bash/Agent state the why) > the tool's salient
                # field > JSON as a last resort. The full JSON stays in the
                # expanded body.
                gist = inp.get("description") or inp.get("file_path") or \
                    inp.get("pattern") or inp.get("query") or inp.get("url") or \
                    inp.get("command") or inp.get("prompt") or \
                    json.dumps(inp, ensure_ascii=False)
                title = f"⚙ {c.get('name', '?')}  {clip(str(gist), 999)}"
                pretty = json.dumps(inp, ensure_ascii=False, indent=2)
                events.append(Event("tool", ts, title, pretty, False, src))
            elif ct == "text":
                body = c.get("text") or ""
                if body.strip():
                    events.append(Event("text", ts, f"🗣 {clip(body, 999)}", body, False, src))
    elif obj.get("type") == "user":
        content = msg.get("content")
        if isinstance(content, str):
            if content.strip():
                events.append(Event("user", ts, f"❯ {clip(content, 999)}", content, False, src))
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    body = tool_result_text(c)
                    kind = "err" if c.get("is_error") else "ok"
                    mark = "✘" if kind == "err" else "✔"
                    events.append(Event(kind, ts, f"{mark} {clip(body, 999)}", body, False, src))
    return events


class Tailer:
    """Reads a file incrementally by byte offset, tolerating a partial line."""

    def __init__(self, path, from_tail=False):
        self.path = path
        self.pos = 0
        self.buf = ""
        if from_tail:
            try:
                size = os.path.getsize(path)
                if size > BACKLOG_BYTES:
                    self.pos = size - BACKLOG_BYTES
                    self.buf = None  # discard the first (partial) line
            except OSError:
                pass

    def read_lines(self):
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.pos)
                chunk = f.read()
                self.pos = f.tell()
        except OSError:
            return []
        if not chunk:
            return []
        if self.buf is None:  # skipping the initial partial line of from_tail mode
            nl = chunk.find("\n")
            if nl < 0:
                return []
            chunk = chunk[nl + 1 :]
            self.buf = ""
        data = self.buf + chunk
        lines = data.split("\n")
        self.buf = lines.pop()  # the last one may be incomplete
        return [ln for ln in lines if ln.strip()]


def agent_display_name(jsonl_path):
    """Readable subagent name, from the .meta.json next to the transcript
    (description > agentType > file id)."""
    meta_path = jsonl_path[: -len(".jsonl")] + ".meta.json"
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return meta.get("description") or meta.get("agentType") or ""
    except (OSError, ValueError):
        return ""


class Session:
    def __init__(self, transcript, session_id):
        self.transcript = transcript
        self.session_id = session_id
        self.tailers = {transcript: Tailer(transcript, from_tail=True)}
        self.names = {transcript: ""}

    def poll(self):
        events = []
        subdir = self.transcript[: -len(".jsonl")] + "/subagents"
        if os.path.isdir(subdir):
            try:
                entries = sorted(os.listdir(subdir))
            except OSError:
                entries = []
            for entry in entries:
                p = os.path.join(subdir, entry)
                if p.endswith(".jsonl") and p not in self.tailers:
                    self.tailers[p] = Tailer(p)
                    label = agent_display_name(p) or entry[: -len(".jsonl")]
                    self.names[p] = label
                    events.append(Event("meta", "--:--:--", f"↳ subagent {label}", "", False, label))
        for path, tailer in self.tailers.items():
            lazy = self.names.get(path, "")
            for raw in tailer.read_lines():
                events.extend(parse_line(raw, lazy))
        return events


COLOR = {"thinking": 1, "tool": 2, "text": 3, "user": 4, "err": 5, "meta": 6, "ok": 7}


def agent_color_pair(name):
    """Deterministic color per agent, avoiding magenta (thinking) and red (error)."""
    palette = (6, 3, 4, 2)  # cyan, green, blue, yellow
    return palette[sum(map(ord, name)) % len(palette)]


def build_lines(events, width, view):
    """-> list of (text, attr_key, event_index|None, seg|None).

    The index serves the click; seg = (start, end) of the [agent] segment in
    the line, painted with the agent's color. `view` filters: "all", "main"
    or a subagent name (meta events always show).
    """
    lines = []
    for i, ev in enumerate(events):
        if ev.kind != "meta":
            if view == "main" and ev.src:
                continue
            if view not in ("all", "main") and ev.src != view:
                continue
        marker = " " if ev.kind in ("thinking", "meta") else ("▾" if ev.expanded else "▸")
        srcseg = f"[{ev.src}]" if ev.src else ""
        src = f"{srcseg} " if srcseg else ""
        title = f"{marker} {ev.ts} {src}{ev.title}"

        def seg_in(text):
            if not srcseg:
                return None
            pos = text.find(srcseg)
            return (pos, pos + len(srcseg)) if pos >= 0 else None

        if ev.kind == "tool":
            # A collapsed tool call doesn't cut the intent with "…": it wraps
            # into indented continuation lines, all clickable for the same
            # event. Other kinds stay on one line — long collapsed text or
            # results spanning 10 lines would defeat the collapse.
            for wt in textwrap.wrap(title, max(20, width - 1), subsequent_indent="      ") or [""]:
                lines.append((wt, ev.kind, i, seg_in(wt)))
        else:
            t = clip(title, max(10, width - 1))
            lines.append((t, ev.kind, i, seg_in(t)))
        if ev.expanded and ev.body:
            for para in ev.body.split("\n"):
                wrapped = textwrap.wrap(para, max(10, width - 6)) or [""]
                for w in wrapped:
                    lines.append(("    " + w, ev.kind + "_body", i, None))
        if ev.kind == "thinking":
            lines.append(("", "plain", None, None))
    return lines


def read_pointer(ptr):
    try:
        with open(ptr, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("transcript_path") or "", d.get("session_id") or "?", bool(d.get("ended"))
    except (OSError, ValueError):
        return "", "?", False


def main(stdscr, watch_dir):
    curses.curs_set(0)
    curses.use_default_colors()
    for pair, fg in ((1, curses.COLOR_MAGENTA), (2, curses.COLOR_YELLOW),
                     (3, curses.COLOR_GREEN), (4, curses.COLOR_BLUE),
                     (5, curses.COLOR_RED), (6, curses.COLOR_CYAN),
                     (7, curses.COLOR_WHITE)):
        curses.init_pair(pair, fg, -1)
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    stdscr.timeout(int(POLL * 1000))

    ptr = pointer_path(watch_dir)
    session = None
    events = [Event("meta", "--:--:--", f"waiting for a Claude Code session in {watch_dir}…", "", False)]
    scroll = 0
    follow = True
    last_poll = 0.0
    view = "all"  # "all" | "main" | a subagent name

    def attr_for(key):
        base = key.replace("_body", "")
        a = curses.color_pair(COLOR.get(base, 0))
        if key.endswith("_body") and base != "thinking":
            a |= curses.A_DIM
        if base == "ok":
            a |= curses.A_DIM
        if base == "meta":
            a |= curses.A_BOLD
        return a

    while True:
        now = time.monotonic()
        if now - last_poll >= POLL:
            last_poll = now
            transcript, sid, ended = read_pointer(ptr)
            if session and ended and sid == session.session_id:
                events.append(Event("meta", "--:--:--", "— session ended — waiting for the next one…", "", False))
                session = None
            elif transcript and not ended and (not session or session.transcript != transcript):
                session = Session(transcript, sid)
                # New/switched session: clear the previous history — keeping
                # old events mixed in confuses more than it helps.
                events = [Event("meta", "--:--:--", f"━━ session {sid} ━━", "", False)]
                scroll = 0
                follow = True
            if session:
                new = session.poll()
                if new:
                    events.extend(new)
                    if follow:
                        scroll = 10 ** 9

        height, width = stdscr.getmaxyx()
        body_h = height - 1
        views = ["all", "main"] + sorted({ev.src for ev in events if ev.src})
        if view not in views:
            view = "all"
        lines = build_lines(events, width, view)
        max_scroll = max(0, len(lines) - body_h)
        scroll = min(scroll, max_scroll)
        if follow:
            scroll = max_scroll

        stdscr.erase()
        visible = lines[scroll : scroll + body_h]
        for y, (text, key, _idx, seg) in enumerate(visible):
            try:
                if seg:
                    s, e = seg
                    a = attr_for(key)
                    stdscr.addstr(y, 0, text[:s], a)
                    stdscr.addstr(y, s, text[s:e], curses.color_pair(agent_color_pair(text[s:e])) | curses.A_BOLD)
                    stdscr.addstr(y, e, text[e:], a)
                else:
                    stdscr.addstr(y, 0, text, attr_for(key))
            except curses.error:
                pass
        status = " click: expand · s: view · f: follow · e/c: expand/collapse · q: quit "
        mode = " [following] " if follow else f" [scroll {scroll}/{max_scroll}] "
        mode += f"[view: {clip(view, 30)}] "
        try:
            stdscr.addstr(height - 1, 0, clip(mode + status, width - 1), curses.A_REVERSE)
        except curses.error:
            pass
        stdscr.refresh()

        try:
            ch = stdscr.getch()
        except KeyboardInterrupt:
            return
        if ch == -1:
            continue
        if ch in (ord("q"), 27):
            return
        elif ch == curses.KEY_RESIZE:
            continue
        elif ch in (curses.KEY_UP, ord("k")):
            follow, scroll = False, max(0, scroll - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            scroll += 1
            follow = scroll >= max_scroll
        elif ch == curses.KEY_PPAGE:
            follow, scroll = False, max(0, scroll - body_h)
        elif ch == curses.KEY_NPAGE:
            scroll += body_h
            follow = scroll >= max_scroll
        elif ch == ord("f"):
            follow = True
        elif ch == ord("s"):
            view = views[(views.index(view) + 1) % len(views)]
            follow = True
        elif ch == ord("e"):
            for ev in events:
                ev.expanded = True
        elif ch == ord("c"):
            for ev in events:
                if ev.kind != "thinking":
                    ev.expanded = False
        elif ch == curses.KEY_MOUSE:
            try:
                _, _mx, my, _, bstate = curses.getmouse()
            except curses.error:
                continue
            b4 = getattr(curses, "BUTTON4_PRESSED", 0)
            b5 = getattr(curses, "BUTTON5_PRESSED", 0)
            if bstate & b4:
                follow, scroll = False, max(0, scroll - 3)
            elif bstate & b5:
                scroll += 3
                follow = scroll >= max_scroll
            elif bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                row = scroll + my
                if 0 <= my < body_h and row < len(lines):
                    idx = lines[row][2]
                    if idx is not None:
                        events[idx].expanded = not events[idx].expanded


if __name__ == "__main__":
    watch_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(main, watch_dir)
    except KeyboardInterrupt:
        pass
