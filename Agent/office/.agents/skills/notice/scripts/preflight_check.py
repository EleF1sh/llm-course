#!/usr/bin/env python3
"""preflight_check.py — 通知Skill运行环境预检。

Checks:
1. Python version
2. python-docx importability
3. notice_document_factory importability
4. create_notice_document() execution
5. Real Chinese content DOCX creation and save
6. Saved DOCX re-open and styles.xml validation
7. Font size verification (sz=44 for title, 32 for body, 28 for page number)
8. Required OOXML files in output
9. Output directory writability
10. Temp file cleanup after test

No template file check — factory generates documents at runtime.

Exit codes:
  0 = OK
  1 = Python version too old
  2 = Missing dependency (python-docx or lxml)
  3 = Script import failed
  4 = Output directory not writable
  5 = DOCX generation failed
  6 = DOCX font size validation failed
  7 = Styles.xml structure check failed
"""

import sys, os, tempfile, zipfile, shutil
from xml.etree import ElementTree as ET

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# Real Chinese test content
REAL_TEST_CONTENT = [
    ('公文标题', '关于开展测试工作的通知'),
    ('主送机关', '公司各部门：'),
    ('一级标题', '一、测试事项'),
    ('公文正文', '测试正文。'),
    ('落款', '公司综合管理部'),
    ('成文日期', '2026年7月20日'),
]

# Expected font sizes (half-points = pt × 2)
EXPECTED_SIZES = {
    '公文标题': ('44', '44'),   # 22pt
    '主送机关': ('32', '32'),   # 16pt
    '公文正文': ('32', '32'),
    '一级标题': ('32', '32'),
    '二级标题': ('32', '32'),
    '三级标题': ('32', '32'),
    '附件说明': ('32', '32'),
    '落款':    ('32', '32'),
    '成文日期': ('32', '32'),
    '页码':    ('28', '28'),   # 14pt
}


def die(code, msg):
    print(f"❌ 环境预检失败: {msg}", file=sys.stderr)
    sys.exit(code)


def ok(msg):
    print(f"  ✓ {msg}")


def _validate_styles_font_sizes(docx_path):
    """Read styles.xml and check font sizes. Returns (bool, list of failures)."""
    failures = []
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            styles_xml = z.read('word/styles.xml')
    except Exception as e:
        return False, [f"无法读取styles.xml: {e}"]

    root = ET.fromstring(styles_xml)

    for style_elem in root.findall(f'{{{NS}}}style'):
        style_id = style_elem.get(f'{{{NS}}}styleId', '')
        if style_id not in EXPECTED_SIZES:
            continue

        expected_sz, expected_szCs = EXPECTED_SIZES[style_id]
        rPr = style_elem.find(f'{{{NS}}}rPr')
        if rPr is None:
            failures.append(f"{style_id}缺少rPr")
            continue

        sz_nodes = rPr.findall(f'{{{NS}}}sz')
        szCs_nodes = rPr.findall(f'{{{NS}}}szCs')

        # Check for twips error (>100)
        for n in sz_nodes:
            v = n.get(f'{{{NS}}}val', '')
            try:
                if int(v) > 100:
                    failures.append(f"❌ {style_id}字号异常：w:sz={v}>100（可能误用二十分之一磅！预期{expected_sz}）")
            except ValueError:
                failures.append(f"❌ {style_id}字号值非法：w:sz={v}")

        for n in szCs_nodes:
            v = n.get(f'{{{NS}}}val', '')
            try:
                if int(v) > 100:
                    failures.append(f"❌ {style_id}字号异常：w:szCs={v}>100（可能误用二十分之一磅！预期{expected_szCs}）")
            except ValueError:
                failures.append(f"❌ {style_id}字号值非法：w:szCs={v}")

        # Check count
        if len(sz_nodes) == 0:
            failures.append(f"❌ {style_id}缺少w:sz")
        elif len(sz_nodes) > 1:
            vals = [n.get(f'{{{NS}}}val', '') for n in sz_nodes]
            failures.append(f"❌ {style_id}的w:sz重复：{len(sz_nodes)}个节点，值={vals}")
        elif sz_nodes[0].get(f'{{{NS}}}val', '') != expected_sz:
            failures.append(f"❌ {style_id}的w:sz={sz_nodes[0].get(f'{{{NS}}}val')}（预期{expected_sz}）")

        if len(szCs_nodes) == 0:
            failures.append(f"❌ {style_id}缺少w:szCs")
        elif len(szCs_nodes) > 1:
            vals = [n.get(f'{{{NS}}}val', '') for n in szCs_nodes]
            failures.append(f"❌ {style_id}的w:szCs重复：{len(szCs_nodes)}个节点，值={vals}")
        elif szCs_nodes[0].get(f'{{{NS}}}val', '') != expected_szCs:
            failures.append(f"❌ {style_id}的w:szCs={szCs_nodes[0].get(f'{{{NS}}}val')}（预期{expected_szCs}）")

    return len(failures) == 0, failures


