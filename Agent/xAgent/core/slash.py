"""斜杠命令注册表（供 TUI 补全与分发）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    help: str
    aliases: tuple[str, ...] = ()


# 名称不含前导 /
SLASH_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("new", "新建会话（先自动保存当前会话）"),
    SlashCommand("resume", "打开历史会话列表并恢复"),
    SlashCommand("save", "保存当前会话到 .agents/sessions/"),
    SlashCommand("quit", "退出 xAgent", ("exit", "q")),
    SlashCommand("compact", "压缩当前上下文"),
    SlashCommand("help", "显示斜杠命令帮助", ("?",)),
    SlashCommand("clear", "清空当前屏幕日志（不删已保存会话）"),
    SlashCommand("settings", "打开设置"),
    SlashCommand("theme", "打开主题切换"),
    SlashCommand("mcp", "重新异步加载 MCP"),
    SlashCommand("status", "显示上下文用量与会话状态"),
)


def all_names() -> list[str]:
    names: list[str] = []
    for cmd in SLASH_COMMANDS:
        names.append(cmd.name)
        names.extend(cmd.aliases)
    return names


def resolve_command(token: str) -> SlashCommand | None:
    raw = (token or "").strip().lstrip("/").lower()
    if not raw:
        return None
    for cmd in SLASH_COMMANDS:
        if raw == cmd.name or raw in cmd.aliases:
            return cmd
    return None


def filter_commands(prefix: str) -> list[SlashCommand]:
    """按前缀过滤（prefix 可带或不带 /）。"""
    p = (prefix or "").strip().lstrip("/").lower()
    if not p:
        return list(SLASH_COMMANDS)
    out: list[SlashCommand] = []
    for cmd in SLASH_COMMANDS:
        keys = (cmd.name, *cmd.aliases)
        if any(k.startswith(p) for k in keys):
            out.append(cmd)
    return out


def help_text() -> str:
    lines = ["可用斜杠命令："]
    for cmd in SLASH_COMMANDS:
        alias = f" ({', '.join('/' + a for a in cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"  /{cmd.name}{alias}  — {cmd.help}")
    return "\n".join(lines)
