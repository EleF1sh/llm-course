from __future__ import annotations

from typing import Any

# OpenAI-compatible function calling 工具定义（来自 Practice02/chat_files.py）
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
                        "description": "目录路径，相对路径相对于课程根",
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
                    "directory": {"type": "string", "description": "目标目录路径"},
                    "filename": {"type": "string", "description": "新文件名"},
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
    {
        "type": "function",
        "function": {
            "name": "fetchpage",
            "description": (
                "抓取指定网页的正文内容并转为 Markdown。"
                "需要阅读/总结某个 URL 的网页正文、新闻、文档时必须调用；"
                "会去掉导航栏、广告、页脚等无关内容，保留标题、段落、列表、表格与链接。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "网页 URL，例如 https://example.com/article",
                    }
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "searchWeb",
            "description": (
                "使用百度千帆 AI 搜索检索互联网最新信息。"
                "需要查新闻、实时资讯、未知事实或开放问题时必须调用；"
                "传入搜索关键词或问题 query，返回摘要与参考来源标题、URL。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或问题，例如：今日北京天气",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "RunCli",
            "description": (
                "在本机以 subprocess（shell=False）运行任意已安装的 CLI 程序。"
                "需要执行系统命令、查看命令输出时调用；"
                "传入程序名 command 与参数列表 args，返回 stdout/stderr/exit_code。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "可执行程序名或路径，例如 python、git、curl",
                    },
                    "args": {
                        "type": "array",
                        "description": "命令行参数列表，每个元素为字符串，例如 [\"--version\"]",
                        "items": {"type": "string"},
                        "default": [],
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
]


def tool_names() -> list[str]:
    return [t["function"]["name"] for t in TOOLS]
