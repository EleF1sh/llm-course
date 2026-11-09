#!/usr/bin/env python3
"""fill_tongzhi_docx.py — 通知 DOCX 纯 Renderer。

Phase 1 架构收敛后：本模块不再包含 Markdown 解析、导语生成或标题内容推断。
仅负责 DOCX 写入、标题视觉换行、样式调用。

输入：NoticeModel JSON（--model），由 notice_model.py 生成。
排版底层：notice_document_factory.py（冻结，不动）。
"""

import json, re, sys, os, hashlib, argparse
from datetime import datetime
from lxml import etree as ET

# Runtime document factory — replaces binary DOCX template (FROZEN)
from notice_document_factory import create_notice_document

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

STYLE_IDS = {
    '公文标题': '公文标题', '主送机关': '主送机关', '公文正文': '公文正文',
    '一级标题': '一级标题', '二级标题': '二级标题', '三级标题': '三级标题',
    '附件说明': '附件说明', '落款': '落款', '成文日期': '成文日期',
}

FONTS = {
    '公文标题': ('方正小标宋简体', '方正小标宋简体', '方正小标宋简体'),
    '主送机关': ('仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312'),
    '公文正文': ('仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312'),
    '一级标题': ('黑体', '黑体', '黑体'),
    '二级标题': ('楷体_GB2312', '楷体_GB2312', '楷体_GB2312'),
    '三级标题': ('仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312'),
    '附件说明': ('仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312'),
    '落款': ('仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312'),
    '成文日期': ('仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312'),
}

# ── RegEx patterns (body classification — shared with notice_model.py) ──
HEADING1_RE = re.compile(r'^([一二三四五六七八九十]+)[、，,]\s*(.+)')
HEADING2_RE = re.compile(r'^（([一二三四五六七八九十]+)）\s*(.*)')
CONTACT_RE = re.compile(r'^(联系人|联系电话|电话|手机|电子邮箱|邮箱|办公地址|地址|联系地址)\s*[：:]\s*(.*)')

# ── Title semantic breaking ──────────────────────────────────
# Phrases that must NOT be split across lines
_TITLE_NO_BREAK = [
    '人工智能', '辅助办公', '数据脱敏', '工具培训',
    '专项检查', '工作会议', '实施方案', '中期检查',
    '的通知',
]

# Title page geometry (from notice_document_factory.py)
_TITLE_PAGE_WIDTH_TWIPS = 11906
_TITLE_MARGIN_LEFT_TWIPS = 1587
_TITLE_MARGIN_RIGHT_TWIPS = 1474
_TITLE_USABLE_TWIPS = _TITLE_PAGE_WIDTH_TWIPS - _TITLE_MARGIN_LEFT_TWIPS - _TITLE_MARGIN_RIGHT_TWIPS  # 8845
_TITLE_FONT_PT = 22  # 二号
_TITLE_FONT_TWIPS_PER_CHAR = _TITLE_FONT_PT * 20  # 440 twips per char approx
_TITLE_MAX_CHARS = int(_TITLE_USABLE_TWIPS / _TITLE_FONT_TWIPS_PER_CHAR)  # ≈ 20


