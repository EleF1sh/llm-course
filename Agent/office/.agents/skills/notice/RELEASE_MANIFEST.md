# RELEASE_MANIFEST

## Skill 信息

| 项目 | 值 |
|------|-----|
| Skill名称 | tongzhi-writer-v1.1-docx |
| 版本 | 1.1.0 (Pre-release) |
| 生成时间 | 2026-07-21 |

## 发布文件清单

| 文件 | 大小 | SHA-256（前32位） | 用途 |
|------|------|-------------------|------|
| SKILL.md | ~ | ~ | Skill定义与工作流 |
| README.md | ~ | ~ | 简要说明 |
| Skill使用说明.md | ~ | ~ | 详细使用文档 |
| CHANGELOG.md | ~ | ~ | 版本变更记录 |
| prompts/通知生成提示词.md | ~ | ~ | 通知写作核心规则 |
| prompts/统一事实一致性复核模板_V1.1.md | ~ | ~ | 事实一致性复核规则 |
| scripts/notice_document_factory.py | ~ | ~ | 运行时文档工厂（纯Python创建DOCX） |
| scripts/fill_tongzhi_docx.py | ~ | ~ | DOCX生成器（工厂模式） |
| scripts/preflight_check.py | ~ | ~ | 环境预检（无模板检查） |
| scripts/validate_notice_docx.py | ~ | ~ | DOCX校验器 |
| scripts/build_and_validate_notice.py | ~ | ~ | 统一交付管道 |

## 验证结果

| 检查项 | 结果 |
|--------|------|
| 绝对路径 | 无 ✅ |
| 测试文件 | 无 ✅ |
| 空目录 | 无 ✅ |
| 临时文件 | 无 ✅ |
| 开发版本命名 | 无 ✅ |
| 独立运行 | ✅ |
| 运行时工厂 | ✅ |
| DOCX生成 | ✅ |
| 无占位残留 | ✅ |
| 无Markdown残留 | ✅ |
| 无空Word段 | ✅ |
| 无不可见字符 | ✅ |
| preflight_check.py | ✅ |
| build_and_validate_notice.py | ✅ |
| 统一交付 ARTIFACT_READY | ✅ |
| 干净安装测试 | ✅ |

## 发布配置

```
binary_files_in_release: 0
binary_template_in_release: false
runtime_docx_output_supported: true
docx_template_mode: runtime_python_factory
template_implementation: scripts/notice_document_factory.py
preflight_check: scripts/preflight_check.py
generator: scripts/fill_tongzhi_docx.py
validator: scripts/validate_notice_docx.py
delivery_pipeline: scripts/build_and_validate_notice.py
final_artifact_required: true
markdown_only_delivery_allowed: false
```

本Skill发布包不包含二进制DOCX模板。页面、样式、页码和分页规则由 `scripts/notice_document_factory.py` 在运行时创建。

## 发布状态

已完成无二进制模板改造和干净安装测试，等待用户人工发布到SkillHub。
