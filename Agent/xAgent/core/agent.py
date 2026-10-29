from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from core.config import WORKSPACE_ROOT
from core.schemas import TOOLS
from core.tools import _err, run_tool

EventCallback = Callable[[str, dict[str, Any]], None]


def default_system_prompt() -> str:
    return (
        "你是简洁友好的中文助手，可以调用本地工具。"
        "问当前日期/时间时必须调用 getDate；"
        "问某年是否闰年时必须调用 isLeapYear；"
        "涉及本地文件/目录的查看、创建、修改、删除、重命名时，"
        "必须调用对应文件工具（getCwd/listDir/getFileType/readFile/"
        "createFile/editFile/makeDir/removeDir/removeFile/renamePath），"
        "不要假装已经操作过文件系统。"
        "需要阅读或总结某个网页 URL 的正文时，必须调用 fetchpage，不要编造网页内容。"
        "需要查互联网最新信息、新闻或开放事实问题时，必须调用 searchWeb，不要编造搜索结果。"
        "需要执行本机 CLI 命令时，必须调用 RunCli，不要假装已经运行过命令。"
        f"所有文件路径都应落在课程目录 {WORKSPACE_ROOT} 内；"
        "相对路径相对于该目录理解。"
    )


class ToolAgent:
    """与 UI 无关的工具调用 Agent（可供 CLI / TUI / 未来 Web 复用）。"""

    def __init__(
        self,
        cfg: dict,
        *,
        on_event: EventCallback | None = None,
        max_rounds: int = 8,
        system_prompt: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.on_event = on_event or (lambda _kind, _payload: None)
        self.max_rounds = max_rounds
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt or default_system_prompt()}
        ]

    def _emit(self, kind: str, **payload: Any) -> None:
        self.on_event(kind, payload)

    def _build_payload(self, messages: list[dict], *, stream: bool = False) -> dict:
        return {
            "model": self.cfg["model"],
            "messages": messages,
            "temperature": self.cfg["temperature"],
            "stream": stream,
            "tools": TOOLS,
            "tool_choice": "auto",
        }

    def chat_once(self, messages: list[dict]) -> dict:
        url = f"{self.cfg['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.cfg["timeout"]) as client:
            resp = client.post(
                url, headers=headers, json=self._build_payload(messages)
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]

    def chat_with_tools(self, messages: list[dict]) -> str:
        for _ in range(self.max_rounds):
            message = self.chat_once(messages)
            tool_calls = message.get("tool_calls") or []

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": message.get("content") or "",
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if not tool_calls:
                text = (message.get("content") or "").strip()
                self._emit("assistant", text=text)
                return text

            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                self._emit("tool_call", name=name, arguments=raw_args)
                try:
                    result = run_tool(name, raw_args)
                except Exception as exc:
                    result = _err(f"tool error: {exc}")
                self._emit("tool_result", name=name, result=result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", name),
                        "content": result,
                    }
                )

        text = "工具调用轮次过多，已停止。"
        self._emit("assistant", text=text)
        return text

    def ask(self, user_text: str) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return ""
        self.history.append({"role": "user", "content": user_text})
        self._emit("user", text=user_text)
        try:
            answer = self.chat_with_tools(self.history)
        except Exception as exc:
            # 回滚本轮脏历史
            while self.history and self.history[-1].get("role") != "user":
                self.history.pop()
            if self.history and self.history[-1].get("role") == "user":
                self.history.pop()
            self._emit("error", text=str(exc))
            raise
        self.history.append({"role": "assistant", "content": answer})
        return answer
