#!/usr/bin/env python3
"""build_and_validate_notice.py — 通知DOCX统一交付管道（Phase 1 架构收敛）。

Pipeline:
  preflight
  → check source file exists and non-empty
  → check facts file exists
  → recompute source SHA-256 and compare with facts
  → Markdown事实复核
  → Markdown解析 → NoticeModel（唯一内容解析层）
  → DOCX生成（纯Renderer，传入NoticeModel）
  → DOCX事实复核
  → DOCX结构校验（含语义校验，传入NoticeModel）
  → ARTIFACT_READY

source哈希不一致时，在DOCX生成之前终止，不创建DOCX，不输出ARTIFACT_READY。

Usage:
  python3 scripts/build_and_validate_notice.py \
    --source "/path/to/用户原始材料.txt" \
    --facts "/path/to/notice_facts.json" \
    --input "/path/to/通知_最终稿.md" \
    --output "/path/to/通知.docx"
"""

import sys
import os
import json
import hashlib
import hmac
import re
import subprocess
import argparse
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)

# Ensure scripts directory is on path for notice_model import
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from notice_model import parse_markdown

# SHA-256 hex pattern: exactly 64 lowercase hex chars
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')

_KEY_SOURCE_SHA256 = 'source_sha256'


def run_step(name, cmd):
    print(f"[{name}]")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  ❌ 失败 (exit={result.returncode})")
        sys.exit(result.returncode)
    print(f"  ✓ 完成\n")


def verify_source_hash(source_path, facts_path):
    """Recompute source SHA-256 and compare with facts' source_sha256.

    Returns (passed, actual_sha256, facts_sha256, error_msg).
    Terminates the pipeline on failure (before DOCX generation).
    """
    if not os.path.exists(source_path):
        print(f"❌ 原始材料文件不存在: {source_path}")
        print("管道终止，不生成产物")
        sys.exit(3)

    if os.path.getsize(source_path) == 0:
        print(f"❌ 原始材料文件为空: {source_path}")
        print("管道终止，不生成产物")
        sys.exit(3)

    with open(source_path, 'rb') as f:
        raw_bytes = f.read()
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    with open(facts_path, 'r', encoding='utf-8') as f:
        facts = json.load(f)

    facts_sha256 = facts.get(_KEY_SOURCE_SHA256, '')

    if not isinstance(facts_sha256, str) or not _SHA256_RE.match(facts_sha256):
        print(f"❌ 事实清单中的source_sha256不是有效的64位十六进制字符串: '{facts_sha256}'")
        print("SOURCE_SHA256_MISMATCH")
        print(f"事实清单哈希: {facts_sha256}")
        print(f"原始材料实际哈希: {actual_sha256}")
        print("FACT_VALIDATION_FAILED")
        print("管道终止，不生成产物")
        sys.exit(3)

    if not hmac.compare_digest(actual_sha256, facts_sha256):
        print("❌ 原始材料SHA-256核验失败")
        print("SOURCE_SHA256_MISMATCH")
        print(f"事实清单哈希: {facts_sha256}")
        print(f"原始材料实际哈希: {actual_sha256}")
        print("FACT_VALIDATION_FAILED")
        print("管道终止，不生成产物")
        sys.exit(3)

    print(f"  ✓ 原始材料SHA-256核验通过: {actual_sha256}")
    return True, actual_sha256, facts_sha256, None


def main():
    ap = argparse.ArgumentParser(
        description='通知DOCX统一交付管道（Phase 1 架构收敛 — 唯一业务入口）'
    )
    ap.add_argument('--source', required=True,
                    help='用户原始材料文件路径 (必填)')
    ap.add_argument('--facts', '-f', required=True,
                    help='事实清单JSON路径 (notice_facts.json, 必填)')
    ap.add_argument('--input', '-i', required=True,
                    help='输入Markdown文件 (必填)')
    ap.add_argument('--output', '-o', required=True,
                    help='输出DOCX文件 (必填)')
    ap.add_argument('--skip-preflight', action='store_true',
                    help='跳过环境预检')
    args = ap.parse_args()

    # Step 1: preflight
    if not args.skip_preflight:
        run_step("环境预检", [
            sys.executable,
            os.path.join(SCRIPT_DIR, 'preflight_check.py')
        ])

    # Step 2: check source file exists and non-empty
    source_path = os.path.abspath(args.source)
    if not os.path.exists(source_path):
        print(f"❌ 原始材料文件不存在: {source_path}")
        print("管道终止，不生成产物")
        sys.exit(3)

    if os.path.getsize(source_path) == 0:
        print(f"❌ 原始材料文件为空: {source_path}")
        print("管道终止，不生成产物")
        sys.exit(3)

    # Step 3: check facts file exists
    facts_path = os.path.abspath(args.facts)
    if not os.path.exists(facts_path):
        print(f"❌ 事实清单不存在: {facts_path}")
        print("管道终止，不生成产物")
        sys.exit(3)

    if not os.path.exists(args.input):
        print(f"❌ Markdown输入文件不存在: {args.input}")
        sys.exit(4)

    # Step 4-5: recompute source SHA-256 and compare with facts
    print("[原始材料SHA-256核验]")
    verify_source_hash(source_path, facts_path)
    print()

    # Step 6: Markdown事实复核 (before DOCX generation, with --source)
    run_step("Markdown事实复核", [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'fact_check_notice.py'),
        '--source', source_path,
        '--facts', facts_path,
        '--markdown', args.input,
        '--markdown-only',
    ])

    # ── Phase 1 NEW: Markdown解析 → NoticeModel ──
    print("[Markdown解析 → NoticeModel]")
    with open(args.input, 'r', encoding='utf-8') as f:
        md_text = f.read()
    model = parse_markdown(md_text)

    # Save model JSON alongside output
    output_dir = os.path.dirname(os.path.abspath(args.output)) or '.'
    model_json_path = os.path.join(output_dir, 'notice_model.json')
    with open(model_json_path, 'w', encoding='utf-8') as f:
        f.write(model.to_json())
    print(f"  ✓ title_text: {model.title_text[:50]}")
    print(f"  ✓ preamble: {model.preamble[:50]}")
    print(f"  ✓ body_blocks: {len(model.body_blocks)} blocks")
    print(f"  ✓ model JSON: {model_json_path}")
    print()

    # Step 7: generate DOCX (pass NoticeModel, NOT markdown)
    run_step("生成DOCX (Renderer)", [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'fill_tongzhi_docx.py'),
        '--model', model_json_path,
        '--input', args.input,   # for logging only
        '--output', args.output,
    ])

    # Step 8: verify output exists
    if not os.path.exists(args.output) or os.path.getsize(args.output) < 30000:
        print(f"❌ 输出文件异常: {args.output}")
        sys.exit(5)

    # Step 9: DOCX事实复核 (with --source)
    run_step("DOCX事实复核", [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'fact_check_notice.py'),
        '--source', source_path,
        '--facts', facts_path,
        '--markdown', args.input,
        '--docx', args.output,
    ])

    # Step 10: DOCX结构校验（含 Phase 1 语义校验）
    run_step("DOCX结构校验（含语义校验）", [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'validate_notice_docx.py'),
        '--file', args.output,
        '--model', model_json_path,
    ])

    # Step 11: report artifact
    abs_path = os.path.abspath(args.output)
    print(f"ARTIFACT_READY={abs_path}")


if __name__ == '__main__':
    main()
