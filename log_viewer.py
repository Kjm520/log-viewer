"""
RPA Log Viewer — tails multiple log files with color-coded output.
Edit the CONFIG section below to change visuals or add/remove logs.
"""

import re
import time
import os
import sys
from rich.console import Console
from rich.text import Text
from config.config import PATHS

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  CONFIG — edit this section to customize                           ║
# ╚══════════════════════════════════════════════════════════════════════╝

# Each log source: (label, file_path, label_style, text_style)
#   label        — tag shown before each line
#   file_path    — absolute path to the log file
#   label_style  — rich style string for the label  (colors, bold, etc.)
#   text_style   — rich style string for the log text
LOG_SOURCES = [
    {
        "label": "Email Bot",
        "path": PATHS.EMAIL_BOT_LOG_PATH,
        "label_style": "bold cyan",
        "text_style": "white",
    },
    {
        "label": "K1 Financials",
        "path": PATHS.FINANCIALS_LOG_PATH,
        "label_style": "bold blue",
        "text_style": "white",
    },
    {
        "label": "Scooper",
        "path": PATHS.SCOOPER_LOG_PATH,
        "label_style": "bold red",
        "text_style": "white",
    },
]

# How often to poll for new lines (seconds)
POLL_INTERVAL = 0.5

# Separator between label and log text
SEPARATOR = "│ "
SEPARATOR_STYLE = "dim"

# Startup banner
BANNER_STYLE = "bold green"
BANNER = "═" * 60

# Timestamp — set to True to prepend a local timestamp to each line
SHOW_TIMESTAMP = False
TIMESTAMP_FORMAT = "%H:%M:%S"
TIMESTAMP_STYLE = "dim green"

# Pattern-based line highlighting — first match wins.
# Each entry: (regex_pattern, rich_style)
# If a log line matches the pattern, the entire line uses that style
# instead of the source's default text_style.
HIGHLIGHT_PATTERNS = [
    (r"-{3,}.*Received message.*-{3,}", "bright_green"),
    (r"Routing as DECLINE", "bold red"),
    # (r"ERROR", "bold red"),
    # (r"WARNING", "bold yellow"),
]
_COMPILED_PATTERNS = [(re.compile(p), s) for p, s in HIGHLIGHT_PATTERNS]

#
# LOGIC
#

console = Console()


def build_line(source: dict, line: str) -> Text:
    """Assemble a single styled output line."""
    parts = Text()

    if SHOW_TIMESTAMP:
        ts = time.strftime(TIMESTAMP_FORMAT)
        parts.append(f"{ts} ", style=TIMESTAMP_STYLE)

    label = source["label"]
    # Pad labels so they align
    max_label = max(len(s["label"]) for s in LOG_SOURCES)
    padded = f"[{label}]".ljust(max_label + 2)

    parts.append(padded, style=source["label_style"])
    parts.append(SEPARATOR, style=SEPARATOR_STYLE)
    text = line.rstrip("\n\r")
    style = source["text_style"]
    for pattern, pat_style in _COMPILED_PATTERNS:
        if pattern.search(text):
            style = pat_style
            break
    parts.append(text, style=style)
    return parts


class LogTailer:
    """Tracks a single log file and yields new lines."""

    def __init__(self, source: dict):
        self.source = source
        self.path = source["path"]
        self._pos = 0
        self._inode = None
        self._init_position()

    def _init_position(self):
        """Seek to end of file on startup (tail -0 behavior)."""
        try:
            stat = os.stat(self.path)
            self._pos = stat.st_size
            self._inode = self._get_inode()
        except FileNotFoundError:
            self._pos = 0

    def _get_inode(self):
        """Get file identity to detect rotation/truncation."""
        try:
            stat = os.stat(self.path)
            return (stat.st_dev, stat.st_ino, stat.st_size)
        except FileNotFoundError:
            return None

    def _was_rotated_or_truncated(self) -> bool:
        """Check if file was rotated, recreated, or truncated."""
        try:
            stat = os.stat(self.path)
            if stat.st_size < self._pos:
                return True
        except FileNotFoundError:
            return True
        return False

    def poll(self) -> list[Text]:
        """Return new styled lines since last poll."""
        lines = []
        if not os.path.exists(self.path):
            return lines

        if self._was_rotated_or_truncated():
            self._pos = 0

        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                for raw in f:
                    stripped = raw.strip()
                    if stripped:
                        lines.append(build_line(self.source, stripped))
                self._pos = f.tell()
        except (OSError, PermissionError):
            pass

        return lines


def print_banner():
    console.print(BANNER, style=BANNER_STYLE)
    console.print("  RPA Log Viewer", style=BANNER_STYLE)
    console.print(BANNER, style=BANNER_STYLE)
    for src in LOG_SOURCES:
        status = "OK" if os.path.exists(src["path"]) else "NOT FOUND"
        tag = Text()
        tag.append(f"  [{src['label']}]", style=src["label_style"])
        tag.append(f"  {src['path']}  ", style="dim")
        tag.append(f"({status})", style="green" if status == "OK" else "red")
        console.print(tag)
    console.print(BANNER, style=BANNER_STYLE)
    console.print()


def main():
    print_banner()
    tailers = [LogTailer(src) for src in LOG_SOURCES]

    try:
        while True:
            for tailer in tailers:
                for line in tailer.poll():
                    console.print(line)
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        console.print("\n[dim]Viewer stopped.[/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main()
