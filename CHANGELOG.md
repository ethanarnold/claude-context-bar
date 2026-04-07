# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-04-07

Initial public release.

### Added
- Live curses TUI dashboard with one row per active Claude Code session,
  showing project name, colored usage bar, percentage, token counts, and
  age since last update.
- Per-row color thresholds: green `< 50%`, yellow `50–85%`, red `≥ 85%`.
- Per-model context-window auto-detection via `MODEL_LIMITS` regex table,
  including the 1M-context Sonnet beta variants.
- `--ascii` flag for terminals without Unicode block-glyph support.
- `--limit N` flag to override the context window in tokens.
- `--no-auto-limit` flag to disable per-model auto-detection.
- `--refresh SEC` flag to change the refresh interval.
- `--once` flag for a one-shot, pipe-friendly snapshot.
- `--version` flag.
- Schema-mismatch warning row: if an `assistant` entry is parsed but no
  recognised `usage` fields are present, the row is colored yellow and
  labelled `schema?` instead of silently rendering 0%.
- Friendly stderr message on native Windows when the `curses` module is
  unavailable, pointing at `pip install windows-curses` or WSL.
- `pyproject.toml` packaging metadata with a `contextbar` console script
  and an optional `[windows]` extra.

[0.1.0]: https://github.com/ethanarnold/claude-context-bar/releases/tag/v0.1.0
