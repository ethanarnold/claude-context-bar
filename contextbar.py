#!/usr/bin/env python3
"""contextbar — live multi-session context meter for Claude Code.

Watches every session file under ~/.claude/projects/ and shows a live
TUI dashboard with one row per session: project name, usage bar,
percentage, token counts, and time since last update.

Run with no arguments for the live TUI dashboard. Use --once for a
one-shot snapshot suitable for piping, --ascii for terminals without
Unicode, --limit to override the context window, and --no-auto-limit
to disable per-model context window detection.

    contextbar              # live TUI
    contextbar --once       # one-shot snapshot
    contextbar --ascii      # ASCII glyphs only
    q to quit the TUI
"""

import argparse
import curses
import json
import locale
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

__version__ = "0.1.0"

PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CONTEXT_LIMIT = 200_000  # default Claude context window
REFRESH_SEC = 1.0

# Per-model context window detection. First match wins.
# 1M-context beta variants of Sonnet are matched before the generic
# sonnet/opus/haiku 200k fallback.
MODEL_LIMITS = [
    (re.compile(r"sonnet.*1m", re.IGNORECASE), 1_000_000),
    (re.compile(r"1m.*sonnet", re.IGNORECASE), 1_000_000),
    (re.compile(r"claude-(?:opus|sonnet|haiku)", re.IGNORECASE), 200_000),
]

GLYPHS_UNICODE = {"fill": "█", "empty": "░", "rule": "─", "ellipsis": "…"}
GLYPHS_ASCII = {"fill": "#", "empty": "-", "rule": "-", "ellipsis": "..."}

# Populated by main() before draw()/run_once() runs.
CONFIG: dict = {
    "limit_override": None,
    "auto_detect_limit": True,
    "glyphs": GLYPHS_UNICODE,
    "refresh": REFRESH_SEC,
    "once": False,
}


def find_sessions():
    """Return [(path, mtime), ...] for every session file, newest first."""
    sessions = []
    if not PROJECTS_DIR.exists():
        return sessions
    for proj in PROJECTS_DIR.iterdir():
        if not proj.is_dir():
            continue
        for f in proj.glob("*.jsonl"):
            try:
                sessions.append((f, f.stat().st_mtime))
            except OSError:
                pass
    sessions.sort(key=lambda x: -x[1])
    return sessions


def infer_limit(model: Optional[str]) -> int:
    """Return the context-window size in tokens for a given model name."""
    if not model:
        return DEFAULT_CONTEXT_LIMIT
    for pattern, limit in MODEL_LIMITS:
        if pattern.search(model):
            return limit
    return DEFAULT_CONTEXT_LIMIT


# Cache parsed session info keyed by path; invalidated by mtime change.
_cache: dict = {}


def read_session_info(path: Path, mtime: float):
    """Return dict with cwd, model, tokens, limit, session_id, or None."""
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]

    info = {
        "cwd": None,
        "model": None,
        "tokens": 0,
        "limit": DEFAULT_CONTEXT_LIMIT,
        "session_id": path.stem,
        "assistant_seen": False,
        "schema_ok": False,
    }
    last_usage = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if info["cwd"] is None and d.get("cwd"):
                    info["cwd"] = d["cwd"]
                if d.get("type") == "assistant":
                    info["assistant_seen"] = True
                    msg = d.get("message", {}) or {}
                    if msg.get("model"):
                        info["model"] = msg["model"]
                    u = msg.get("usage")
                    if u:
                        if any(
                            k in u
                            for k in (
                                "input_tokens",
                                "cache_creation_input_tokens",
                                "cache_read_input_tokens",
                                "output_tokens",
                            )
                        ):
                            info["schema_ok"] = True
                        last_usage = u
    except OSError:
        return None

    if last_usage:
        info["tokens"] = (
            (last_usage.get("input_tokens") or 0)
            + (last_usage.get("cache_creation_input_tokens") or 0)
            + (last_usage.get("cache_read_input_tokens") or 0)
            + (last_usage.get("output_tokens") or 0)
        )

    if CONFIG["limit_override"]:
        info["limit"] = CONFIG["limit_override"]
    elif CONFIG["auto_detect_limit"]:
        info["limit"] = infer_limit(info["model"])
    else:
        info["limit"] = DEFAULT_CONTEXT_LIMIT

    _cache[path] = (mtime, info)
    return info


def display_name(info: dict) -> str:
    cwd = info.get("cwd")
    if cwd:
        parts = Path(cwd).parts
        if len(parts) >= 2:
            return "/".join(parts[-2:])
        return parts[-1] if parts else cwd
    return info["session_id"][:8]


def fmt_tokens(n: int) -> str:
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def fmt_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def make_bar(pct: float, width: int) -> str:
    g = CONFIG["glyphs"]
    filled = int(round(pct * width))
    filled = max(0, min(width, filled))
    return g["fill"] * filled + g["empty"] * (width - filled)


