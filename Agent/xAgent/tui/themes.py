"""xAgent 主题定义。切换 App.theme 时，CSS 变量会驱动整界面刷新。"""

from __future__ import annotations

from textual.theme import Theme

# 默认：暖石墨 + 陶土金
XAGENT_INK = Theme(
    name="xagent-ink",
    primary="#c4a574",
    secondary="#8fa3b0",
    accent="#d4b896",
    foreground="#ebe4d8",
    background="#161412",
    surface="#1a1714",
    panel="#221f1c",
    success="#9aaf8f",
    warning="#c9a227",
    error="#c97b7b",
    dark=True,
    variables={
        "footer-key-foreground": "#c4a574",
        "input-selection-background": "#c4a574 30%",
    },
)

# 备选：雾蓝石墨（偏冷）
XAGENT_MIST = Theme(
    name="xagent-mist",
    primary="#7eb8da",
    secondary="#9aa7b8",
    accent="#a8c5d4",
    foreground="#e2e6ec",
    background="#12141a",
    surface="#181b22",
    panel="#22262f",
    success="#8fbf9f",
    warning="#d4a574",
    error="#d98989",
    dark=True,
    variables={
        "footer-key-foreground": "#7eb8da",
        "input-selection-background": "#7eb8da 30%",
    },
)

CUSTOM_THEMES: tuple[Theme, ...] = (XAGENT_INK, XAGENT_MIST)
DEFAULT_THEME = XAGENT_INK.name
