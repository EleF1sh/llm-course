#!/usr/bin/env python3
"""create_notice_facts.py — 通用事实清单创建脚本。

从用户原始材料文件计算真实 SHA-256，结合 draft JSON 中的动态事实字段，
生成正式的 notice_facts.json。

不信任 draft 中预先填写的 source_sha256，由本脚本重新计算并写入。

Usage:
  python3 scripts/create_notice_facts.py \
    --source "/abs/path/用户原始材料.txt" \
    --draft "/abs/path/notice_facts_draft.json" \
    --output "/abs/path/notice_facts.json"

Output on success:
  FACTS_CREATED
  SOURCE_SHA256=<64-char hex>
  FACTS_READY=<abs path to notice_facts.json>
"""

import sys
import os
import json
import hashlib
import argparse
import re
import tempfile

# ── JSON schema keys ───────────────────────────────────────────
KEY_SCHEMA_VERSION = 'schema_version'
KEY_SOURCE_SHA256 = 'source_sha256'
KEY_REQUIRED_EXACT = 'required_exact'
KEY_REQUIRED_ITEMS = 'required_items'
KEY_FORBIDDEN_EXACT = 'forbidden_exact'
KEY_CONTACT = 'contact'
KEY_ISSUER = 'issuer'
KEY_DOCUMENT_DATE = 'document_date'

REQUIRED_DRAFT_KEYS = [
    KEY_REQUIRED_EXACT,
    KEY_REQUIRED_ITEMS,
    KEY_FORBIDDEN_EXACT,
    KEY_CONTACT,
    KEY_ISSUER,
    KEY_DOCUMENT_DATE,
]

# SHA-256 hex pattern: exactly 64 lowercase hex chars
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

# Skill directory (for output path validation)
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def compute_source_sha256(source_path):
    """Compute SHA-256 of source file using raw bytes.

    Returns 64-character lowercase hexadecimal string.
    """
    with open(source_path, 'rb') as f:
        raw_bytes = f.read()
    return hashlib.sha256(raw_bytes).hexdigest()


def validate_draft(draft):
    """Validate draft JSON structure. Returns list of errors."""
    errors = []

    for key in REQUIRED_DRAFT_KEYS:
        if key not in draft:
            errors.append(f"draft缺少顶层键: {key}")

    if errors:
        return errors

    # Validate required_exact is a list
    if not isinstance(draft[KEY_REQUIRED_EXACT], list):
        errors.append("required_exact 必须是数组")

    # Validate required_items is a list
    if not isinstance(draft[KEY_REQUIRED_ITEMS], list):
        errors.append("required_items 必须是数组")

    # Validate forbidden_exact is a list
    if not isinstance(draft[KEY_FORBIDDEN_EXACT], list):
        errors.append("forbidden_exact 必须是数组")

    # Validate contact
    contact = draft.get(KEY_CONTACT, {})
    if not isinstance(contact, dict):
        errors.append("contact 必须是对象")
    else:
        for ck in ('name', 'phone', 'email'):
            if ck not in contact:
                errors.append(f"contact 缺少键: {ck}")

    # Validate issuer
    if not isinstance(draft.get(KEY_ISSUER), str) or not draft.get(KEY_ISSUER):
        errors.append("issuer 必须是非空字符串")

    # Validate document_date
    if not isinstance(draft.get(KEY_DOCUMENT_DATE), str) or not draft.get(KEY_DOCUMENT_DATE):
        errors.append("document_date 必须是非空字符串")

    return errors


def is_within_skill_dir(path):
    """Check if a path is within the Skill installation directory."""
    abs_path = os.path.abspath(path)
    skill_abs = os.path.abspath(SKILL_DIR)
    return abs_path.startswith(skill_abs + os.sep) or abs_path == skill_abs


