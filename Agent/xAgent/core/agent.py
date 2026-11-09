from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from core.config import (
    OFFICE_ROOT,
    PROJECT_ROOT,
    WORKSPACE_ROOT,
    get_runtime_config,
    load_agents_md,
    load_office_prompt,
)
from core.context_compact import (
    COMPACT_SYSTEM_PROMPT,
    USAGE_THRESHOLD,
    ContextUsage,
    archive_messages,
    build_archive_footer,
    messages_to_transcript,
)

AGENTS_MD_META = "agents.md"
from core.schemas import get_tools
from core.skills import discover_skills, skills_catalog_prompt
from core.tools import _err, run_tool

EventCallback = Callable[[str, dict[str, Any]], None]


def default_system_prompt() -> str:
    # 初始化阶段只注册元数据，不把 SKILL.md 正文塞进上下文
    discover_skills()
    base = (
        "你是办公助手「小办」，可以调用本地工具。"
        "身份与行为以项目根目录工作区文件为准（SOUL / IDENTITY / USER / AGENTS）。"
        "问当前日期/时间时必须调用 getDate；"
        "问某年是否闰年时必须调用 isLeapYear；"
        "涉及本地文件/目录的查看、创建、修改、删除、重命名时，"
        "必须调用对应文件工具（getCwd/listDir/getFileType/readFile/"
        "createFile/editFile/makeDir/removeDir/removeFile/renamePath），"
        "不要假装已经操作过文件系统。"
        "需要阅读或总结某个网页 URL 的正文时，必须调用 fetchpage，不要编造网页内容。"
        "需要查互联网最新信息、新闻或开放事实问题时，必须调用 searchWeb，不要编造搜索结果。"
        "需要执行本机 CLI 命令时，必须调用 RunCli，不要假装已经运行过命令。"
        "用户要找/装/列出技能商店中的技能时，可调用 skillhubSearch / skillhubInstall / skillhubList。"
        "当某项任务匹配已发现的 Skill 描述时，必须先调用 loadSkill 加载完整说明再按说明执行；"
        "需要 Skill 内附件时，再次调用 loadSkill 并传入 filename。"
        "用户要求创建新 Skill 时，必须调用 createSkill（name + skillContext）；"
        "不要手写覆盖已有技能；额外的 references/scripts 等用 makeDir/createFile 补充。"
        "用户提供 MCP Server 配置（url/command 或完整 JSON）要写入 `.mcp.json` 时，必须调用 createMCP；"
        "不要手写捏造已连接；写入成功后以返回的 reload_status / 工具列表为准。"
        "若工具列表中出现 MCP 工具（描述常带 [MCP:服务器名] 前缀），可直接按 Function Calling 调用。"
        "当压缩摘要缺少历史细节时，必须调用 recallContext（必填 text，可选 id）检索归档，"
        "不要编造未检索到的历史内容。"
        f"项目根目录（启动时 cwd，用于发现 `.agents/skills` 与 `.mcp.json`）：{PROJECT_ROOT}；"
        f"办公工作区：{OFFICE_ROOT}；"
        f"文件工具沙箱（listDir/readFile 等）根目录：{WORKSPACE_ROOT}；"
        "相对路径相对于文件沙箱根理解；Skill 附件请用 loadSkill。"
    )
    parts = [base]
    office = load_office_prompt()
    if office:
        parts.append(office)
    parts.append(skills_catalog_prompt())
    return "\n\n".join(parts)


