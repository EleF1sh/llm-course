from __future__ import annotations

from typing import Any

# OpenAI-compatible function calling 本地工具定义（MCP 工具在运行时合并）
LOCAL_TOOLS: list[dict[str, Any]] = [
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
    {
        "type": "function",
        "function": {
            "name": "loadSkill",
            "description": (
                "按需加载项目 `.agents/skills` 中某个 Skill 的完整说明或附件。"
                "仅传 name 时返回该 Skill 的 SKILL.md 全文；"
                "同时传 filename 时只读取附件（不重复加载 SKILL.md）。"
                "需要遵循某技能流程、阅读其脚本/模板/提示词时必须调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Skill 名称（YAML frontmatter 的 name，或技能目录名）",
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "可选。相对于 Skill 目录、项目根的路径，或绝对路径；"
                            "也可只给文件名（在 Skill 目录内唯一时自动定位）"
                        ),
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createSkill",
            "description": (
                "根据用户自然语言需求，在当前项目 `.agents/skills/` 下新建一个 Skill。"
                "传入 name 与要写入 SKILL.md 的完整 skillContext（含 YAML frontmatter）。"
                "已存在同名技能时拒绝覆盖；额外目录/脚本请再用 makeDir、createFile 等文件工具创建。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Skill 名称：小写英文字母、数字与连字符，例如 meeting-notes"
                        ),
                    },
                    "skillContext": {
                        "type": "string",
                        "description": (
                            "写入 SKILL.md 的完整内容，须含 YAML frontmatter"
                            "（name、description）及正文说明"
                        ),
                    },
                },
                "required": ["name", "skillContext"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skillhubSearch",
            "description": (
                "在 SkillHub 商店搜索技能。"
                "用户要找技能、插件、扩展能力时必须调用；传入关键词 query。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如 calendar、pdf",
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
            "name": "skillhubInstall",
            "description": (
                "从 SkillHub 安装技能到当前项目根的 .agents/skills。"
                "用户确认安装某个技能后调用；传入 slug，可选 namespace。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "技能 slug，例如 calendar",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "可选命名空间，例如 clawhub_ndcccccc",
                    },
                },
                "required": ["slug"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skillhubList",
            "description": "列出当前项目 .agents/skills 中已发现的技能（name + description）。",
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
            "name": "createMCP",
            "description": (
                "根据用户提供的 MCP Server 配置，写入当前项目根目录的 `.mcp.json`。"
                "用户给出 ModelScope / 本地 MCP 的 url 或 stdio command 时必须调用。"
                "默认与已有配置合并并立即重连；可用 merge=false 整文件覆盖。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "configJson": {
                        "type": "string",
                        "description": (
                            "MCP 配置 JSON 字符串。可以是完整 "
                            '`{"mcpServers":{...}}`、仅 servers 映射，'
                            "或单个 server 对象（此时必须同时传 serverName）"
                        ),
                    },
                    "serverName": {
                        "type": "string",
                        "description": "单个 Server 的名称，例如 Bazi-MCP、PetHospitalMCP",
                    },
                    "type": {
                        "type": "string",
                        "description": "传输类型：streamable_http 或 stdio",
                    },
                    "url": {
                        "type": "string",
                        "description": "Streamable HTTP 的 MCP 端点 URL",
                    },
                    "command": {
                        "type": "string",
                        "description": "stdio 启动命令，例如 npx、python",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "stdio 命令参数列表",
                    },
                    "merge": {
                        "type": "boolean",
                        "description": "是否合并进已有 .mcp.json（默认 true）",
                    },
                    "reload": {
                        "type": "boolean",
                        "description": "写入后是否立即重连 MCP（默认 true）",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recallContext",
            "description": (
                "从项目 `.agents/context/` 归档中按关键词检索压缩前的原始上下文。"
                "当压缩摘要缺少细节、需要核对历史对话/工具结果时必须调用。"
                "text 为必填关键词；id 可选，指定归档编号（如 20261022-153000）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要查找的关键词或文本片段",
                    },
                    "id": {
                        "type": "string",
                        "description": "可选。归档编号，例如 20261022-153000（可省略 .jsonl）",
                    },
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
]

# 兼容旧导入名：仅本地工具；完整列表请用 get_tools()
TOOLS: list[dict[str, Any]] = LOCAL_TOOLS


def get_tools() -> list[dict[str, Any]]:
    """本地工具 + 已连接 MCP Server 动态注册的工具。"""
    try:
        from core.mcp_client import get_mcp_tools

        mcp_tools = get_mcp_tools()
    except Exception:
        mcp_tools = []
    if not mcp_tools:
        return list(LOCAL_TOOLS)
    return list(LOCAL_TOOLS) + list(mcp_tools)


def tool_names() -> list[str]:
    return [t["function"]["name"] for t in get_tools()]
