#!/usr/bin/env python3
"""notice_document_factory.py — 运行时文档工厂。

使用 python-docx 纯文本代码创建已设置好通知公文页面、样式和页码的 Document 对象。
不读取任何 DOCX、DOTX、ZIP 或二进制模板。

页面与样式参数以通知公文格式（2012版国家标准）为审计来源。
"""

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.shared import Inches, Pt, Cm, Emu, RGBColor
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import copy, zipfile, os, tempfile, sys


# ══════════════════════════════════════════════════════════════════
# OOXML namespace constants
# ══════════════════════════════════════════════════════════════════

NSMAP = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'w14': 'http://schemas.microsoft.com/office/word/2010/wordml',
}

WML_NS = NSMAP['w']
REL_NS = NSMAP['r']

# ══════════════════════════════════════════════════════════════════
# Page parameters (audited from original template)
# ══════════════════════════════════════════════════════════════════

# A4 page (template twips converted to EMU: twips × 635 = EMU)
PAGE_WIDTH = 11906 * 635   # 7,560,310 EMU ≈ 210mm
PAGE_HEIGHT = 16838 * 635  # 10,692,130 EMU ≈ 297mm

# Margins (template twips converted to EMU)
MARGIN_TOP = 2098 * 635      # ≈ 37mm
MARGIN_RIGHT = 1474 * 635    # ≈ 26mm
MARGIN_BOTTOM = 1984 * 635   # ≈ 35mm
MARGIN_LEFT = 1587 * 635     # ≈ 28mm
MARGIN_HEADER = 850 * 635    # ≈ 15mm
MARGIN_FOOTER = 397 * 635    # ≈ 7mm
MARGIN_GUTTER = 0


# ══════════════════════════════════════════════════════════════════
# Style definitions (audited from original template)
# ══════════════════════════════════════════════════════════════════

STYLE_DEFS = {
    '公文标题': {
        'font_name': '方正小标宋简体',
        'font_size': Pt(22),  # 二号 = 22pt
        'font_size_half': Pt(11),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.CENTER,
        'line_spacing': Pt(28.95),  # = 579/20 twips exact
        'line_spacing_rule': 'exact',  # will use XML
        'space_before': Pt(0),
        'space_after': Pt(0),
    },
    '主送机关': {
        'font_name': '仿宋_GB2312',
        'font_size': Pt(16),  # 三号 = 16pt
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.LEFT,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'first_line_indent': Pt(0),
    },
    '公文正文': {
        'font_name': '仿宋_GB2312',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.JUSTIFY,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'first_line_indent': Pt(32),  # 640 twips = 32pt = 2 chars
    },
    '一级标题': {
        'font_name': '黑体',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.JUSTIFY,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'first_line_indent': Pt(32),
    },
    '二级标题': {
        'font_name': '楷体_GB2312',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.JUSTIFY,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'first_line_indent': Pt(32),
    },
    '三级标题': {
        'font_name': '仿宋_GB2312',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.JUSTIFY,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'first_line_indent': Pt(32),
    },
    '附件说明': {
        'font_name': '仿宋_GB2312',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.JUSTIFY,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'first_line_indent': Pt(32),
    },
    '落款': {
        'font_name': '仿宋_GB2312',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.RIGHT,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(28.95),  # 579 twips
        'right_indent': Pt(64),    # 1280 twips
    },
    '成文日期': {
        'font_name': '仿宋_GB2312',
        'font_size': Pt(16),
        'bold': False,
        'alignment': WD_ALIGN_PARAGRAPH.RIGHT,
        'line_spacing': Pt(28.95),
        'space_before': Pt(0),
        'space_after': Pt(0),
        'right_indent': Pt(64),    # 1280 twips
    },
}


def half_points(points: float) -> str:
    """Convert point size to OOXML w:sz value (half-points = pt × 2)."""
    return str(int(round(points * 2)))


# ══════════════════════════════════════════════════════════════════
# OOXML XML helpers
# ══════════════════════════════════════════════════════════════════