def _break_title(title):
    """Break long title at semantic boundary for single-paragraph display with <w:br/>.

    Returns list of lines that will be rendered as one paragraph with <w:br/>.
    This is purely a visual/rendering concern.
    """
    if not title:
        return ['']
    if len(title) <= _TITLE_MAX_CHARS:
        return [title]

    n = len(title)
    target = n // 2

    def _is_valid_break(pos):
        if pos <= 2 or pos >= n - 2:
            return False
        tail_len = n - pos
        if 2 <= tail_len <= 4:
            return False
        for phrase in _TITLE_NO_BREAK:
            idx = title.find(phrase)
            if idx >= 0 and idx < pos < idx + len(phrase):
                return False
        return True

    search_range = max(n // 3, 1)
    for offset in range(search_range):
        for direction in [0, 1]:
            pos = target + (offset if direction else -offset)
            if 0 < pos < n and _is_valid_break(pos):
                line1 = title[:pos]
                line2 = title[pos:]
                if abs(len(line1) - len(line2)) <= 4:
                    return [line1, line2]

    for sep in ['，', '、']:
        idx = title.rfind(sep, 0, target + 4)
        if idx > 2:
            bp = idx + 1
            if _is_valid_break(bp):
                line1 = title[:bp]
                line2 = title[bp:]
                if abs(len(line1) - len(line2)) <= 4:
                    return [line1, line2]

    mid = n // 2
    return [title[:mid], title[mid:]]


# ── Non-breaking ─────────────────────────────────────────────
def _pb(t):
    return t.replace('-', '\u2011')
def _pe(t):
    t = t.replace('@', '\u2060@\u2060')
    parts = t.split('\u2060@\u2060')
    if len(parts) == 2:
        parts[1] = parts[1].replace('.', '\u2060.\u2060')
        return '\u2060@\u2060'.join(parts)
    return t


# ── XML builders ─────────────────────────────────────────────
def _rn(text, style_id, bold=False):
    r = ET.Element(f'{{{NS}}}r')
    rPr = ET.SubElement(r, f'{{{NS}}}rPr')
    rf = ET.SubElement(rPr, f'{{{NS}}}rFonts')
    f = FONTS.get(style_id, FONTS['公文正文'])
    rf.set(f'{{{NS}}}ascii', f[0]); rf.set(f'{{{NS}}}hAnsi', f[1])
    rf.set(f'{{{NS}}}eastAsia', f[2]); rf.set(f'{{{NS}}}cs', f[2])
    if bold or style_id == '三级标题':
        ET.SubElement(rPr, f'{{{NS}}}b')
    t = ET.SubElement(r, f'{{{NS}}}t')
    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    t.text = text
    return r

def _br():
    r = ET.Element(f'{{{NS}}}r')
    ET.SubElement(r, f'{{{NS}}}br')
    return r

def _p(style_id, runs=None):
    p = ET.Element(f'{{{NS}}}p')
    pPr = ET.SubElement(p, f'{{{NS}}}pPr')
    ET.SubElement(pPr, f'{{{NS}}}pStyle').set(f'{{{NS}}}val', style_id)
    if runs:
        for r in runs:
            p.append(r)
    return p

def _tp(text, style_id, bold=False):
    p = _p(style_id)
    if text:
        p.append(_rn(text, style_id, bold))
    return p

def _mp(lines, style_id, bold=False):
    """Single paragraph with <w:br/> between lines."""
    p = _p(style_id)
    for i, line in enumerate(lines):
        if i > 0:
            p.append(_br())
        if line:
            p.append(_rn(line, style_id, bold))
    return p

def _contact_para(text):
    """Create a contact info paragraph with LEFT alignment, zero indent."""
    p = _p(STYLE_IDS['公文正文'])
    pr = p.find(f'{{{NS}}}pPr')
    jc = ET.SubElement(pr, f'{{{NS}}}jc')
    jc.set(f'{{{NS}}}val', 'left')
    ind = ET.SubElement(pr, f'{{{NS}}}ind')
    ind.set(f'{{{NS}}}firstLine', '0')
    ind.set(f'{{{NS}}}left', '0')
    if text:
        p.append(_rn(text, '公文正文'))
    return p

def _kn(p):
    pr = p.find(f'{{{NS}}}pPr')
    if pr is None: pr = ET.SubElement(p, f'{{{NS}}}pPr'); p.insert(0, pr)
    ET.SubElement(pr, f'{{{NS}}}keepNext')

def _kl(p):
    pr = p.find(f'{{{NS}}}pPr')
    if pr is None: pr = ET.SubElement(p, f'{{{NS}}}pPr'); p.insert(0, pr)
    ET.SubElement(pr, f'{{{NS}}}keepLines')

def _spacing(p, before=0, after=0):
    pr = p.find(f'{{{NS}}}pPr')
    if pr is None: pr = ET.SubElement(p, f'{{{NS}}}pPr'); p.insert(0, pr)
    sp = ET.SubElement(pr, f'{{{NS}}}spacing')
    sp.set(f'{{{NS}}}before', str(before))
    sp.set(f'{{{NS}}}after', str(after))
    sp.set(f'{{{NS}}}line', '360')
    sp.set(f'{{{NS}}}lineRule', 'auto')

def _widow_control(p):
    pr = p.find(f'{{{NS}}}pPr')
    if pr is None: pr = ET.SubElement(p, f'{{{NS}}}pPr'); p.insert(0, pr)
    ET.SubElement(pr, f'{{{NS}}}widowControl')

def _gs(p):
    ps = p.find(f'{{{NS}}}pPr/{{{NS}}}pStyle')
    return ps.get(f'{{{NS}}}val', '') if ps is not None else ''


# ══════════════════════════════════════════════════════════════════
# Pure Renderer — only render, never parse
# ══════════════════════════════════════════════════════════════════

def fill_docx(model, output_path, input_path=None, forced_title_lines=None):
    """Pure renderer: NoticeModel → DOCX。

    Args:
        model: NoticeModel dict 或 NoticeModel instance
        output_path: 输出 .docx 路径
        input_path: 可选的输入文件路径（仅用于日志记录）
        forced_title_lines: 可选，强制标题行（仅用于视觉换行覆盖，不影响内容）
    """
    title_text = model.get('title_text', '') if isinstance(model, dict) else model.title_text

    if forced_title_lines:
        title_lines = forced_title_lines
    else:
        title_lines = _break_title(title_text) if title_text else ['']

    recipient = model.get('main_recipient', '〔主送机关〕') if isinstance(model, dict) else model.main_recipient
    recipient = (recipient + '：') if recipient and not recipient.endswith('：') else recipient
    if not recipient:
        recipient = '〔主送机关〕：'

    preamble = model.get('preamble', '') if isinstance(model, dict) else model.preamble
    body_blocks = model.get('body_blocks', []) if isinstance(model, dict) else model.body_blocks
    issuer = model.get('issuer', '') if isinstance(model, dict) else model.issuer
    date_val = model.get('document_date', '〔日期〕') if isinstance(model, dict) else model.document_date

    # ── Get runtime-generated document (no template) ──
    doc = create_notice_document()
    body = doc.element.body

    # Find sectPr (last child of body) — we insert paragraphs before it
    sectPr = None
    ns_sectPr = f'{{{NS}}}sectPr'
    for child in body:
        if child.tag == ns_sectPr:
            sectPr = child
            break

    def _insert_para(p):
        if sectPr is not None:
            body.insert(list(body).index(sectPr), p)
        else:
            body.append(p)

    # ── 1. Title (visual breaking only — content from NoticeModel) ──
    tp = _mp(title_lines, STYLE_IDS['公文标题'])
    _insert_para(tp)

    # ── 2. Recipient ──
    rp = _tp(recipient, STYLE_IDS['主送机关'])
    _insert_para(rp)

    # ── 2.5. Preamble (from NoticeModel — renderer does NOT generate) ──
    if preamble:
        pre_p = _tp(preamble, STYLE_IDS['公文正文'])
        _widow_control(pre_p)
        _insert_para(pre_p)

    # ── 3. Body ──
    for idx, (etype, text) in enumerate(body_blocks):
        if not text:
            continue

        if etype == 'heading1':
            p = _tp(text, STYLE_IDS['一级标题'])
            _kl(p)
            _kn(p)
            _widow_control(p)
            _insert_para(p)

        elif etype == 'heading2':
            hm = HEADING2_RE.match(text)
            if hm:
                remainder = hm.group(2)
                period_idx = remainder.find('。')
                is_hybrid = (period_idx > 0 and
                             period_idx < len(remainder) - 2 and
                             len(remainder) > 15)
            else:
                is_hybrid = False

            if is_hybrid:
                prefix_text = remainder[:period_idx + 1]
                body_text = remainder[period_idx + 1:]
                p = _p(STYLE_IDS['公文正文'])
                num_prefix = hm.group(0)[:len(hm.group(0)) - len(remainder)]
                p.append(_rn(num_prefix + prefix_text, '二级标题'))
                p.append(_rn(body_text, '公文正文'))
                _widow_control(p)
                _insert_para(p)
            else:
                p = _tp(text, STYLE_IDS['二级标题'])
                _kl(p)
                next_is_h2 = (idx + 1 < len(body_blocks) and
                              body_blocks[idx + 1][0] == 'heading2')
                if not next_is_h2:
                    _kn(p)
                _widow_control(p)
                _insert_para(p)

        elif etype == 'attach_header':
            p = _tp(text, STYLE_IDS['附件说明'])
            _kn(p)
            _widow_control(p)
            _insert_para(p)

        elif etype == 'attach_item':
            p = _tp(text, STYLE_IDS['公文正文'])
            _kl(p)
            _widow_control(p)
            _insert_para(p)

        elif etype == 'contact':
            p = _contact_para(text)
            _widow_control(p)
            _insert_para(p)

        else:
            p = _tp(text, STYLE_IDS['公文正文'])
            _widow_control(p)
            _insert_para(p)

    # ── Post-process: contact chain and tail control ──
    all_body_paras = list(body.findall(f'{{{NS}}}p'))

    contact_indices = []
    for i, p in enumerate(all_body_paras):
        text = ''.join(t.text or '' for t in p.findall(f'.//{{{NS}}}t'))
        if CONTACT_RE.match(text.strip()):
            contact_indices.append(i)

    issuer_idx = None
    date_idx = None
    for i, p in enumerate(all_body_paras):
        st = _gs(p)
        if st == '落款':
            issuer_idx = i
        elif st == '成文日期':
            date_idx = i

    for idx in contact_indices:
        if all_body_paras[idx].find(f'{{{NS}}}pPr/{{{NS}}}keepNext') is None:
            _kn(all_body_paras[idx])

    if issuer_idx is not None and all_body_paras[issuer_idx].find(f'{{{NS}}}pPr/{{{NS}}}keepNext') is None:
        _kn(all_body_paras[issuer_idx])

    if date_idx is not None:
        dp = all_body_paras[date_idx]
        dp_pr = dp.find(f'{{{NS}}}pPr')
        if dp_pr is not None:
            dkn = dp_pr.find(f'{{{NS}}}keepNext')
            if dkn is not None:
                dp_pr.remove(dkn)

    target_before = contact_indices[0] if contact_indices else issuer_idx
    if target_before is not None:
        for i in range(target_before - 1, -1, -1):
            text = ''.join(t.text or '' for t in all_body_paras[i].findall(f'.//{{{NS}}}t'))
            if text.strip():
                st = _gs(all_body_paras[i])
                if st in ('公文正文', '一级标题', '二级标题'):
                    if all_body_paras[i].find(f'{{{NS}}}pPr/{{{NS}}}keepNext') is None:
                        _kn(all_body_paras[i])
                    break
    elif issuer_idx is not None:
        for i in range(issuer_idx - 1, -1, -1):
            text = ''.join(t.text or '' for t in all_body_paras[i].findall(f'.//{{{NS}}}t'))
            if text.strip():
                st = _gs(all_body_paras[i])
                if st in ('公文正文', '一级标题', '二级标题'):
                    if all_body_paras[i].find(f'{{{NS}}}pPr/{{{NS}}}keepNext') is None:
                        _kn(all_body_paras[i])
                    break

    # ── 4. Issuer ──
    issuer_lines = _break_issuer(issuer) if issuer and len(issuer) > 16 else ([issuer] if issuer else [''])
    ip = _mp(issuer_lines, STYLE_IDS['落款'])
    _spacing(ip, before=0, after=0)
    _kl(ip)
    _kn(ip)
    _widow_control(ip)
    _insert_para(ip)

    # ── 5. Date (NO keepNext) ──
    dp = _tp(date_val, STYLE_IDS['成文日期'])
    _spacing(dp, before=0, after=0)
    _widow_control(dp)
    _insert_para(dp)

    # ── Save ──
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)
    doc.save(output_path)

    # ── Empty paragraph audit ──
    paras = list(body.findall(f'{{{NS}}}p'))
    total_p = len(paras)
    nonempty_p = 0
    empty_p = 0
    max_cons = 0
    cur_cons = 0
    for p in paras:
        text = ''.join(t.text or '' for t in p.findall(f'.//{{{NS}}}t'))
        if text.strip():
            nonempty_p += 1
            cur_cons = 0
        else:
            empty_p += 1
            cur_cons += 1
            max_cons = max(max_cons, cur_cons)

    # ── Log ──
    sha_in = ''
    if input_path and os.path.exists(input_path):
        with open(input_path, 'rb') as f:
            sha_in = hashlib.sha256(f.read()).hexdigest()
    with open(output_path, 'rb') as f:
        sha_out = hashlib.sha256(f.read()).hexdigest()

    log = {
        'input_markdown': input_path or '',
        'input_sha256': sha_in,
        'generator_version': 'V7.0-phase1',
        'docx_template_mode': 'runtime_python_factory',
        'template_implementation': 'scripts/notice_document_factory.py',
        'content_model': 'scripts/notice_model.py',
        'output_docx': output_path,
        'output_sha256': sha_out,
        'total_word_paragraphs': total_p,
        'nonempty_word_paragraphs': nonempty_p,
        'empty_word_paragraphs': empty_p,
        'max_consecutive_empty_paragraphs': max_cons,
        'wps_app_path': '/Applications/wpsoffice.app',
        'wps_version': '12.1.26030',
        'render_engine': 'WPS Office',
        'render_engine_version': '12.1.26030',
        'rendered_pages': None,
        'page_count_source': '等待用户WPS打印预览确认',
        'generated_at': datetime.now().isoformat(),
    }
    log_path = output_path.replace('.docx', '_生成记录.json')
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    return output_path


