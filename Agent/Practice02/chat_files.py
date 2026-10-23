from __future__ import annotations

import configparser
import json
import mimetypes
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

CONFIG_PATH = Path(__file__).with_name("config.ini")
# 文件工具只允许操作本课程仓库，防止误改系统目录
WORKSPACE_ROOT = Path(r"D:\LLM-Course").resolve()
TEXT_READ_LIMIT = 200_000  # 单文件最多读这么多字符，避免一次塞爆上下文

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": (
                "获取当前电脑的本地日期和时间。"
                "询问今天几号、现在几点、当前日期/时间时必须调用，不要猜测。"
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
                "判断指定公历年份是否为闰年。询问某年是否闰年时必须调用，传入 year。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "公历年份，例如 2024",
                    }
                },
                "required": ["year"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getCwd",
            "description": "获取当前工作目录（Python Path.cwd）。",
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
            "name": "listDir",
            "description": "列出指定目录下的文件与子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，相对路径相对于课程根 D:\\LLM-Course",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定路径是文件还是目录，以及后缀、MIME 等类型信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录路径"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "读取指定纯文本文件内容。二进制文件会拒绝。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文本文件路径"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "在指定目录下新建文件（可写初始内容）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "目标目录路径",
                    },
                    "filename": {
                        "type": "string",
                        "description": "新文件名，例如 note.txt",
                    },
                    "content": {
                        "type": "string",
                        "description": "可选初始文本内容，默认空",
                    },
                },
                "required": ["directory", "filename"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "覆盖写入指定纯文本文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "已有文本文件路径"},
                    "content": {"type": "string", "description": "要写入的完整文本"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "makeDir",
            "description": "创建新目录（可递归创建中间目录）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要创建的目录路径"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "removeDir",
            "description": "删除目录；非空目录也会整棵删除（仅限课程仓库内）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的目录路径"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "removeFile",
            "description": "删除指定文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的文件路径"}
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renamePath",
            "description": "重命名文件或目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "原路径"},
                    "dst": {"type": "string", "description": "新路径"},
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
]


def _ok(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _err(message: str, **extra: Any) -> str:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _resolve_in_workspace(path_str: str) -> Path:
    """把用户路径解析到绝对路径，并强制落在 WORKSPACE_ROOT 内。"""
    raw = Path(path_str)
    if not raw.is_absolute():
        raw = WORKSPACE_ROOT / raw
    resolved = raw.resolve()
    root = WORKSPACE_ROOT
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(
            f"路径不允许越出课程目录 {root}: {resolved}"
        ) from exc
    return resolved


def _path_or_err(path_str: str) -> Path | str:
    """成功返回 Path；越界等权限问题返回错误 JSON 字符串。"""
    try:
        return _resolve_in_workspace(path_str)
    except PermissionError as exc:
        return _err(str(exc))


def _looks_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    # 高比例不可打印字节则视为二进制
    if not sample:
        return False
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
    nontext = sample.translate(None, text_chars)
    return float(len(nontext)) / float(len(sample)) > 0.30


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
    y = int(year)
    leap = (y % 4 == 0) and (y % 100 != 0 or y % 400 == 0)
    return _ok(
        {
            "year": y,
            "is_leap_year": leap,
            "days_in_year": 366 if leap else 365,
            "february_days": 29 if leap else 28,
        }
    )


def getCwd() -> str:
    cwd = Path.cwd().resolve()
    return _ok({"cwd": str(cwd), "workspace_root": str(WORKSPACE_ROOT)})


def listDir(path: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return _err("路径不存在", path=str(target))
    if not target.is_dir():
        return _err("不是目录", path=str(target))
    entries = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "kind": "dir" if child.is_dir() else "file",
                "size": None if child.is_dir() else child.stat().st_size,
            }
        )
    return _ok({"path": str(target), "count": len(entries), "entries": entries})