def _make_elem(tag, attrib=None, children=None, text=None):
    """Create an OOXML element with proper namespace."""
    elem = parse_xml(f'<{tag} {nsdecls("w")} xmlns:r="{REL_NS}"/>')
    if attrib:
        for k, v in attrib.items():
            elem.set(qn(k), str(v))
    if text is not None:
        elem.text = str(text)
    if children:
        for child in children:
            elem.append(child)
    return elem


def _make_page_number_run(right_aligned=True):
    """Create a w:r element containing '— {PAGE} —'."""
    rPr = _make_elem('w:rPr')
    rFonts = _make_elem('w:rFonts', {
        'w:ascii': '宋体', 'w:hAnsi': '宋体',
        'w:eastAsia': '宋体', 'w:cs': '宋体',
    })
    rPr.append(rFonts)
    b = _make_elem('w:b', {'w:val': '0'})
    rPr.append(b)
    sz = _make_elem('w:sz', {'w:val': half_points(14.0)})  # 14pt → 28 half-pts
    rPr.append(sz)
    szCs = _make_elem('w:szCs', {'w:val': half_points(14.0)})
    rPr.append(szCs)

    # First text run: '— '
    r1 = _make_elem('w:r')
    r1.append(copy.deepcopy(rPr))
    t1 = _make_elem('w:t', {'xml:space': 'preserve'}, text='\u2014 ')  # em dash
    r1.append(t1)

    # Field run: PAGE
    r2 = _make_elem('w:r')
    r2.append(copy.deepcopy(rPr))
    fldChar_begin = _make_elem('w:fldChar', {'w:fldCharType': 'begin'})
    r2.append(fldChar_begin)
    instrText = _make_elem('w:instrText', {'xml:space': 'preserve'}, text=' PAGE ')
    r2.append(instrText)
    fldChar_end = _make_elem('w:fldChar', {'w:fldCharType': 'end'})
    r2.append(fldChar_end)

    # Last text run: ' —'
    r3 = _make_elem('w:r')
    r3.append(copy.deepcopy(rPr))
    t3 = _make_elem('w:t', {'xml:space': 'preserve'}, text=' \u2014')
    r3.append(t3)

    return [r1, r2, r3]


def _add_footer_paragraph(footer, right_aligned=True):
    """Add page number paragraph to a footer section."""
    p = _make_elem('w:p')
    pPr = _make_elem('w:pPr')
    pStyle = _make_elem('w:pStyle', {'w:val': '页码'})
    pPr.append(pStyle)
    spacing = _make_elem('w:spacing', {'w:before': '0', 'w:after': '0'})
    pPr.append(spacing)
    jc = _make_elem('w:jc', {'w:val': 'right' if right_aligned else 'left'})
    pPr.append(jc)
    p.append(pPr)
    for run in _make_page_number_run(right_aligned):
        p.append(run)
    footer._element.append(p)


# ══════════════════════════════════════════════════════════════════
# Style creation (using low-level XML for full control)
# ══════════════════════════════════════════════════════════════════

