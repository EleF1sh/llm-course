from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any

# 本包目录：.../Agent/xAgent（仅用于找默认 config / ui.ini）
_XAGENT_DIR = Path(__file__).resolve().parents[1]

# 项目根 = 启动时用户工作目录（cwd），不是 python.exe / 不是 Agent 代码目录
PROJECT_ROOT: Path
SKILLS_DIR: Path
WORKSPACE_ROOT: Path
OFFICE_ROOT: Path

UI_SETTINGS_PATH = _XAGENT_DIR / "ui.ini"
CHAT_HISTORY_PATH = _XAGENT_DIR / "chat_history.json"

# 模块级默认值（可被 config.ini [agent] 覆盖）
DEFAULT_MAX_TOOL_ROUNDS = 24
MIN_MAX_TOOL_ROUNDS = 1
MAX_MAX_TOOL_ROUNDS = 100
CHAT_HISTORY_LIMIT = 400
OFFICE_PROMPT_CHAR_LIMIT = 14_000
TEXT_READ_LIMIT = 200_000
FETCHPAGE_MARKDOWN_LIMIT = 80_000
RUNCLI_TIMEOUT_SEC = 30
RUNCLI_OUTPUT_LIMIT = 12_000
DEFAULT_CONTEXT_WINDOW = 128_000
COMPACT_THRESHOLD = 0.60
COMPACT_TARGET_TOKENS = 5_000
COMPACT_TIMEOUT_SEC = 180.0
RECALL_MAX_HITS = 12
RECALL_MAX_CHARS = 6_000

_OFFICE_BOOTSTRAP_FILES = (
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    # AGENTS.md 改为会话首次一次性注入历史，见 ToolAgent.ensure_agents_md
    "TOOLS.md",
)

# 最近一次 load_config 结果（供 tools / compact 读取）
_RUNTIME_CFG: dict[str, Any] = {}

MOCK_CONFIG_INI = """\
[llm]
# OpenAI-compatible endpoint（需支持 tools / function calling）
base_url = https://api.deepseek.com/v1
api_key = replace-me
model = deepseek-chat
temperature = 0.7
timeout = 60
# context_window = 128000

[agent]
max_tool_rounds = 24
office_prompt_char_limit = 14000
chat_history_limit = 400
text_read_limit = 200000
fetchpage_markdown_limit = 80000
runcli_timeout_sec = 30
runcli_output_limit = 12000
default_context_window = 128000
compact_threshold = 0.60
compact_target_tokens = 5000
compact_timeout_sec = 180
recall_max_hits = 12
recall_max_chars = 6000

[search]
# 百度千帆 AI 搜索 API Key（searchWeb 工具鉴权）
baidu_qianfan_api_key = replace-me
"""


def _guess_file_workspace(project_root: Path) -> Path:
    """文件工具沙箱：优先 git 仓库根 / Agent 的上一级，避免困在 office 子目录。"""
    if (
        project_root.name.lower() == "office"
        and project_root.parent.name.lower() == "agent"
    ):
        return project_root.parent.parent.resolve()
    for parent in (project_root, *project_root.parents):
        if (parent / ".git").exists():
            return parent.resolve()
    if project_root.name.lower() == "xagent" and project_root.parent.name.lower() == "agent":
        return project_root.parent.parent.resolve()
    return project_root.resolve()


def init_runtime_paths(cwd: Path | None = None) -> Path:
    """以启动时 cwd 为项目根（Skill 发现），并解析文件沙箱 / office。"""
    global PROJECT_ROOT, SKILLS_DIR, WORKSPACE_ROOT, OFFICE_ROOT
    PROJECT_ROOT = (cwd or Path.cwd()).resolve()
    SKILLS_DIR = PROJECT_ROOT / ".agents" / "skills"
    if os.getenv("XAGENT_WORKSPACE"):
        WORKSPACE_ROOT = Path(os.environ["XAGENT_WORKSPACE"]).resolve()
    else:
        WORKSPACE_ROOT = _guess_file_workspace(PROJECT_ROOT)
    OFFICE_ROOT = PROJECT_ROOT
    try:
        from core.skills import reset_skill_registry

        reset_skill_registry()
    except ImportError:
        pass
    return PROJECT_ROOT


init_runtime_paths()


