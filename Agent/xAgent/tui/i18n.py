from __future__ import annotations

from typing import Any

# 界面语言包：保留原有英文，并提供中文。
LOCALES: dict[str, dict[str, Any]] = {
    "en-US": {
        "display_name": "English",
        "tools_title": "TOOLS",
        "lang_label": "Language",
        "input_placeholder": "Type a message, Enter to send",
        "quit": "Quit",
        "clear_input": "Clear",
        "busy": "Thinking / calling tools…",
        "ready": "Ready. Try: What is today's date? / Is 2024 a leap year? / List Agent directory",
        "config_error": "Config error: {error}",
        "config_load_fail": "Failed to load config: {error}",
        "need_api_key": "Please set api_key in config.ini",
        "need_api_key_hint": "Copy config.ini.example → config.ini and fill in the key",
        "agent_not_ready": "Agent is not ready",
        "empty_reply": "(empty reply)",
        "request_failed": "Request failed: {error}",
        "lang_switched": "UI language switched to: {name}",
        "meta": "model: {model}    workspace: {workspace}    config: {config}",
        "sub_title": "model: {model}   workspace: {workspace}",
        "open_palette": "Open the command palette",
        "palette": "palette",
        "search_commands": "Search for commands…",
        "cmd_theme": "Theme",
        "cmd_theme_help": "Change the current theme",
        "cmd_settings": "Settings",
        "cmd_settings_help": "Open settings (tool-call round limit, etc.)",
        "settings_title": "Settings",
        "settings_rounds_label": "Max tool-call rounds",
        "settings_rounds_help": "How many tool rounds one reply may use (1–100). Higher helps long PPT/Word tasks.",
        "settings_save": "Save",
        "settings_cancel": "Cancel",
        "settings_saved": "Settings saved. Max tool rounds = {n}",
        "settings_invalid": "Invalid number. Enter an integer from 1 to 100.",
        "cmd_quit": "Quit",
        "cmd_quit_help": "Quit the application as soon as possible",
        "cmd_keys": "Keys",
        "cmd_keys_show": "Show help for the focused widget and a summary of available keys",
        "cmd_keys_hide": "Hide the keys and widget help panel",
        "cmd_maximize": "Maximize",
        "cmd_maximize_help": "Maximize the focused widget",
        "cmd_minimize": "Minimize",
        "cmd_minimize_help": "Minimize the widget and restore to normal size",
        "cmd_screenshot": "Screenshot",
        "cmd_screenshot_help": "Save an SVG 'screenshot' of the current screen",
        "cmd_toggle_side": "Toggle sidebar",
        "cmd_toggle_side_help": "Collapse or expand the left tools sidebar",
        "toggle_side": "Sidebar",
        "collapse_side": "Collapse",
        "expand_side": "Expand",
        "search_history": "Search",
        "view_history": "History",
        "clear_history": "Clear",
        "search_placeholder": "Search history…",
        "search_hits": "Found {n} match(es)",
        "search_empty": "No matches",
        "history_title": "Chat History",
        "history_close": "Close",
        "history_count": "{n} messages",
        "history_hint": "Saved {n} messages. Click History (top-right) to browse/search.",
        "history_restored": "Restored {n} history messages into this session",
        "history_cleared": "History cleared",
        "search_cleared": "Showing full history",
        "context_bar": "Context {used} / {window}{default_tag} · {percent}%",
        "context_default_tag": " (default)",
        "context_warn": "Context usage ≥ 60%. Run /compact to compress before continuing.",
        "context_blocked": "Input blocked until /compact succeeds (context ≥ 60%).",
        "compact_start": "Compressing context… (tools disabled)",
        "compact_done": "Context compacted. Archive id: {id}",
        "compact_fail": "Compact failed: {error}",
        "compact_compare_title": "Context Compact Preview",
        "compact_before": "Before",
        "compact_after": "After",
        "compact_close": "Close",
        "compact_busy": "Already busy; try /compact again later",
        "config_created_title": "config.ini created",
        "config_created_body": "Created a mock config at:\n{path}\n\nEdit api_key (and other fields), then restart xAgent.",
        "config_created_ok": "OK",
        "resume_title": "Resume session",
        "resume_hint": "↑↓ select · Enter confirm · Esc cancel",
        "resume_empty": "(no saved sessions)",
        "resume_cancel": "Cancel",
        "resume_ok": "Resume",
        "mcp_title": "MCP",
        "mcp_loading": "Loading MCP…",
        "mcp_none": "(no MCP servers)",
        "mcp_server": "● {name}",
        "session_saved": "Session saved: {id}",
        "session_new": "New session started (previous saved as {id})",
        "session_resumed": "Resumed session: {id}",
        "agents_injected": "Injected AGENTS.md into session history ({chars} chars)",
        "slash_help_title": "Slash commands",
        "labels": {
            "user": "You",
            "assistant": "Bot",
            "tool": "Tool",
            "result": "Result",
            "system": "System",
            "warn": "Warn",
            "error": "Error",
            "log": "Log",
        },
    },
    "zh-CN": {
        "display_name": "中文",
        "tools_title": "工具",
        "lang_label": "语言",
        "input_placeholder": "输入消息，Enter 发送",
        "quit": "退出",
        "clear_input": "清空",
        "busy": "正在思考 / 调用工具…",
        "ready": "已就绪。试试：今天是几号？ / 2024年是闰年吗？ / 列出 Agent 目录",
        "config_error": "配置错误：{error}",
        "config_load_fail": "无法加载配置：{error}",
        "need_api_key": "请填写 config.ini 中的 api_key",
        "need_api_key_hint": "复制 config.ini.example → config.ini 并填写密钥",
        "agent_not_ready": "Agent 未就绪",
        "empty_reply": "(空回复)",
        "request_failed": "请求失败：{error}",
        "lang_switched": "界面语言已切换为：{name}",
        "meta": "模型: {model}    工作区: {workspace}    配置: {config}",
        "sub_title": "模型: {model}   工作区: {workspace}",
        "open_palette": "打开命令面板",
        "palette": "命令面板",
        "search_commands": "搜索命令…",
        "cmd_theme": "主题",
        "cmd_theme_help": "切换当前主题",
        "cmd_settings": "设置",
        "cmd_settings_help": "打开设置（工具调用轮次上限等）",
        "settings_title": "设置",
        "settings_rounds_label": "工具调用轮次上限",
        "settings_rounds_help": "单次回复最多可连续调用工具的次数（1–100）。做 PPT/长文档时可调高。",
        "settings_save": "保存",
        "settings_cancel": "取消",
        "settings_saved": "设置已保存。工具轮次上限 = {n}",
        "settings_invalid": "数字无效。请输入 1–100 的整数。",
        "cmd_quit": "退出",
        "cmd_quit_help": "尽快退出应用程序",
        "cmd_keys": "快捷键",
        "cmd_keys_show": "显示当前控件帮助与可用快捷键摘要",
        "cmd_keys_hide": "隐藏快捷键与控件帮助面板",
        "cmd_maximize": "最大化",
        "cmd_maximize_help": "最大化当前焦点控件",
        "cmd_minimize": "还原",
        "cmd_minimize_help": "还原控件到正常大小",
        "cmd_screenshot": "截图",
        "cmd_screenshot_help": "将当前屏幕保存为 SVG 截图",
        "cmd_toggle_side": "折叠侧栏",
        "cmd_toggle_side_help": "折叠或展开左侧工具栏",
        "toggle_side": "侧栏",
        "collapse_side": "折叠",
        "expand_side": "展开",
        "search_history": "查询",
        "view_history": "历史",
        "clear_history": "清空记录",
        "search_placeholder": "搜索历史…",
        "search_hits": "找到 {n} 条匹配",
        "search_empty": "无匹配记录",
        "history_title": "历史记录",
        "history_close": "关闭",
        "history_count": "共 {n} 条",
        "history_hint": "已保存 {n} 条记录。点右上角「历史」可浏览/搜索。",
        "history_restored": "已载入 {n} 条历史到当前会话",
        "history_cleared": "历史记录已清空",
        "search_cleared": "已显示全部历史",
        "context_bar": "上下文 {used} / {window}{default_tag} · {percent}%",
        "context_default_tag": "「默认」",
        "context_warn": "上下文已达窗口 60%，请执行 /compact 压缩后再继续。",
        "context_blocked": "上下文已达限额，请先输入 /compact 完成压缩。",
        "compact_start": "正在压缩上下文…（期间禁止工具调用）",
        "compact_done": "上下文压缩完成。归档编号：{id}",
        "compact_fail": "压缩失败：{error}",
        "compact_compare_title": "上下文压缩对照",
        "compact_before": "压缩前",
        "compact_after": "压缩后",
        "compact_close": "关闭",
        "compact_busy": "当前正忙，请稍后再执行 /compact",
        "config_created_title": "已创建 config.ini",
        "config_created_body": "已在当前目录生成示例配置：\n{path}\n\n请填写真实的 api_key 等字段后，重新启动 xAgent 才能正常工作。",
        "config_created_ok": "知道了",
        "resume_title": "恢复历史会话",
        "resume_hint": "↑↓ 选择 · Enter 确认 · Esc 取消",
        "resume_empty": "（暂无已保存会话）",
        "resume_cancel": "取消",
        "resume_ok": "恢复",
        "mcp_title": "MCP",
        "mcp_loading": "正在加载 MCP…",
        "mcp_none": "（暂无 MCP 服务器）",
        "mcp_server": "● {name}",
        "session_saved": "会话已保存：{id}",
        "session_new": "已新建会话（上一会话保存为 {id}）",
        "session_resumed": "已恢复会话：{id}",
        "agents_injected": "已将 AGENTS.md 注入会话历史（{chars} 字）",
        "slash_help_title": "斜杠命令",
        "labels": {
            "user": "你",
            "assistant": "助手",
            "tool": "工具",
            "result": "结果",
            "system": "系统",
            "warn": "注意",
            "error": "错误",
            "log": "日志",
        },
    },
}