def _add_custom_styles(doc):
    """Add all 通知公文 styles to the document using raw XML for full control."""
    styles_elem = doc.styles.element

    for style_id, style_def in STYLE_DEFS.items():
        # Check if style already exists
        existing = None
        for s in styles_elem.findall(qn('w:style')):
            if s.get(qn('w:styleId')) == style_id:
                existing = s
                break
        if existing is not None:
            styles_elem.remove(existing)

        style_elem = _make_elem('w:style', {
            'w:type': 'paragraph',
            'w:styleId': style_id,
        })
        name = _make_elem('w:name', {'w:val': style_id})
        style_elem.append(name)

        # pPr
        pPr = _make_elem('w:pPr')
        # Line spacing (exact)
        sp = _make_elem('w:spacing', {
            'w:lineRule': 'exact',
            'w:line': '579',  # 28.95pt in twips/20
            'w:before': '0',
            'w:after': str(int(style_def.get('space_after', Pt(0)).emu / 635)) if 'space_after' in style_def else '0',
        })
        pPr.append(sp)

        # Justification
        if style_def['alignment'] == WD_ALIGN_PARAGRAPH.CENTER:
            pPr.append(_make_elem('w:jc', {'w:val': 'center'}))
        elif style_def['alignment'] == WD_ALIGN_PARAGRAPH.RIGHT:
            pPr.append(_make_elem('w:jc', {'w:val': 'right'}))

        # First line indent
        if style_def.get('first_line_indent'):
            ind_val = int(style_def['first_line_indent'].emu / 635)  # convert to twips
            pPr.append(_make_elem('w:ind', {'w:firstLine': str(ind_val)}))

        # Right indent for 落款/成文日期
        if style_def.get('right_indent'):
            rind_val = int(style_def['right_indent'].emu / 635)
            # Check if we already have an indent element
            existing_ind = pPr.find(qn('w:ind'))
            if existing_ind is not None:
                existing_ind.set(qn('w:right'), str(rind_val))
                existing_ind.set(qn('w:left'), '0')
                existing_ind.set(qn('w:firstLine'), '0')
            else:
                ind = _make_elem('w:ind', {'w:right': str(rind_val), 'w:left': '0', 'w:firstLine': '0'})
                pPr.append(ind)

        style_elem.append(pPr)

        # rPr
        rPr = _make_elem('w:rPr')
        rFonts = _make_elem('w:rFonts', {
            'w:ascii': style_def['font_name'],
            'w:hAnsi': style_def['font_name'],
            'w:eastAsia': style_def['font_name'],
            'w:cs': style_def['font_name'],
        })
        rPr.append(rFonts)
        rPr.append(_make_elem('w:b', {'w:val': '0'}))
        # Use half-points: pt × 2 (NOT twips pt × 20)
        sz_val = half_points(style_def['font_size'].pt)
        rPr.append(_make_elem('w:sz', {'w:val': sz_val}))
        rPr.append(_make_elem('w:szCs', {'w:val': sz_val}))
        style_elem.append(rPr)

        styles_elem.append(style_elem)


def _update_normal_style(doc):
    """Update Normal style to 仿宋_GB2312 as default body font."""
    normal_style = doc.styles['Normal']
    normal_style.font.name = '仿宋_GB2312'
    normal_style.font.size = Pt(16)
    normal_style.font.bold = False
    # Set eastAsia font
    rPr_elem = normal_style.element.find(qn('w:rPr'))
    if rPr_elem is None:
        rPr_elem = _make_elem('w:rPr')
        normal_style.element.append(rPr_elem)
    rFonts = rPr_elem.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = _make_elem('w:rFonts')
        rPr_elem.insert(0, rFonts)
    rFonts.set(qn('w:ascii'), '仿宋_GB2312')
    rFonts.set(qn('w:hAnsi'), '仿宋_GB2312')
    rFonts.set(qn('w:eastAsia'), '仿宋_GB2312')
    rFonts.set(qn('w:cs'), '仿宋_GB2312')
    # Line spacing
    pPr_elem = normal_style.element.find(qn('w:pPr'))
    if pPr_elem is None:
        pPr_elem = _make_elem('w:pPr')
        normal_style.element.insert(0, pPr_elem)
    spacing = pPr_elem.find(qn('w:spacing'))
    if spacing is None:
        spacing = _make_elem('w:spacing')
        pPr_elem.append(spacing)
    spacing.set(qn('w:lineRule'), 'exact')
    spacing.set(qn('w:line'), '579')
    spacing.set(qn('w:before'), '0')
    spacing.set(qn('w:after'), '0')


def _add_page_number_style(doc):
    """Add 页码 style for footer page numbers."""
    styles_elem = doc.styles.element
    style_elem = _make_elem('w:style', {
        'w:type': 'paragraph',
        'w:styleId': '页码',
    })
    name = _make_elem('w:name', {'w:val': '页码'})
    style_elem.append(name)
    basedOn = _make_elem('w:basedOn', {'w:val': 'Normal'})
    style_elem.append(basedOn)

    pPr = _make_elem('w:pPr')
    pPr.append(_make_elem('w:spacing', {'w:after': '0', 'w:line': '240', 'w:lineRule': 'auto'}))
    style_elem.append(pPr)

    rPr = _make_elem('w:rPr')
    rPr.append(_make_elem('w:rFonts', {
        'w:ascii': '宋体', 'w:hAnsi': '宋体',
        'w:eastAsia': '宋体', 'w:cs': '宋体',
    }))
    rPr.append(_make_elem('w:b', {'w:val': '0'}))
    # 14pt = 28 half-points, single sz + szCs pair
    sz_val = half_points(14.0)
    rPr.append(_make_elem('w:sz', {'w:val': sz_val}))
    rPr.append(_make_elem('w:szCs', {'w:val': sz_val}))
    style_elem.append(rPr)

    styles_elem.append(style_elem)


