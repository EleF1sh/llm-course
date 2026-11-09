"""上下文压缩、归档与关键词检索（无向量库的简易方案）。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import (
    COMPACT_TARGET_TOKENS,
    COMPACT_THRESHOLD,
    DEFAULT_CONTEXT_WINDOW,
    PROJECT_ROOT,
    RECALL_MAX_CHARS,
    RECALL_MAX_HITS,
    get_runtime_config,
)

# 兼容旧名
TARGET_SUMMARY_TOKENS = COMPACT_TARGET_TOKENS
USAGE_THRESHOLD = COMPACT_THRESHOLD

COMPACT_SYSTEM_PROMPT = """你是一名 AI Agent 的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便 Agent 在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约 5,000 Tokens 的 Markdown 摘要。

摘要应重点保留以下内容：

1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent 正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和 Agent 已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：

- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过 `recallContext` 工具重新检索。
- 使用清晰的 Markdown 结构输出摘要，不要附加解释或无关内容。

**最终目标：使一个从未阅读过原始对话的 Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。**"""

# 常见模型窗口（token）；未知则用默认并标记「默认」
_MODEL_WINDOWS: dict[str, int] = {
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.1-mini": 1_047_576,
    "claude-3-5-sonnet": 200_000,
    "claude-sonnet-4": 200_000,
    "qwen-plus": 131_072,
    "qwen-max": 131_072,
}


def context_dir(project_root: Path | None = None) -> Path:
    root = (project_root or PROJECT_ROOT).resolve()
    path = root / ".agents" / "context"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_archive_id(now: datetime | None = None) -> str:
    dt = now or datetime.now()
    return dt.strftime("%Y%m%d-%H%M%S")


def resolve_context_window(cfg: dict[str, Any]) -> tuple[int, bool]:
    """返回 (窗口大小, 是否为默认值)。"""
    raw = cfg.get("context_window")
    if raw is not None:
        try:
            n = int(raw)
            if n > 0:
                return n, False
        except (TypeError, ValueError):
            pass
    model = str(cfg.get("model") or "").strip().lower()
    for key, size in _MODEL_WINDOWS.items():
        if key in model:
            return size, False
    default_win = int(
        cfg.get("default_context_window")
        or get_runtime_config().get("default_context_window")
        or DEFAULT_CONTEXT_WINDOW
    )
    return default_win, True


def estimate_text_tokens(text: str) -> int:
    """粗估：中文偏多按 ~1.5 字/token，英文按 ~4 字符/token，取偏保守值。"""
    if not text:
        return 0
    # 统计 CJK
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = max(0, len(text) - cjk)
    return max(1, int(cjk / 1.5 + other / 4))


def _message_to_text(msg: dict[str, Any]) -> str:
    parts: list[str] = []
    role = msg.get("role", "")
    parts.append(f"role={role}")
    content = msg.get("content")
    if content is not None:
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append(json.dumps(content, ensure_ascii=False))
    if msg.get("tool_calls"):
        parts.append(json.dumps(msg["tool_calls"], ensure_ascii=False))
    if msg.get("tool_call_id"):
        parts.append(f"tool_call_id={msg['tool_call_id']}")
    if msg.get("name"):
        parts.append(f"name={msg['name']}")
    return "\n".join(parts)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        total += estimate_text_tokens(_message_to_text(msg))
        total += 4  # 角色/分隔开销
    return total


def estimate_tools_tokens(tools: list[dict[str, Any]] | None) -> int:
    if not tools:
        return 0
    return estimate_text_tokens(json.dumps(tools, ensure_ascii=False))


def format_tokens_k(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return str(n)


def archive_messages(
    messages: list[dict[str, Any]],
    *,
    archive_id: str | None = None,
    project_root: Path | None = None,
) -> tuple[str, Path]:
    """把完整消息列表写入 `.agents/context/{id}.jsonl`。成功后返回 (id, path)。"""
    aid = archive_id or new_archive_id()
    path = context_dir(project_root) / f"{aid}.jsonl"
    meta = {
        "type": "meta",
        "id": aid,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "message_count": len(messages),
    }
    lines = [json.dumps(meta, ensure_ascii=False)]
    for i, msg in enumerate(messages):
        record = {
            "type": "message",
            "index": i,
            "role": msg.get("role"),
            "content": msg.get("content"),
        }
        if "tool_calls" in msg:
            record["tool_calls"] = msg["tool_calls"]
        if "tool_call_id" in msg:
            record["tool_call_id"] = msg["tool_call_id"]
        if "name" in msg:
            record["name"] = msg["name"]
        lines.append(json.dumps(record, ensure_ascii=False))
    # 先写临时文件再替换，保证「成功保存」才算完成
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise OSError(f"归档写入失败: {path}")
    return aid, path


def messages_to_transcript(messages: list[dict[str, Any]]) -> str:
    """供压缩 LLM 阅读的纯文本转录。"""
    chunks: list[str] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        header = f"### [{i}] {role}"
        body_parts: list[str] = []
        content = msg.get("content")
        if content:
            body_parts.append(
                content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            )
        if msg.get("tool_calls"):
            body_parts.append(
                "tool_calls:\n"
                + json.dumps(msg["tool_calls"], ensure_ascii=False, indent=2)
            )
        if msg.get("tool_call_id"):
            body_parts.append(f"tool_call_id: {msg['tool_call_id']}")
        chunks.append(header + "\n" + "\n".join(body_parts))
    return "\n\n".join(chunks)


def build_archive_footer(archive_id: str, when: datetime | None = None) -> str:
    dt = when or datetime.now()
    stamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"\n\n此前上下文已于 {stamp} 完成压缩，"
        f"原始上下文保存在编号为 {archive_id} 的归档文件中。"
        f"如需查找历史信息，请使用 recallContext 工具。"
    )


def _tokenize_query(text: str) -> list[str]:
    raw = (text or "").strip().lower()
    if not raw:
        return []
    # 空格/标点拆词；保留长度>=2 的片段，外加整句
    parts = re.split(r"[\s,，。；;、|/\\]+", raw)
    tokens = [p for p in parts if len(p) >= 2]
    if raw not in tokens:
        tokens.insert(0, raw)
    return tokens


def _score_line(haystack: str, tokens: list[str]) -> int:
    h = haystack.lower()
    score = 0
    for t in tokens:
        if t in h:
            score += h.count(t) * max(1, len(t))
    return score


def recall_context(
    text: str,
    *,
    archive_id: str | None = None,
    project_root: Path | None = None,
    max_hits: int | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """本地关键词检索归档。"""
    query = (text or "").strip()
    if not query:
        return {"ok": False, "error": "参数 text 不能为空"}

    rt = get_runtime_config()
    if max_hits is None:
        max_hits = int(rt.get("recall_max_hits") or RECALL_MAX_HITS)
    if max_chars is None:
        max_chars = int(rt.get("recall_max_chars") or RECALL_MAX_CHARS)

    root = context_dir(project_root)
    tokens = _tokenize_query(query)
    files: list[Path]
    if archive_id:
        aid = archive_id.strip().removesuffix(".jsonl")
        path = root / f"{aid}.jsonl"
        if not path.is_file():
            return {"ok": False, "error": f"归档不存在: {aid}", "id": aid}
        files = [path]
    else:
        files = sorted(root.glob("*.jsonl"), key=lambda p: p.name, reverse=True)

    hits: list[dict[str, Any]] = []
    for path in files:
        aid = path.stem
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            hits.append({"id": aid, "error": str(exc)})
            continue
        scored: list[tuple[int, int, str]] = []
        for line_no, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            score = _score_line(line, tokens)
            if score <= 0:
                continue
            scored.append((score, line_no, line))
        scored.sort(key=lambda x: (-x[0], x[1]))
        for score, line_no, line in scored[:max_hits]:
            # 截断过长行
            snippet = line if len(line) <= 800 else line[:800] + "…"
            hits.append(
                {
                    "id": aid,
                    "line": line_no,
                    "score": score,
                    "snippet": snippet,
                }
            )

    hits.sort(key=lambda h: (-int(h.get("score") or 0), str(h.get("id")), int(h.get("line") or 0)))
    hits = hits[:max_hits]

    # 控制总长度
    out_hits: list[dict[str, Any]] = []
    used = 0
    for h in hits:
        snip = str(h.get("snippet") or "")
        if used + len(snip) > max_chars and out_hits:
            break
        out_hits.append(h)
        used += len(snip)

    return {
        "ok": True,
        "query": query,
        "id": archive_id.strip().removesuffix(".jsonl") if archive_id else None,
        "searched_files": len(files),
        "hit_count": len(out_hits),
        "hits": out_hits,
        "note": "结果已截断，可缩小关键词或指定 id 精确检索"
        if len(hits) > len(out_hits) or len(files) > 1
        else "",
    }


class ContextUsage:
    """会话上下文用量状态。"""

    def __init__(self) -> None:
        self.used_tokens: int = 0
        self.window_tokens: int = DEFAULT_CONTEXT_WINDOW
        self.window_is_default: bool = True
        self.from_api: bool = False
        self.blocked: bool = False
        self.warn_shown: bool = False

    @property
    def ratio(self) -> float:
        if self.window_tokens <= 0:
            return 0.0
        return self.used_tokens / self.window_tokens

    @property
    def percent(self) -> float:
        return round(self.ratio * 100, 1)

    def refresh_window(self, cfg: dict[str, Any]) -> None:
        self.window_tokens, self.window_is_default = resolve_context_window(cfg)

    def update_from_api(self, usage: dict[str, Any] | None) -> bool:
        if not usage:
            return False
        # 优先 total；否则 prompt+completion；再否则 prompt
        total = usage.get("total_tokens")
        if total is None:
            pt = usage.get("prompt_tokens")
            ct = usage.get("completion_tokens")
            if pt is not None or ct is not None:
                total = int(pt or 0) + int(ct or 0)
        if total is None:
            return False
        self.used_tokens = int(total)
        self.from_api = True
        self._apply_threshold()
        return True

    def update_estimate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        self.used_tokens = estimate_messages_tokens(messages) + estimate_tools_tokens(
            tools
        )
        self.from_api = False
        self._apply_threshold()

    def _apply_threshold(self) -> None:
        threshold = float(
            get_runtime_config().get("compact_threshold") or USAGE_THRESHOLD
        )
        if self.ratio >= threshold:
            self.blocked = True
        # 压缩成功后由外部 clear_block

    def clear_block(self) -> None:
        self.blocked = False
        self.warn_shown = False

    def status_line(self) -> str:
        used_k = format_tokens_k(self.used_tokens)
        win_k = format_tokens_k(self.window_tokens)
        default_tag = "「默认」" if self.window_is_default else ""
        src = "API" if self.from_api else "估算"
        return f"上下文 {used_k} / {win_k}{default_tag} · {self.percent:.1f}%（{src}）"
