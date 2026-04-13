"""
Log Viewer — tails multiple log files in a PySide6 GUI.
Edit the CONFIG section below to change visuals or add/remove logs.
"""

import re
import os
import sys
import ctypes
from collections import deque

from PySide6.QtCore import Qt, QTimer, QSize, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QTextCharFormat, QTextCursor,
    QShortcut, QKeySequence, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QFrame, QPushButton, QLineEdit, QColorDialog,
)

from config.config import PATHS

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  CONFIG                                                              ║
# ╚══════════════════════════════════════════════════════════════════════╝

LOG_SOURCES = [
    {"label": "Email Bot",     "path": PATHS.EMAIL_BOT_LOG_PATH,  "label_color": "#8fd68a", "text_color": "#cccccc"},
    {"label": "K1 Financials", "path": PATHS.FINANCIALS_LOG_PATH, "label_color": "#5599ff", "text_color": "#cccccc"},
    {"label": "Scooper",       "path": PATHS.SCOOPER_LOG_PATH,    "label_color": "#ff6b6b", "text_color": "#cccccc"},
]

POLL_INTERVAL_MS = 500
SEPARATOR = " │ "

HIGHLIGHT_PATTERNS = [
    (r"-{3,}.*Received message.*-{3,}", "#55ff55"),
    (r"Routing as DECLINE", "#ff3333"),
]
_COMPILED_PATTERNS = [(re.compile(p), c) for p, c in HIGHLIGHT_PATTERNS]

WINDOW_TITLE = "Log Viewer"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 760
WINDOW_OPACITY = 0.6  # opacity used when transparency is toggled ON (Ctrl+T). Startup is always 1.0.

# Palette
BG = "#1a1a1c"
HEADER_BG = "#232327"
CARD_BG = "#2a2a2f"
CARD_HOVER_BG = "#34343a"
CARD_DISABLED_BG = "#1f1f22"
STATUSBAR_BG = "#1d1d20"
BORDER = "#35353a"
MUTED = "#888888"
TEXT = "#e0e0e0"
ACCENT = "#4f9fff"
ACCENT_DIM = "#2a5a9a"

FONT_FAMILY = "Cascadia Mono"
FONT_FALLBACK = "Consolas"
FONT_SIZE = 10
UI_FONT = "Segoe UI"
MAX_LINES = 500
MAX_LINES_PER_POLL = 2000  # cap backlog flush on resume or first read
CLEAR_ICON_SIZE = 14

# ╔══════════════════════════════════════════════════════════════════════╗
# ║  TAILER                                                              ║
# ╚══════════════════════════════════════════════════════════════════════╝


class LogTailer:
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
                    if len(results) >= MAX_LINES_PER_POLL:
                        # Cap backlog: skip remainder, resume tailing from here
                        f.seek(0, os.SEEK_END)
                        break
                self._pos = f.tell()
        except (OSError, PermissionError):
            pass
        return results


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  WIDGETS                                                             ║
# ╚══════════════════════════════════════════════════════════════════════╝


