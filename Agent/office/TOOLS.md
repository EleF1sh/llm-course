# TOOLS.md - 本地工具备忘

技能负责「怎么用工具」；这里只记**本机环境**约定。

## 路径

| 用途 | 路径 |
|------|------|
| 办公工作区 | `D:\LLM-Course\Agent\office` |
| 技能 | `D:\LLM-Course\Agent\office\.agents\skills` |
| 日记 | `D:\LLM-Course\Agent\office\memory` |
| 项目 | `D:\LLM-Course\Agent\office\projects` |
| 产出 | `D:\LLM-Course\Agent\office\output` |
| xAgent 代码 | `D:\LLM-Course\Agent\xAgent` |
| 课程根（文件工具沙箱） | `D:\LLM-Course` |

## 命令

```powershell
# 启动 xAgent
python "D:\LLM-Course\Agent\xAgent\run.py"
# 或双击：Agent\office\启动 xAgent.bat

# SkillHub（装到本工作区技能目录）
skillhub search <关键词>
skillhub install <slug> --namespace <ns> --dir "D:\LLM-Course\Agent\office\.agents\skills"
```

## 通知写作（notice）

- 技能根目录：`.agents/skills/notice`
- 脚本：`notice/scripts/`（事实表、校验、DOCX 套版等）
- 成稿与中间文件优先放到 `output/` 或 `projects/<主题>/`

## officecli（已收入技能目录）

- Skill：`.agents/skills/officecli/`
- 可执行文件：`.agents/skills/officecli/bin/officecli-win-x64.exe`
- 说明书：`.agents/skills/officecli/references/OfficeCli操作说明.md`
- 用法：先 `loadSkill name=officecli`，再 `RunCli` 调上述 exe
- 产出默认：`output\`
- 老师原来的 `Agent\新建文件夹\` 可不再使用（已复制进技能内）

## 备注

- Windows + PowerShell；优先用 `office\start-xagent.bat` 启动
- Python：优先 `%LocalAppData%\Programs\Python\Python313\python.exe`