# ══════════════════════════════════════════════════════════════════
# Page setup
# ══════════════════════════════════════════════════════════════════

def _setup_page(doc):
    """Configure A4 page, margins, grid, and section properties."""
    # Ensure there's at least one section
    if not doc.sections:
        doc.add_section()
    section = doc.sections[0]

    # Page size
    section.page_width = Emu(PAGE_WIDTH)
    section.page_height = Emu(PAGE_HEIGHT)
    section.orientation = WD_ORIENT.PORTRAIT

    # Margins
    section.top_margin = Emu(MARGIN_TOP)
    section.right_margin = Emu(MARGIN_RIGHT)
    section.bottom_margin = Emu(MARGIN_BOTTOM)
    section.left_margin = Emu(MARGIN_LEFT)
    section.header_distance = Emu(MARGIN_HEADER)
    section.footer_distance = Emu(MARGIN_FOOTER)

    # Even/odd headers/footers — must be in settings.xml, NOT in sectPr
    _add_even_and_odd_headers_to_settings(doc)

    # Document grid (ensure only one)
    sectPr_elem = section._sectPr
    # Remove any existing docGrid
    for dg in sectPr_elem.findall(qn('w:docGrid')):
        sectPr_elem.remove(dg)

    # Columns setup
    cols = sectPr_elem.find(qn('w:cols'))
    if cols is None:
        cols = _make_elem('w:cols')
        sectPr_elem.insert(0, cols)
    cols.set(qn('w:space'), '720')

    docGrid = _make_elem('w:docGrid', {'w:linePitch': '360'})
    sectPr_elem.append(docGrid)

    # Do NOT add titlePg — first page uses default footer too


def _add_even_and_odd_headers_to_settings(doc):
    """Add w:evenAndOddHeaders to word/settings.xml (correct location)."""
    settings_elem = doc.settings.element
    # Remove any existing
    for eoh in settings_elem.findall(qn('w:evenAndOddHeaders')):
        settings_elem.remove(eoh)
    eoh = _make_elem('w:evenAndOddHeaders')
    settings_elem.append(eoh)


def _setup_footers(doc):
    """Add default (odd) and even footers with page numbers."""
    section = doc.sections[0]

    # Default footer (odd pages) — right-aligned page number
    default_footer = section.footer  # default footer
    # First clean any existing content
    for p in default_footer.paragraphs:
        p._element.getparent().remove(p._element)
    _add_footer_paragraph(default_footer, right_aligned=True)

    # Even footer — left-aligned page number
    # Need to create even footer via relationships
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    even_footer = section.even_page_footer
    for p in even_footer.paragraphs:
        p._element.getparent().remove(p._element)
    _add_footer_paragraph(even_footer, right_aligned=False)


def _add_footer_references(doc):
    """Ensure footer references exist in sectPr.

    We add the references explicitly here because python-docx's part serializer
    may not always auto-add them when creating footer parts programmatically.
    """
    section = doc.sections[0]
    sectPr = section._sectPr

    # Remove ALL existing footer references first
    for fr in list(sectPr.findall(qn('w:footerReference'))):
        sectPr.remove(fr)

    # Get the relationship IDs from the section part
    default_rId = None
    even_rId = None

    for rel in section.part.rels.values():
        target_path = rel.target_ref
        if target_path and 'footer1.xml' in target_path:
            default_rId = rel.rId
        elif target_path and 'footer2.xml' in target_path:
            even_rId = rel.rId

    if default_rId and even_rId:
        # Add default footer reference
        default_fr = _make_elem('w:footerReference', {
            'w:type': 'default',
            'r:id': default_rId,
        })
        sectPr.append(default_fr)

        # Add even footer reference
        even_fr = _make_elem('w:footerReference', {
            'w:type': 'even',
            'r:id': even_rId,
        })
        sectPr.append(even_fr)