DEFAULT_LANG = "zh-CN"


class I18n:
    """界面文案与语言切换（仅 UI，不影响 LLM 对话内容）。"""

    def __init__(self, lang: str = DEFAULT_LANG) -> None:
        self._lang = lang if lang in LOCALES else DEFAULT_LANG

    @property
    def lang(self) -> str:
        return self._lang

    @property
    def display_name(self) -> str:
        return str(LOCALES[self._lang]["display_name"])

    def available(self) -> list[tuple[str, str]]:
        """Select 选项：[(显示名, 语言代码), ...]"""
        return [(str(v["display_name"]), code) for code, v in LOCALES.items()]

    def set_lang(self, lang: str) -> bool:
        if lang not in LOCALES:
            return False
        self._lang = lang
        return True

    def t(self, key: str, **kwargs: Any) -> str:
        pack = LOCALES[self._lang]
        text = pack.get(key)
        if text is None:
            text = LOCALES["en-US"].get(key, key)
        if isinstance(text, str) and kwargs:
            return text.format(**kwargs)
        return str(text)

    def label(self, kind: str) -> str:
        """返回显示标签文案（颜色由当前 Theme 决定）。"""
        labels: dict[str, str] = LOCALES[self._lang]["labels"]
        return labels.get(kind, labels["log"])


i18n = I18n()
