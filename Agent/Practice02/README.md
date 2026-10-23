# Practice02

命令行 LLM Agent（OpenAI 兼容 function calling）。本目录有两套入口：

| 文件 | 说明 |
|------|------|
| `chat.py` | 基础版：`getDate` + `isLeapYear` |
| `chat_files.py` | 完整版：上述 2 个 + **10 个本地文件工具** |
| `chat_files_architecture.mmd` | `chat_files.py` 的 Mermaid 架构图 |

---

## 准备

```powershell
cd D:\LLM-Course\Agent\Practice02
copy config.ini.example config.ini
# 编辑 config.ini：base_url / api_key / model（需支持 tools）
pip install -r requirements.txt
```

也可复制 `..\Practice01\config.ini`。`config.ini` 已被仓库 `.gitignore` 忽略。

---

## `chat_files.py` 架构说明

### 运行流程

1. `main()` 读取 `config.ini`，初始化带 system 提示的 `history`
2. 用户输入 → `chat_with_tools()` 循环（最多 8 轮工具往返）
3. `chat_once()` → `build_payload()`（附带全部 `TOOLS`）→ HTTP `POST /chat/completions`
4. 若返回 `tool_calls`：`run_tool()` 本地执行 → 把 `role=tool` 结果写回 history → 再请求模型
5. 无工具调用时输出最终文本回答

架构图见同目录 **`chat_files_architecture.mmd`**（可用 [Mermaid Live](https://mermaid.live) 打开预览）。

### 工具一览

| 工具 | 作用 | 实现 |
|------|------|------|
| `getDate` | 本机日期时间 | 本地 `date` / `time` 命令（非 Python `datetime`） |
| `isLeapYear` | 是否闰年 | Python 计算（参数 `year`） |
| `getCwd` | 当前工作目录 | Python `Path.cwd()` |
| `listDir` | 列目录 | Python `pathlib` |
| `getFileType` | 文件/目录类型与 MIME | Python `mimetypes` |
| `readFile` | 读纯文本 | Python；二进制拒绝 |
| `createFile` | 指定目录新建文件 | Python |
| `editFile` | 覆盖写纯文本 | Python；二进制拒绝 |
| `makeDir` | 建目录 | Python |
| `removeDir` | 删目录（含非空） | Python `shutil.rmtree` |
| `removeFile` | 删文件 | Python |
| `renamePath` | 重命名文件/目录 | Python |

### 安全约束

- 所有文件路径必须落在 **`D:\LLM-Course`**（`WORKSPACE_ROOT`）内，越界返回错误 JSON
- 禁止删除课程根目录本身
- `readFile` / `editFile` 对疑似二进制文件拒绝操作
- 单文件读取上限约 20 万字符，避免撑爆上下文

### 关键函数

- `load_config` / `build_payload` / `chat_once` / `chat_with_tools`：对话与 Agent 循环
- `run_tool` / `_parse_tool_args`：工具名分发与参数解析
- `_resolve_in_workspace` / `_path_or_err`：路径沙箱
- `_ok` / `_err`：统一 JSON 结果格式

---

## 运行

```powershell
# 仅日期 + 闰年
python chat.py

# 含文件操作（作业完整版）
python chat_files.py
```

### 建议试用提示词

- 「现在几点」「2024 是闰年吗」
- 「当前工作目录」「列出 Agent 目录」
- 「在 Agent/Practice02 下创建 _demo，再新建 a.txt 写入 hello」
- 「读一下 Agent/Practice02/_demo/a.txt」

课程验收示例提示词（把文件名换成本地真实名）：

> 基于 `@Agent/Practice02/chat_files.py` 创作代码架构图，使用 Mermaid 格式，保存为 .mmd 格式纯文本文件。基于代码更新 README.md 文件。

本目录已提供对应产物：`chat_files_architecture.mmd` + 本 README。
