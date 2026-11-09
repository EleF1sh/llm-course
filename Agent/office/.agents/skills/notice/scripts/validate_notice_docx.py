#!/usr/bin/env python3
"""validate_notice_docx.py — 通知 DOCX 最终校验器（含 Phase 1 语义校验）。

Checks: file integrity, OOXML structure, content quality, format standards,
font size precision, footer references, section properties, and semantic validation.
"""

import sys, os, argparse, zipfile, re, json
from xml.etree import ElementTree as ET

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

REQUIRED_XML = [
    '[Content_Types].xml',
    'word/document.xml',
    'word/styles.xml',
]

BAD_CHARS = {'\u2060': 'U+2060', '\u200B': 'U+200B', '\uFEFF': 'U+FEFF'}
PLACEHOLDER_TEXTS = ['[公文标题]', '[主送机关]', '[正文段落]', '[正文段2]', '[发文单位]', '[日期]']
QINGSHI_KW = ['请示', '请批示', '妥否', '以上请示', '特此请示', '请予审批']

# Phrases that must NOT be split in title
TITLE_NO_BREAK = [
    '人工智能', '辅助办公', '数据脱敏', '工具培训',
    '专项检查', '工作会议', '实施方案', '中期检查',
    '的通知',
]

# ── Font size expectations (half-points = pt × 2) ──
EXPECTED_FONT_SIZES = {
    '公文标题': ('44', '44'),   # 22pt × 2
    '主送机关': ('32', '32'),   # 16pt × 2
    '公文正文': ('32', '32'),
    '一级标题': ('32', '32'),
    '二级标题': ('32', '32'),
    '三级标题': ('32', '32'),
    '附件说明': ('32', '32'),
    '联系方式': ('32', '32'),
    '落款':    ('32', '32'),
    '成文日期': ('32', '32'),
    '页码':    ('28', '28'),   # 14pt × 2
}

