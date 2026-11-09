# 通知写作助手 V1.1

公文通知辅助写作 Skill，提供"信息检查→通知生成→事实复核→Markdown解析(NoticeModel)→DOCX渲染"完整工作流。

## 架构（Phase 1 收敛后）

```
Markdown → notice_model.py (唯一内容解析层)
         → NoticeModel
         → fill_tongzhi_docx.py (纯 Renderer)
         → validate_notice_docx.py (含语义校验)
```

- **notice_model.py**：标题提取、导语识别、正文结构化 —— 唯一内容权威来源
- **fill_tongzhi_docx.py**：DOCX 写入、标题视觉换行、样式调用 —— 不解析 Markdown
- **notice_document_factory.py**：排版底层，运行时创建 DOCX（冻结）

## 功能

- 通知文种生成
- 信息不足拦截（缺失关键事实时停止并追问）
- 事实冲突识别（不同来源数据不一致时拒绝生成）
- 事实一致性复核
- Markdown 到 DOCX 自动排版
- 公文标题语义断行（长标题自动划分视觉均衡行）
- 一级、二级结构排版（黑体/楷体区分）
- 长落款排版（语义断行、跨页保护）
- 多页自然分页（无手动分页符）

## 使用流程

```
提供材料
→ 信息完整性检查
→ 缺失或冲突则停止并追问
→ 生成通知
→ 事实一致性复核
→ 自动修订
→ DOCX 排版
→ 人工确认
```

## 数据安全提示

- 不在公开模型中输入未脱敏敏感数据
- 正式发文前人工复核
- 模型不得自行补写关键事实（日期、地点、人员、联系人等）

## 版本

当前版本：1.1.0 (Pre-release)

## 运行要求

- Python 3.8+
- python-docx >= 1.1.0（`pip install python-docx`）
- lxml（随 python-docx 自动安装）
- 对任务工作空间具有写入权限

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/preflight_check.py` | 环境预检 |
| `scripts/notice_model.py` | 唯一内容解析层（Markdown → NoticeModel） |
| `scripts/notice_document_factory.py` | 运行时文档工厂（纯Python创建DOCX，冻结） |
| `scripts/fill_tongzhi_docx.py` | DOCX纯Renderer（NoticeModel → DOCX） |
| `scripts/validate_notice_docx.py` | DOCX校验器（含语义校验） |
| `scripts/build_and_validate_notice.py` | 统一交付管道（唯一业务入口） |

本Skill发布包不包含二进制DOCX模板。页面、样式、页码和分页规则由 `scripts/notice_document_factory.py` 在运行时创建。

## 统一交付命令

```bash
python3 scripts/build_and_validate_notice.py \
  --source source.txt \
  --facts notice_facts.json \
  --input notice.md \
  --output notice.docx
```

管道自动完成：preflight → SHA-256核验 → Markdown事实复核 → Markdown解析(NoticeModel) → DOCX生成(Renderer) → DOCX事实复核 → DOCX结构校验(含语义) → ARTIFACT_READY

成功时输出：`ARTIFACT_READY=/path/to/notice.docx`
