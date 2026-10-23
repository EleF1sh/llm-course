from __future__ import annotations

import configparser
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

CONFIG_PATH = Path(__file__).with_name("config.ini")

# OpenAI-compatible function calling tool definitions
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": (
                "获取当前电脑的本地日期和时间。"
                "当用户询问今天几号、现在几点、当前日期/时间时必须调用本工具，"
                "不要自行猜测时间。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": (
                "判断指定公历年份是否为闰年。"
                "当用户询问某年是不是闰年、某年有多少天、2月有几天（需结合该年）时，"
                "必须调用本工具，不要自行心算。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的公历年份，例如 2024",
                    }
                },
                "required": ["year"],
                "additionalProperties": False,
            },
        },
    },
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"缺少 {CONFIG_PATH.name}。请复制 config.ini.example 为 config.ini 并填写。"
        )
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH, encoding="utf-8")
    section = parser["llm"]
    return {
        "base_url": section.get("base_url", "https://api.openai.com/v1").rstrip("/"),
        "api_key": section.get("api_key", ""),
        "model": section.get("model", "gpt-4o-mini"),
        "temperature": section.getfloat("temperature", 0.7),
        "timeout": section.getfloat("timeout", 60),
    }


def getDate() -> str:
    """通过本地 date 命令读取本机日期时间（不用 Python datetime）。"""
    system = platform.system()
    if system == "Windows":
        # Windows 的 date 无 /t 会进入交互改日期；用 date /t + time /t 取日期时间
        completed = subprocess.run(
            ["cmd", "/c", "date /t & time /t"],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            check=False,
        )
    else:
        completed = subprocess.run(
            ["date"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    out = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    if completed.returncode != 0 and not out:
        raise RuntimeError(f"date 命令失败 (code={completed.returncode}): {err or 'no output'}")
    if err and not out:
        return err
    return out or err or "(empty)"


def isLeapYear(year: int) -> str:
    """用 Python 计算公历年是否闰年（不调用外部命令）。"""
    y = int(year)
    # 能被 4 整除；世纪年须能被 400 整除
    leap = (y % 4 == 0) and (y % 100 != 0 or y % 400 == 0)
    return json.dumps(
        {
            "year": y,
            "is_leap_year": leap,
            "days_in_year": 366 if leap else 365,
            "february_days": 29 if leap else 28,
            "rule": "divisible by 4, except centuries not divisible by 400",
        },
        ensure_ascii=False,
    )


def _parse_tool_args(arguments: str | dict | None) -> dict[str, Any]:
    if arguments is None or arguments == "":
        return {}
    if isinstance(arguments, dict):
        return arguments
    try:
        data = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def run_tool(name: str, arguments: str | dict | None = None) -> str:
    """Dispatch function-call tools by name."""
    if name == "getDate":
        return getDate()
    if name == "isLeapYear":
        args = _parse_tool_args(arguments)
        if "year" not in args:
            return json.dumps(
                {"error": "missing required argument: year"},
                ensure_ascii=False,
            )
        try:
            year = int(args["year"])
        except (TypeError, ValueError):
            return json.dumps(
                {"error": "year must be an integer", "got": args.get("year")},
                ensure_ascii=False,
            )
        return isLeapYear(year)
    return json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)


def build_payload(cfg: dict, messages: list[dict], *, stream: bool = False) -> dict:
    return {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg["temperature"],
        "stream": stream,
        "tools": TOOLS,
        "tool_choice": "auto",
    }


def chat_once(cfg: dict, messages: list[dict]) -> dict:
    """Non-streaming chat completion; returns the assistant message object."""
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=cfg["timeout"]) as client:
        resp = client.post(url, headers=headers, json=build_payload(cfg, messages))
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]


def chat_with_tools(cfg: dict, messages: list[dict], *, max_rounds: int = 4) -> str:
    """
    Agent loop: model may call getDate / isLeapYear; we run the tool locally
    and feed the result back until a normal text answer is produced.
    """
    for _ in range(max_rounds):
        message = chat_once(cfg, messages)
        tool_calls = message.get("tool_calls") or []

        # Normalize assistant message for history (keep tool_calls if any)
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": message.get("content") or "",
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if not tool_calls:
            return (message.get("content") or "").strip()

        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            _safe_print(f"\n[tool] {name}({raw_args})")
            try:
                result = run_tool(name, raw_args)
            except Exception as exc:
                result = f"tool error: {exc}"
            _safe_print(f"[tool result] {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "content": result,
                }
            )

    return "工具调用轮次过多，已停止。"


def _safe_print(text: str = "", end: str = "\n", flush: bool = False) -> None:
    """Print text even when the Windows console encoding rejects some characters."""
    try:
        print(text, end=end, flush=flush)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        data = (text + end).encode(enc, errors="replace")
        sys.stdout.buffer.write(data)
        if flush:
            sys.stdout.flush()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cfg = load_config()
    if not cfg["api_key"] or cfg["api_key"] == "replace-me":
        _safe_print("请先在 config.ini 填写有效的 api_key / base_url / model。")
        sys.exit(1)

    history: list[dict] = [
        {
            "role": "system",
            "content": (
                "你是一个简洁、友好的中文助手。"
                "当用户询问当前日期、时间、今天几号、现在几点时，"
                "必须调用 getDate 工具，不要自己编造时间。"
                "当用户询问某年是否闰年时，必须调用 isLeapYear 工具，"
                "传入 year 参数，不要自己心算。"
            ),
        }
    ]

    _safe_print(
        "Practice02 多轮对话（getDate + isLeapYear）已启动。输入内容回车发送；Ctrl+C 退出。"
    )
    _safe_print(
        f"model={cfg['model']} | tools=getDate(date命令), isLeapYear(Python计算)"
    )

    while True:
        try:
            user = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            _safe_print("\n再见。")
            break
        if not user:
            continue
        history.append({"role": "user", "content": user})
        _safe_print("助手: ", end="", flush=True)
        try:
            answer = chat_with_tools(cfg, history)
            _safe_print(answer)
        except Exception as exc:
            _safe_print(f"\n[错误] {exc}")
            # 回滚本轮 user，避免脏历史
            while history and history[-1].get("role") != "user":
                history.pop()
            if history and history[-1].get("role") == "user":
                history.pop()
            continue
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
