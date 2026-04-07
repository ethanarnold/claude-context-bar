# claude-context-bar

A live, multi-session context-window meter for [Claude Code](https://docs.claude.com/en/docs/claude-code).

## What it does

`contextbar` watches every session file under `~/.claude/projects/` and shows a
live TUI dashboard with one row per active Claude Code session: project name,
colored usage bar, percentage, token counts, and time since the session was
last updated. It refreshes once per second, depends only on the Python
standard library, and ships as a single file.

## Install

**From GitHub (recommended):**

```bash
pip install git+https://github.com/ethanarnold/claude-context-bar.git
```

**Native Windows (adds `windows-curses`):**

```bash
pip install "git+https://github.com/ethanarnold/claude-context-bar.git#egg=claude-context-bar[windows]"
```

**No-install one-liner:**

```bash
curl -O https://raw.githubusercontent.com/ethanarnold/claude-context-bar/main/contextbar.py
python3 contextbar.py
```

## Usage

```text
contextbar [--ascii] [--limit N] [--no-auto-limit]
           [--refresh SEC] [--once] [--version]
```

| Flag              | Example                          | Effect |
|-------------------|----------------------------------|--------|
| _(no flags)_      | `contextbar`                     | Live TUI dashboard. Press `q` to quit. |
| `--once`          | `contextbar --once`              | Print one snapshot line per session and exit. Pipe-friendly. |
| `--ascii`         | `contextbar --ascii`             | Use ASCII glyphs (`#`/`-`) instead of Unicode block characters. |
| `--limit N`       | `contextbar --limit 1000000`     | Override the context window in tokens. Disables auto-detect. |
| `--no-auto-limit` | `contextbar --no-auto-limit`     | Disable per-model context window detection; use the 200k default. |
| `--refresh SEC`   | `contextbar --refresh 0.5`       | Change the refresh interval (default: 1.0s). |
| `--version`       | `contextbar --version`           | Print version and exit. |

Combine `--once --ascii` for clean piping:

```bash
contextbar --once --ascii | head -3
```

## How it works

Claude Code stores each session as a JSON-Lines file under
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. `contextbar` walks
those files and, for each one, scans entries of the form:

```json
{"type": "assistant", "message": {"model": "claude-...", "usage": { ... }}}
```

The token count for a session is the sum of the four token fields in the
**most recent** `usage` object:

- `input_tokens`
- `cache_creation_input_tokens`
- `cache_read_input_tokens`
- `output_tokens`

The model name is read from `message.model` on the same entries and is used
to pick the right context window via the regex table in `MODEL_LIMITS`.

## Color thresholds

| Usage      | Color  |
|------------|--------|
| `< 50%`    | Green  |
| `50%–85%`  | Yellow |
| `≥ 85%`    | Red    |
| schema mismatch | Yellow with `schema?` label |

## Caveats

- The Claude Code session file format is **undocumented and unofficial**. If
  it changes, the bar may render `0%` or display a yellow `schema?` warning
  on affected rows. Open an issue if you see this.
- Model auto-detection is regex-based and only knows about `opus`, `sonnet`,
  `haiku`, and the 1M-context Sonnet beta. Use `--limit` for anything else.
- The TUI uses Unicode block glyphs by default. On terminals that can't
  render them, pass `--ascii`.
- Reads files only — `contextbar` never writes to or modifies your Claude
  Code sessions.

## Requirements

- Python **3.9+**
- A `curses`-capable terminal:
  - macOS / Linux / WSL: built in
  - Native Windows: `pip install windows-curses` (or use the `[windows]`
    install extra above)
- Claude Code installed and run at least once, so that
  `~/.claude/projects/` exists

## Development

```bash
git clone https://github.com/ethanarnold/claude-context-bar.git
cd claude-context-bar
python3 contextbar.py
```

Single-file project. No build step, no dependencies.

## License

[MIT](LICENSE) © 2026 Ethan

## Disclaimer

Not affiliated with Anthropic. "Claude" and "Claude Code" are trademarks of
Anthropic. This project depends on an undocumented file format and may break
without warning when Claude Code is updated.