def project_config_path(project_root: Path | None = None) -> Path:
    return (project_root or PROJECT_ROOT).resolve() / "config.ini"


def resolve_config_path(project_root: Path | None = None) -> Path:
    """优先当前项目目录 config.ini，其次 xAgent 包内、Practice02。"""
    root = (project_root or PROJECT_ROOT).resolve()
    candidates = (
        root / "config.ini",
        _XAGENT_DIR / "config.ini",
        _XAGENT_DIR.parent / "Practice02" / "config.ini",
    )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def ensure_project_config(project_root: Path | None = None) -> tuple[Path, bool]:
    """若当前项目目录没有 config.ini，则写入完整配置（优先复制包内已有文件）。

    Returns:
        (project_config_path, created_new_in_project_dir)
    """
    root = (project_root or PROJECT_ROOT).resolve()
    local = root / "config.ini"
    if local.exists():
        return local, False
    # 若包内已有可用 config，复制过去，避免首次从 office 启动丢失密钥
    pkg = _XAGENT_DIR / "config.ini"
    if pkg.is_file():
        try:
            local.write_text(pkg.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            local.write_text(MOCK_CONFIG_INI, encoding="utf-8")
    else:
        local.write_text(MOCK_CONFIG_INI, encoding="utf-8")
    return local, True


def get_runtime_config() -> dict[str, Any]:
    return dict(_RUNTIME_CFG) if _RUNTIME_CFG else {}


def _apply_agent_defaults(parser: configparser.ConfigParser) -> dict[str, Any]:
    """从 [agent] 读可调参数，缺省用模块默认值。"""
    def _get(key: str, fallback: str) -> str:
        if parser.has_section("agent") and key in parser["agent"]:
            return parser.get("agent", key, fallback=fallback).strip() or fallback
        return fallback

    def _int(key: str, default: int) -> int:
        try:
            return int(_get(key, str(default)))
        except ValueError:
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(_get(key, str(default)))
        except ValueError:
            return default

    return {
        "max_tool_rounds": clamp_max_tool_rounds(
            _int("max_tool_rounds", DEFAULT_MAX_TOOL_ROUNDS)
        ),
        "office_prompt_char_limit": _int(
            "office_prompt_char_limit", OFFICE_PROMPT_CHAR_LIMIT
        ),
        "chat_history_limit": _int("chat_history_limit", CHAT_HISTORY_LIMIT),
        "text_read_limit": _int("text_read_limit", TEXT_READ_LIMIT),
        "fetchpage_markdown_limit": _int(
            "fetchpage_markdown_limit", FETCHPAGE_MARKDOWN_LIMIT
        ),
        "runcli_timeout_sec": _int("runcli_timeout_sec", RUNCLI_TIMEOUT_SEC),
        "runcli_output_limit": _int("runcli_output_limit", RUNCLI_OUTPUT_LIMIT),
        "default_context_window": _int(
            "default_context_window", DEFAULT_CONTEXT_WINDOW
        ),
        "compact_threshold": _float("compact_threshold", COMPACT_THRESHOLD),
        "compact_target_tokens": _int(
            "compact_target_tokens", COMPACT_TARGET_TOKENS
        ),
        "compact_timeout_sec": _float("compact_timeout_sec", COMPACT_TIMEOUT_SEC),
        "recall_max_hits": _int("recall_max_hits", RECALL_MAX_HITS),
        "recall_max_chars": _int("recall_max_chars", RECALL_MAX_CHARS),
    }


def _sync_module_defaults(agent_cfg: dict[str, Any]) -> None:
    """把运行时配置同步到模块级常量，供未改尽的引用点使用。"""
    global CHAT_HISTORY_LIMIT, OFFICE_PROMPT_CHAR_LIMIT, TEXT_READ_LIMIT
    global FETCHPAGE_MARKDOWN_LIMIT, RUNCLI_TIMEOUT_SEC, RUNCLI_OUTPUT_LIMIT
    global DEFAULT_CONTEXT_WINDOW, COMPACT_THRESHOLD, COMPACT_TARGET_TOKENS
    global COMPACT_TIMEOUT_SEC, RECALL_MAX_HITS, RECALL_MAX_CHARS
    global DEFAULT_MAX_TOOL_ROUNDS
    CHAT_HISTORY_LIMIT = int(agent_cfg["chat_history_limit"])
    OFFICE_PROMPT_CHAR_LIMIT = int(agent_cfg["office_prompt_char_limit"])
    TEXT_READ_LIMIT = int(agent_cfg["text_read_limit"])
    FETCHPAGE_MARKDOWN_LIMIT = int(agent_cfg["fetchpage_markdown_limit"])
    RUNCLI_TIMEOUT_SEC = int(agent_cfg["runcli_timeout_sec"])
    RUNCLI_OUTPUT_LIMIT = int(agent_cfg["runcli_output_limit"])
    DEFAULT_CONTEXT_WINDOW = int(agent_cfg["default_context_window"])
    COMPACT_THRESHOLD = float(agent_cfg["compact_threshold"])
    COMPACT_TARGET_TOKENS = int(agent_cfg["compact_target_tokens"])
    COMPACT_TIMEOUT_SEC = float(agent_cfg["compact_timeout_sec"])
    RECALL_MAX_HITS = int(agent_cfg["recall_max_hits"])
    RECALL_MAX_CHARS = int(agent_cfg["recall_max_chars"])
    DEFAULT_MAX_TOOL_ROUNDS = int(agent_cfg["max_tool_rounds"])


def load_config(config_path: Path | None = None) -> dict:
    global _RUNTIME_CFG
    path = config_path or resolve_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"缺少配置文件 {path}。请填写 api_key 后重新启动。"
        )
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section("llm"):
        raise ValueError(f"配置缺少 [llm] 段: {path}")
    section = parser["llm"]
    search_key = ""
    if parser.has_section("search"):
        search_key = parser.get("search", "baidu_qianfan_api_key", fallback="").strip()
    context_window: int | None = None
    if "context_window" in section:
        try:
            context_window = int(section.get("context_window", "").strip() or "0") or None
        except ValueError:
            context_window = None
    agent_cfg = _apply_agent_defaults(parser)
    _sync_module_defaults(agent_cfg)
    cfg = {
        "base_url": section.get("base_url", "https://api.openai.com/v1").rstrip("/"),
        "api_key": section.get("api_key", ""),
        "model": section.get("model", "gpt-4o-mini"),
        "temperature": section.getfloat("temperature", 0.7),
        "timeout": section.getfloat("timeout", 60),
        "context_window": context_window,
        "baidu_qianfan_api_key": search_key,
        "config_path": str(path),
        **agent_cfg,
    }
    _RUNTIME_CFG = cfg
    return cfg