def draw(stdscr):
    curses.curs_set(0)
    try:
        curses.use_default_colors()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_YELLOW, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
    except curses.error:
        pass
    stdscr.nodelay(True)
    stdscr.timeout(int(CONFIG["refresh"] * 1000))

    while True:
        now = time.time()
        sessions = find_sessions()
        rows = []
        for path, mtime in sessions:
            info = read_session_info(path, mtime)
            if info is None:
                continue
            rows.append((path, mtime, info))

        stdscr.erase()
        h, w = stdscr.getmaxyx()

        title = f"contextbar — {len(rows)} session{'' if len(rows) == 1 else 's'}"
        try:
            stdscr.addnstr(0, 0, title, w - 1, curses.A_BOLD)
            stdscr.addnstr(1, 0, CONFIG["glyphs"]["rule"] * (w - 1), w - 1)
        except curses.error:
            pass

        # Layout widths
        max_name = max((len(display_name(r[2])) for r in rows), default=12)
        name_w = min(30, max(12, max_name))
        right_w = 26  # " 100%  100k/200k  10s ago"
        bar_w = max(6, w - name_w - right_w - 6)

        line = 2
        for path, mtime, info in rows:
            if line >= h - 1:
                try:
                    stdscr.addnstr(
                        line,
                        0,
                        f" {CONFIG['glyphs']['ellipsis']}{len(rows) - (line - 2)} more (resize terminal)",
                        w - 1,
                        curses.A_DIM,
                    )
                except curses.error:
                    pass
                break

            name = display_name(info)
            if len(name) > name_w:
                name = name[: name_w - 1] + CONFIG["glyphs"]["ellipsis"]

            tokens = info["tokens"]
            limit = info["limit"]
            pct = tokens / limit if limit else 0
            bar = make_bar(min(pct, 1.0), bar_w)
            tok_str = f"{fmt_tokens(tokens)}/{fmt_tokens(limit)}"
            age = fmt_age(max(0, now - mtime))

            warn_schema = info.get("assistant_seen") and not info.get("schema_ok")

            if warn_schema:
                color = curses.color_pair(2)
            elif pct < 0.5:
                color = curses.color_pair(1)
            elif pct < 0.85:
                color = curses.color_pair(2)
            else:
                color = curses.color_pair(3)

            try:
                col = 0
                stdscr.addnstr(line, col, f" {name:<{name_w}} ", name_w + 2)
                col += name_w + 2
                stdscr.addnstr(line, col, f"[{bar}] ", bar_w + 3, color)
                col += bar_w + 3
                if warn_schema:
                    tail = f" ?    schema?         {age}"
                else:
                    tail = f"{int(pct * 100):3d}%  {tok_str:<13} {age}"
                stdscr.addnstr(line, col, tail, max(0, w - col - 1))
            except curses.error:
                pass
            line += 1

        if not rows:
            try:
                stdscr.addnstr(3, 2, "No Claude Code sessions found.", w - 3)
            except curses.error:
                pass

        footer = f" q=quit  refresh {CONFIG['refresh']:g}s "
        try:
            stdscr.addnstr(h - 1, 0, footer, w - 1, curses.A_DIM)
        except curses.error:
            pass

        stdscr.refresh()

        try:
            ch = stdscr.getch()
        except KeyboardInterrupt:
            return
        if ch in (ord("q"), ord("Q"), 27):
            return
        # KEY_RESIZE handled implicitly by next iteration


def run_once() -> int:
    """One-shot snapshot mode. Prints one line per session and exits."""
    now = time.time()
    g = CONFIG["glyphs"]
    bar_w = 24
    for path, mtime in find_sessions():
        info = read_session_info(path, mtime)
        if info is None:
            continue
        name = display_name(info)
        tokens = info["tokens"]
        limit = info["limit"]
        pct = tokens / limit if limit else 0
        bar = make_bar(min(pct, 1.0), bar_w)
        tok_str = f"{fmt_tokens(tokens)}/{fmt_tokens(limit)}"
        age = fmt_age(max(0, now - mtime))
        warn_schema = info.get("assistant_seen") and not info.get("schema_ok")
        if warn_schema:
            print(f"{name} [{bar}] schema? {tok_str} {age}")
        else:
            print(f"{name} [{bar}] {int(pct * 100):3d}% {tok_str} {age}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="contextbar",
        description="Live multi-session context-window meter for Claude Code.",
    )
    p.add_argument(
        "--ascii",
        action="store_true",
        help="use ASCII-only glyphs (for terminals without Unicode)",
    )
    p.add_argument(
        "--limit",
        type=int,
        metavar="N",
        default=None,
        help="override context window size in tokens (disables auto-detect)",
    )
    p.add_argument(
        "--no-auto-limit",
        action="store_true",
        help="disable per-model context window auto-detection",
    )
    p.add_argument(
        "--refresh",
        type=float,
        metavar="SEC",
        default=REFRESH_SEC,
        help=f"refresh interval in seconds (default: {REFRESH_SEC})",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="print one-shot snapshot and exit (pipe-friendly)",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"contextbar {__version__}",
    )
    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    CONFIG["glyphs"] = GLYPHS_ASCII if args.ascii else GLYPHS_UNICODE
    CONFIG["limit_override"] = args.limit
    CONFIG["auto_detect_limit"] = not args.no_auto_limit and args.limit is None
    CONFIG["refresh"] = args.refresh
    CONFIG["once"] = args.once

    if args.once:
        return run_once()

    try:
        import curses as _curses  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "contextbar: the 'curses' module is unavailable on this system.\n"
            "On native Windows install the windows-curses package:\n"
            "    pip install windows-curses\n"
            "Or run contextbar inside WSL.\n"
        )
        return 2

    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    try:
        curses.wrapper(draw)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
