"""xAgent 业务核心：配置、工具、对话 Agent（与 UI 无关）。"""

from core.agent import ToolAgent
from core.config import PROJECT_ROOT, SKILLS_DIR, WORKSPACE_ROOT, load_config
from core.schemas import LOCAL_TOOLS, TOOLS, get_tools, tool_names

__all__ = [
    "ToolAgent",
    "PROJECT_ROOT",
    "SKILLS_DIR",
    "WORKSPACE_ROOT",
    "load_config",
    "LOCAL_TOOLS",
    "TOOLS",
    "get_tools",
    "tool_names",
]
