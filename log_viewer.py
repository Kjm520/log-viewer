"""
Log Viewer — tails multiple log files in a tkinter GUI.
Edit the CONFIG section below to change visuals or add/remove logs.
"""

import re
import os
import sys
import ctypes
import tkinter as tk
from tkinter import font as tkfont
from config.config import PATHS

ctypes.windll.shcore.SetProcessDpiAwareness(2)

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  CONFIG — edit this section to customize                             ║
# ╚══════════════════════════════════════════════════════════════════════╝

LOG_SOURCES = [
    {
        "label": "Email Bot",
        "path": PATHS.EMAIL_BOT_LOG_PATH,
        "label_color": "#d9ead3",
        "text_color": "#cccccc",
    },
    {
        "label": "K1 Financials",
        "path": PATHS.FINANCIALS_LOG_PATH,
        "label_color": "#5599ff",
        "text_color": "#cccccc",
    },
    {
        "label": "Scooper",
        "path": PATHS.SCOOPER_LOG_PATH,
        "label_color": "#ff5555",
        "text_color": "#cccccc",
    },
]

# How often to poll for new lines (milliseconds)
POLL_INTERVAL_MS = 500

# Separator between label and log text
SEPARATOR = " │ "

# Pattern-based line highlighting — first match wins.
HIGHLIGHT_PATTERNS = [
    (r"-{3,}.*Received message.*-{3,}", "#55ff55"),
    (r"Routing as DECLINE", "#ff3333"),
]
_COMPILED_PATTERNS = [(re.compile(p), c) for p, c in HIGHLIGHT_PATTERNS]

# Window settings
WINDOW_TITLE = "Log Viewer"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700
BG_COLOR = "#1e1e1e"
FONT_FAMILY = "Consolas"
FONT_SIZE = 10
MAX_LINES = 200

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  LOGIC                                                               ║
# ╚══════════════════════════════════════════════════════════════════════╝


class LogTailer:
    """Tracks a single log file and yields new lines."""

    def __init__(self, source: dict):
        self.source = source
        self.path = source["path"]
        self._pos = 0
        self._init_position()

    def _init_position(self):
        try:
            self._pos = os.stat(self.path).st_size
        except FileNotFoundError:
            self._pos = 0

    def _was_rotated_or_truncated(self) -> bool:
        try:
            if os.stat(self.path).st_size < self._pos:
                return True
        except FileNotFoundError:
            return True
        return False

    def poll(self) -> list[tuple[dict, str]]:
        """Return new (source, text) pairs since last poll."""
        results = []
        if not os.path.exists(self.path):
            return results

        if self._was_rotated_or_truncated():
            self._pos = 0

        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._pos)
                for raw in f:
                    stripped = raw.strip()
                    if stripped:
                        results.append((self.source, stripped))
                self._pos = f.tell()
        except (OSError, PermissionError):
            pass

        return results


class LogViewerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg=BG_COLOR)
        self.root.minsize(600, 300)
        _base = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
        self.root.iconbitmap(os.path.join(_base, "assets", "icons", "logs.ico"))

        # Dark title bar (Windows 10/11)
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

        self._auto_scroll = True
        self._max_label = max(len(s["label"]) for s in LOG_SOURCES)

        self._setup_widgets()
        self._setup_tags()

        self.tailers = [LogTailer(src) for src in LOG_SOURCES]

        self._poll()

    def _setup_widgets(self):
        header_bg = "#252526"
        accent = "#007acc"

        # ── Header ──────────────────────────────────────────────
        header = tk.Frame(self.root, bg=header_bg)
        header.pack(fill=tk.X)

        # Accent stripe along the top
        tk.Frame(header, bg=accent, height=2).pack(fill=tk.X)

        # Title + status cards on one row
        title_row = tk.Frame(header, bg=header_bg)
        title_row.pack(fill=tk.X, padx=16, pady=(10, 10))
        tk.Label(
            title_row, text="Log Viewer", bg=header_bg, fg="#e0e0e0",
            font=tkfont.Font(family="Segoe UI", size=14, weight="bold"),
        ).pack(side=tk.LEFT)

        cards_row = tk.Frame(title_row, bg=header_bg)
        cards_row.pack(side=tk.RIGHT)

        self._status_dots = []
        for src in LOG_SOURCES:
            exists = os.path.exists(src["path"])
            card = tk.Frame(cards_row, bg="#2d2d2d", padx=10, pady=5)
            card.pack(side=tk.LEFT, padx=(0, 8))

            dot = tk.Label(
                card, text="●", bg="#2d2d2d",
                fg="#55cc55" if exists else "#ff5555",
                font=tkfont.Font(family="Segoe UI", size=9),
            )
            dot.pack(side=tk.LEFT)

            tk.Label(
                card, text=f"  {src['label']}", bg="#2d2d2d",
                fg=src["label_color"],
                font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
            ).pack(side=tk.LEFT)

            tk.Label(
                card, text=f"  {os.path.basename(src['path'])}", bg="#2d2d2d",
                fg="#888888",
                font=tkfont.Font(family="Segoe UI", size=8),
            ).pack(side=tk.LEFT)

            self._status_dots.append((dot, src))

        # Bottom accent stripe on header
        tk.Frame(header, bg=accent, height=1).pack(fill=tk.X)

        # ── Log text area ───────────────────────────────────────
        self.text = tk.Text(
            self.root,
            bg=BG_COLOR,
            fg="#cccccc",
            font=tkfont.Font(family=FONT_FAMILY, size=FONT_SIZE),
            wrap=tk.WORD,
            state=tk.DISABLED,
            cursor="arrow",
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=4,
        )
        self.text.pack(fill=tk.BOTH, expand=True)

        # Pause auto-scroll when user scrolls up, resume when at bottom
        self.text.bind("<MouseWheel>", self._on_scroll)
        self.text.bind("<Button-4>", self._on_scroll)
        self.text.bind("<Button-5>", self._on_scroll)

        # ── Status bar ──────────────────────────────────────────
        self.status_frame = tk.Frame(self.root, bg="#2d2d2d", height=24)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_label = tk.Label(
            self.status_frame,
            text="",
            bg="#2d2d2d",
            fg="#888888",
            font=tkfont.Font(family=FONT_FAMILY, size=FONT_SIZE - 1),
            anchor=tk.W,
            padx=8,
        )
        self.status_label.pack(fill=tk.X)

    def _setup_tags(self):
        self.text.tag_configure("separator", foreground="#555555")

        for src in LOG_SOURCES:
            tag = self._label_tag(src)
            self.text.tag_configure(tag, foreground=src["label_color"])
            text_tag = f"text_{src['label'].replace(' ', '_')}"
            self.text.tag_configure(text_tag, foreground=src["text_color"])

        for i, (_, color) in enumerate(_COMPILED_PATTERNS):
            self.text.tag_configure(f"hl_{i}", foreground=color)

    def _label_tag(self, source: dict) -> str:
        return f"label_{source['label'].replace(' ', '_')}"

    def _append(self, text: str, tag: str):
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, text, tag)
        self.text.configure(state=tk.DISABLED)

    def _append_line(self, source: dict, line: str):
        label = source["label"]
        padded = f"[{label}]".ljust(self._max_label + 2)

        # Determine text color — highlight patterns override
        text_tag = f"text_{label.replace(' ', '_')}"
        for i, (pattern, _) in enumerate(_COMPILED_PATTERNS):
            if pattern.search(line):
                text_tag = f"hl_{i}"
                break

        self._append(padded, self._label_tag(source))
        self._append(SEPARATOR, "separator")
        self._append(line + "\n", text_tag)

        self._trim_lines()

        if self._auto_scroll:
            self.text.see(tk.END)

    def _trim_lines(self):
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > MAX_LINES:
            overshoot = line_count - MAX_LINES
            self.text.configure(state=tk.NORMAL)
            self.text.delete("1.0", f"{overshoot}.0")
            self.text.configure(state=tk.DISABLED)

    def _on_scroll(self, _event):
        self.root.after(50, self._check_scroll_position)

    def _check_scroll_position(self):
        # If scrollbar is at the bottom, re-enable auto-scroll
        self._auto_scroll = self.text.yview()[1] >= 0.99

    def _update_status(self):
        for dot, src in self._status_dots:
            exists = os.path.exists(src["path"])
            dot.configure(fg="#55cc55" if exists else "#ff5555")

        sources = []
        for src in LOG_SOURCES:
            exists = os.path.exists(src["path"])
            marker = "●" if exists else "○"
            sources.append(f"{marker} {src['label']}")
        scroll_indicator = "AUTO-SCROLL" if self._auto_scroll else "PAUSED"
        self.status_label.configure(text=f"  {' │ '.join(sources)} │ {scroll_indicator}")

    def _poll(self):
        for tailer in self.tailers:
            for source, line in tailer.poll():
                self._append_line(source, line)

        self._update_status()
        self.root.after(POLL_INTERVAL_MS, self._poll)

    def run(self):
        self.root.mainloop()


def main():
    app = LogViewerApp()
    app.run()


if __name__ == "__main__":
    main()
