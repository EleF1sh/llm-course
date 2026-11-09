"""启动 Textual TUI：python run.py

项目根目录 = 启动时的用户工作目录（cwd），用于发现 `.agents/skills`。
请在目标工作区（例如 Agent/office）下启动，或使用 office 目录中的启动脚本。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在导入 agent / 扫描技能之前固定项目根 = 启动 cwd
from core.config import init_runtime_paths

init_runtime_paths(Path.cwd())

from tui.app import main

if __name__ == "__main__":
    main()