def load_baidu_qianfan_api_key(config_path: Path | None = None) -> str:
    """读取 [search].baidu_qianfan_api_key；缺失时返回空字符串。"""
    path = config_path or resolve_config_path()
    if not path.exists():
        return ""
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return ""
    if not parser.has_section("search"):
        return ""
    return parser.get("search", "baidu_qianfan_api_key", fallback="").strip()


def clamp_max_tool_rounds(value: int | str | None, default: int | None = None) -> int:
    """把工具轮次上限限制在合理范围。"""
    if default is None:
        default = DEFAULT_MAX_TOOL_ROUNDS
    try:
        n = int(str(value).strip()) if value is not None and str(value).strip() else default
    except (TypeError, ValueError):
        n = default
    return max(MIN_MAX_TOOL_ROUNDS, min(MAX_MAX_TOOL_ROUNDS, n))


def load_ui_settings() -> dict:
    """读取界面偏好（主题、工具轮次等），文件不存在时返回空字典。"""
    if not UI_SETTINGS_PATH.exists():
        return {}
    parser = configparser.ConfigParser()
    parser.read(UI_SETTINGS_PATH, encoding="utf-8")
    if not parser.has_section("ui"):
        return {}
    section = parser["ui"]
    out: dict[str, Any] = {}
    theme = section.get("theme", "").strip()
    if theme:
        out["theme"] = theme
    raw_rounds = section.get("max_tool_rounds", "").strip()
    if raw_rounds:
        out["max_tool_rounds"] = clamp_max_tool_rounds(raw_rounds)
    return out