# ── Preamble detection regex ──
PREAMBLE_RE = re.compile(r'通知如下[：:]?$')


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: strip whitespace, normalize internal spaces."""
    return re.sub(r'\s+', '', text)


def _validate_font_sizes(path, failures):
    """Validate font sizes in word/styles.xml."""
    try:
        with zipfile.ZipFile(path, 'r') as z:
            styles_xml = z.read('word/styles.xml')
    except Exception as e:
        failures.append(f"无法读取word/styles.xml: {e}")
        return

    root = ET.fromstring(styles_xml)

    for style_elem in root.findall(f'{{{NS}}}style'):
        style_id = style_elem.get(f'{{{NS}}}styleId', '')
        if style_id not in EXPECTED_FONT_SIZES:
            continue

        expected_sz, expected_szCs = EXPECTED_FONT_SIZES[style_id]

        rPr = style_elem.find(f'{{{NS}}}rPr')
        if rPr is None:
            failures.append(f"{style_id}缺少rPr")
            continue

        sz_nodes = rPr.findall(f'{{{NS}}}sz')
        szCs_nodes = rPr.findall(f'{{{NS}}}szCs')

        sz_vals = [n.get(f'{{{NS}}}val', '') for n in sz_nodes]
        szCs_vals = [n.get(f'{{{NS}}}val', '') for n in szCs_nodes]

        for v in sz_vals:
            try:
                if int(v) > 100:
                    failures.append(f"{style_id}字号异常：w:sz={v}（预期{expected_sz}），可能误用了二十分之一磅单位")
            except ValueError:
                failures.append(f"{style_id}字号值非法：w:sz={v}")

        for v in szCs_vals:
            try:
                if int(v) > 100:
                    failures.append(f"{style_id}字号异常：w:szCs={v}（预期{expected_szCs}），可能误用了二十分之一磅单位")
            except ValueError:
                failures.append(f"{style_id}字号值非法：w:szCs={v}")

        if len(sz_nodes) == 0:
            failures.append(f"{style_id}缺少w:sz")
        elif len(sz_nodes) > 1:
            failures.append(f"{style_id}的w:sz重复：{len(sz_nodes)}个节点，值={sz_vals}")
        elif sz_vals[0] != expected_sz:
            failures.append(f"{style_id}的w:sz={sz_vals[0]}（预期{expected_sz}）")

        if len(szCs_nodes) == 0:
            failures.append(f"{style_id}缺少w:szCs")
        elif len(szCs_nodes) > 1:
            failures.append(f"{style_id}的w:szCs重复：{len(szCs_nodes)}个节点，值={szCs_vals}")
        elif szCs_vals[0] != expected_szCs:
            failures.append(f"{style_id}的w:szCs={szCs_vals[0]}（预期{expected_szCs}）")

    if not any('字号' in f or 'w:sz' in f for f in failures):
        print(f"  ✓ 字号检查通过（{len(EXPECTED_FONT_SIZES)}个样式）")
    else:
        print(f"  ⚠ 字号检查发现{sum(1 for f in failures if '字号' in f or 'w:sz' in f)}个问题")


def _validate_section_and_footers(path, failures):
    """Validate section properties and footer references."""
    try:
        with zipfile.ZipFile(path, 'r') as z:
            names = z.namelist()
            doc_xml = z.read('word/document.xml')
            settings_xml = z.read('word/settings.xml') if 'word/settings.xml' in names else None
            footer_files = [n for n in names if 'footer' in n.lower() and n.endswith('.xml')]
    except Exception as e:
        failures.append(f"无法读取DOCX结构: {e}")
        return

    doc_root = ET.fromstring(doc_xml)
    body = doc_root.find(f'{{{NS}}}body')
    if body is None:
        return

    sectPr = body.find(f'{{{NS}}}sectPr')
    if sectPr is None:
        failures.append("缺少sectPr")
        return

    footer_refs = sectPr.findall(f'{{{NS}}}footerReference')
    has_default = any(fr.get(f'{{{NS}}}type') == 'default' for fr in footer_refs)
    has_even = any(fr.get(f'{{{NS}}}type') == 'even' for fr in footer_refs)
    if not has_default:
        failures.append("sectPr缺少default footerReference")
    if not has_even:
        failures.append("sectPr缺少even footerReference")
    if has_default and has_even:
        print(f"  ✓ footerReference: default + even")

    if sectPr.find(f'{{{NS}}}evenAndOddHeaders') is not None:
        failures.append("sectPr中不应包含evenAndOddHeaders（应在word/settings.xml中）")

    if settings_xml is not None:
        settings_root = ET.fromstring(settings_xml)
        if settings_root.find(f'{{{NS}}}evenAndOddHeaders') is not None:
            print(f"  ✓ evenAndOddHeaders在settings.xml中")
        else:
            failures.append("word/settings.xml缺少evenAndOddHeaders")
    else:
        failures.append("缺少word/settings.xml")

    if sectPr.find(f'{{{NS}}}titlePg') is not None:
        failures.append("sectPr中不应包含titlePg")

    doc_grids = sectPr.findall(f'{{{NS}}}docGrid')
    if len(doc_grids) == 0:
        failures.append("sectPr缺少docGrid")
    elif len(doc_grids) > 1:
        failures.append(f"sectPr中docGrid重复：{len(doc_grids)}个（预期1）")
    else:
        print(f"  ✓ docGrid: 1")

    page_found = False
    for fn in footer_files:
        try:
            with zipfile.ZipFile(path, 'r') as z2:
                footer_xml = z2.read(fn)
        except Exception:
            continue
        footer_root = ET.fromstring(footer_xml)
        fld_chars = footer_root.findall(f'.//{{{NS}}}fldChar')
        instr_texts = footer_root.findall(f'.//{{{NS}}}instrText')
        has_begin = any(fc.get(f'{{{NS}}}fldCharType') == 'begin' for fc in fld_chars)
        has_page = any('PAGE' in (it.text or '') for it in instr_texts)
        if has_begin and has_page:
            page_found = True
            print(f"  ✓ {fn}: 含PAGE域")
            break
    if footer_files and not page_found:
        failures.append("页脚中未发现PAGE域")


# ══════════════════════════════════════════════════════════════════
# Phase 1: Semantic validation against NoticeModel
# ══════════════════════════════════════════════════════════════════

def _validate_semantic(paras, model_data, failures):
    """Perform semantic validation: title count, title text, preamble count, preamble content."""
    if model_data is None:
        print("  ⚠ 未提供 --model，跳过语义校验")
        return

    def get_text(p):
        return ''.join(t.text or '' for t in p.findall(f'.//{{{NS}}}t'))

    def get_style(p):
        ps = p.find(f'{{{NS}}}pPr/{{{NS}}}pStyle')
        return ps.get(f'{{{NS}}}val', '') if ps is not None else ''

    # ── Title count: must be 1 ──
    title_paras = [p for p in paras if get_style(p) == '公文标题']
    title_count = len(title_paras)

    if title_count == 0:
        failures.append("SEMANTIC: DOCX中缺少公文标题（数量=0，预期=1）")
    elif title_count > 1:
        failures.append(f"SEMANTIC: DOCX中标题数量={title_count}（预期=1）")
    else:
        print(f"  ✓ 语义-标题数量: 1")

        # ── Title text completeness ──
        docx_title_raw = get_text(title_paras[0])
        docx_title_norm = _normalize_text(docx_title_raw)
        model_title_norm = _normalize_text(model_data.get('title_text', ''))

        if docx_title_norm != model_title_norm:
            failures.append(
                f"SEMANTIC: DOCX标题与NoticeModel不一致\n"
                f"    DOCX: {docx_title_raw[:60]}\n"
                f"    Model: {model_data.get('title_text', '')[:60]}"
            )
        else:
            print(f"  ✓ 语义-标题完整: 与NoticeModel一致")

    # ── Preamble count: must be 1 ──
    preamble_paras = []
    for p in paras:
        st = get_style(p)
        text = get_text(p).strip()
        if st == '公文正文' and PREAMBLE_RE.search(text):
            preamble_paras.append(p)

    preamble_count = len(preamble_paras)

    if preamble_count == 0:
        failures.append("SEMANTIC: DOCX中缺少导语（数量=0，预期=1）")
    elif preamble_count > 1:
        failures.append(f"SEMANTIC: DOCX中导语数量={preamble_count}（预期=1）")
    else:
        print(f"  ✓ 语义-导语数量: 1")

        # ── Preamble content check ──
        docx_preamble = get_text(preamble_paras[0]).strip()
        model_preamble = model_data.get('preamble', '').strip()

        if docx_preamble != model_preamble:
            failures.append(
                f"SEMANTIC: DOCX导语与NoticeModel不一致\n"
                f"    DOCX: {docx_preamble[:60]}\n"
                f"    Model: {model_preamble[:60]}"
            )
        else:
            print(f"  ✓ 语义-导语内容: 与NoticeModel一致")


# ══════════════════════════════════════════════════════════════════
# Main validation
# ══════════════════════════════════════════════════════════════════

def validate(path, model_path=None):
    failures = []
    model_data = None

    # ── Load model if provided ──
    if model_path and os.path.exists(model_path):
        with open(model_path, 'r', encoding='utf-8') as f:
            model_data = json.load(f)
        print(f"  ✓ NoticeModel已加载: {model_path}")
    elif model_path:
        print(f"  ⚠ NoticeModel文件不存在: {model_path}")

    print(f"校验: {path}")

    # ── File checks ──
    if not os.path.exists(path):
        failures.append("文件不存在")
        return failures
    if not path.endswith('.docx'):
        failures.append(f"后缀不是.docx: {path}")
        return failures
    sz = os.path.getsize(path)
    if sz < 30000:
        failures.append(f"文件大小异常 ({sz} bytes)")
        return failures
    print(f"  ✓ 文件存在, {sz} bytes")

    # ── ZIP checks ──
    try:
        with zipfile.ZipFile(path, 'r') as z:
            names = z.namelist()
            doc_xml = z.read('word/document.xml')
    except zipfile.BadZipFile:
        failures.append("ZIP结构损坏")
        return failures
    except KeyError:
        failures.append("缺少 word/document.xml")
        return failures

    for r in REQUIRED_XML:
        if r not in names:
            failures.append(f"缺少: {r}")
        else:
            print(f"  ✓ {r}")
    if failures:
        return failures

    # ── Content checks ──
    root = ET.fromstring(doc_xml)
    body = root.find(f'{{{NS}}}body')
    if body is None:
        failures.append("缺少 body 元素")
        return failures

    def get_text(p):
        return ''.join(t.text or '' for t in p.findall(f'.//{{{NS}}}t'))

    def get_style(p):
        ps = p.find(f'{{{NS}}}pPr/{{{NS}}}pStyle')
        return ps.get(f'{{{NS}}}val', '') if ps is not None else ''

    def has_keep_next(p):
        return p.find(f'{{{NS}}}pPr/{{{NS}}}keepNext') is not None

    def has_keep_lines(p):
        return p.find(f'{{{NS}}}pPr/{{{NS}}}keepLines') is not None

    def has_br(p):
        return len(p.findall(f'.//{{{NS}}}br')) > 0

    def get_text_before_br(p):
        runs = list(p.findall(f'{{{NS}}}r'))
        text_parts = []
        for r in runs:
            br = r.find(f'{{{NS}}}br')
            if br is not None:
                break
            t = r.find(f'{{{NS}}}t')
            if t is not None and t.text:
                text_parts.append(t.text)
        return ''.join(text_parts)

    def get_text_after_br(p):
        runs = list(p.findall(f'{{{NS}}}r'))
        text_parts = []
        found_br = False
        for r in runs:
            br = r.find(f'{{{NS}}}br')
            if br is not None:
                found_br = True
                continue
            if found_br:
                t = r.find(f'{{{NS}}}t')
                if t is not None and t.text:
                    text_parts.append(t.text)
        return ''.join(text_parts)

    paras = list(body.findall(f'{{{NS}}}p'))
    all_text = ''.join(get_text(p) for p in paras)

    # ── Empty paragraph check ──
    empty_paras = []
    for i, p in enumerate(paras):
        text = get_text(p).strip()
        if not text:
            empty_paras.append(i + 1)
    if empty_paras:
        failures.append(f"存在{len(empty_paras)}个空Word段落（第{empty_paras}段）")

    # Empty content
    if not all_text.strip():
        failures.append("正文为空")

    # Placeholder check
    for ph in PLACEHOLDER_TEXTS:
        if ph in all_text:
            failures.append(f"残留模板占位: {ph}")

    # Markdown check
    if '# ' in all_text:
        failures.append("残留Markdown标题符号")

    # 请示 check
    for kw in QINGSHI_KW:
        if kw in all_text:
            failures.append(f"残留请示词汇: {kw}")

    # Bad chars (general)
    for ch, name in BAD_CHARS.items():
        if ch in all_text:
            failures.append(f"含不可见字符: {name}")

    # Style presence
    styles_used = set(get_style(p) for p in paras)
    print(f"  ✓ 样式: {sorted(styles_used)}")

    required_styles = ['公文标题', '主送机关', '公文正文', '落款', '成文日期']
    for rs in required_styles:
        if rs not in styles_used:
            failures.append(f"缺少样式: {rs}")

    # ── Title semantic break check ──
    title_paras = [p for p in paras if get_style(p) == '公文标题']
    if not title_paras:
        failures.append("缺少公文标题")
    else:
        title_text = get_text(title_paras[0])
        if len(title_text) < 4:
            failures.append(f"标题过短: {title_text}")
        print(f"  ✓ 标题: {title_text[:40]}")

        if has_br(title_paras[0]):
            before = get_text_before_br(title_paras[0])
            after = get_text_after_br(title_paras[0])
            for phrase in TITLE_NO_BREAK:
                combined = before + after
                idx = combined.find(phrase)
                if idx >= 0:
                    if idx < len(before) < idx + len(phrase):
                        failures.append(f"标题在词组'{phrase}'内部换行")
            print(f"  ✓ 标题断行: {before} / {after}")
        else:
            print(f"  ✓ 标题单行")

    # ── Preamble existence check ──
    preamble_ok = False
    recipient_idx = None
    first_h1_idx = None
    for i, p in enumerate(paras):
        st = get_style(p)
        if st == '主送机关':
            recipient_idx = i
        elif st == '一级标题' and first_h1_idx is None:
            first_h1_idx = i

    if recipient_idx is not None and first_h1_idx is not None and first_h1_idx > recipient_idx:
        for i in range(recipient_idx + 1, first_h1_idx):
            st = get_style(paras[i])
            text = get_text(paras[i])
            if st == '公文正文' and ('通知如下' in text):
                preamble_ok = True
                break
        if preamble_ok:
            print(f"  ✓ 通知导语存在")
        else:
            failures.append("主送机关后、首个一级标题前缺少通知导语（应含'通知如下'）")

    # Recipient check
    recip_paras = [p for p in paras if get_style(p) == '主送机关']
    if not recip_paras:
        failures.append("缺少主送机关")
    else:
        rtext = get_text(recip_paras[0])
        if not rtext.endswith('：'):
            failures.append("主送机关不以：结尾")
        print(f"  ✓ 主送: {rtext[:30]}")

    # Body check
    body_paras = [p for p in paras if get_style(p) in ('公文正文', '一级标题', '二级标题')]
    if len(body_paras) < 2:
        failures.append("正文段落不足")

    # Issuer & date check
    issuer_paras = [p for p in paras if get_style(p) == '落款']
    date_paras = [p for p in paras if get_style(p) == '成文日期']
    if not issuer_paras:
        failures.append("缺少落款")
    if not date_paras:
        failures.append("缺少成文日期")
    print(f"  ✓ 落款 + 日期")

    # Heading1 keepNext check
    h1_paras = [p for p in paras if get_style(p) == '一级标题']
    h1_no_kn = [p for p in h1_paras if not has_keep_next(p)]
    if h1_no_kn:
        texts = [get_text(p)[:20] for p in h1_no_kn]
        failures.append(f"一级标题缺少keepNext: {texts}")
    else:
        print(f"  ✓ {len(h1_paras)}个一级标题全有keepNext")

    # Body keepNext check
    body_kn = [p for p in paras if get_style(p) == '公文正文' and has_keep_next(p)]
    print(f"  ✓ 正文keepNext: {len(body_kn)}")

    # Contact consecutiveness check
    contact_re = re.compile(r'^(联系人|联系电话|电话|手机|电子邮箱|邮箱|办公地址|地址|联系地址)\s*[：:]')
    contact_indices = []
    for i, p in enumerate(paras):
        text = get_text(p)
        if contact_re.match(text.strip()):
            contact_indices.append(i)

    if contact_indices:
        for j in range(1, len(contact_indices)):
            prev = contact_indices[j - 1]
            curr = contact_indices[j]
            for k in range(prev + 1, curr):
                text = get_text(paras[k]).strip()
                if text and not contact_re.match(text):
                    failures.append(f"联系方式不连续：联系人相关段落之间夹有其他内容（第{k+1}段）")
                    break
        print(f"  ✓ 联系方式连续性: {len(contact_indices)}项")

        for idx in contact_indices:
            if not has_keep_next(paras[idx]):
                text = get_text(paras[idx])[:20]
                failures.append(f"联系方式缺少keepNext: {text}")
        if all(has_keep_next(paras[idx]) for idx in contact_indices):
            print(f"  ✓ 联系方式keepNext链: {len(contact_indices)}项全部")

        for idx in contact_indices:
            text = get_text(paras[idx])
            if text.strip().startswith('电子邮箱') or text.strip().startswith('邮箱'):
                for ch, name in BAD_CHARS.items():
                    if ch in text:
                        failures.append(f"电子邮箱含不可见字符: {name}")

    # Issuer keepNext check
    if issuer_paras:
        for ip in issuer_paras:
            if not has_keep_next(ip):
                failures.append("落款缺少keepNext")
        if all(has_keep_next(ip) for ip in issuer_paras):
            print(f"  ✓ 落款keepNext")

    # Date NO keepNext check
    if date_paras:
        for dp in date_paras:
            if has_keep_next(dp):
                failures.append("成文日期不应有keepNext")
        if all(not has_keep_next(dp) for dp in date_paras):
            print(f"  ✓ 日期无keepNext")

    # Manual page break
    manual_breaks = [b for r in root.findall(f'.//{{{NS}}}r') for b in r.findall(f'{{{NS}}}br') if b.get(f'{{{NS}}}type') == 'page']
    if manual_breaks:
        failures.append(f"含{len(manual_breaks)}个手动分页符")

    # Page settings
    sectPr = body.find(f'{{{NS}}}sectPr')
    if sectPr is not None:
        pgSz = sectPr.find(f'{{{NS}}}pgSz')
        if pgSz is not None:
            w = int(pgSz.get(f'{{{NS}}}w', '0'))
            h = int(pgSz.get(f'{{{NS}}}h', '0'))
            if 11900 <= w <= 11910 and 16830 <= h <= 16840:
                print(f"  ✓ A4页面")
            else:
                print(f"  ⚠ 页面尺寸: {w}x{h} (非标准A4)")

    # Font size validation
    _validate_font_sizes(path, failures)

    # Section and footer validation
    _validate_section_and_footers(path, failures)

    # ── Phase 1: Semantic validation ──
    _validate_semantic(paras, model_data, failures)

    # Print failures
    if failures:
        print(f"\n❌ 校验失败 ({len(failures)}项):")
        for f in failures:
            print(f"  - {f}")
    else:
        print(f"\n✅ 校验通过")

    return failures


def main():
    ap = argparse.ArgumentParser(description='通知 DOCX 校验器（含 Phase 1 语义校验）')
    ap.add_argument('--file', '-f', required=True, help='DOCX 文件路径')
    ap.add_argument('--model', '-m', help='NoticeModel JSON 文件路径（Phase 1 语义校验）')
    args = ap.parse_args()
    failures = validate(args.file, model_path=args.model)
    if failures:
        print("VALIDATION_FAILED")
        sys.exit(6)
    else:
        print("VALIDATION_PASSED")
        sys.exit(0)


if __name__ == '__main__':
    main()