def getFileType(path: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return _err("路径不存在", path=str(target))
    if target.is_dir():
        return _ok(
            {
                "path": str(target),
                "kind": "directory",
                "suffix": "",
                "mime": "inode/directory",
            }
        )
    mime, encoding = mimetypes.guess_type(str(target))
    return _ok(
        {
            "path": str(target),
            "kind": "file",
            "suffix": target.suffix,
            "mime": mime or "application/octet-stream",
            "encoding_hint": encoding,
            "size": target.stat().st_size,
        }
    )


def readFile(path: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return _err("文件不存在", path=str(target))
    if not target.is_file():
        return _err("不是文件", path=str(target))
    sample = target.read_bytes()[:8192]
    if _looks_binary(sample):
        return _err("拒绝读取：看起来是二进制文件", path=str(target))
    text = target.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > TEXT_READ_LIMIT
    if truncated:
        text = text[:TEXT_READ_LIMIT]
    return _ok(
        {
            "path": str(target),
            "content": text,
            "truncated": truncated,
            "chars": len(text),
        }
    )


def createFile(directory: str, filename: str, content: str = "") -> str:
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        return _err("filename 必须是单层文件名，不能含路径分隔符", filename=filename)
    folder = _path_or_err(directory)
    if isinstance(folder, str):
        return folder
    if folder.exists() and not folder.is_dir():
        return _err("directory 不是目录", path=str(folder))
    folder.mkdir(parents=True, exist_ok=True)
    target = _path_or_err(str(folder / filename))
    if isinstance(target, str):
        return target
    if target.exists():
        return _err("文件已存在", path=str(target))
    target.write_text(content if content is not None else "", encoding="utf-8")
    return _ok({"created": str(target), "bytes": target.stat().st_size})


def editFile(path: str, content: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return _err("文件不存在", path=str(target))
    if not target.is_file():
        return _err("不是文件", path=str(target))
    sample = target.read_bytes()[:8192]
    if sample and _looks_binary(sample):
        return _err("拒绝编辑：看起来是二进制文件", path=str(target))
    target.write_text(content if content is not None else "", encoding="utf-8")
    return _ok({"edited": str(target), "bytes": target.stat().st_size})


def makeDir(path: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if target.exists():
        if target.is_dir():
            return _ok({"path": str(target), "created": False, "message": "目录已存在"})
        return _err("路径已存在且不是目录", path=str(target))
    target.mkdir(parents=True, exist_ok=False)
    return _ok({"path": str(target), "created": True})


def removeDir(path: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if target == WORKSPACE_ROOT:
        return _err("禁止删除课程根目录", path=str(target))
    if not target.exists():
        return _err("目录不存在", path=str(target))
    if not target.is_dir():
        return _err("不是目录（删文件请用 removeFile）", path=str(target))
    shutil.rmtree(target)
    return _ok({"removed_dir": str(target)})


def removeFile(path: str) -> str:
    target = _path_or_err(path)
    if isinstance(target, str):
        return target
    if not target.exists():
        return _err("文件不存在", path=str(target))
    if not target.is_file():
        return _err("不是文件（删目录请用 removeDir）", path=str(target))
    target.unlink()
    return _ok({"removed_file": str(target)})


def renamePath(src: str, dst: str) -> str:
    source = _path_or_err(src)
    if isinstance(source, str):
        return source
    dest = _path_or_err(dst)
    if isinstance(dest, str):
        return dest
    if not source.exists():
        return _err("源路径不存在", src=str(source))
    if dest.exists():
        return _err("目标路径已存在", dst=str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    return _ok({"from": str(source), "to": str(dest)})


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
    args = _parse_tool_args(arguments)
    try:
        if name == "getDate":
            return getDate()
        if name == "isLeapYear":
            if "year" not in args:
                return _err("缺少参数 year")
            return isLeapYear(int(args["year"]))
        if name == "getCwd":
            return getCwd()
        if name == "listDir":
            return listDir(str(args.get("path", "")))
        if name == "getFileType":
            return getFileType(str(args.get("path", "")))
        if name == "readFile":
            return readFile(str(args.get("path", "")))
        if name == "createFile":
            return createFile(
                str(args.get("directory", "")),
                str(args.get("filename", "")),
                str(args.get("content", "")),
            )
        if name == "editFile":
            return editFile(str(args.get("path", "")), str(args.get("content", "")))
        if name == "makeDir":
            return makeDir(str(args.get("path", "")))
        if name == "removeDir":
            return removeDir(str(args.get("path", "")))
        if name == "removeFile":
            return removeFile(str(args.get("path", "")))
        if name == "renamePath":
            return renamePath(str(args.get("src", "")), str(args.get("dst", "")))
        return _err(f"unknown tool: {name}")
    except PermissionError as exc:
        return _err(str(exc))
    except (TypeError, ValueError) as exc:
        return _err(f"参数错误: {exc}")
    except OSError as exc:
        return _err(f"系统错误: {exc}")


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


def chat_with_tools(cfg: dict, messages: list[dict], *, max_rounds: int = 8) -> str:
    for _ in range(max_rounds):
        message = chat_once(cfg, messages)
        tool_calls = message.get("tool_calls") or []

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
                result = _err(f"tool error: {exc}")
            # 控制台预览别太长
            preview = result if len(result) <= 800 else result[:800] + "...(truncated)"
            _safe_print(f"[tool result] {preview}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "content": result,
                }
            )

    return "工具调用轮次过多，已停止。"


def _safe_print(text: str = "", end: str = "\n", flush: bool = False) -> None:
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
                "你是简洁友好的中文助手，可以调用本地工具。"
                "问当前日期/时间时必须调用 getDate；"
                "问某年是否闰年时必须调用 isLeapYear；"
                "涉及本地文件/目录的查看、创建、修改、删除、重命名时，"
                "必须调用对应文件工具（getCwd/listDir/getFileType/readFile/"
                "createFile/editFile/makeDir/removeDir/removeFile/renamePath），"
                "不要假装已经操作过文件系统。"
                f"所有文件路径都应落在课程目录 {WORKSPACE_ROOT} 内；"
                "相对路径相对于该目录理解。"
            ),
        }
    ]

    tool_names = [t["function"]["name"] for t in TOOLS]
    _safe_print("Practice02 文件工具版已启动。Ctrl+C 退出。")
    _safe_print(f"model={cfg['model']}")
    _safe_print(f"workspace={WORKSPACE_ROOT}")
    _safe_print(f"tools={', '.join(tool_names)}")

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
            while history and history[-1].get("role") != "user":
                history.pop()
            if history and history[-1].get("role") == "user":
                history.pop()
            continue
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