def atomic_write_json(path, data):
    """Atomically write JSON to path: write to temp file, then rename.

    Uses UTF-8 encoding with ensure_ascii=False.
    """
    dir_path = os.path.dirname(os.path.abspath(path))
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    # Write to temp file in same directory (for atomic rename on same filesystem)
    fd, tmp_path = tempfile.mkstemp(
        dir=dir_path if dir_path else '.',
        suffix='.tmp',
        prefix='.notice_facts_',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        # Atomic rename (on POSIX, rename is atomic on same filesystem)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def main():
    ap = argparse.ArgumentParser(
        description='创建通知事实清单 (notice_facts.json) — 计算真实source_sha256'
    )
    ap.add_argument('--source', required=True,
                    help='用户原始材料文件路径 (必填)')
    ap.add_argument('--draft', required=True,
                    help='事实清单草稿JSON路径 (notice_facts_draft.json, 必填)')
    ap.add_argument('--output', required=True,
                    help='输出事实清单JSON路径 (notice_facts.json, 必填)')
    args = ap.parse_args()

    # ── 1. Validate source file ──
    source_path = os.path.abspath(args.source)

    if not os.path.exists(source_path):
        print(f"ERROR: source文件不存在: {source_path}", file=sys.stderr)
        sys.exit(1)

    if os.path.getsize(source_path) == 0:
        print(f"ERROR: source文件为空: {source_path}", file=sys.stderr)
        sys.exit(1)

    # ── 2. Validate draft file ──
    draft_path = os.path.abspath(args.draft)

    if not os.path.exists(draft_path):
        print(f"ERROR: draft文件不存在: {draft_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(draft_path, 'r', encoding='utf-8') as f:
            draft = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: draft JSON解析失败: {e}", file=sys.stderr)
        sys.exit(1)

    draft_errors = validate_draft(draft)
    if draft_errors:
        print("ERROR: draft结构校验失败:", file=sys.stderr)
        for err in draft_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # ── 3. Validate output path ──
    output_path = os.path.abspath(args.output)

    if is_within_skill_dir(output_path):
        print(f"ERROR: 输出文件不得位于Skill安装目录中: {output_path}", file=sys.stderr)
        sys.exit(1)

    # ── 4. Compute real SHA-256 from source file bytes ──
    real_sha256 = compute_source_sha256(source_path)

    # Validate computed hash format
    if not _SHA256_RE.match(real_sha256):
        print(f"ERROR: 计算的SHA-256格式异常: {real_sha256}", file=sys.stderr)
        sys.exit(1)

    # ── 5. Build output facts JSON ──
    # Do NOT trust draft's source_sha256 — always use computed value
    facts = {
        KEY_SCHEMA_VERSION: '1.0',
        KEY_SOURCE_SHA256: real_sha256,
        KEY_REQUIRED_EXACT: draft[KEY_REQUIRED_EXACT],
        KEY_REQUIRED_ITEMS: draft[KEY_REQUIRED_ITEMS],
        KEY_FORBIDDEN_EXACT: draft[KEY_FORBIDDEN_EXACT],
        KEY_CONTACT: draft[KEY_CONTACT],
        KEY_ISSUER: draft[KEY_ISSUER],
        KEY_DOCUMENT_DATE: draft[KEY_DOCUMENT_DATE],
    }

    # ── 6. Atomic write ──
    try:
        atomic_write_json(output_path, facts)
    except Exception as e:
        print(f"ERROR: 写入输出文件失败: {e}", file=sys.stderr)
        sys.exit(1)

    # ── 7. Verify written file ──
    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            written = json.load(f)
        if written.get(KEY_SOURCE_SHA256) != real_sha256:
            print(f"ERROR: 写入后的source_sha256不一致", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: 写入文件验证失败: {e}", file=sys.stderr)
        sys.exit(1)

    # ── 8. Success output ──
    print("FACTS_CREATED")
    print(f"SOURCE_SHA256={real_sha256}")
    print(f"FACTS_READY={output_path}")
    sys.exit(0)


if __name__ == '__main__':
    main()