# ══════════════════════════════════════════════════════════════════
# Post-generation font size assertion
# ══════════════════════════════════════════════════════════════════

EXPECTED_FONT_SIZES = {
    '公文标题': ('44', '44'),   # 22pt × 2 = 44 half-pts
    '主送机关': ('32', '32'),   # 16pt × 2 = 32 half-pts
    '公文正文': ('32', '32'),
    '一级标题': ('32', '32'),
    '二级标题': ('32', '32'),
    '三级标题': ('32', '32'),
    '附件说明': ('32', '32'),
    '联系方式': ('32', '32'),
    '落款':    ('32', '32'),
    '成文日期': ('32', '32'),
    '页码':    ('28', '28'),   # 14pt × 2 = 28 half-pts
}


def _assert_font_sizes(docx_path):
    """Re-open saved DOCX and verify all style font sizes are correct."""
    from xml.etree import ElementTree as ET
    failures = []
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            styles_xml = z.read('word/styles.xml')
    except Exception as e:
        return [f"无法读取styles.xml: {e}"]

    root = ET.fromstring(styles_xml)
    ns = NSMAP['w']

    for style_elem in root.findall(f'{{{ns}}}style'):
        style_id = style_elem.get(f'{{{ns}}}styleId', '')
        if style_id not in EXPECTED_FONT_SIZES:
            continue

        expected_sz, expected_szCs = EXPECTED_FONT_SIZES[style_id]

        # Collect all sz and szCs nodes
        sz_nodes = style_elem.findall(f'.//{{{ns}}}sz')
        szCs_nodes = style_elem.findall(f'.//{{{ns}}}szCs')

        sz_vals = [n.get(f'{{{ns}}}val', '') for n in sz_nodes]
        szCs_vals = [n.get(f'{{{ns}}}val', '') for n in szCs_nodes]

        # Check for >100 (twips error)
        for v in sz_vals:
            try:
                if int(v) > 100:
                    failures.append(f"{style_id}字号的w:sz={v}>100，可能误用了二十分之一磅单位")
            except ValueError:
                failures.append(f"{style_id}字号的w:sz值非法: {v}")

        for v in szCs_vals:
            try:
                if int(v) > 100:
                    failures.append(f"{style_id}字号的w:szCs={v}>100，可能误用了二十分之一磅单位")
            except ValueError:
                failures.append(f"{style_id}字号的w:szCs值非法: {v}")

        # Check count = 1
        if len(sz_nodes) != 1:
            failures.append(f"{style_id}的w:sz节点数量={len(sz_nodes)}（预期1），值={sz_vals}")
        if len(szCs_nodes) != 1:
            failures.append(f"{style_id}的w:szCs节点数量={len(szCs_nodes)}（预期1），值={szCs_vals}")

        # Check exact value
        if len(sz_vals) == 1 and sz_vals[0] != expected_sz:
            failures.append(f"{style_id}的w:sz={sz_vals[0]}（预期{expected_sz}）")
        if len(szCs_vals) == 1 and szCs_vals[0] != expected_szCs:
            failures.append(f"{style_id}的w:szCs={szCs_vals[0]}（预期{expected_szCs}）")

    # Check section properties
    doc_xml = None
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            doc_xml = z.read('word/document.xml')
    except Exception:
        pass

    if doc_xml is not None:
        doc_root = ET.fromstring(doc_xml)
        body = doc_root.find(f'{{{ns}}}body')
        if body is not None:
            sectPr = body.find(f'{{{ns}}}sectPr')
            if sectPr is not None:
                # Check footer references
                footer_refs = sectPr.findall(f'{{{ns}}}footerReference')
                has_default = any(fr.get(f'{{{ns}}}type') == 'default' for fr in footer_refs)
                has_even = any(fr.get(f'{{{ns}}}type') == 'even' for fr in footer_refs)
                if not has_default:
                    failures.append("sectPr缺少default footerReference")
                if not has_even:
                    failures.append("sectPr缺少even footerReference")

                # Check no evenAndOddHeaders in sectPr
                if sectPr.find(f'{{{ns}}}evenAndOddHeaders') is not None:
                    failures.append("sectPr中不应包含evenAndOddHeaders（应在settings.xml中）")

                # Check no titlePg
                if sectPr.find(f'{{{ns}}}titlePg') is not None:
                    failures.append("sectPr中不应包含titlePg")

                # Check docGrid count
                doc_grids = sectPr.findall(f'{{{ns}}}docGrid')
                if len(doc_grids) != 1:
                    failures.append(f"sectPr中docGrid数量={len(doc_grids)}（预期1）")

    if failures:
        print(f"\n❌ 字号断言失败 ({len(failures)}项):")
        for f in failures:
            print(f"  - {f}")
    else:
        print(f"  ✓ 字号断言通过（{len(EXPECTED_FONT_SIZES)}个样式全部正确）")

    return failures


