#!/usr/bin/env python3
"""notice_model.py — 通知内容模型（唯一内容解析层）。

职责：
- Markdown 解析
- 标题提取（仅 # 格式）
- 主送机关识别
- 导语识别（存在则保留，缺失则生成，>1个则报错）
- 正文结构化
- 落款识别
- 日期识别

输出：NoticeModel

此模块是 Phase 1 架构收敛的核心——它是 title_text / preamble / body_blocks
的唯一权威来源。Renderer (fill_tongzhi_docx.py) 不得自行解析 Markdown 或生成导语。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ══════════════════════════════════════════════════════════════════
# RegEx patterns — shared with fill_tongzhi_docx.py for body classification
# ══════════════════════════════════════════════════════════════════

HEADING1_RE = re.compile(r'^([一二三四五六七八九十]+)[、，,]\s*(.+)')
HEADING2_RE = re.compile(r'^（([一二三四五六七八九十]+)）\s*(.*)')
CONTACT_RE = re.compile(
    r'^(联系人|联系电话|电话|手机|电子邮箱|邮箱|办公地址|地址|联系地址)\s*[：:]\s*(.*)'
)
ATTACH_HEADER_RE = re.compile(r'^(附件)[：:]?\s*$')
ATTACH_ITEM_RE = re.compile(r'^(\d+)[.．、)）]\s*(.+)')
BODY_ATTACH_RE = re.compile(r'^[六七八九十]+[、，,]\s*(附件)')
DATE_RE = re.compile(r'^(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日$')
DATE_ALT_RE = re.compile(r'^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})$')
PREAMBLE_RE = re.compile(r'通知如下[：:]?$')


# ══════════════════════════════════════════════════════════════════
# NoticeModel
# ══════════════════════════════════════════════════════════════════

@dataclass
class NoticeModel:
    """通知内容模型 — 唯一内容权威来源。

    字段：
        title_text:     完整标题文本（不含 # 前缀）
        main_recipient: 主送机关（不含结尾冒号）
        preamble:       导语（过渡句，末尾含"通知如下："）
        body_blocks:    正文结构化列表，每项为 (type, text)
                        type ∈ {heading1, heading2, paragraph, contact,
                                attach_header, attach_item}
        issuer:         发文单位完整名称
        document_date:  成文日期（或占位符）
    """
    title_text: str = ""
    main_recipient: str = ""
    preamble: str = ""
    body_blocks: List[Tuple[str, str]] = field(default_factory=list)
    issuer: str = ""
    document_date: str = ""

    # ── serialization ──

    def to_dict(self) -> dict:
        return {
            'title_text': self.title_text,
            'main_recipient': self.main_recipient,
            'preamble': self.preamble,
            'body_blocks': self.body_blocks,
            'issuer': self.issuer,
            'document_date': self.document_date,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> 'NoticeModel':
        return cls(**{k: data.get(k, v) for k, v in cls().to_dict().items()})

    @classmethod
    def from_json(cls, raw: str) -> 'NoticeModel':
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_json_file(cls, path: str) -> 'NoticeModel':
        with open(path, 'r', encoding='utf-8') as f:
            return cls.from_json(f.read())


# ══════════════════════════════════════════════════════════════════
# Preamble generation
# ══════════════════════════════════════════════════════════════════

def _generate_preamble(title_text: str) -> str:
    """从标题生成中性过渡导语。

    "关于召开XXXX会议的通知" → "现就召开XXXX会议有关事项通知如下："
    """
    topic = title_text
    if topic.startswith('关于'):
        topic = topic[2:]
    if topic.endswith('的通知'):
        topic = topic[:-3]
    elif topic.endswith('通知'):
        topic = topic[:-2]
    return f'现就{topic}有关事项通知如下：'


# ══════════════════════════════════════════════════════════════════
# Markdown parser → NoticeModel
# ══════════════════════════════════════════════════════════════════

def parse_markdown(md_text: str) -> NoticeModel:
    """解析 Markdown 文本为 NoticeModel。

    规则：
    - 标题仅接受 # 完整标题文本（单行）
    - 标题跨行 → INPUT_SCHEMA_FAILED
    - 导语存在则保留，缺失则自动生成，>1个则报错
    - 不得保存 title_lines / forced_title_lines

    Raises:
        SystemExit: INPUT_SCHEMA_FAILED
    """
    raw_lines = md_text.split('\n')
    clean_lines = [line.rstrip('\r') for line in raw_lines]

    # ── Step 1: 提取标题（仅 # 格式） ──
    title_text = ''
    title_line_idx = None

    for i, line in enumerate(clean_lines):
        s = line.strip()
        if s.startswith('# '):
            title_text = s[2:].strip()
            title_line_idx = i
            break
        # 非 # 开头的非空行不能作为标题 — 标题必须由 # 标记
        if s and not title_line_idx:
            # 无 # 标题 → 失败
            _fail(
                'INPUT_SCHEMA_FAILED',
                '标题必须以 "# " 开头，但首行非 # 格式',
                f'首行内容: {s[:60]}',
            )

    if not title_text:
        _fail('INPUT_SCHEMA_FAILED', '未找到标题（需要 "# 标题文本"）')

    # 标题完整性：Markdown 标题必须在一行内
    # 检查后续行是否以非 # 开头的短文本（可能是标题续行）
    if title_line_idx is not None:
        for j in range(title_line_idx + 1, min(title_line_idx + 3, len(clean_lines))):
            next_s = clean_lines[j].strip()
            if next_s and not next_s.startswith('#') and not next_s.endswith('：'):
                # 如果下一行看起来像是标题的续行（短文本，不含标点结束符）
                if len(next_s) < 30 and not re.search(r'[。！？：]', next_s):
                    _fail(
                        'INPUT_SCHEMA_FAILED',
                        '标题不能跨行——检测到可能的标题断行',
                        f'标题第一行: {title_text}',
                        f'疑似续行: {next_s}',
                    )

    # ── Step 2: 提取主送机关 ──
    main_recipient = ''
    recipient_idx = None
    search_start = (title_line_idx + 1) if title_line_idx is not None else 0

    for i in range(search_start, len(clean_lines)):
        s = clean_lines[i].strip()
        if not s:
            continue
        if s.endswith('：'):
            main_recipient = s.rstrip('：').strip()
            recipient_idx = i
            break

    # ── Step 3: 收集正文行 ──
    body_start = (
        (recipient_idx + 1) if recipient_idx is not None
        else ((title_line_idx + 1) if title_line_idx is not None else 0)
    )

    body_lines = []
    for i in range(body_start, len(clean_lines)):
        s = clean_lines[i].strip()
        if not s:
            continue
        if s.startswith('# '):
            continue
        body_lines.append(s)

    # ── Step 4: 提取导语 ──
    preamble = ''
    preamble_indices = []

    for i, s in enumerate(body_lines):
        if PREAMBLE_RE.search(s):
            preamble_indices.append(i)

    if len(preamble_indices) == 0:
        # 没有导语 → 自动生成
        preamble = _generate_preamble(title_text)
    elif len(preamble_indices) == 1:
        preamble = body_lines[preamble_indices[0]]
    else:
        _fail(
            'INPUT_SCHEMA_FAILED',
            f'检测到 {len(preamble_indices)} 个导语（只能有 0 或 1 个）',
            *(body_lines[i] for i in preamble_indices),
        )

    # ── Step 5: 提取落款和日期 ──
    date_val = ''
    issuer_val = ''
    date_idx = None

    for i in range(len(body_lines) - 1, -1, -1):
        s = body_lines[i]
        m = DATE_RE.match(s)
        if not m:
            m = DATE_ALT_RE.match(s)
        if m:
            date_val = s
            date_idx = i
            break

    if date_idx is not None:
        for i in range(date_idx - 1, -1, -1):
            s = body_lines[i].strip()
            if not s:
                continue
            if re.match(r'^[\d]', s):
                continue
            if CONTACT_RE.match(s):
                continue
            if HEADING1_RE.match(s) or HEADING2_RE.match(s) or ATTACH_ITEM_RE.match(s):
                continue
            issuer_val = s
            break

    # 从 body_lines 中移除落款和日期
    body_without_tail = []
    for i, s in enumerate(body_lines):
        is_date = (date_idx is not None and i == date_idx)
        is_issuer = (
            issuer_val
            and s.strip() == issuer_val
            and date_idx is not None
            and i < date_idx
            and i > date_idx - 3
        )
        # Also remove preamble from body if it was found in body
        is_preamble = preamble_indices and i in preamble_indices
        if is_date or is_issuer or is_preamble:
            continue
        body_without_tail.append(s)

    # ── Step 6: 分类正文块 ──
    body_blocks: List[Tuple[str, str]] = []
    for s in body_without_tail:
        s = s.strip()
        if not s:
            continue

        if ATTACH_HEADER_RE.match(s):
            body_blocks.append(('attach_header', s.rstrip('：:') + '：'))
        elif BODY_ATTACH_RE.match(s):
            body_blocks.append(('heading1', s))
        elif ATTACH_ITEM_RE.match(s):
            body_blocks.append(('attach_item', s))
        elif HEADING1_RE.match(s):
            body_blocks.append(('heading1', s))
        elif HEADING2_RE.match(s):
            body_blocks.append(('heading2', s))
        elif CONTACT_RE.match(s):
            m = CONTACT_RE.match(s)
            label, value = m.group(1), m.group(2)
            body_blocks.append(('contact', f'{label}：{value}'))
        else:
            body_blocks.append(('paragraph', s))

    return NoticeModel(
        title_text=title_text,
        main_recipient=main_recipient if main_recipient else '〔主送机关〕',
        preamble=preamble,
        body_blocks=body_blocks,
        issuer=issuer_val if issuer_val else '',
        document_date=date_val if date_val else '〔日期〕',
    )


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _fail(code: str, *reasons: str) -> None:
    """输出错误并退出。"""
    print(code, file=sys.stderr)
    for r in reasons:
        print(f'  {r}', file=sys.stderr)
    sys.exit(2)


# ══════════════════════════════════════════════════════════════════
# CLI entry
# ══════════════════════════════════════════════════════════════════

def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description='通知 Markdown → NoticeModel 解析器')
    ap.add_argument('--input', '-i', required=True, help='输入 Markdown 文件')
    ap.add_argument('--output', '-o', help='输出 NoticeModel JSON 文件（可选，默认 stdout）')
    args = ap.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        md_text = f.read()

    model = parse_markdown(md_text)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(model.to_json())
        print(f'NoticeModel → {args.output}')
    else:
        print(model.to_json())


if __name__ == '__main__':
    main()
