from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
from typing import Any

# 课程仓库根：默认 D:\LLM-Course，可用环境变量覆盖
WORKSPACE_ROOT = Path(
    os.getenv("XAGENT_WORKSPACE", r"D:\LLM-Course")
).resolve()

# 配置文件优先：本包旁 config.ini → Practice02/config.ini
_XAGENT_DIR = Path(__file__).resolve().parents[1]
_CONFIG_CANDIDATES = (
    _XAGENT_DIR / "config.ini",
    Path(r"D:\LLM-Course\Agent\Practice02\config.ini"),
)
UI_SETTINGS_PATH = _XAGENT_DIR / "ui.ini"
CHAT_HISTORY_PATH = _XAGENT_DIR / "chat_history.json"
CHAT_HISTORY_LIMIT = 400


def resolve_config_path() -> Path:
    for path in _CONFIG_CANDIDATES:
        if path.exists():
            return path
    return _CONFIG_CANDIDATES[0]


def load_config(config_path: Path | None = None) -> dict:
    path = config_path or resolve_config_path()
    if not path.exists():
        raise FileNotFoundError(
            f"缺少配置文件 {path}。请复制 config.ini.example 为 config.ini 并填写。"
        )
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    section = parser["llm"]
    search_key = ""
    if parser.has_section("search"):
        search_key = parser.get("search", "baidu_qianfan_api_key", fallback="").strip()
    return {
        "base_url": section.get("base_url", "https://api.openai.com/v1").rstrip("/"),
        "api_key": section.get("api_key", ""),
        "model": section.get("model", "gpt-4o-mini"),
        "temperature": section.getfloat("temperature", 0.7),
        "timeout": section.getfloat("timeout", 60),
        "baidu_qianfan_api_key": search_key,
        "config_path": str(path),
    }


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


def load_ui_settings() -> dict:
    """读取界面偏好（主题等），文件不存在时返回空字典。"""
    if not UI_SETTINGS_PATH.exists():
        return {}
    parser = configparser.ConfigParser()
    parser.read(UI_SETTINGS_PATH, encoding="utf-8")
    if not parser.has_section("ui"):
        return {}
    section = parser["ui"]
    theme = section.get("theme", "").strip()
    return {"theme": theme} if theme else {}


def save_ui_settings(*, theme: str | None = None) -> None:
    """写入界面偏好；未传入的字段保留原值。原子写入，避免退出时写半截。"""
    parser = configparser.ConfigParser()
    if UI_SETTINGS_PATH.exists():
        parser.read(UI_SETTINGS_PATH, encoding="utf-8")
    if not parser.has_section("ui"):
        parser.add_section("ui")
    if theme is not None and theme.strip():
        parser.set("ui", "theme", theme.strip())
    UI_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = UI_SETTINGS_PATH.with_suffix(".ini.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    tmp_path.replace(UI_SETTINGS_PATH)


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
    return out[-CHAT_HISTORY_LIMIT:]


def save_chat_history(records: list[dict[str, Any]]) -> None:
    """保存对话历史（截断到上限）。"""
    slim = records[-CHAT_HISTORY_LIMIT:]
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
