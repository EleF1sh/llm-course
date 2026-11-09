#!/usr/bin/env python3
"""fact_check_notice.py — 通知事实一致性通用复核器（含原始材料SHA-256强制核验）。

从 --facts JSON 读取动态事实清单，先对 --source 原始材料计算 SHA-256 并与
facts 中的 source_sha256 做安全比较，通过后再对 --markdown 和 --docx 进行逐项对比。

原始材料哈希核验失败时，立即终止，不继续进行 Markdown 或 DOCX 事实校验。

Usage:
  # Full mode: SHA-256 check + Markdown + DOCX fact check
  python3 scripts/fact_check_notice.py \
    --source "/path/to/用户原始材料.txt" \
    --facts "/path/to/notice_facts.json" \
    --markdown "/path/to/通知_最终稿.md" \
    --docx "/path/to/通知.docx"

  # Markdown-only mode: SHA-256 check + Markdown fact check (before DOCX generation)
  python3 scripts/fact_check_notice.py \
    --source "/path/to/用户原始材料.txt" \
    --facts "/path/to/notice_facts.json" \
    --markdown "/path/to/通知_最终稿.md" \
    --markdown-only
"""

import sys
import os
import argparse
import json
import hashlib
import hmac
import re
import zipfile
from xml.etree import ElementTree as ET

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# ── JSON schema keys ───────────────────────────────────────────
_KEY_SCHEMA_VERSION = 'schema_version'
_KEY_SOURCE_SHA256 = 'source_sha256'
_KEY_REQUIRED_EXACT = 'required_exact'
_KEY_REQUIRED_ITEMS = 'required_items'
_KEY_FORBIDDEN_EXACT = 'forbidden_exact'
_KEY_CONTACT = 'contact'
_KEY_ISSUER = 'issuer'
_KEY_DOCUMENT_DATE = 'document_date'

_REQUIRED_TOP_KEYS = [
    _KEY_SCHEMA_VERSION,
    _KEY_SOURCE_SHA256,
    _KEY_REQUIRED_EXACT,
    _KEY_REQUIRED_ITEMS,
    _KEY_FORBIDDEN_EXACT,
    _KEY_CONTACT,
    _KEY_ISSUER,
    _KEY_DOCUMENT_DATE,
]

# SHA-256 hex pattern: exactly 64 lowercase hex chars
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


def extract_docx_text(docx_path):
    """Extract all text from word/document.xml in reading order."""
    with zipfile.ZipFile(docx_path, 'r') as z:
        doc_xml = z.read('word/document.xml')
    root = ET.fromstring(doc_xml)
    body = root.find(f'{{{NS}}}body')
    if body is None:
        return ''
    paras = body.findall(f'{{{NS}}}p')
    lines = []
    for p in paras:
        text = ''.join(t.text or '' for t in p.findall(f'.//{{{NS}}}t'))
        if text.strip():
            lines.append(text)
    return '\n'.join(lines)


def read_markdown_text(md_path):
    """Read markdown file as plain text."""
    with open(md_path, 'r', encoding='utf-8') as f:
        return f.read()


def validate_facts_structure(facts):
    """Validate facts JSON structure. Returns list of errors."""
    errors = []

    for key in _REQUIRED_TOP_KEYS:
        if key not in facts:
            errors.append(f"事实清单缺少顶层键: {key}")

    if errors:
        return errors

    # Validate required_exact is a list
    if not isinstance(facts[_KEY_REQUIRED_EXACT], list):
        errors.append("required_exact 必须是数组")

    # Validate required_items is a list
    if not isinstance(facts[_KEY_REQUIRED_ITEMS], list):
        errors.append("required_items 必须是数组")

    # Validate forbidden_exact is a list
    if not isinstance(facts[_KEY_FORBIDDEN_EXACT], list):
        errors.append("forbidden_exact 必须是数组")

    # Validate contact
    contact = facts.get(_KEY_CONTACT, {})
    if not isinstance(contact, dict):
        errors.append("contact 必须是对象")
    else:
        for ck in ('name', 'phone', 'email'):
            if ck not in contact:
                errors.append(f"contact 缺少键: {ck}")

    return errors