def _break_issuer(issuer, max_w=40):
    """Break long issuer at semantic boundaries."""
    if len(issuer) <= 16:
        return [issuer]

    candidates = []
    for marker in ['与', '和', '暨', '及']:
        idx = issuer.find(marker)
        if 4 <= idx < len(issuer) - 4:
            after = idx + len(marker)
            if len(issuer[after:]) >= 4:
                candidates.append((after, abs(len(issuer[:after]) - len(issuer[after:]))))

    for marker in ['办公室', '管理部', '人力资源部', '研究管理部']:
        idx = issuer.find(marker)
        if 0 < idx < len(issuer) - 4:
            after = idx + len(marker)
            if len(issuer[after:]) >= 4:
                candidates.append((after, abs(len(issuer[:after]) - len(issuer[after:])) + 5))

    if not candidates:
        mid = len(issuer) // 2
        return [issuer[:mid], issuer[mid:]]

    candidates.sort(key=lambda x: x[1])
    pos = candidates[0][0]
    return [issuer[:pos], issuer[pos:]]


# ══════════════════════════════════════════════════════════════════
# Main — accepts NoticeModel JSON via --model
# ══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description='通知 DOCX 纯 Renderer (Phase 1)')
    ap.add_argument('--model', '-m', required=True,
                    help='NoticeModel JSON 文件路径（由 notice_model.py 生成）')
    ap.add_argument('--output', '-o', required=True,
                    help='输出 DOCX 路径')
    ap.add_argument('--input', '-i', default='',
                    help='原始 Markdown 文件（仅用于日志记录）')
    ap.add_argument('--force-title', nargs='*',
                    help='强制标题视觉换行（覆盖自动断行，不影响内容）')
    args = ap.parse_args()

    if not os.path.exists(args.model):
        print(f"ERROR: Model JSON not found: {args.model}", file=sys.stderr)
        sys.exit(1)

    with open(args.model, 'r', encoding='utf-8') as f:
        model_data = json.load(f)

    ftl = list(args.force_title) if args.force_title else None

    input_path = args.input if args.input else None

    filled = fill_docx(model_data, args.output, input_path, forced_title_lines=ftl)
    print(f"DOCX: {filled}")

    # Quick post-generation checks
    import zipfile
    with zipfile.ZipFile(filled) as z:
        doc_xml = z.read('word/document.xml')
    root = ET.fromstring(doc_xml)
    all_text = ''.join(t.text or '' for t in root.findall(f'.//{{{NS}}}t'))

    issues = []
    if '〔主送机关〕' in all_text:
        issues.append('未替换主送占位')
    if '# ' in all_text:
        issues.append('正文含#标记')
    issues_any = len(issues) > 0

    print(f"Check: {'PASS' if not issues_any else 'FAIL'}")
    for i in issues:
        print(f"  ✗ {i}")
    if not issues_any:
        print("  ✓ 无占位残留  ✓ 无Markdown标记")


if __name__ == '__main__':
    main()