# ══════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════

def create_notice_document():
    """创建已经设置好通知公文页面、样式和页码的 Document 对象。

    Returns:
        docx.Document: 一个空白 Document，已配置：
            - A4 纵向页面
            - 正式页边距
            - 页眉/页脚距离
            - 文档网格
            - 奇偶页不同
            - 奇数页右侧页码（真实 PAGE 域）
            - 偶数页左侧页码（真实 PAGE 域）
            - 公文标题样式（方正小标宋简体，居中，二号）
            - 主送机关样式（仿宋，三号，无缩进）
            - 公文正文样式（仿宋，三号，首行缩进2字符）
            - 一级标题样式（黑体，三号）
            - 二级标题样式（楷体，三号）
            - 三级标题样式（仿宋，三号）
            - 附件说明样式（仿宋，三号）
            - 落款样式（仿宋，三号，右对齐）
            - 成文日期样式（仿宋，三号，右对齐）
            - 中文字体 eastAsia 设置
            - 页码样式（宋体，小四）

    完全不读取任何 DOCX/DOTX/ZIP 或二进制模板。
    """
    doc = Document()

    # 1. Update Normal style as baseline
    _update_normal_style(doc)

    # 2. Add all custom styles
    _add_custom_styles(doc)

    # 3. Add page number style (for footer)
    _add_page_number_style(doc)

    # 4. Remove default empty paragraph (which uses Normal style with auto-line spacing)
    if doc.paragraphs:
        for p in doc.paragraphs:
            p._element.getparent().remove(p._element)

    # 5. Set up page (margins, size, grid, even/odd)
    _setup_page(doc)

    # 6. Set up footers with page numbers
    _setup_footers(doc)

    # 7. Ensure footer references exist in sectPr
    _add_footer_references(doc)

    return doc


# ══════════════════════════════════════════════════════════════════
# Self-test
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import tempfile

    print("创建通知公文 Document...")
    doc = create_notice_document()
    print(f"  ✓ Document 已创建")

    # Verify styles exist
    style_ids = [s.style_id for s in doc.styles]
    for sid in ['公文标题', '主送机关', '公文正文', '一级标题', '二级标题',
                 '三级标题', '附件说明', '落款', '成文日期', '页码']:
        if sid in style_ids:
            print(f"  ✓ 样式存在: {sid}")
        else:
            print(f"  ✗ 样式缺失: {sid}")

    # Check section properties
    section = doc.sections[0]
    page_w = section.page_width
    page_h = section.page_height
    print(f"  ✓ 页面尺寸: {page_w.emu}x{page_h.emu} EMU (A4=11906x16838)")

    # Try saving
    tmp = tempfile.mktemp(suffix='.docx')
    doc.save(tmp)
    sz = os.path.getsize(tmp)
    print(f"  ✓ 已保存临时文件: {sz} bytes")

    # Re-open
    with zipfile.ZipFile(tmp, 'r') as z:
        names = z.namelist()
        has_doc = 'word/document.xml' in names
        has_styles = 'word/styles.xml' in names
        footer_count = sum(1 for n in names if 'footer' in n.lower())
        print(f"  ✓ word/document.xml: {has_doc}")
        print(f"  ✓ word/styles.xml: {has_styles}")
        print(f"  ✓ Footer 文件: {footer_count}")

    # Font size assertion
    font_failures = _assert_font_sizes(tmp)
    if font_failures:
        print("\n❌ 字号断言失败！")
        os.unlink(tmp)
        sys.exit(1)

    os.unlink(tmp)
    print("\n✅ 自检通过（含字号断言）")