def verify_source_sha256(source_path, facts):
    """Verify source file SHA-256 against facts' source_sha256.

    Returns (passed, actual_sha256, facts_sha256, error_msg).
    """
    # 1. Check source file exists
    if not os.path.exists(source_path):
        return False, None, None, f"原始材料文件不存在: {source_path}"

    # 2. Check source file non-empty
    if os.path.getsize(source_path) == 0:
        return False, None, None, f"原始材料文件为空: {source_path}"

    # 3. Read source raw bytes
    with open(source_path, 'rb') as f:
        raw_bytes = f.read()

    if not raw_bytes:
        return False, None, None, f"原始材料文件内容为空: {source_path}"

    # 4. Compute actual SHA-256
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    # 5. Read facts' source_sha256
    facts_sha256 = facts.get(_KEY_SOURCE_SHA256, '')

    # 6. Check source_sha256 is 64-char hex string
    if not isinstance(facts_sha256, str):
        return False, actual_sha256, str(facts_sha256), \
            f"source_sha256不是字符串: {type(facts_sha256)}"

    if not _SHA256_RE.match(facts_sha256):
        return False, actual_sha256, facts_sha256, \
            f"source_sha256不是有效的64位十六进制字符串: '{facts_sha256}'"

    # 7. Secure comparison using hmac.compare_digest
    if not hmac.compare_digest(actual_sha256, facts_sha256):
        return False, actual_sha256, facts_sha256, \
            f"SOURCE_SHA256_MISMATCH\n事实清单哈希: {facts_sha256}\n原始材料实际哈希: {actual_sha256}"

    # 8. Match
    return True, actual_sha256, facts_sha256, None


def check_text(text, label, facts, failures):
    """Run fact assertions against a single text corpus (markdown or docx).
    Mutates failures list in place.
    """
    # ── required_exact ──
    for item in facts.get(_KEY_REQUIRED_EXACT, []):
        field = item.get('field', '?')
        value = item.get('value', '')
        if value not in text:
            failures.append(f"[{label}] 缺少事实 {field}: '{value}'")

    # ── required_items ──
    for item in facts.get(_KEY_REQUIRED_ITEMS, []):
        field = item.get('field', '?')
        items_list = item.get('items', [])
        found = 0
        for sub in items_list:
            if sub in text:
                found += 1
        if found != len(items_list):
            failures.append(f"[{label}] {field}项数不足: 应{len(items_list)}项，实{found}项")

    # ── forbidden_exact ──
    for item in facts.get(_KEY_FORBIDDEN_EXACT, []):
        field = item.get('field', '?')
        value = item.get('value', '')
        if value and value in text:
            failures.append(f"[{label}] 禁止出现 {field}: '{value}'")

    # ── contact ──
    contact = facts.get(_KEY_CONTACT, {})
    if contact:
        name = contact.get('name', '')
        phone = contact.get('phone', '')
        email = contact.get('email', '')
        if name and name not in text:
            failures.append(f"[{label}] 缺少联系人: {name}")
        if phone and phone not in text:
            failures.append(f"[{label}] 缺少联系电话: {phone}")
        if email and email not in text:
            failures.append(f"[{label}] 缺少电子邮箱: {email}")

    # ── issuer ──
    issuer = facts.get(_KEY_ISSUER, '')
    if issuer and issuer not in text:
        failures.append(f"[{label}] 缺少发文部门: {issuer}")

    # ── document_date ──
    doc_date = facts.get(_KEY_DOCUMENT_DATE, '')
    if doc_date and doc_date not in text:
        failures.append(f"[{label}] 缺少成文日期: {doc_date}")


def cross_check_texts(md_text, docx_text, facts, failures):
    """Check consistency between markdown and DOCX versions."""
    # Check that required_exact values are consistent across both
    for item in facts.get(_KEY_REQUIRED_EXACT, []):
        field = item.get('field', '?')
        value = item.get('value', '')
        in_md = value in md_text
        in_docx = value in docx_text
        if in_md != in_docx:
            failures.append(f"Markdown与DOCX不一致: {field} ('{value}')")

    # Check contact consistency
    contact = facts.get(_KEY_CONTACT, {})
    for ck, label in [('name', '联系人'), ('phone', '联系电话'), ('email', '电子邮箱')]:
        val = contact.get(ck, '')
        if val:
            in_md = val in md_text
            in_docx = val in docx_text
            if in_md != in_docx:
                failures.append(f"Markdown与DOCX{label}不一致")

    # Check issuer consistency
    issuer = facts.get(_KEY_ISSUER, '')
    if issuer:
        in_md = issuer in md_text
        in_docx = issuer in docx_text
        if in_md != in_docx:
            failures.append("Markdown与DOCX发文部门不一致")

    # Check document_date consistency
    doc_date = facts.get(_KEY_DOCUMENT_DATE, '')
    if doc_date:
        in_md = doc_date in md_text
        in_docx = doc_date in docx_text
        if in_md != in_docx:
            failures.append("Markdown与DOCX成文日期不一致")