class StatusCard(QFrame):
    """Clickable status card. Left-click toggles visibility, right-click changes color."""
    toggled = Signal(object)
    color_changed = Signal(object)  # emits self

    def __init__(self, src: dict):
        super().__init__()
        self.src = src
        self.enabled = True
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("statusCard")
        self._build()
        self._apply_style()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        self.dot = QLabel("●")
        self.dot.setFont(QFont(UI_FONT, 9))
        lay.addWidget(self.dot)

        self.label = QLabel(self.src["label"])
        self.label.setFont(QFont(UI_FONT, 9, QFont.Bold))
        lay.addWidget(self.label)

        self.name = QLabel(os.path.basename(self.src["path"]))
        self.name.setFont(QFont(UI_FONT, 8))
        lay.addWidget(self.name)

    def _apply_style(self):
        if self.enabled:
            bg = CARD_BG
            dot_color = "#55cc55" if os.path.exists(self.src["path"]) else "#ff5555"
            label_color = self.src["label_color"]
            name_color = MUTED
            deco = ""
        else:
            bg = CARD_DISABLED_BG
            dot_color = "#555555"
            label_color = "#555555"
            name_color = "#3f3f42"
            deco = "text-decoration: line-through;"

        self.setStyleSheet(f"""
            QFrame#statusCard {{
                background-color: {bg};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
            QFrame#statusCard:hover {{
                background-color: {CARD_HOVER_BG if self.enabled else CARD_DISABLED_BG};
                border-color: {ACCENT_DIM if self.enabled else BORDER};
            }}
        """)
        self.dot.setStyleSheet(f"color: {dot_color}; background: transparent; border: none;")
        self.label.setStyleSheet(f"color: {label_color}; background: transparent; border: none; {deco}")
        self.name.setStyleSheet(f"color: {name_color}; background: transparent; border: none; {deco}")

    def refresh_dot(self):
        if not self.enabled:
            return
        exists = os.path.exists(self.src["path"])
        self.dot.setStyleSheet(
            f"color: {'#55cc55' if exists else '#ff5555'}; background: transparent; border: none;"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.enabled = not self.enabled
            self._apply_style()
            self.toggled.emit(self)
        elif event.button() == Qt.RightButton:
            self._open_color_picker()
        super().mousePressEvent(event)

    def _open_color_picker(self):
        current = QColor(self.src["label_color"])
        dlg = QColorDialog(current, self)
        dlg.setWindowTitle(f"Title color — {self.src['label']}")
        dlg.setOption(QColorDialog.DontUseNativeDialog, False)
        if dlg.exec():
            chosen = dlg.currentColor()
            if chosen.isValid():
                self.src["label_color"] = chosen.name()
                self._apply_style()
                self.color_changed.emit(self)


def _load_icon(path: str | None) -> QIcon | None:
    if not path:
        return None
    if not os.path.exists(path):
        print(f"[log_viewer] WARN: missing icon asset: {path}", file=sys.stderr)
        return None
    return QIcon(QPixmap(path))


class IconButton(QPushButton):
    def __init__(self, icon_path: str | None = None, hover_icon_path: str | None = None,
                 glyph: str | None = None, tooltip: str = "",
                 icon_size: int = CLEAR_ICON_SIZE):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setFixedHeight(32)
        self.setMinimumWidth(32)
        self._icon_idle = _load_icon(icon_path)
        self._icon_hover = _load_icon(hover_icon_path) or self._icon_idle
        if self._icon_idle:
            self.setIcon(self._icon_idle)
            self.setIconSize(QSize(icon_size, icon_size))
        if glyph:
            self.setText(glyph)
            self.setFont(QFont(UI_FONT, 11, QFont.Bold))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {CARD_BG};
                color: {MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: {CARD_HOVER_BG};
                color: {TEXT};
                border-color: {ACCENT_DIM};
            }}
            QPushButton:pressed {{
                background-color: {CARD_DISABLED_BG};
            }}
        """)

    def set_active(self, active: bool):
        if self._icon_idle:
            self.setIcon(self._icon_hover if active else self._icon_idle)

    def enterEvent(self, event):
        if self._icon_idle and self._icon_hover:
            self.setIcon(self._icon_hover)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._icon_idle and not self.property("persistent_active"):
            self.setIcon(self._icon_idle)
        super().leaveEvent(event)


class SearchBar(QFrame):
    changed = Signal(str)
    closed = Signal()

    def __init__(self, icon_path: str | None = None):
        super().__init__()
        self._icon_path = icon_path
        self.setObjectName("searchBar")
        self.setStyleSheet(f"""
            QFrame#searchBar {{
                background-color: {HEADER_BG};
                border-bottom: 1px solid {BORDER};
            }}
            QLineEdit {{
                background-color: {CARD_BG};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                selection-background-color: {ACCENT_DIM};
            }}
            QLineEdit:focus {{
                border-color: {ACCENT};
            }}
            QLabel {{
                color: {MUTED};
                background: transparent;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(8)

        icon = QLabel()
        if self._icon_path and os.path.exists(self._icon_path):
            icon.setPixmap(QPixmap(self._icon_path).scaled(
                14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("🔎")
            icon.setFont(QFont(UI_FONT, 10))
        lay.addWidget(icon)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Filter visible lines…  (Esc to close)")
        self.edit.setFont(QFont(UI_FONT, 10))
        self.edit.textChanged.connect(self.changed.emit)
        lay.addWidget(self.edit, 1)

        close = IconButton(glyph="✕", tooltip="Close (Esc)")
        close.setFixedWidth(32)
        close.clicked.connect(self.closed.emit)
        lay.addWidget(close)

        self.setVisible(False)

    def open_bar(self):
        self.setVisible(True)
        self.edit.setFocus()
        self.edit.selectAll()


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  MAIN WINDOW                                                         ║
# ╚══════════════════════════════════════════════════════════════════════╝


class LogViewerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(720, 360)

        _base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        self._icons_dir = os.path.join(_base, "assets", "icons")
        self._os_icons = os.path.join(self._icons_dir, "os_icons")
        self._btn_icons = os.path.join(self._icons_dir, "button_icons")
        self.setWindowIcon(QIcon(os.path.join(self._os_icons, "logs.ico")))

        self._auto_scroll = True
        self._paused = False
        self._transparent = False
        self._filter_text = ""
        self._suppress_scroll_update = False
        self._max_label = max(len(s["label"]) for s in LOG_SOURCES)
        self._lines: deque[tuple[dict, str]] = deque(maxlen=MAX_LINES)
        self._enabled_sources: set[str] = {s["label"] for s in LOG_SOURCES}

        self._build_ui()
        self._wire_shortcuts()
        self._apply_dark_titlebar()

        self.tailers = [LogTailer(src) for src in LOG_SOURCES]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_INTERVAL_MS)

        self._filter_debounce = QTimer(self)
        self._filter_debounce.setSingleShot(True)
        self._filter_debounce.setInterval(120)
        self._filter_debounce.timeout.connect(self._rerender)

        self._update_status()

    def _apply_dark_titlebar(self):
        try:
            hwnd = int(self.winId())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value),
            )
        except Exception:
            pass

    def _wire_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._clear)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._open_search)
        QShortcut(QKeySequence("Escape"), self, activated=self._close_search)
        QShortcut(QKeySequence("Ctrl+P"), self, activated=self._toggle_pause)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._toggle_opacity)

    # ── UI construction ────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_divider())
        root.addWidget(self._build_header())
        root.addWidget(self._make_divider())

        # Search bar (hidden by default)
        self.search = SearchBar(icon_path=os.path.join(self._btn_icons, "search_888888.png"))
        self.search.changed.connect(self._on_filter_changed)
        self.search.closed.connect(self._close_search)
        root.addWidget(self.search)

        # Log area
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.NoWrap)
        self.text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG};
                color: {TEXT};
                border: none;
                padding: 8px 12px;
                selection-background-color: {ACCENT_DIM};
            }}
            QScrollBar:vertical {{
                background: {BG};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {CARD_BG};
                border-radius: 6px;
                min-height: 30px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {CARD_HOVER_BG};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: {BG};
                height: 12px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {CARD_BG};
                border-radius: 6px;
                min-width: 30px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {CARD_HOVER_BG};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
        """)
        self.text.setFont(self._mono_font())
        self.text.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.text, 1)

        root.addWidget(self._build_statusbar())

    def _make_divider(self) -> QWidget:
        d = QWidget()
        d.setFixedHeight(1)
        d.setStyleSheet(f"background-color: {BORDER};")
        return d

    def _mono_font(self) -> QFont:
        f = QFont(FONT_FAMILY, FONT_SIZE)
        if not f.exactMatch():
            f = QFont(FONT_FALLBACK, FONT_SIZE)
        return f

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(f"background-color: {HEADER_BG};")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        brand = QLabel()
        logo_path = os.path.join(self._os_icons, "logs.ico")
        if os.path.exists(logo_path):
            brand.setPixmap(QPixmap(logo_path).scaled(
                20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(brand)

        wordmark = QLabel("Log Viewer")
        wordmark.setFont(QFont(UI_FONT, 11, QFont.DemiBold))
        wordmark.setStyleSheet(f"color: {TEXT}; background: transparent;")
        lay.addWidget(wordmark)

        lay.addStretch(1)

        self._cards: list[StatusCard] = []
        for src in LOG_SOURCES:
            card = StatusCard(src)
            card.toggled.connect(self._on_source_toggled)
            card.color_changed.connect(lambda _c: self._rerender())
            self._cards.append(card)
            lay.addWidget(card)

        lay.addSpacing(8)

        self.opacity_btn = IconButton(
            icon_path=os.path.join(self._btn_icons, "opacity_888888.png"),
            hover_icon_path=os.path.join(self._btn_icons, "opacity_E0E0E0.png"),
            tooltip="Toggle transparency (Ctrl+T)",
        )
        self.opacity_btn.clicked.connect(self._toggle_opacity)
        self.opacity_btn.setProperty("persistent_active", self._transparent)
        self.opacity_btn.set_active(self._transparent)
        lay.addWidget(self.opacity_btn)

        self.search_btn = IconButton(
            icon_path=os.path.join(self._btn_icons, "search_888888.png"),
            hover_icon_path=os.path.join(self._btn_icons, "search_E0E0E0.png"),
            tooltip="Search (Ctrl+F)",
        )
        self.search_btn.clicked.connect(self._open_search)
        lay.addWidget(self.search_btn)

        self.pause_btn = IconButton(
            icon_path=os.path.join(self._btn_icons, "pause_888888.png"),
            hover_icon_path=os.path.join(self._btn_icons, "pause_E0E0E0.png"),
            tooltip="Pause (Ctrl+P)",
        )
        self.pause_btn.clicked.connect(self._toggle_pause)
        lay.addWidget(self.pause_btn)

        self.clear_btn = IconButton(
            icon_path=os.path.join(self._btn_icons, "clear_888888.png"),
            hover_icon_path=os.path.join(self._btn_icons, "clear_E0E0E0.png"),
            tooltip="Clear (Ctrl+L)",
        )
        self.clear_btn.clicked.connect(self._clear)
        lay.addWidget(self.clear_btn)

        return header

    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"""
            QWidget {{
                background-color: {STATUSBAR_BG};
                border-top: 1px solid {BORDER};
            }}
            QLabel {{ background: transparent; }}
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(16)

        self.status_left = QLabel()
        self.status_left.setFont(QFont(UI_FONT, 8))
        self.status_left.setStyleSheet(f"color: {MUTED};")
        lay.addWidget(self.status_left)

        lay.addStretch(1)

        self.status_right = QLabel()
        self.status_right.setFont(QFont(UI_FONT, 8))
        self.status_right.setStyleSheet(f"color: {MUTED};")
        lay.addWidget(self.status_right)

        return bar

    # ── Event handlers ─────────────────────────────────────────────

    def _on_source_toggled(self, card: StatusCard):
        if card.enabled:
            self._enabled_sources.add(card.src["label"])
        else:
            self._enabled_sources.discard(card.src["label"])
        self._rerender()

    def _on_filter_changed(self, text: str):
        self._filter_text = text.lower()
        self._filter_debounce.start()

    def _on_scroll(self, _value):
        if self._suppress_scroll_update:
            return
        sb = self.text.verticalScrollBar()
        self._auto_scroll = sb.value() >= sb.maximum() - 2
        self._update_status()

    def _open_search(self):
        self.search.open_bar()

    def _close_search(self):
        if self.search.isVisible():
            self._filter_text = ""
            self.search.setVisible(False)
            self.search.edit.clear()
            self._rerender()
            self.text.setFocus()

    def _toggle_opacity(self):
        self._transparent = not self._transparent
        self.setWindowOpacity(WINDOW_OPACITY if self._transparent else 1.0)
        self.opacity_btn.setProperty("persistent_active", self._transparent)
        self.opacity_btn.set_active(self._transparent)

    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_btn.setProperty("persistent_active", self._paused)
        self.pause_btn.set_active(self._paused)
        self.pause_btn.setToolTip("Resume (Ctrl+P)" if self._paused else "Pause (Ctrl+P)")
        self._update_status()

    def _clear(self):
        self._lines.clear()
        self.text.clear()
        self._auto_scroll = True
        self._update_status()

    # ── Rendering ──────────────────────────────────────────────────

    def _visible(self, source: dict, line: str) -> bool:
        if source["label"] not in self._enabled_sources:
            return False
        if self._filter_text and self._filter_text not in line.lower():
            return False
        return True

    def _append_to_widget(self, source: dict, line: str):
        label = source["label"]
        padded = f"[{label}]".ljust(self._max_label + 2)

        text_color = source["text_color"]
        for pattern, color in _COMPILED_PATTERNS:
            if pattern.search(line):
                text_color = color
                break

        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(padded, self._fmt(source["label_color"], bold=True))
        cursor.insertText(SEPARATOR, self._fmt("#4a4a4f"))
        cursor.insertText(line + "\n", self._fmt(text_color))

        if self._auto_scroll:
            sb = self.text.verticalScrollBar()
            self._suppress_scroll_update = True
            sb.setValue(sb.maximum())
            self._suppress_scroll_update = False

    def _rerender(self):
        self._suppress_scroll_update = True
        self.text.setUpdatesEnabled(False)
        try:
            self.text.clear()
            for src, line in self._lines:
                if self._visible(src, line):
                    self._append_to_widget(src, line)
        finally:
            self.text.setUpdatesEnabled(True)
            self._suppress_scroll_update = False
        self._update_status()

    def _fmt(self, color: str, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        f = self._mono_font()
        f.setBold(bold)
        fmt.setFont(f)
        return fmt

    def _update_status(self):
        for card in self._cards:
            card.refresh_dot()

        total = len(self._lines)
        visible = sum(1 for s, l in self._lines if self._visible(s, l))
        enabled = len(self._enabled_sources)

        left = f"  {visible:,} visible  │  {total:,} buffered  │  {enabled}/{len(LOG_SOURCES)} sources"
        if self._filter_text:
            left += f"  │  filter: \"{self._filter_text}\""
        self.status_left.setText(left)

        state = []
        state.append("PAUSED" if self._paused else "LIVE")
        state.append("AUTO-SCROLL" if self._auto_scroll else "SCROLL-LOCK")
        self.status_right.setText("  │  ".join(state) + "  ")

    # ── Poll loop ──────────────────────────────────────────────────

    def _poll(self):
        if self._paused:
            self._update_status()
            return

        new_lines = []
        for tailer in self.tailers:
            new_lines.extend(tailer.poll())

        for source, line in new_lines:
            self._lines.append((source, line))
            if self._visible(source, line):
                self._append_to_widget(source, line)

        # If buffer trimmed but display still holds more than MAX_LINES, rerender
        if self.text.document().blockCount() > MAX_LINES + 50:
            self._rerender()

        self._update_status()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = LogViewerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