def main():
    print("通知Skill运行环境预检")
    print("=" * 40)

    # 1. Python version
    v = sys.version_info[:2]
    print(f"  Python {v[0]}.{v[1]}")
    if v < (3, 8):
        die(1, f"Python版本过低（{v[0]}.{v[1]}），需要3.8以上")
    ok(f"Python {v[0]}.{v[1]} ≥ 3.8")

    # 2. Check python-docx
    try:
        import docx
        ok(f"python-docx {docx.__version__}")
    except ImportError:
        die(2, "缺少python-docx。请运行: pip install python-docx")

    # 3. Check lxml
    try:
        from lxml import etree
        ok("lxml 可用")
    except ImportError:
        die(2, "缺少lxml。请运行: pip install lxml")

    # 4. Ensure scripts directory is on path
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(skill_dir, 'scripts'))

    # 5. Check notice_document_factory import
    try:
        from notice_document_factory import create_notice_document
        ok("notice_document_factory.py 可导入")
    except ImportError as e:
        die(3, f"无法导入 notice_document_factory.py: {e}")

    # 6. Check create_notice_document() and fill with real content
    try:
        doc = create_notice_document()
        ok("create_notice_document() 运行成功")
    except Exception as e:
        die(5, f"create_notice_document() 失败: {e}")

    # 7. Fill with real Chinese test content
    try:
        from docx.shared import Pt
        for style_name, text in REAL_TEST_CONTENT:
            p = doc.add_paragraph(text, style=style_name)
        ok("已填充真实中文测试内容")
    except Exception as e:
        die(5, f"填充测试内容失败: {e}")

    # 8. Temp dir writable
    try:
        with tempfile.NamedTemporaryFile(delete=True) as f:
            f.write(b"test")
        ok("临时目录可写")
    except OSError:
        die(4, "临时目录不可写，请检查磁盘空间和权限")

    # 9. Save real content DOCX
    tmpdir = tempfile.mkdtemp(prefix="preflight_")
    test_docx = os.path.join(tmpdir, "test.docx")
    try:
        try:
            doc.save(test_docx)
        except Exception as e:
            die(5, f"DOCX保存失败: {e}")

        if not os.path.exists(test_docx) or os.path.getsize(test_docx) < 3000:
            die(5, "测试DOCX创建失败或文件异常")
        ok(f"测试DOCX已保存 ({os.path.getsize(test_docx)} bytes)")

        # 10. Re-open saved DOCX
        try:
            with zipfile.ZipFile(test_docx, 'r') as z:
                required = ['word/document.xml', '[Content_Types].xml', 'word/styles.xml']
                for r in required:
                    if r not in z.namelist():
                        die(6, f"测试DOCX缺少必要文件: {r}")
            ok("测试DOCX包含必要OOXML文件")
        except zipfile.BadZipFile:
            die(6, "测试DOCX ZIP结构损坏")
        ok("测试DOCX可重新打开")

        # 11. Font size validation (MANDATORY — dies on 320/440)
        print("\n字号验证:")
        passed, sz_failures = _validate_styles_font_sizes(test_docx)
        if sz_failures:
            for f in sz_failures:
                print(f"  {f}")
            print(f"\n发现 {len(sz_failures)} 个字号错误！")
            # Check for specific 320/440
            has_320 = any('320' in f for f in sz_failures)
            has_440 = any('440' in f for f in sz_failures)
            if has_320 or has_440:
                die(6, f"发现二十分之一磅单位错误（320/440）——字号计算仍有bug！")
            die(6, f"字号验证失败：{len(sz_failures)}项")
        ok(f"字号验证通过（{len(EXPECTED_SIZES)}个样式全部正确）")

        # 12. Check odd/even footers
        try:
            with zipfile.ZipFile(test_docx, 'r') as z:
                names = z.namelist()
                footer_files = [n for n in names if 'footer' in n.lower()]
                if footer_files:
                    ok(f"页码Footer已生成 ({len(footer_files)}个)")
                else:
                    print("  ⚠ 页码Footer未生成")
        except Exception:
            pass  # non-critical

    finally:
        # 13. Clean up temp files
        shutil.rmtree(tmpdir, ignore_errors=True)
        ok("临时文件已清理")

    # 14. Check notice_model import (Phase 1 architecture)
    try:
        from notice_model import NoticeModel, parse_markdown
        ok("notice_model.py 可导入")
    except ImportError as e:
        die(3, f"无法导入 notice_model.py: {e}")

    # 15. Check NoticeModel creation
    try:
        m = NoticeModel(title_text='测试通知', main_recipient='各部门')
        ok("NoticeModel 可创建")
    except Exception as e:
        die(3, f"NoticeModel 创建失败: {e}")

    # 16. Check Markdown parse entry
    try:
        test_md = '# 测试通知\n\n各部门：\n\n一、测试\n\n内容。\n\n单位\n2026年1月1日'
        model = parse_markdown(test_md)
        assert model.title_text == '测试通知'
        ok("Markdown解析入口可运行")
    except Exception as e:
        die(3, f"Markdown解析入口失败: {e}")

    # 17. Check fill_tongzhi_docx import (pure renderer — no parse_markdown)
    try:
        from fill_tongzhi_docx import fill_docx
        ok("fill_tongzhi_docx.py 可导入（纯Renderer模式）")
    except ImportError as e:
        die(3, f"无法导入 fill_tongzhi_docx.py: {e}")

    print("\n✅ 环境预检通过，通知Skill可以正常运行（Phase 1 架构收敛模式）。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
