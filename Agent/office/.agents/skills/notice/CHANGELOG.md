# Changelog

## 1.3.0 (内部generator版本)

- 新增 `scripts/create_notice_facts.py` 通用事实清单创建脚本
  - 从原始材料文件计算真实source_sha256（二进制字节）
  - 不信任draft中预先填写的source_sha256
  - 原子写入（临时文件+替换）
  - 输出不得位于Skill安装目录
- 重写 `scripts/fact_check_notice.py` 强制SHA-256核验
  - 新增--source必填参数（所有生产模式）
  - 读取source原始字节计算SHA-256
  - 使用hmac.compare_digest安全比较
  - 哈希失败立即终止，不继续Markdown/DOCX校验
  - 输出SOURCE_SHA256_MISMATCH和FACT_VALIDATION_FAILED
- 修改 `scripts/build_and_validate_notice.py` 管道
  - 新增--source必填参数
  - SHA-256核验在DOCX生成之前
  - 哈希失败时不创建DOCX，不输出ARTIFACT_READY
  - Markdown和DOCX事实复核均传入同一个--source
- 更新SKILL.md工作流
- 新增tests/test_source_sha256.py完整测试套件
- 新增测试fixtures（原始材料文件、事实草稿文件）
- 填入fixture facts的真实source_sha256

## 1.2.0 (内部generator版本)

- 完成无二进制模板改造：删除 `templates/通知正文模板.docx`
- 新建 `scripts/notice_document_factory.py` 运行时文档工厂
  - 纯Python代码创建A4公文页面、正式页边距、文档网格
  - 奇偶页不同，奇数页右侧页码，偶数页左侧页码（真实PAGE域）
  - 所有公文样式（方正小标宋/黑体/楷体/仿宋）通过代码定义
  - 不读取任何DOCX/DOTX/ZIP或二进制模板
- `fill_tongzhi_docx.py` 彻底删除模板依赖
  - 移除 TEMPLATE_PATH、--template 参数
  - 移除 ZipFile 模板读写、模板回退逻辑
  - 改用 `create_notice_document()` 创建文档
- `preflight_check.py` 删除模板文件存在性检查和ZIP结构检查
  - 改为检查 python-docx、lxml、工厂导入和最小DOCX生成
- `build_and_validate_notice.py` 确认不传递模板参数
- 更新所有文档：不再提及二进制模板
- `RELEASE_MANIFEST.md` 标记 binary_files_in_release: 0

## 1.1.0

- 完成通知文种正式发布整理
- 增加信息不足和事实冲突拦截
- 修复模板占位和重复标题问题
- 修复Markdown空行生成空Word段问题
- 改进长标题语义断行（一个段落内真实换行）
- 改进长落款单页与跨页保护（一个段落内真实换行）
- 修复一级标题页尾孤行（heading1无条件keepNext）
- 改进混合二级标题与正文的自然分页（双run格式，无keepLines）
- 修复邮箱不可见字符（U+2060/U+200B/U+FEFF）导致的WPS异常间距
- 联系方式使用零首行缩进
- 附件项使用公文正文样式（不加粗）
- 使用Markdown作为正式正文输入源
- 移除测试输出、调试文件和本机硬编码路径

## 1.0.0

- 开发与测试版本
- 已归档为 tongzhi-writer-v1.0-test
- 不作为正式发布版本
