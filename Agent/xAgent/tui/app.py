from __future__ import annotations

import re
import sys
import time
import unicodedata
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from collections.abc import Iterable

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.events import Click
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    RichLog,
    Select,
    Static,
)
from textual.widgets._header import HeaderIcon
from textual.widgets.option_list import Option

from core.agent import ToolAgent
from core.config import (
    DEFAULT_MAX_TOOL_ROUNDS,
    MAX_MAX_TOOL_ROUNDS,
    MIN_MAX_TOOL_ROUNDS,
    PROJECT_ROOT,
    WORKSPACE_ROOT,
    clear_chat_history_file,
    clamp_max_tool_rounds,
    ensure_project_config,
    init_runtime_paths,
    load_chat_history,
    load_config,
    resolve_max_tool_rounds,
    resolve_saved_theme,
    save_chat_history,
    save_ui_settings,
)
from core.context_compact import format_tokens_k
from core.mcp_client import shutdown_mcp, start_mcp_async
from core.schemas import tool_names
from core.sessions import list_sessions, load_session, save_session
from core.slash import filter_commands, help_text, resolve_command
from tui.i18n import DEFAULT_LANG, i18n
from tui.panels import ConfigCreatedScreen, ResumeSessionScreen
from tui.themes import CUSTOM_THEMES, DEFAULT_THEME

# 标签列固定显示宽度（两字中文 = 4 列）
_LABEL_COLS = 4
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

# 对话标签 kind → 主题色变量名（切换主题时整表跟随）
_LABEL_THEME_KEYS: dict[str, str] = {
    "user": "foreground",
    "assistant": "success",
    "tool": "secondary",
    "result": "primary",
    "system": "secondary-muted",
    "warn": "warning",
    "error": "error",
    "log": "secondary-muted",
}


def _display_width(text: str) -> int:
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return width


def _pad_label(label: str, cols: int = _LABEL_COLS) -> str:
    pad = max(cols - _display_width(label), 0)
    return label + (" " * pad)


def _trim_url(url: str) -> str:
    return url.rstrip(".,;:!?)]}>\"'")


def _linkify_rich(text: str) -> str:
    """把 http(s) URL 转成 Rich 可点击 [link=...] 标记。"""
    parts: list[str] = []
    last = 0
    for match in _URL_RE.finditer(text):
        parts.append(escape(text[last : match.start()]))
        raw = match.group(0)
        url = _trim_url(raw)
        trailing = raw[len(url) :]
        parts.append(f"[link={url}]{escape(url)}[/link]")
        if trailing:
            parts.append(escape(trailing))
        last = match.end()
    parts.append(escape(text[last:]))
    return "".join(parts)


def _format_history_line(kind: str, text: str) -> str:
    body = _linkify_rich(text)
    label = i18n.label(kind)
    # 历史窗用固定色，避免依赖 App 主题变量解析时机
    colors = {
        "user": "#ebe4d8",
        "assistant": "#9aaf8f",
        "tool": "#8fa3b0",
        "result": "#c4a574",
        "system": "#9a9288",
        "warn": "#c9a227",
        "error": "#c97b7b",
        "log": "#9a9288",
    }
    color = colors.get(kind, colors["log"])
    head = escape(_pad_label(label))
    return f"[bold {color}]{head}[/bold {color}][dim]│[/dim] {body}"


