from __future__ import annotations

import json
import mimetypes
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.config import WORKSPACE_ROOT, load_baidu_qianfan_api_key

TEXT_READ_LIMIT = 200_000


def _ok(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _err(message: str, **extra: Any) -> str:
    payload: dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _resolve_in_workspace(path_str: str) -> Path:
    raw = Path(path_str)
    if not raw.is_absolute():
        raw = WORKSPACE_ROOT / raw
    resolved = raw.resolve()
    try:
        resolved.relative_to(WORKSPACE_ROOT)
    except ValueError as exc:
        raise PermissionError(
            f"路径不允许越出课程目录 {WORKSPACE_ROOT}: {resolved}"
        ) from exc
    return resolved


def _path_or_err(path_str: str) -> Path | str:
    try:
        return _resolve_in_workspace(path_str)
    except PermissionError as exc:
        return _err(str(exc))


def _looks_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
    nontext = sample.translate(None, text_chars)
    return float(len(nontext)) / float(len(sample)) > 0.30


def getDate() -> str:
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
    return _ok({"cwd": str(Path.cwd().resolve()), "workspace_root": str(WORKSPACE_ROOT)})


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


FETCHPAGE_MARKDOWN_LIMIT = 80_000


def fetchpage(url: str) -> str:
    """用本地 curl 拉取 HTML，再用 trafilatura 抽取正文 Markdown。"""
    target = (url or "").strip()
    if not target:
        return _err("缺少参数 url")
    if not (target.startswith("http://") or target.startswith("https://")):
        return _err("url 必须以 http:// 或 https:// 开头", url=target)

    curl_bin = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_bin:
        return _err("未找到本地 curl，请先安装并加入 PATH")

    completed = subprocess.run(
        [
            curl_bin,
            "-fsSL",
            "--max-time",
            "30",
            "-A",
            "xAgent-fetchpage/1.0",
            "--compressed",
            target,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    html = completed.stdout or ""
    err = (completed.stderr or "").strip()
    if completed.returncode != 0 or not html.strip():
        return _err(
            f"curl 抓取失败 (code={completed.returncode}): {err or 'empty body'}",
            url=target,
        )

    try:
        import trafilatura
    except ImportError:
        return _err("未安装 trafilatura，请执行: pip install trafilatura")

    markdown = trafilatura.extract(
        html,
        url=target,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_images=False,
        favor_recall=False,
    )
    if not markdown or not str(markdown).strip():
        return _err("未能从页面抽取正文（可能是空页或反爬）", url=target)

    text = str(markdown).strip()
    truncated = False
    if len(text) > FETCHPAGE_MARKDOWN_LIMIT:
        text = text[:FETCHPAGE_MARKDOWN_LIMIT] + "\n\n...(truncated)"
        truncated = True

    return _ok(
        {
            "url": target,
            "markdown": text,
            "chars": len(text),
            "truncated": truncated,
        }
    )


QIANFAN_WEB_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


def searchWeb(query: str) -> str:
    """调用百度千帆 AI 搜索，返回摘要与参考来源标题/URL。"""
    q = (query or "").strip()
    if not q:
        return _err("缺少参数 query")

    api_key = load_baidu_qianfan_api_key()
    if not api_key or api_key == "replace-me":
        return _err(
            "未配置百度千帆搜索密钥：请在 config.ini 的 [search] 节填写 "
            "baidu_qianfan_api_key"
        )

    payload = {
        "messages": [{"role": "user", "content": q}],
        "search_source": "baidu_search_v2",
        "edition": "standard",
        "resource_type_filter": [{"type": "web", "top_k": 10}],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        import httpx
    except ImportError:
        return _err("未安装 httpx，请执行: pip install httpx")

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(QIANFAN_WEB_SEARCH_URL, headers=headers, json=payload)
    except httpx.TimeoutException:
        return _err("百度千帆搜索请求超时", query=q)
    except httpx.RequestError as exc:
        return _err(f"网络请求失败: {exc}", query=q)

    try:
        data = resp.json()
    except Exception:
        return _err(
            f"API 返回非 JSON (HTTP {resp.status_code})",
            query=q,
            body=(resp.text or "")[:500],
        )

    if resp.status_code >= 400 or data.get("code") not in (None, 0, "0"):
        msg = data.get("message") or data.get("error_msg") or resp.text or "unknown error"
        return _err(
            f"百度千帆搜索失败 (HTTP {resp.status_code}): {msg}",
            query=q,
            code=data.get("code"),
            request_id=data.get("request_id") or data.get("requestId"),
        )

    references = data.get("references") or []
    sources: list[dict[str, Any]] = []
    summaries: list[str] = []
    for item in references:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("web_anchor") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(
            item.get("snippet") or item.get("content") or ""
        ).strip()
        if title or url:
            sources.append({"title": title, "url": url})
        if snippet:
            label = title or url or "来源"
            summaries.append(f"- {label}: {snippet[:400]}")

    if not sources and not summaries:
        return _err("搜索成功但无可用结果", query=q, request_id=data.get("request_id"))

    summary_text = "\n".join(summaries) if summaries else "(无摘要，仅有来源列表)"
    return _ok(
        {
            "query": q,
            "summary": summary_text,
            "sources": sources,
            "count": len(sources),
            "request_id": data.get("request_id") or data.get("requestId"),
        }
    )


RUNCLI_TIMEOUT_SEC = 30
RUNCLI_OUTPUT_LIMIT = 12_000


def _truncate_cli_output(text: str, limit: int = RUNCLI_OUTPUT_LIMIT) -> tuple[str, bool]:
    raw = text or ""
    if len(raw) <= limit:
        return raw, False
    return raw[:limit] + "\n...(truncated)", True


def RunCli(command: str, args: list[str] | None = None) -> str:
    """用 subprocess 列表方式（shell=False）运行本地 CLI。"""
    cmd = (command or "").strip()
    if not cmd:
        return _err("缺少参数 command")

    argv: list[str] = [cmd]
    if args is None:
        pass
    elif isinstance(args, str):
        # 容错：偶发把单个参数当成字符串传入
        if args.strip():
            argv.append(args.strip())
    elif isinstance(args, list):
        for item in args:
            argv.append(str(item))
    else:
        return _err("参数 args 必须是字符串数组", got=type(args).__name__)

    try:
        completed = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUNCLI_TIMEOUT_SEC,
            check=False,
        )
    except FileNotFoundError:
        return _err(f"找不到可执行程序: {cmd}", command=cmd, args=argv[1:])
    except subprocess.TimeoutExpired as exc:
        out, out_cut = _truncate_cli_output((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        err, err_cut = _truncate_cli_output((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return _err(
            f"命令超时（>{RUNCLI_TIMEOUT_SEC}s）",
            command=cmd,
            args=argv[1:],
            stdout=out,
            stderr=err,
            stdout_truncated=out_cut,
            stderr_truncated=err_cut,
            exit_code=None,
        )
    except OSError as exc:
        return _err(f"无法启动进程: {exc}", command=cmd, args=argv[1:])

    stdout, stdout_cut = _truncate_cli_output(completed.stdout or "")
    stderr, stderr_cut = _truncate_cli_output(completed.stderr or "")
    return _ok(
        {
            "command": cmd,
            "args": argv[1:],
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": completed.returncode,
            "stdout_truncated": stdout_cut,
            "stderr_truncated": stderr_cut,
            "timeout_sec": RUNCLI_TIMEOUT_SEC,
        }
    )


def parse_tool_args(arguments: str | dict | None) -> dict[str, Any]:
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
    args = parse_tool_args(arguments)
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
        if name == "fetchpage":
            return fetchpage(str(args.get("url", "")))
        if name == "searchWeb":
            return searchWeb(str(args.get("query", "")))
        if name == "RunCli":
            raw_args = args.get("args", [])
            return RunCli(str(args.get("command", "")), raw_args if isinstance(raw_args, list) else raw_args)
        return _err(f"unknown tool: {name}")
    except PermissionError as exc:
        return _err(str(exc))
    except (TypeError, ValueError) as exc:
        return _err(f"参数错误: {exc}")
    except OSError as exc:
        return _err(f"系统错误: {exc}")
