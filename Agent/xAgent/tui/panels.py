"""TUI 浮动面板：配置提示、会话恢复等。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

from tui.i18n import i18n


class ConfigCreatedScreen(ModalScreen[None]):
    """当前目录新建了 mock config.ini，提示修改后重启。"""

    BINDINGS = [Binding("escape", "close", "Close", show=True)]

    CSS = """
    ConfigCreatedScreen { align: center middle; }
    #cfg-panel {
        width: 72;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $warning;
        padding: 1 2;
    }
    #cfg-title { text-style: bold; color: $warning; height: 1; margin-bottom: 1; }
    #cfg-body { height: auto; margin-bottom: 1; }
    #cfg-actions { height: 3; align: right middle; }
    """

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="cfg-panel"):
            yield Label(i18n.t("config_created_title"), id="cfg-title")
            yield Static(
                i18n.t("config_created_body", path=self._path),
                id="cfg-body",
            )
            with Horizontal(id="cfg-actions"):
                yield Button(i18n.t("config_created_ok"), id="cfg-ok", variant="primary", compact=True)

    def on_mount(self) -> None:
        self.query_one("#cfg-ok", Button).focus()

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg-ok":
            self.dismiss(None)


class ResumeSessionScreen(ModalScreen[str | None]):
    """历史会话列表：上下选择，回车确认，ESC 取消。"""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("enter", "confirm", "OK", show=True),
    ]

    CSS = """
    ResumeSessionScreen { align: center middle; }
    #resume-panel {
        width: 80%;
        height: 70%;
        background: $surface;
        border: solid $primary;
        padding: 1 1;
        layout: vertical;
    }
    #resume-title { text-style: bold; color: $primary; height: 1; margin-bottom: 1; }
    #resume-hint { color: $text-muted; height: 1; margin-bottom: 1; }
    #resume-list { height: 1fr; border: solid $foreground 20%; }
    #resume-actions { height: 3; align: right middle; margin-top: 1; }
    """

    def __init__(self, sessions: list[dict]) -> None:
        super().__init__()
        self._sessions = sessions

    def compose(self) -> ComposeResult:
        with Vertical(id="resume-panel"):
            yield Label(i18n.t("resume_title"), id="resume-title")
            yield Static(i18n.t("resume_hint"), id="resume-hint")
            yield ListView(id="resume-list")
            with Horizontal(id="resume-actions"):
                yield Button(i18n.t("resume_cancel"), id="resume-cancel", compact=True)
                yield Button(i18n.t("resume_ok"), id="resume-ok", variant="primary", compact=True)

    def on_mount(self) -> None:
        lv = self.query_one("#resume-list", ListView)
        if not self._sessions:
            lv.append(ListItem(Label(i18n.t("resume_empty"))))
        else:
            for item in self._sessions:
                title = str(item.get("title") or item.get("id"))
                meta = f"{item.get('id')}  ·  {item.get('saved_at')}  ·  {item.get('message_count')} msgs"
                lv.append(ListItem(Label(f"{title}\n{meta}")))
            lv.index = 0
        lv.focus()

    def _selected_id(self) -> str | None:
        lv = self.query_one("#resume-list", ListView)
        if not self._sessions:
            return None
        idx = lv.index
        if idx is None or idx < 0 or idx >= len(self._sessions):
            return None
        return str(self._sessions[idx]["id"])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        self.dismiss(self._selected_id())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.dismiss(self._selected_id())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "resume-cancel":
            self.dismiss(None)
        elif event.button.id == "resume-ok":
            self.dismiss(self._selected_id())
