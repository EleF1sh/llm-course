"""Agent Skills：按项目根目录发现技能，按需 loadSkill 加载全文。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import core.config as _cfg

# 仅解析 Frontmatter 时最多读这么多字节，避免把大 SKILL.md 全文载入内存仅为注册
_FRONTMATTER_READ_LIMIT = 16_384
_SKILL_BODY_READ_LIMIT = 200_000

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)",
    re.DOTALL,
)


@dataclass(frozen=True)
class SkillInfo:
    """初始化阶段注册的技能元数据（不含正文）。"""

    name: str
    description: str
    dir: Path
    skill_md: Path


_REGISTRY: dict[str, SkillInfo] = {}
_DISCOVERED = False


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    block = match.group(1)
    data: dict[str, str] = {}
    # 简单 YAML：支持 name: value / name: "value" / 续行不处理（description 单行或引号包裹）
    key: str | None = None
    buf: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if key and (raw_line.startswith("  ") or raw_line.startswith("\t")):
            buf.append(line.strip())
            continue
        if ":" not in line:
            continue
        if key is not None:
            data[key] = _strip_yaml_scalar("\n".join(buf).strip())
        key, _, rest = line.partition(":")
        key = key.strip()
        buf = [rest.lstrip()]
    if key is not None:
        data[key] = _strip_yaml_scalar("\n".join(buf).strip())
    return data


def _strip_yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _read_frontmatter_only(skill_md: Path) -> dict[str, str]:
    try:
        with skill_md.open("r", encoding="utf-8", errors="replace") as fh:
            chunk = fh.read(_FRONTMATTER_READ_LIMIT)
    except OSError:
        return {}
    return _parse_frontmatter(chunk)


def _iter_skill_md_files(skills_dir: Path) -> list[Path]:
    if not skills_dir.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(skills_dir.rglob("SKILL.md")):
        if path.is_file():
            found.append(path)
    return found


def reset_skill_registry() -> None:
    """路径重新初始化后清空缓存，下次 discover 会重扫。"""
    global _DISCOVERED, _REGISTRY
    _DISCOVERED = False
    _REGISTRY = {}


def discover_skills(skills_dir: Path | None = None, *, force: bool = False) -> list[SkillInfo]:
    """扫描 `.agents/skills`，仅注册 name + description。"""
    global _DISCOVERED, _REGISTRY
    if _DISCOVERED and not force:
        return list({id(s): s for s in _REGISTRY.values()}.values())

    root = (skills_dir or _cfg.SKILLS_DIR).resolve()
    registry: dict[str, SkillInfo] = {}
    for skill_md in _iter_skill_md_files(root):
        meta = _read_frontmatter_only(skill_md)
        name = (meta.get("name") or "").strip()
        description = (meta.get("description") or "").strip()
        if not name or not description:
            continue
        info = SkillInfo(
            name=name,
            description=description,
            dir=skill_md.parent.resolve(),
            skill_md=skill_md.resolve(),
        )
        registry[name] = info
        # 目录名别名（如 notice），便于 LLM / 用户用短名加载
        folder = skill_md.parent.name
        if folder and folder not in registry:
            registry[folder] = info

    _REGISTRY = registry
    _DISCOVERED = True
    return list({id(s): s for s in registry.values()}.values())


def get_skill(name: str) -> SkillInfo | None:
    discover_skills()
    key = (name or "").strip()
    if not key:
        return None
    if key in _REGISTRY:
        return _REGISTRY[key]
    # 相对路径别名：notice / @ns/slug
    skills_root = _cfg.SKILLS_DIR.resolve()
    for info in {id(s): s for s in _REGISTRY.values()}.values():
        try:
            rel = info.dir.relative_to(skills_root).as_posix()
        except ValueError:
            rel = info.dir.name
        if key == rel or key == info.dir.name:
            return info
    return None


def skills_catalog_prompt() -> str:
    """仅含 name/description 的 System Prompt 片段。"""
    skills = discover_skills()
    if not skills:
        return (
            "You have access to the following skills:\n"
            "(none discovered under `.agents/skills` of the project root)\n"
            f"Project root: {_cfg.PROJECT_ROOT}\n"
            f"Skills dir: {_cfg.SKILLS_DIR}\n"
            "Use the `loadSkill` tool to load the full instructions of a skill when needed. "
            "You can also load additional files referenced by a skill."
        )

    unique = list(skills)
    unique.sort(key=lambda s: s.name.lower())

    lines = [
        "You have access to the following skills:",
    ]
    for s in unique:
        lines.append(f"- `{s.name}`: {s.description}")
    lines.append(
        "Use the `loadSkill` tool to load the full instructions of a skill when needed. "
        "You can also load additional files referenced by a skill "
        "(pass `filename` relative to the skill directory, or a unique basename)."
    )
    lines.append(f"Project root (cwd at launch): {_cfg.PROJECT_ROOT}")
    lines.append(f"Skills directory: {_cfg.SKILLS_DIR}")
    return "\n".join(lines)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _looks_binary(sample: bytes) -> bool:
    if b"\x00" in sample:
        return True
    if not sample:
        return False
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)))
    nontext = sample.translate(None, text_chars)
    return float(len(nontext)) / float(len(sample)) > 0.30


def _read_text_file(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if _looks_binary(data[:8192]):
        return {
            "ok": False,
            "error": f"拒绝读取二进制文件: {path}",
            "path": str(path),
        }
    text = data.decode("utf-8", errors="replace")
    truncated = False
    if len(text) > _SKILL_BODY_READ_LIMIT:
        text = text[:_SKILL_BODY_READ_LIMIT]
        truncated = True
    return {
        "ok": True,
        "path": str(path),
        "content": text,
        "truncated": truncated,
        "chars": len(text),
    }


def _resolve_attachment(skill: SkillInfo, filename: str) -> dict[str, Any]:
    raw = (filename or "").strip()
    if not raw:
        return {"ok": False, "error": "filename 为空"}

    skill_root = skill.dir.resolve()
    project_root = _cfg.PROJECT_ROOT.resolve()
    candidates: list[Path] = []

    p = Path(raw)
    # 1) 绝对路径
    if p.is_absolute():
        candidates.append(p)
    else:
        # 2) 相对 Skill 目录
        candidates.append(skill_root / p)
        # 3) 相对项目根
        candidates.append(project_root / p)

    # 精确路径：存在且落在 skill 目录内
    exact_hits: list[Path] = []
    for c in candidates:
        try:
            resolved = c.resolve()
        except OSError:
            continue
        if resolved.is_file() and _is_under(resolved, skill_root):
            exact_hits.append(resolved)
    # 去重
    exact_unique = list({str(x): x for x in exact_hits}.values())
    if len(exact_unique) == 1:
        return _read_text_file(exact_unique[0])
    if len(exact_unique) > 1:
        return {
            "ok": False,
            "error": "匹配到多个文件，请指定更精确的路径",
            "candidates": [str(x) for x in exact_unique],
        }

    # 仅文件名：在 Skill 目录内递归搜索
    basename = p.name
    recursive_hits = [
        hit.resolve()
        for hit in skill_root.rglob(basename)
        if hit.is_file() and _is_under(hit.resolve(), skill_root)
    ]
    recursive_unique = list({str(x): x for x in recursive_hits}.values())
    if len(recursive_unique) == 1:
        return _read_text_file(recursive_unique[0])
    if len(recursive_unique) > 1:
        return {
            "ok": False,
            "error": "同名文件不唯一，请用相对 Skill 目录的路径指定其一",
            "candidates": [
                hit.relative_to(skill_root).as_posix() for hit in recursive_unique
            ],
        }

    return {
        "ok": False,
        "error": f"在技能 `{skill.name}` 目录内未找到文件: {raw}",
        "skill_dir": str(skill_root),
    }


def load_skill(name: str, filename: str | None = None) -> dict[str, Any]:
    """按需加载 Skill 正文或附件（结果供 loadSkill 工具返回）。"""
    discover_skills()
    skill = get_skill(name)
    if skill is None:
        available = sorted({s.name for s in _REGISTRY.values()})
        return {
            "ok": False,
            "error": f"未找到技能: {name}",
            "available": available,
            "skills_dir": str(_cfg.SKILLS_DIR),
        }

    fn = (filename or "").strip()
    if not fn:
        body = _read_text_file(skill.skill_md)
        if not body.get("ok"):
            return body
        return {
            "ok": True,
            "skill": skill.name,
            "kind": "skill_md",
            "path": body["path"],
            "content": body["content"],
            "truncated": body.get("truncated", False),
            "chars": body.get("chars"),
            "skill_dir": str(skill.dir),
        }

    attached = _resolve_attachment(skill, fn)
    if not attached.get("ok"):
        attached["skill"] = skill.name
        attached["skill_dir"] = str(skill.dir)
        return attached
    return {
        "ok": True,
        "skill": skill.name,
        "kind": "attachment",
        "filename": fn,
        "path": attached["path"],
        "content": attached["content"],
        "truncated": attached.get("truncated", False),
        "chars": attached.get("chars"),
        "skill_dir": str(skill.dir),
    }


_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_skill_name(raw: str) -> str:
    """统一为小写字母/数字/连字符（kebab-case）。"""
    s = (raw or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def _yaml_quote(value: str) -> str:
    """Frontmatter 标量：含特殊字符时用双引号并转义。"""
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    value = " ".join(value.split())
    if not value:
        return '""'
    needs_quote = bool(re.search(r'[:#\[\]{}",\n]|^\s|\s$', value)) or value.lower() in {
        "true",
        "false",
        "null",
        "yes",
        "no",
    }
    if needs_quote or '"' in value or "\\" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _ensure_skill_md(name: str, skill_context: str) -> tuple[str, dict[str, str] | None]:
    """确保内容含合法 YAML frontmatter；必要时自动补全。返回 (正文, 错误信息)。"""
    text = (skill_context or "").strip()
    if not text:
        return "", {"ok": False, "error": "skillContext 为空"}

    meta = _parse_frontmatter(text)
    if meta.get("name") and meta.get("description"):
        # 强制 frontmatter name 与目录名一致
        fm_name = normalize_skill_name(str(meta["name"]))
        if fm_name != name:
            # 重写 frontmatter 中的 name
            body = _FRONTMATTER_RE.sub("", text, count=1).lstrip("\n")
            desc = str(meta["description"]).strip()
            text = (
                f"---\nname: {name}\n"
                f"description: {_yaml_quote(desc)}\n"
                f"---\n\n{body}"
            )
        return text, None

    # 无完整 frontmatter：从正文抽一行作 description，或用占位
    body = text
    if meta:
        # 有 --- 但缺字段
        body = _FRONTMATTER_RE.sub("", text, count=1).lstrip("\n") or text
    desc = (meta.get("description") or "").strip()
    if not desc:
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("---"):
                continue
            desc = line[:200]
            break
    if not desc:
        desc = f"Skill {name}"
    text = f"---\nname: {name}\ndescription: {_yaml_quote(desc)}\n---\n\n{body}\n"
    return text, None


def create_skill(name: str, skill_context: str) -> dict[str, Any]:
    """在项目 `.agents/skills/<name>/SKILL.md` 新建技能（不覆盖已有）。"""
    raw_name = (name or "").strip()
    slug = normalize_skill_name(raw_name)
    if not slug or not _SKILL_NAME_RE.fullmatch(slug):
        return {
            "ok": False,
            "error": (
                "无效的 Skill 名称。请使用小写英文字母、数字与连字符"
                "（例如 my-skill、notice-helper）。"
            ),
            "received": raw_name,
            "normalized": slug,
        }

    content, err = _ensure_skill_md(slug, skill_context)
    if err:
        return err

    skills_root = _cfg.SKILLS_DIR.resolve()
    skills_root.mkdir(parents=True, exist_ok=True)
    target_dir = (skills_root / slug).resolve()
    try:
        target_dir.relative_to(skills_root)
    except ValueError:
        return {"ok": False, "error": "技能路径越界，已拒绝", "path": str(target_dir)}

    if target_dir.exists():
        return {
            "ok": False,
            "error": f"技能已存在，拒绝覆盖: {slug}",
            "skill_dir": str(target_dir),
            "hint": "请换一个 name，或先用文件工具手动处理已有技能。",
        }

    # 同名 frontmatter 已注册到其它目录时也拒绝
    discover_skills()
    existing = get_skill(slug)
    if existing is not None:
        return {
            "ok": False,
            "error": f"技能名 `{slug}` 已被注册，拒绝覆盖",
            "skill_dir": str(existing.dir),
        }

    target_dir.mkdir(parents=False, exist_ok=False)
    skill_md = target_dir / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8", newline="\n")

    discover_skills(force=True)
    return {
        "ok": True,
        "name": slug,
        "skill_dir": str(target_dir),
        "skill_md": str(skill_md),
        "chars": len(content),
        "hint": (
            "若还需 references/、scripts/ 或其它附件，"
            "请继续用 makeDir / createFile / editFile 在该技能目录下创建。"
        ),
    }