class HistoryBrowserScreen(ModalScreen[None]):
    """独立历史浏览窗：可查看全部记录并按关键词查询。"""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
    ]

    CSS = """
    HistoryBrowserScreen {
        align: center middle;
    }

    #hist-panel {
        width: 90%;
        height: 85%;
        background: $surface;
        border: solid $primary;
        padding: 1 1;
    }

    #hist-title {
        text-style: bold;
        color: $primary;
        height: 1;
        margin-bottom: 1;
    }

    #hist-toolbar {
        height: 3;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    #hist-q {
        width: 1fr;
        margin-right: 1;
    }

    #hist-go, #hist-close {
        min-width: 10;
        margin-right: 1;
    }

    #hist-close {
        margin-right: 0;
    }

    #hist-meta {
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }

    #hist-log {
        height: 1fr;
        border: solid $foreground 12%;
        background: $panel-darken-1;
        padding: 1 1;
    }
    """

    def __init__(self, records: list[dict], query: str = "") -> None:
        super().__init__()
        self._records = list(records)
        self._query = query

    def compose(self) -> ComposeResult:
        with Vertical(id="hist-panel"):
            yield Label(i18n.t("history_title"), id="hist-title")
            with Horizontal(id="hist-toolbar"):
                yield Input(
                    value=self._query,
                    placeholder=i18n.t("search_placeholder"),
                    id="hist-q",
                )
                yield Button(i18n.t("search_history"), id="hist-go", compact=True)
                yield Button(i18n.t("history_close"), id="hist-close", compact=True)
            yield Static("", id="hist-meta")
            yield RichLog(
                id="hist-log",
                markup=True,
                wrap=True,
                highlight=False,
                auto_scroll=False,
            )

    def on_mount(self) -> None:
        self._render_list(self._query)
        self.query_one("#hist-q", Input).focus()

    def _matched(self, query: str) -> list[dict]:
        q = (query or "").strip().lower()
        if not q:
            return list(self._records)
        return [
            item
            for item in self._records
            if q in str(item.get("text", "")).lower()
            or q in str(item.get("kind", "")).lower()
            or q in i18n.label(str(item.get("kind", ""))).lower()
        ]

    def _render_list(self, query: str) -> None:
        items = self._matched(query)
        log = self.query_one("#hist-log", RichLog)
        meta = self.query_one("#hist-meta", Static)
        log.clear()
        if not self._records:
            meta.update(i18n.t("history_count", n=0))
            log.write(i18n.t("search_empty"))
            return
        if (query or "").strip() and not items:
            meta.update(i18n.t("search_empty"))
        elif (query or "").strip():
            meta.update(i18n.t("search_hits", n=len(items)))
        else:
            meta.update(i18n.t("history_count", n=len(items)))
        for item in items:
            log.write(
                _format_history_line(str(item.get("kind", "log")), str(item.get("text", "")))
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hist-go":
            self._render_list(self.query_one("#hist-q", Input).value)
        elif event.button.id == "hist-close":
            self.dismiss()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "hist-q":
            self._render_list(event.value)


class CompactCompareScreen(ModalScreen[None]):
    """压缩对照：左原文 / 右摘要。"""

    BINDINGS = [
        Binding("escape", "close", "Close", show=True),
    ]

    CSS = """
    CompactCompareScreen {
        align: center middle;
    }

    #cmp-panel {
        width: 96%;
        height: 90%;
        background: $surface;
        border: solid $primary;
        padding: 1 1;
        layout: vertical;
    }

    #cmp-title {
        text-style: bold;
        color: $primary;
        height: 1;
        margin-bottom: 1;
    }

    #cmp-cols {
        height: 1fr;
        layout: horizontal;
    }

    #cmp-left, #cmp-right {
        width: 1fr;
        height: 1fr;
        layout: vertical;
        margin: 0 1;
    }

    #cmp-left-title, #cmp-right-title {
        height: 1;
        text-style: bold;
        color: $text-muted;
        margin-bottom: 0;
    }

    #cmp-before, #cmp-after {
        height: 1fr;
        border: solid $foreground 20%;
        background: $panel;
    }

    #cmp-actions {
        height: 3;
        layout: horizontal;
        align: right middle;
        margin-top: 1;
    }
    """

    def __init__(self, before: str, after: str) -> None:
        super().__init__()
        self._before = before or ""
        self._after = after or ""

    def compose(self) -> ComposeResult:
        with Vertical(id="cmp-panel"):
            yield Label(i18n.t("compact_compare_title"), id="cmp-title")
            with Horizontal(id="cmp-cols"):
                with Vertical(id="cmp-left"):
                    yield Label(i18n.t("compact_before"), id="cmp-left-title")
                    yield RichLog(id="cmp-before", markup=False, wrap=True, auto_scroll=False)
                with Vertical(id="cmp-right"):
                    yield Label(i18n.t("compact_after"), id="cmp-right-title")
                    yield RichLog(id="cmp-after", markup=False, wrap=True, auto_scroll=False)
            with Horizontal(id="cmp-actions"):
                yield Button(i18n.t("compact_close"), id="cmp-close", variant="primary", compact=True)

    def on_mount(self) -> None:
        before = self.query_one("#cmp-before", RichLog)
        after = self.query_one("#cmp-after", RichLog)
        before.write(self._before)
        after.write(self._after)
        self.query_one("#cmp-close", Button).focus()

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cmp-close":
            self.dismiss(None)


class SettingsScreen(ModalScreen[int | None]):
    """设置：工具调用轮次上限等，写入 ui.ini。"""

    BINDINGS = [
        Binding("escape", "cancel", "Close", show=True),
    ]

    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #set-panel {
        width: 64;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #set-title {
        text-style: bold;
        color: $primary;
        height: 1;
        margin-bottom: 1;
    }

    #set-rounds-label {
        height: 1;
        margin-bottom: 0;
    }

    #set-rounds-help {
        color: $text-muted;
        height: auto;
        margin-bottom: 1;
    }

    #set-rounds {
        width: 1fr;
        margin-bottom: 1;
    }

    #set-error {
        color: $error;
        height: auto;
        margin-bottom: 1;
    }

    #set-actions {
        height: 3;
        layout: horizontal;
        align: right middle;
    }

    #set-save, #set-cancel {
        min-width: 10;
        margin-left: 1;
    }
    """

    def __init__(self, max_tool_rounds: int) -> None:
        super().__init__()
        self._rounds = clamp_max_tool_rounds(max_tool_rounds)

    def compose(self) -> ComposeResult:
        with Vertical(id="set-panel"):
            yield Label(i18n.t("settings_title"), id="set-title")
            yield Label(i18n.t("settings_rounds_label"), id="set-rounds-label")
            yield Static(i18n.t("settings_rounds_help"), id="set-rounds-help")
            yield Input(value=str(self._rounds), id="set-rounds", type="integer")
            yield Static("", id="set-error")
            with Horizontal(id="set-actions"):
                yield Button(i18n.t("settings_cancel"), id="set-cancel", compact=True)
                yield Button(i18n.t("settings_save"), id="set-save", variant="primary", compact=True)

    def on_mount(self) -> None:
        self.query_one("#set-error", Static).update("")
        self.query_one("#set-rounds", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _try_save(self) -> None:
        raw = self.query_one("#set-rounds", Input).value.strip()
        err = self.query_one("#set-error", Static)
        try:
            n = int(raw)
        except ValueError:
            err.update(i18n.t("settings_invalid"))
            return
        if n < MIN_MAX_TOOL_ROUNDS or n > MAX_MAX_TOOL_ROUNDS:
            err.update(i18n.t("settings_invalid"))
            return
        self.dismiss(clamp_max_tool_rounds(n))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "set-cancel":
            self.dismiss(None)
        elif event.button.id == "set-save":
            self._try_save()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "set-rounds":
            self._try_save()


class SideToggle(Static):
    """轻量折叠控件：始终占位可点，避免收起后命中区域丢失。"""

    can_focus = True
    DEFAULT_CSS = """
    SideToggle {
        width: 3;
        height: 1;
        color: $text-muted;
        background: transparent;
        content-align: center middle;
        text-style: bold;
    }
    SideToggle:hover {
        color: $primary;
        background: $boost;
    }
    SideToggle:focus {
        color: $accent;
        background: $boost;
        text-style: bold;
    }
    """

    def on_click(self, event: Click) -> None:
        event.stop()
        self.app.action_toggle_sidebar()


class XAgentTUI(App):
    """按效果图实现的 Textual 界面：侧栏工具 + 对话流 + 底栏输入。"""

    TITLE = "xAgent"
    # 全部使用主题变量，命令面板切换 Theme 时整界面一起变
    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }

    Header {
        background: $surface;
        color: $foreground;
        text-style: bold;
        dock: top;
        border-bottom: solid $foreground 12%;
    }

    Footer {
        background: $surface;
        color: $text-muted;
        border-top: solid $foreground 12%;
    }

    #body {
        height: 1fr;
        layout: horizontal;
    }

    #side {
        width: 28;
        background: $surface;
        border-right: solid $foreground 12%;
        padding: 1 1 1 2;
        layout: vertical;
    }

    #side.-collapsed {
        width: 3;
        min-width: 3;
        padding: 1 0;
    }

    #side-header {
        height: 1;
        width: 1fr;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    #side.-collapsed #side-header {
        height: 1fr;
        width: 1fr;
        margin-bottom: 0;
        align: center middle;
    }

    #side-title {
        text-style: bold;
        color: $primary;
        width: 1fr;
        height: 1;
        content-align: left middle;
    }

    #side.-collapsed #side-title {
        display: none;
    }

    #side-toggle {
        width: 3;
        height: 1;
    }

    #side.-collapsed #side-toggle {
        width: 1fr;
        height: 1fr;
        min-height: 3;
        content-align: center middle;
        color: $text-muted;
    }

    #side.-collapsed #side-toggle:hover {
        color: $primary;
        background: $boost;
    }

    #side-body {
        height: 1fr;
        layout: vertical;
    }

    #side.-collapsed #side-body {
        display: none;
    }

    #lang-label {
        color: $text-muted;
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }

    #lang {
        width: 1fr;
        height: auto;
        margin-bottom: 1;
    }

    #lang > SelectCurrent {
        background: $panel;
        color: $foreground;
        border: solid $foreground 18%;
        padding: 0 1;
        height: 3;
    }

    #lang:focus > SelectCurrent {
        border: solid $primary;
        color: $foreground;
    }

    #lang.-expanded > SelectCurrent {
        border: solid $primary;
    }

    #lang SelectOverlay {
        background: $panel;
        border: solid $foreground 20%;
        padding: 0;
    }

    #tools {
        color: $text-muted;
        height: auto;
        max-height: 40%;
        padding-top: 0;
    }

    #mcp-label {
        color: $text-muted;
        text-style: bold;
        height: 1;
        margin-top: 1;
    }

    #mcp-panel {
        color: $text-muted;
        height: 1fr;
        padding-top: 0;
    }

    #slash-panel {
        display: none;
        height: auto;
        max-height: 10;
        border: solid $primary;
        background: $surface;
        margin-bottom: 0;
    }

    #slash-panel.-show {
        display: block;
    }

    #main {
        width: 1fr;
        layout: vertical;
        padding: 0 1;
        background: $background;
    }

    #topbar {
        height: auto;
        layout: vertical;
        margin: 1 0 0 0;
    }

    #topbar-row {
        height: 3;
        layout: horizontal;
        align: left middle;
        width: 1fr;
    }

    #context-bar {
        width: 1fr;
        height: 1;
        color: $warning;
        text-style: bold;
        padding: 0 1;
        content-align: left middle;
        margin-bottom: 0;
    }

    #meta {
        width: 1fr;
        height: 3;
        color: $text-muted;
        padding: 0 1;
        content-align: left middle;
        background: transparent;
        border: none;
    }

    #btn-history,
    #btn-clear {
        min-width: 10;
        height: 3;
        margin-left: 1;
        background: $panel;
        color: $foreground;
        border: solid $foreground 18%;
    }

    #btn-history:hover {
        border: solid $primary;
        color: $primary;
    }

    #btn-clear:hover {
        border: solid $error;
        color: $error;
    }

    #log {
        height: 1fr;
        border: solid $foreground 12%;
        background: $panel-darken-1;
        padding: 1 1;
        margin-top: 1;
        scrollbar-background: $panel-darken-1;
        scrollbar-color: $panel;
        scrollbar-color-hover: $primary;
    }

    #composer {
        height: auto;
        layout: vertical;
        margin: 1 0;
    }

    #busy {
        height: 1;
        color: $warning;
        padding: 0 1;
        margin-bottom: 0;
    }

    #prompt {
        width: 1fr;
        background: $panel-darken-1;
        border: solid $foreground 18%;
        padding: 0 1;
        color: $foreground;
    }

    #prompt:focus {
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar"),
        Binding("escape", "clear_input", "Clear", show=False),
    ]

    SIDE_EXPANDED_WIDTH = 28
    SIDE_COLLAPSED_WIDTH = 3

    def __init__(self) -> None:
        super().__init__()
        self.agent: ToolAgent | None = None
        self._busy = False
        self._cfg: dict | None = None
        self._side_collapsed = False
        self._theme_ready = False
        self._history: list[dict] = []
        self._persist_history = True
        self._context_blocked = False
        self._warned_context = False
        # 尽早注册并恢复主题（须在首次刷新 CSS 前尽量生效）
        for theme in CUSTOM_THEMES:
            self.register_theme(theme)
        self._preferred_theme = resolve_saved_theme(
            self.available_themes, DEFAULT_THEME
        )
        if self.theme != self._preferred_theme:
            self.theme = self._preferred_theme

    def _theme_color(self, key: str, fallback: str = "#ebe4d8") -> str:
        """取当前主题的具体色值（供 Rich 标记使用；跳过 auto/带空格的值）。"""
        # 确保使用最新主题变量
        if not self.theme_variables:
            self.get_css_variables()
        color = self.theme_variables.get(key, "")
        if not color or " " in color or color.startswith("auto"):
            color = self.theme_variables.get("foreground", fallback)
        return color or fallback

    def _label_color(self, kind: str) -> str:
        return self._theme_color(_LABEL_THEME_KEYS.get(kind, "foreground"))

    def _persist_theme(self, theme_name: str | None = None) -> None:
        name = (theme_name or self.theme or "").strip()
        if not name:
            return
        try:
            save_ui_settings(theme=name)
            self._preferred_theme = name
        except OSError:
            pass

    def watch_theme(self, theme_name: str) -> None:
        """主题一变就落盘；挂载后同步依赖色值的控件。"""
        self._persist_theme(theme_name)
        if self._theme_ready:
            try:
                self.get_css_variables()
                self._refresh_tools_panel()
                self._refresh_meta()
            except Exception:
                pass

    def _apply_preferred_theme(self) -> None:
        """强制套用已保存主题并刷新样式（避免 on_mount 前 CSS 仍是默认主题）。"""
        name = resolve_saved_theme(self.available_themes, DEFAULT_THEME)
        self._preferred_theme = name
        if self.theme != name:
            self.theme = name
        else:
            # 同名时 reactive 不触发 watch，手动刷新
            self.get_css_variables()
            self.refresh_css(animate=False)
        self._persist_theme(name)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """命令面板条目跟随界面语言。"""
        yield SystemCommand(
            i18n.t("cmd_toggle_side"),
            i18n.t("cmd_toggle_side_help"),
            self.action_toggle_sidebar,
        )
        yield SystemCommand(
            i18n.t("cmd_theme"),
            i18n.t("cmd_theme_help"),
            self.action_change_theme,
        )
        yield SystemCommand(
            i18n.t("cmd_settings"),
            i18n.t("cmd_settings_help"),
            self.action_open_settings,
        )
        yield SystemCommand(
            i18n.t("cmd_quit"),
            i18n.t("cmd_quit_help"),
            self.action_quit,
        )
        if screen.query("HelpPanel"):
            yield SystemCommand(
                i18n.t("cmd_keys"),
                i18n.t("cmd_keys_hide"),
                self.action_hide_help_panel,
            )
        else:
            yield SystemCommand(
                i18n.t("cmd_keys"),
                i18n.t("cmd_keys_show"),
                self.action_show_help_panel,
            )
        if screen.maximized is not None:
            yield SystemCommand(
                i18n.t("cmd_minimize"),
                i18n.t("cmd_minimize_help"),
                screen.action_minimize,
            )
        elif screen.focused is not None and screen.focused.allow_maximize:
            yield SystemCommand(
                i18n.t("cmd_maximize"),
                i18n.t("cmd_maximize_help"),
                screen.action_maximize,
            )
        yield SystemCommand(
            i18n.t("cmd_screenshot"),
            i18n.t("cmd_screenshot_help"),
            lambda: self.set_timer(0.1, self.deliver_screenshot),
        )

    def action_command_palette(self) -> None:
        if self.use_command_palette and not CommandPalette.is_open(self):
            self.push_screen(
                CommandPalette(
                    placeholder=i18n.t("search_commands"),
                    id="--command-palette",
                )
            )

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="side"):
                with Horizontal(id="side-header"):
                    yield Label(i18n.t("tools_title"), id="side-title")
                    yield SideToggle("‹", id="side-toggle")
                with Vertical(id="side-body"):
                    yield Label(i18n.t("lang_label"), id="lang-label")
                    yield Select(
                        i18n.available(),
                        value=DEFAULT_LANG,
                        id="lang",
                        allow_blank=False,
                        compact=True,
                    )
                    yield Static(id="tools")
                    yield Label(i18n.t("mcp_title"), id="mcp-label")
                    yield Static(i18n.t("mcp_loading"), id="mcp-panel")
            with Vertical(id="main"):
                with Vertical(id="topbar"):
                    yield Static("", id="context-bar")
                    with Horizontal(id="topbar-row"):
                        yield Static(id="meta")
                        yield Button(
                            i18n.t("view_history"),
                            id="btn-history",
                            compact=True,
                        )
                        yield Button(
                            i18n.t("clear_history"),
                            id="btn-clear",
                            compact=True,
                        )
                yield RichLog(
                    id="log",
                    markup=True,
                    wrap=True,
                    highlight=False,
                    auto_scroll=True,
                )
                with Vertical(id="composer"):
                    yield Label("", id="busy")
                    yield OptionList(id="slash-panel")
                    yield Input(
                        placeholder=i18n.t("input_placeholder"),
                        id="prompt",
                    )
        yield Footer()

    def on_mount(self) -> None:
        for theme in CUSTOM_THEMES:
            self.register_theme(theme)
        self._apply_preferred_theme()
        self._theme_ready = True

        self._apply_ui_language()
        self._refresh_tools_panel()
        self._refresh_mcp_panel([], loading=True)
        log = self.query_one("#log", RichLog)
        meta = self.query_one("#meta", Static)
        prompt = self.query_one("#prompt", Input)
        self.query_one("#busy", Label).display = False
        self.query_one("#slash-panel", OptionList).display = False

        # 当前项目目录无 config.ini → 创建并弹窗提示
        cfg_path, created = ensure_project_config(PROJECT_ROOT)
        if created:
            self.push_screen(ConfigCreatedScreen(str(cfg_path)))
            self._log_line(
                log,
                "warn",
                i18n.t("config_created_body", path=str(cfg_path)),
            )

        try:
            cfg = load_config(cfg_path if created else None)
            self._cfg = cfg
        except Exception as exc:
            meta.update(i18n.t("config_error", error=str(exc)))
            self._log_line(log, "error", i18n.t("config_load_fail", error=str(exc)))
            prompt.disabled = True
            return

        if not cfg.get("api_key") or cfg["api_key"] == "replace-me":
            meta.update(i18n.t("need_api_key"))
            self._log_line(log, "warn", i18n.t("need_api_key_hint"))
            prompt.disabled = True
            return

        rounds = resolve_max_tool_rounds()
        self.agent = ToolAgent(
            cfg, on_event=self._on_agent_event, max_rounds=rounds
        )
        # MCP 异步加载：先进入界面，完成后再刷新侧栏
        start_mcp_async(PROJECT_ROOT, on_done=self._on_mcp_loaded)
        self._refresh_tools_panel()
        self._refresh_meta()
        self._refresh_context_bar()
        self._restore_history()
        prompt.focus()

    def _on_mcp_loaded(self, messages: list[str], snapshot: list[dict]) -> None:
        try:
            self.call_from_thread(self._apply_mcp_loaded, messages, snapshot)
        except Exception:
            pass

    def _apply_mcp_loaded(self, messages: list[str], snapshot: list[dict]) -> None:
        log = self.query_one("#log", RichLog)
        for msg in messages:
            kind = "warn" if ("失败" in msg or "错误" in msg) else "system"
            self._log_line(log, kind, msg)
        self._refresh_mcp_panel(snapshot, loading=False)
        self._refresh_tools_panel()

    def _refresh_mcp_panel(
        self, snapshot: list[dict] | None = None, *, loading: bool = False
    ) -> None:
        panel = self.query_one("#mcp-panel", Static)
        mute = self._theme_color("secondary-muted", "#6b6560")
        text = self._theme_color("foreground", "#b8b0a4")
        ok = self._theme_color("success", "#6a9f6a")
        if loading:
            panel.update(f"[{mute}]{i18n.t('mcp_loading')}[/{mute}]")
            return
        if not snapshot:
            panel.update(f"[{mute}]{i18n.t('mcp_none')}[/{mute}]")
            return
        lines: list[str] = []
        for srv in snapshot:
            name = str(srv.get("name") or "?")
            lines.append(f"[{ok}]●[/{ok}] [{text}]{name}[/{text}]")
            tools = srv.get("tools") or []
            if not tools:
                lines.append(f"  [{mute}](no tools)[/{mute}]")
            else:
                for t in tools:
                    exposed = t.get("exposed") or t.get("original") or "?"
                    lines.append(f"  [{mute}]·[/{mute}] [{text}]{exposed}[/{text}]")
        panel.update("\n".join(lines))

    def _refresh_tools_panel(self) -> None:
        tools_panel = self.query_one("#tools", Static)
        mute = self._theme_color("secondary-muted", "#6b6560")
        text = self._theme_color("foreground", "#b8b0a4")
        tools_panel.update(
            "\n".join(f"[{mute}]·[/{mute}] [{text}]{name}[/{text}]" for name in tool_names())
        )

    def _refresh_meta(self) -> None:
        if not self._cfg:
            return
        cfg = self._cfg
        self.sub_title = i18n.t(
            "sub_title",
            model=cfg["model"],
            workspace=str(PROJECT_ROOT),
        )
        self.query_one("#meta", Static).update(
            i18n.t(
                "meta",
                model=cfg["model"],
                workspace=str(PROJECT_ROOT),
                config=Path(cfg["config_path"]).name,
            )
        )

    def _refresh_context_bar(self, payload: dict | None = None) -> None:
        bar = self.query_one("#context-bar", Static)
        if self.agent is None:
            bar.update("")
            return
        usage = self.agent.usage
        if payload:
            used = int(payload.get("used") or usage.used_tokens)
            window = int(payload.get("window") or usage.window_tokens)
            percent = float(payload.get("percent") or usage.percent)
            is_default = bool(payload.get("is_default", usage.window_is_default))
            blocked = bool(payload.get("blocked", usage.blocked))
        else:
            used = usage.used_tokens
            window = usage.window_tokens
            percent = usage.percent
            is_default = usage.window_is_default
            blocked = usage.blocked
        self._context_blocked = blocked
        default_tag = i18n.t("context_default_tag") if is_default else ""
        line = i18n.t(
            "context_bar",
            used=format_tokens_k(used),
            window=format_tokens_k(window),
            default_tag=default_tag,
            percent=f"{percent:.1f}",
        )
        if blocked:
            line = f"[b]⚠ {line} — /compact[/b]"
        elif percent >= 60:
            line = f"⚠ {line}"
        bar.update(line)

    def _apply_ui_language(self) -> None:
        """根据当前语言刷新静态控件与系统绑定文案。"""
        self.query_one("#side-title", Label).update(i18n.t("tools_title"))
        try:
            self.query_one("#mcp-label", Label).update(i18n.t("mcp_title"))
        except Exception:
            pass
        self.query_one("#lang-label", Label).update(i18n.t("lang_label"))
        self.query_one("#prompt", Input).placeholder = i18n.t("input_placeholder")
        self.query_one("#btn-history", Button).label = i18n.t("view_history")
        self.query_one("#btn-clear", Button).label = i18n.t("clear_history")
        self._refresh_side_toggle()
        self.bind("ctrl+q", "quit", description=i18n.t("quit"), show=True)
        self.bind("ctrl+b", "toggle_sidebar", description=i18n.t("toggle_side"), show=True)
        self.bind("escape", "clear_input", description=i18n.t("clear_input"), show=False)
        self.bind(
            self.COMMAND_PALETTE_BINDING,
            "command_palette",
            description=i18n.t("palette"),
            show=False,
        )
        try:
            self.query_one(HeaderIcon).tooltip = i18n.t("open_palette")
        except Exception:
            pass
        self._refresh_meta()
        self.refresh_bindings()

    def _save_history(self) -> None:
        if not self._persist_history:
            return
        try:
            save_chat_history(self._history)
        except OSError:
            pass

    def _write_log_line(self, log: RichLog, kind: str, text: str) -> None:
        color = self._label_color(kind)
        body = _linkify_rich(text)
        label = i18n.label(kind)
        head = escape(_pad_label(label))
        log.write(f"[bold {color}]{head}[/bold {color}][dim]│[/dim] {body}")

    def _open_history_browser(self, query: str = "") -> None:
        # 打开前从磁盘再读一次，避免漏掉已落盘内容
        disk = load_chat_history()
        if len(disk) > len(self._history):
            self._history = disk
        elif self._history:
            self._save_history()
        self.push_screen(HistoryBrowserScreen(self._history, query=query))

    def _restore_history(self) -> None:
        """启动时载入历史到内存，并回放进当前会话日志，便于直接查看。"""
        saved = load_chat_history()
        log = self.query_one("#log", RichLog)
        self._history = saved
        if saved:
            self._persist_history = False
            for item in saved:
                self._write_log_line(log, str(item["kind"]), str(item["text"]))
            self._write_log_line(
                log, "system", i18n.t("history_restored", n=len(saved))
            )
            self._write_log_line(
                log, "system", i18n.t("history_hint", n=len(saved))
            )
            self._persist_history = True
        else:
            self._log_line(log, "system", i18n.t("ready"))

    def _clear_history(self) -> None:
        self._history = []
        clear_chat_history_file()
        log = self.query_one("#log", RichLog)
        log.clear()
        if self._cfg:
            self.agent = ToolAgent(
                self._cfg,
                on_event=self._on_agent_event,
                max_rounds=resolve_max_tool_rounds(),
            )
        self._log_line(log, "system", i18n.t("history_cleared"))
        if self.agent is not None:
            self._log_line(log, "system", i18n.t("ready"))
        self.query_one("#prompt", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-history":
            self._open_history_browser()
        elif event.button.id == "btn-clear":
            self._clear_history()

    def _refresh_side_toggle(self) -> None:
        toggle = self.query_one("#side-toggle", SideToggle)
        if self._side_collapsed:
            toggle.update("›")
            toggle.tooltip = i18n.t("expand_side")
        else:
            toggle.update("‹")
            toggle.tooltip = i18n.t("collapse_side")

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._side_collapsed = collapsed
        side = self.query_one("#side", Vertical)
        side.set_class(collapsed, "-collapsed")
        # 用 styles 写死宽度时，展开也要显式恢复，否则会卡在收起宽度
        side.styles.width = (
            self.SIDE_COLLAPSED_WIDTH if collapsed else self.SIDE_EXPANDED_WIDTH
        )
        self._refresh_side_toggle()
        # 收起后把焦点放到展开钮，避免焦点落在已隐藏的 Select 上
        if collapsed:
            self.query_one("#side-toggle", SideToggle).focus()
        else:
            try:
                self.query_one("#prompt", Input).focus()
            except Exception:
                pass

    def action_toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self._side_collapsed)

    def action_open_settings(self) -> None:
        current = (
            self.agent.max_rounds
            if self.agent is not None
            else resolve_max_tool_rounds()
        )

        def _on_close(value: int | None) -> None:
            if value is None:
                return
            save_ui_settings(max_tool_rounds=value)
            if self.agent is not None:
                self.agent.max_rounds = value
            self._log_line(
                self.query_one("#log", RichLog),
                "system",
                i18n.t("settings_saved", n=value),
            )

        self.push_screen(SettingsScreen(current), _on_close)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "lang":
            return
        lang = str(event.value)
        if not i18n.set_lang(lang):
            return
        self._apply_ui_language()
        self._log_line(
            self.query_one("#log", RichLog),
            "system",
            i18n.t("lang_switched", name=i18n.display_name),
        )

    def _log_line(self, log: RichLog, kind: str, text: str) -> None:
        """效果图格式：标签 │ 内容；URL 可点；默认写入本地历史。"""
        if self._persist_history:
            self._history.append(
                {"kind": kind, "text": text, "ts": int(time.time() * 1000)}
            )
            self._save_history()
        self._write_log_line(log, kind, text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        busy_label = self.query_one("#busy", Label)
        prompt = self.query_one("#prompt", Input)
        if busy:
            busy_label.update(i18n.t("busy"))
            busy_label.display = True
            prompt.disabled = True
        else:
            busy_label.update("")
            busy_label.display = False
            prompt.disabled = False
            prompt.focus()

    def _append_event(self, kind: str, payload: dict) -> None:
        log = self.query_one("#log", RichLog)
        if kind == "tool_call":
            self._log_line(
                log,
                "tool",
                f"{payload.get('name')}({payload.get('arguments')})",
            )
        elif kind == "tool_result":
            result = str(payload.get("result", ""))
            preview = result if len(result) <= 500 else result[:500] + "...(truncated)"
            self._log_line(log, "result", preview)
        elif kind == "error":
            self._log_line(log, "error", str(payload.get("text", "")))
        elif kind == "context_usage":
            self._refresh_context_bar(payload)
            if payload.get("blocked") and not getattr(self, "_warned_context", False):
                self._warned_context = True
                self._log_line(log, "warn", i18n.t("context_warn"))
        elif kind == "compact_start":
            self._log_line(log, "system", i18n.t("compact_start"))
        elif kind == "compact_archived":
            self._log_line(
                log,
                "system",
                f"归档已保存: {payload.get('id')} → {payload.get('path')}",
            )
        elif kind == "compact_done":
            self._warned_context = False
            self._refresh_context_bar()
        elif kind == "compact_error":
            self._log_line(
                log,
                "error",
                i18n.t("compact_fail", error=payload.get("text") or ""),
            )
        elif kind == "agents_md_injected":
            self._log_line(
                log,
                "system",
                i18n.t("agents_injected", chars=payload.get("chars") or 0),
            )

    def _on_agent_event(self, kind: str, payload: dict) -> None:
        try:
            self.call_from_thread(self._append_event, kind, payload)
        except Exception:
            pass

    def _show_answer(self, text: str, ok: bool) -> None:
        log = self.query_one("#log", RichLog)
        if ok:
            self._log_line(log, "assistant", text or i18n.t("empty_reply"))
        else:
            self._log_line(log, "error", i18n.t("request_failed", error=text))
        self._refresh_context_bar()
        self._set_busy(False)

    def _show_compact_result(self, result: dict | None, error: str | None) -> None:
        log = self.query_one("#log", RichLog)
        self._set_busy(False)
        self._refresh_context_bar()
        if error:
            self._log_line(log, "error", i18n.t("compact_fail", error=error))
            return
        assert result is not None
        self._log_line(
            log, "system", i18n.t("compact_done", id=result.get("archive_id") or "")
        )
        self.push_screen(
            CompactCompareScreen(
                str(result.get("before") or ""),
                str(result.get("after") or ""),
            )
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "prompt":
            return
        value = event.value or ""
        self._update_slash_panel(value)

    def _update_slash_panel(self, value: str) -> None:
        panel = self.query_one("#slash-panel", OptionList)
        if not value.startswith("/") or " " in value.strip():
            panel.clear_options()
            panel.display = False
            return
        matches = filter_commands(value)
        panel.clear_options()
        if not matches:
            panel.display = False
            return
        for cmd in matches:
            panel.add_option(
                Option(f"/{cmd.name}  — {cmd.help}", id=f"slash-{cmd.name}")
            )
        panel.display = True

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "slash-panel":
            return
        opt_id = str(event.option_id or "")
        if not opt_id.startswith("slash-"):
            return
        name = opt_id[len("slash-") :]
        prompt = self.query_one("#prompt", Input)
        prompt.value = f"/{name}"
        prompt.cursor_position = len(prompt.value)
        event.option_list.display = False
        prompt.focus()

    def _hide_slash_panel(self) -> None:
        panel = self.query_one("#slash-panel", OptionList)
        panel.clear_options()
        panel.display = False

    def _save_current_session(self) -> dict | None:
        if self.agent is None:
            return None
        result = save_session(
            agent_history=self.agent.history,
            ui_history=self._history,
            session_id=self.agent.session_id,
            project_root=PROJECT_ROOT,
        )
        self.agent.session_id = str(result["id"])
        return result

    def _cmd_new(self) -> None:
        assert self.agent is not None
        saved = self._save_current_session()
        sid = (saved or {}).get("id", "?")
        self.agent.reset_session()
        self._history = []
        clear_chat_history_file()
        log = self.query_one("#log", RichLog)
        log.clear()
        self._log_line(log, "system", i18n.t("session_new", id=sid))
        self._refresh_context_bar()

    def _cmd_save(self) -> None:
        result = self._save_current_session()
        if not result:
            return
        self._log_line(
            self.query_one("#log", RichLog),
            "system",
            i18n.t("session_saved", id=result["id"]),
        )

    def _cmd_resume(self) -> None:
        sessions = list_sessions(PROJECT_ROOT)

        def _on_pick(session_id: str | None) -> None:
            if not session_id or self.agent is None:
                return
            data = load_session(session_id, PROJECT_ROOT)
            self.agent.load_history_messages(list(data.get("agent_history") or []))
            self.agent.session_id = str(data.get("id") or session_id)
            self._history = list(data.get("ui_history") or [])
            log = self.query_one("#log", RichLog)
            log.clear()
            for item in self._history:
                self._write_log_line(
                    log, str(item.get("kind", "log")), str(item.get("text", ""))
                )
            self._log_line(
                log, "system", i18n.t("session_resumed", id=self.agent.session_id)
            )
            self._refresh_context_bar()
            self._save_history()

        self.push_screen(ResumeSessionScreen(sessions), _on_pick)

    def _cmd_status(self) -> None:
        if self.agent is None:
            return
        u = self.agent.refresh_usage(estimate_only=True)
        self._refresh_context_bar()
        self._log_line(
            self.query_one("#log", RichLog),
            "system",
            f"{u.status_line()} · session={self.agent.session_id or '(unsaved)'} · msgs={len(self.agent.history)}",
        )

    def _cmd_mcp_reload(self) -> None:
        self._refresh_mcp_panel([], loading=True)
        self._log_line(self.query_one("#log", RichLog), "system", i18n.t("mcp_loading"))
        start_mcp_async(
            PROJECT_ROOT, on_done=self._on_mcp_loaded, force_reload=True
        )

    def _dispatch_slash(self, text: str) -> bool:
        """处理斜杠命令；返回 True 表示已消费。"""
        raw = text.strip()
        if not raw.startswith("/"):
            return False
        token = raw.split(maxsplit=1)[0]
        cmd = resolve_command(token)
        if cmd is None:
            self._log_line(
                self.query_one("#log", RichLog),
                "warn",
                f"未知命令: {token}。输入 /help 查看列表。",
            )
            return True

        self._log_line(self.query_one("#log", RichLog), "user", raw)
        self._hide_slash_panel()
        name = cmd.name
        if name == "quit":
            self.call_later(self.action_quit)
            return True
        if name == "help":
            self._log_line(self.query_one("#log", RichLog), "system", help_text())
            return True
        if name == "clear":
            self.query_one("#log", RichLog).clear()
            self._log_line(
                self.query_one("#log", RichLog), "system", i18n.t("history_cleared")
            )
            return True
        if name == "settings":
            self.action_open_settings()
            return True
        if name == "theme":
            self.action_change_theme()
            return True
        if name == "new":
            if self.agent is None:
                return True
            self._cmd_new()
            return True
        if name == "save":
            self._cmd_save()
            return True
        if name == "resume":
            self._cmd_resume()
            return True
        if name == "status":
            self._cmd_status()
            return True
        if name == "mcp":
            self._cmd_mcp_reload()
            return True
        if name == "compact":
            if self._busy:
                self._log_line(
                    self.query_one("#log", RichLog), "warn", i18n.t("compact_busy")
                )
                return True
            self._set_busy(True)
            self._run_compact()
            return True
        return True

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        event.input.value = ""
        self._hide_slash_panel()
        if not text or self._busy:
            return
        if self.agent is None and not text.startswith("/"):
            self._log_line(
                self.query_one("#log", RichLog), "error", i18n.t("agent_not_ready")
            )
            return

        if text.startswith("/"):
            cmd = resolve_command(text.split()[0])
            if self.agent is None and (not cmd or cmd.name not in {"quit", "help"}):
                self._log_line(
                    self.query_one("#log", RichLog), "error", i18n.t("agent_not_ready")
                )
                return
            self._dispatch_slash(text)
            return

        if self.agent is None:
            self._log_line(
                self.query_one("#log", RichLog), "error", i18n.t("agent_not_ready")
            )
            return

        # 达到限额后禁止普通提示词
        if self.agent.usage.blocked or self._context_blocked:
            self._log_line(
                self.query_one("#log", RichLog), "warn", i18n.t("context_blocked")
            )
            return

        # 发送前估算一次
        self.agent.refresh_usage(estimate_only=True)
        self._refresh_context_bar()
        if self.agent.usage.blocked:
            self._log_line(
                self.query_one("#log", RichLog), "warn", i18n.t("context_blocked")
            )
            return

        self._log_line(self.query_one("#log", RichLog), "user", text)
        self._set_busy(True)
        self._ask_agent(text)

    @work(thread=True, exclusive=True)
    def _ask_agent(self, text: str) -> None:
        assert self.agent is not None
        try:
            answer = self.agent.ask(text)
            self.call_from_thread(self._show_answer, answer, True)
        except Exception as exc:
            self.call_from_thread(self._show_answer, str(exc), False)

    @work(thread=True, exclusive=True)
    def _run_compact(self) -> None:
        assert self.agent is not None
        try:
            result = self.agent.compact()
            self.call_from_thread(self._show_compact_result, result, None)
        except Exception as exc:
            self.call_from_thread(self._show_compact_result, None, str(exc))

    def action_clear_input(self) -> None:
        prompt = self.query_one("#prompt", Input)
        prompt.value = ""
        prompt.focus()

    def on_unmount(self) -> None:
        self._save_history()
        self._persist_theme(self._preferred_theme or self.theme)
        try:
            shutdown_mcp()
        except Exception:
            pass

    async def action_quit(self) -> None:
        self._save_history()
        self._persist_theme(self._preferred_theme or self.theme)
        try:
            shutdown_mcp()
        except Exception:
            pass
        self.exit()


def main() -> None:
    # 再次确认项目根 = 启动 cwd（run.py 已调用；直接 python -m 时也生效）
    init_runtime_paths(Path.cwd())
    XAgentTUI().run()


if __name__ == "__main__":
    main()