def save_ui_settings(
    *,
    theme: str | None = None,
    max_tool_rounds: int | None = None,
) -> None:
    """写入界面偏好；未传入的字段保留原值。原子写入，避免退出时写半截。"""
    parser = configparser.ConfigParser()
    if UI_SETTINGS_PATH.exists():
        parser.read(UI_SETTINGS_PATH, encoding="utf-8")
    if not parser.has_section("ui"):
        parser.add_section("ui")
    if theme is not None and theme.strip():
        parser.set("ui", "theme", theme.strip())
    if max_tool_rounds is not None:
        parser.set(
            "ui",
            "max_tool_rounds",
            str(clamp_max_tool_rounds(max_tool_rounds)),
        )
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = UI_SETTINGS_PATH.with_suffix(".ini.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    tmp_path.replace(UI_SETTINGS_PATH)


def resolve_max_tool_rounds() -> int:
    """优先 ui.ini，其次 config.ini [agent]，再默认。"""
    saved = load_ui_settings().get("max_tool_rounds")
    if saved is not None:
        return clamp_max_tool_rounds(saved)
    cfg = get_runtime_config()
    if cfg.get("max_tool_rounds") is not None:
        return clamp_max_tool_rounds(cfg["max_tool_rounds"])
    return DEFAULT_MAX_TOOL_ROUNDS


def resolve_saved_theme(available: dict[str, object], default: str) -> str:
    """从 ui.ini 解析可用主题名；无效则回退 default。"""
    saved = (load_ui_settings().get("theme") or "").strip()
    if saved and saved in available:
        return saved
    if default in available:
        return default
    return "textual-dark"


def load_chat_history() -> list[dict[str, Any]]:
    """读取本地对话历史；损坏或缺失时返回空列表。"""
    if not CHAT_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(CHAT_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        text = item.get("text")
        if not kind or not isinstance(text, str):
            continue
        out.append({"kind": kind, "text": text, "ts": item.get("ts")})
    limit = int(get_runtime_config().get("chat_history_limit") or CHAT_HISTORY_LIMIT)
    return out[-limit:]


def save_chat_history(records: list[dict[str, Any]]) -> None:
    """保存对话历史（截断到上限）。"""
    limit = int(get_runtime_config().get("chat_history_limit") or CHAT_HISTORY_LIMIT)
    slim = records[-limit:]
    payload = [
        {"kind": r["kind"], "text": r["text"], "ts": r.get("ts")}
        for r in slim
        if isinstance(r, dict) and r.get("kind") and isinstance(r.get("text"), str)
    ]
    CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHAT_HISTORY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CHAT_HISTORY_PATH)


def clear_chat_history_file() -> None:
    try:
        if CHAT_HISTORY_PATH.exists():
            CHAT_HISTORY_PATH.unlink()
    except OSError:
        pass


def load_agents_md(project_root: Path | None = None) -> str | None:
    """读取项目根 AGENTS.md；不存在则返回 None。"""
    path = (project_root or PROJECT_ROOT) / "AGENTS.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def load_office_prompt(char_limit: int | None = None) -> str:
    """注入项目根下的身份/规则文件（不含 AGENTS.md，避免重复注入）。"""
    if char_limit is None:
        char_limit = int(
            get_runtime_config().get("office_prompt_char_limit") or OFFICE_PROMPT_CHAR_LIMIT
        )
    if not OFFICE_ROOT.is_dir():
        return ""
    header = (
        f"你驻扎在办公工作区 {OFFICE_ROOT}。"
        "下列文件定义身份、灵魂、用户与工作约定；请遵循。"
        f"日记写在 {OFFICE_ROOT / 'memory'}；产出默认 {OFFICE_ROOT / 'output'}；"
        f"项目放 {OFFICE_ROOT / 'projects'}。"
        "AGENTS.md 若存在，已在会话历史中一次性注入，请直接遵循历史中的内容。"
    )
    chunks: list[str] = [header]
    used = len(header)
    any_file = False
    for name in _OFFICE_BOOTSTRAP_FILES:
        path = OFFICE_ROOT / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not body:
            continue
        any_file = True
        block = f"\n\n## {name}\n{body}"
        if used + len(block) > char_limit:
            remain = char_limit - used - 80
            if remain > 200:
                chunks.append(block[:remain] + "\n…(truncated)")
            break
        chunks.append(block)
        used += len(block)
    return "".join(chunks) if any_file else ""
