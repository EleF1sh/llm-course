"""命名会话的保存 / 列出 / 恢复（项目根 `.agents/sessions/`）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import PROJECT_ROOT


def sessions_dir(project_root: Path | None = None) -> Path:
    path = (project_root or PROJECT_ROOT).resolve() / ".agents" / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_session_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S")


def _preview_from_history(agent_history: list[dict[str, Any]], limit: int = 80) -> str:
    for msg in reversed(agent_history or []):
        if msg.get("role") != "user":
            continue
        if msg.get("xagent_meta") == "agents.md":
            continue
        text = str(msg.get("content") or "").strip().replace("\n", " ")
        if text:
            return text[:limit] + ("…" if len(text) > limit else "")
    return "(空会话)"


def save_session(
    *,
    agent_history: list[dict[str, Any]],
    ui_history: list[dict[str, Any]],
    session_id: str | None = None,
    title: str | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    sid = session_id or new_session_id()
    path = sessions_dir(project_root) / f"{sid}.json"
    preview = title or _preview_from_history(agent_history)
    payload = {
        "id": sid,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "title": preview,
        "agent_history": agent_history,
        "ui_history": ui_history,
        "message_count": len(agent_history or []),
        "ui_count": len(ui_history or []),
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"ok": True, "id": sid, "path": str(path), "title": preview}


def list_sessions(project_root: Path | None = None) -> list[dict[str, Any]]:
    root = sessions_dir(project_root)
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"), key=lambda p: p.name, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        items.append(
            {
                "id": str(data.get("id") or path.stem),
                "title": str(data.get("title") or path.stem),
                "saved_at": str(data.get("saved_at") or ""),
                "message_count": int(data.get("message_count") or 0),
                "path": str(path),
            }
        )
    return items


def load_session(
    session_id: str, project_root: Path | None = None
) -> dict[str, Any]:
    sid = (session_id or "").strip().removesuffix(".json")
    path = sessions_dir(project_root) / f"{sid}.json"
    if not path.is_file():
        raise FileNotFoundError(f"会话不存在: {sid}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("会话文件格式无效")
    data["id"] = str(data.get("id") or sid)
    data["agent_history"] = list(data.get("agent_history") or [])
    data["ui_history"] = list(data.get("ui_history") or [])
    return data