class ToolAgent:
    """与 UI 无关的工具调用 Agent（可供 CLI / TUI / 未来 Web 复用）。"""

    def __init__(
        self,
        cfg: dict,
        *,
        on_event: EventCallback | None = None,
        max_rounds: int = 24,
        system_prompt: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.on_event = on_event or (lambda _kind, _payload: None)
        self.max_rounds = max_rounds
        self.history: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt or default_system_prompt()}
        ]
        self.usage = ContextUsage()
        self.usage.refresh_window(cfg)
        self._compacting = False
        self._last_api_usage: dict[str, Any] | None = None
        self.session_id: str | None = None
        self.refresh_usage(estimate_only=True)
        self.ensure_agents_md()

    def ensure_agents_md(self) -> bool:
        """会话首次加载：若存在 AGENTS.md 且尚未注入，则追加一条历史消息并返回 True。"""
        if any(m.get("xagent_meta") == AGENTS_MD_META for m in self.history):
            return False
        body = load_agents_md(PROJECT_ROOT)
        if not body:
            return False
        msg = {
            "role": "user",
            "content": (
                "【项目约定 AGENTS.md — 一次注入，后续轮次请直接遵循本条内容】\n\n"
                + body
            ),
            "xagent_meta": AGENTS_MD_META,
        }
        # 插在 system 之后，保证后续轮次稳定复用（利于缓存）
        if self.history and self.history[0].get("role") == "system":
            self.history.insert(1, msg)
        else:
            self.history.insert(0, msg)
        self._emit("agents_md_injected", chars=len(body))
        self.refresh_usage(estimate_only=True)
        return True

    def reset_session(self, *, keep_system: bool = True) -> None:
        """新建空会话（保留 system prompt）。"""
        system = None
        if keep_system:
            for m in self.history:
                if m.get("role") == "system":
                    system = dict(m)
                    break
        self.history = [system or {"role": "system", "content": default_system_prompt()}]
        self.session_id = None
        self._last_api_usage = None
        self.usage.clear_block()
        self.ensure_agents_md()
        self.refresh_usage(estimate_only=True)

    def load_history_messages(self, messages: list[dict[str, Any]]) -> None:
        """从已保存会话恢复 agent_history。"""
        if not messages:
            self.reset_session()
            return
        self.history = [dict(m) for m in messages]
        self._last_api_usage = None
        self.usage.clear_block()
        self.ensure_agents_md()
        self.refresh_usage(estimate_only=True)

    def _emit(self, kind: str, **payload: Any) -> None:
        self.on_event(kind, payload)

    def refresh_usage(self, *, estimate_only: bool = False) -> ContextUsage:
        self.usage.refresh_window(self.cfg)
        if estimate_only or not self._last_api_usage:
            self.usage.update_estimate(self.history, get_tools())
        elif not self.usage.update_from_api(self._last_api_usage):
            self.usage.update_estimate(self.history, get_tools())
        self._emit(
            "context_usage",
            used=self.usage.used_tokens,
            window=self.usage.window_tokens,
            percent=self.usage.percent,
            blocked=self.usage.blocked,
            is_default=self.usage.window_is_default,
            from_api=self.usage.from_api,
            line=self.usage.status_line(),
        )
        return self.usage

    def _build_payload(
        self,
        messages: list[dict],
        *,
        stream: bool = False,
        with_tools: bool = True,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.cfg["model"],
            "messages": messages,
            "temperature": self.cfg["temperature"],
            "stream": stream,
        }
        if with_tools:
            payload["tools"] = get_tools()
            payload["tool_choice"] = "auto"
        return payload

    def chat_once(
        self, messages: list[dict], *, with_tools: bool = True
    ) -> dict:
        url = f"{self.cfg['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg['api_key']}",
            "Content-Type": "application/json",
        }
        timeout = self.cfg["timeout"]
        if not with_tools:
            compact_to = float(
                self.cfg.get("compact_timeout_sec")
                or get_runtime_config().get("compact_timeout_sec")
                or 180
            )
            timeout = max(float(timeout), compact_to)
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                headers=headers,
                json=self._build_payload(messages, with_tools=with_tools),
            )
            resp.raise_for_status()
            data = resp.json()
        usage = data.get("usage")
        if isinstance(usage, dict):
            self._last_api_usage = usage
        return data["choices"][0]["message"]

    def chat_with_tools(self, messages: list[dict]) -> str:
        for _ in range(self.max_rounds):
            if self._compacting:
                raise RuntimeError("正在压缩上下文，禁止工具调用与普通对话")
            message = self.chat_once(messages, with_tools=True)
            self.refresh_usage()
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
                if self._compacting:
                    raise RuntimeError("正在压缩上下文，禁止工具调用")
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
        if self._compacting:
            raise RuntimeError("正在压缩上下文，请稍候")
        if self.usage.blocked:
            th = float(
                get_runtime_config().get("compact_threshold") or USAGE_THRESHOLD
            )
            raise RuntimeError(
                f"上下文已达窗口 {th:.0%} 限额，"
                "请先输入 /compact 完成压缩后再继续对话"
            )
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
        self.refresh_usage()
        return answer

    def compact(self) -> dict[str, Any]:
        """手动压缩：先归档 → 再 LLM 摘要 → 替换历史。失败则保留原上下文。"""
        if self._compacting:
            raise RuntimeError("压缩已在进行中")
        if len(self.history) <= 1:
            raise RuntimeError("当前几乎没有可压缩的对话历史")

        self._compacting = True
        self._emit("compact_start")
        before_text = messages_to_transcript(self.history)
        snapshot = [dict(m) for m in self.history]
        try:
            archive_id, archive_path = archive_messages(
                snapshot, project_root=PROJECT_ROOT
            )
            self._emit(
                "compact_archived",
                id=archive_id,
                path=str(archive_path),
            )

            transcript = messages_to_transcript(snapshot)
            compact_messages = [
                {"role": "system", "content": COMPACT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "以下是需要压缩的历史上下文（按时间顺序）。"
                        "请按系统要求输出 Markdown 摘要，不要调用任何工具。\n\n"
                        + transcript
                    ),
                },
            ]
            # 压缩期间禁止 Function Calling
            message = self.chat_once(compact_messages, with_tools=False)
            summary = (message.get("content") or "").strip()
            if not summary:
                raise RuntimeError("压缩模型返回空摘要")

            now = datetime.now()
            footer = build_archive_footer(archive_id, now)
            summary_with_note = summary + footer

            system_msg = snapshot[0] if snapshot and snapshot[0].get("role") == "system" else {
                "role": "system",
                "content": default_system_prompt(),
            }
            self.history = [
                system_msg,
                {
                    "role": "user",
                    "content": "请阅读以下压缩后的工作摘要，并据此继续协助我完成任务。",
                },
                {"role": "assistant", "content": summary_with_note},
            ]
            self.usage.clear_block()
            self.refresh_usage(estimate_only=True)
            result = {
                "ok": True,
                "archive_id": archive_id,
                "archive_path": str(archive_path),
                "before": before_text,
                "after": summary_with_note,
                "usage_line": self.usage.status_line(),
            }
            self._emit("compact_done", **result)
            return result
        except Exception as exc:
            # 失败：恢复快照
            self.history = snapshot
            self.refresh_usage(estimate_only=True)
            self._emit("compact_error", text=str(exc))
            raise
        finally:
            self._compacting = False