def check_facts(source_path, facts_path, md_path, docx_path):
    """Run full fact validation including SHA-256 source verification.

    Returns (passed, failures, md_text, docx_text).
    """
    # ── Load facts ──
    with open(facts_path, 'r', encoding='utf-8') as f:
        facts = json.load(f)

    failures = []

    # ── Validate facts structure ──
    struct_errors = validate_facts_structure(facts)
    failures.extend(struct_errors)
    if struct_errors:
        return False, failures, '', ''

    # ── 1. Verify source SHA-256 (MANDATORY — before any content checks) ──
    sha_passed, actual_sha, facts_sha, sha_error = verify_source_sha256(source_path, facts)
    if not sha_passed:
        failures.append(sha_error)
        return False, failures, '', ''

    # ── 2. Read texts ──
    md_text = read_markdown_text(md_path)
    docx_text = extract_docx_text(docx_path)

    if not md_text.strip():
        failures.append("Markdown文件内容为空")
    if not docx_text.strip():
        failures.append("DOCX文件内容为空")

    if failures:
        return False, failures, md_text, docx_text

    # ── 3. Check Markdown ──
    check_text(md_text, 'Markdown', facts, failures)

    # ── 4. Check DOCX ──
    check_text(docx_text, 'DOCX', facts, failures)

    # ── 5. Cross-check consistency ──
    cross_check_texts(md_text, docx_text, facts, failures)

    return len(failures) == 0, failures, md_text, docx_text


def check_markdown_only(source_path, facts_path, md_path):
    """Check SHA-256 + markdown only (before DOCX exists).

    Returns (passed, failures).
    """
    with open(facts_path, 'r', encoding='utf-8') as f:
        facts = json.load(f)

    failures = []
    struct_errors = validate_facts_structure(facts)
    failures.extend(struct_errors)
    if struct_errors:
        return False, failures

    # ── 1. Verify source SHA-256 (MANDATORY — before any content checks) ──
    sha_passed, actual_sha, facts_sha, sha_error = verify_source_sha256(source_path, facts)
    if not sha_passed:
        failures.append(sha_error)
        return False, failures

    md_text = read_markdown_text(md_path)
    if not md_text.strip():
        failures.append("Markdown文件内容为空")
        return False, failures

    check_text(md_text, 'Markdown', facts, failures)
    return len(failures) == 0, failures


def main():
    ap = argparse.ArgumentParser(
        description='通知事实一致性通用复核器（含原始材料SHA-256强制核验）'
    )
    ap.add_argument('--source', required=True,
                    help='用户原始材料文件路径 (必填)')
    ap.add_argument('--facts', required=True,
                    help='事实清单JSON路径 (notice_facts.json, 必填)')
    ap.add_argument('--markdown', required=True,
                    help='Markdown最终稿路径 (必填)')
    ap.add_argument('--docx', default=None,
                    help='DOCX文件路径（markdown-only模式时不需要）')
    ap.add_argument('--markdown-only', action='store_true',
                    help='仅校验Markdown（DOCX生成前使用）')
    args = ap.parse_args()

    # Validate inputs exist
    if not os.path.exists(args.source):
        print(f"FACT_VALIDATION_FAILED: 原始材料文件不存在 {args.source}")
        sys.exit(1)
    if not os.path.exists(args.facts):
        print(f"FACT_VALIDATION_FAILED: 事实清单不存在 {args.facts}")
        sys.exit(1)
    if not os.path.exists(args.markdown):
        print(f"FACT_VALIDATION_FAILED: Markdown文件不存在 {args.markdown}")
        sys.exit(1)

    if args.markdown_only:
        passed, failures = check_markdown_only(args.source, args.facts, args.markdown)
        if passed:
            print("✅ SHA-256核验通过，Markdown事实一致性复核通过")
            print("FACT_VALIDATION_PASSED")
            sys.exit(0)
        else:
            print(f"\n❌ 复核失败 ({len(failures)}项):")
            for f_msg in failures:
                print(f"  - {f_msg}")
            print("\nFACT_VALIDATION_FAILED")
            sys.exit(2)
    else:
        if not args.docx:
            print("FACT_VALIDATION_FAILED: 需要--docx参数（或使用--markdown-only）")
            sys.exit(1)
        if not os.path.exists(args.docx):
            print(f"FACT_VALIDATION_FAILED: DOCX文件不存在 {args.docx}")
            sys.exit(1)

        passed, failures, md_text, docx_text = check_facts(
            args.source, args.facts, args.markdown, args.docx
        )

        if passed:
            print("✅ SHA-256核验通过，事实一致性复核通过")
            print("FACT_VALIDATION_PASSED")
            sys.exit(0)
        else:
            print(f"\n❌ 复核失败 ({len(failures)}项):")
            for f_msg in failures:
                print(f"  - {f_msg}")
            print("\nFACT_VALIDATION_FAILED")
            sys.exit(2)


if __name__ == '__main__':
    main()
