---
name: officecli
description: Use bundled officecli CLI to create/read/edit .docx .xlsx .pptx without Microsoft Office. Trigger when making or editing Word/Excel/PPT via officecli.
---

# officecli

本技能已内置可执行文件与说明书，**不要再使用** `Agent\新建文件夹\` 路径。

## 路径（相对本技能目录）

| 文件 | 位置 |
|------|------|
| 可执行文件 | `bin/officecli-win-x64.exe` |
| 操作说明 | `references/OfficeCli操作说明.md` |

绝对路径（从 office 项目根启动时）：

- `D:\LLM-Course\Agent\office\.agents\skills\officecli\bin\officecli-win-x64.exe`

需要读说明书时：`loadSkill`，`name=officecli`，`filename=references/OfficeCli操作说明.md`（或 `OfficeCli操作说明.md`）。

## 调用方式

始终用 `RunCli`：

- `command` = 上面的 **绝对路径**（推荐），或项目内相对路径拼到绝对路径
- `args` = officecli 参数列表，例如 `["help","pptx"]`、`["create","...\\output\\a.pptx"]`

## 规则

1. **不要猜参数**。先 `help` / `help pptx` / `help docx paragraph` 等。
2. 优先 L1（create/view/get/query）→ L2（add/set/remove）→ 必要时才 L3 raw。
3. 改完执行 `validate` 或 `view issues`。
4. 成稿默认写到项目 `output\`（如 `D:\LLM-Course\Agent\office\output\`）。
5. 交给 Word/WPS 打开前先 `close` 或 `save`。
6. 路径、XPath（如 `/slide[1]`）加引号。

## 专用场景

融资路演 / 学术论文 / 财务模型 / 看板 / Morph 动画等，先：

`RunCli` → `load_skill <name>`

按打印出的规则执行（每个成品只 load 一个专用 skill）。
