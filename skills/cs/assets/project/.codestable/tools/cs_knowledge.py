#!/usr/bin/env python3
"""Read and maintain the CodeStable project knowledge wiki.

The tool is intentionally dependency-free. Read commands never write. The only
commands that mutate the wiki are ``learn``, ``reindex`` and ``template`` when
an explicit output path is supplied.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = 1

CATEGORY_DEFS: dict[str, dict[str, Any]] = {
    "requirements": {
        "label": "需求",
        "description": "稳定目标、约束、业务规则与非目标",
        "aliases": ("需求", "requirement", "requirements", "业务规则", "constraint", "goal", "non-goal"),
    },
    "architecture": {
        "label": "架构",
        "description": "组件职责、依赖方向、关键数据流与系统边界",
        "aliases": ("架构", "architecture", "module", "component", "dependency", "模块", "组件", "依赖", "边界"),
    },
    "interfaces": {
        "label": "接口",
        "description": "API、事件、协议、输入输出与失败语义",
        "aliases": ("接口", "api", "interface", "event", "protocol", "endpoint", "事件", "协议", "请求", "响应"),
    },
    "data-model": {
        "label": "数据模型",
        "description": "实体、字段、状态、约束、序列化与迁移语义",
        "aliases": ("数据模型", "data model", "schema", "entity", "field", "状态机", "字段", "实体", "序列化", "数据库", "表"),
    },
    "error-handling": {
        "label": "异常处理",
        "description": "错误分类、传播、重试、降级、恢复与可观测性",
        "aliases": ("异常", "错误", "error", "exception", "retry", "fallback", "降级", "重试", "恢复", "失败"),
    },
    "transaction-boundaries": {
        "label": "事务边界",
        "description": "原子性、提交点、补偿、一致性、幂等与并发边界",
        "aliases": ("事务", "transaction", "atomic", "commit", "rollback", "补偿", "一致性", "幂等", "并发", "锁"),
    },
    "compatibility": {
        "label": "兼容性",
        "description": "公共或持久化兼容、版本、迁移、回滚与弃用",
        "aliases": ("兼容", "compatibility", "backward", "version", "migration", "upgrade", "版本", "迁移", "升级", "弃用", "回滚"),
    },
    "performance-risks": {
        "label": "性能风险",
        "description": "热点、复杂度、容量、延迟、吞吐、内存与外部资源风险",
        "aliases": ("性能", "performance", "latency", "throughput", "memory", "容量", "延迟", "吞吐", "内存", "慢", "热点", "复杂度"),
    },
    "security-boundaries": {
        "label": "安全边界",
        "description": "信任边界、认证授权、敏感数据、输入验证与滥用防护",
        "aliases": ("安全", "security", "auth", "permission", "authorization", "认证", "授权", "权限", "敏感", "secret", "token", "注入"),
    },
    "acceptance": {
        "label": "验收标准",
        "description": "可观察的完成条件、测试矩阵、验证入口与不可接受行为",
        "aliases": ("验收", "acceptance", "test", "verify", "validation", "测试", "验证", "通过", "标准", "matrix"),
    },
    "decisions": {
        "label": "历史决策",
        "description": "已接受或提议的决策、理由、后果、替代方案与取代关系",
        "aliases": ("决策", "decision", "adr", "rationale", "选择", "历史", "替代方案", "why"),
    },
}

CARD_STATUSES = {"current", "proposed", "deprecated", "superseded"}
INPUT_CARD_STATUSES = {"current", "proposed", "deprecated"}
CONFIDENCE_LEVELS = {"verified", "accepted", "inferred"}
TASK_STATUSES = {"completed", "in-progress", "partial", "blocked", "cancelled"}
FRONT_MATTER_ORDER = (
    "id",
    "type",
    "category",
    "title",
    "status",
    "confidence",
    "created_at",
    "updated_at",
    "revision",
    "task_id",
    "task_status",
    "fingerprint",
    "pinned",
    "tags",
    "paths",
    "symbols",
    "supersedes",
    "superseded_by",
    "card_ids",
    "deliverable",
    "knowledge_summary",
    "source",
    "consolidated_into",
)

SECRET_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)

STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "or", "for", "in", "on", "with", "this", "that",
    "fix", "implement", "task", "issue", "feature", "change", "update", "please",
    "修复", "实现", "处理", "任务", "问题", "需求", "功能", "修改", "更新", "一下", "这个", "当前", "项目",
}

PATH_SIGNAL_STOPWORDS = {
    "app", "apps", "lib", "libs", "src", "source", "test", "tests",
    "go", "java", "js", "jsx", "md", "py", "pyi", "rb", "ts", "tsx",
}


class KnowledgeError(RuntimeError):
    """Raised for deterministic user-facing validation failures."""


@dataclass(frozen=True)
class SearchDocument:
    source_type: str
    source_path: str
    title: str
    content: str
    category: str | None = None
    identifier: str | None = None
    status: str = "current"
    confidence: str = "accepted"
    tags: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    pinned: bool = False


@dataclass(frozen=True)
class GitChange:
    status: str
    old_path: str
    new_path: str


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def now_local() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now_local().isoformat(timespec="seconds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clip(value: str, limit: int) -> str:
    value = normalize_space(value)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def unique_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values: Iterable[Any] = [value]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        raise KnowledgeError(f"expected a string array, got {type(value).__name__}")
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = normalize_space(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def safe_int(value: Any, fallback: int, minimum: int = 1, maximum: int = 100_000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(maximum, max(minimum, parsed))


def slugify(value: str, fallback: str = "item") -> str:
    text = normalize_space(value).lower()
    text = re.sub(r"[^\w\u3400-\u9fff]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"[_-]+", "-", text).strip("-")
    return (text[:72].rstrip("-") or fallback)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KnowledgeError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise KnowledgeError(f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}") from exc


def find_project_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".codestable" / "config.json").is_file():
            return candidate
    raise KnowledgeError("could not find .codestable/config.json; run the cs bootstrap first")


def resolve_inside(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise KnowledgeError(f"configured path escapes project root: {relative}") from exc
    return candidate


def load_config(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    path = root / ".codestable" / "config.json"
    data = read_json(path)
    if not isinstance(data, dict):
        raise KnowledgeError(".codestable/config.json must contain a JSON object")
    if data.get("mode") != "knowledge_wiki":
        raise KnowledgeError("project runtime is not in knowledge_wiki mode; run bootstrap.py --upgrade")
    if int(data.get("schema_version", 0) or 0) != SCHEMA_VERSION:
        raise KnowledgeError(
            f"unsupported config schema {data.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
    return data


def configured_categories(config: dict[str, Any]) -> list[str]:
    wiki = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    values = wiki.get("categories") if isinstance(wiki, dict) else None
    categories = unique_strings(values if isinstance(values, list) else list(CATEGORY_DEFS))
    missing = [category for category in CATEGORY_DEFS if category not in categories]
    return [category for category in categories if category in CATEGORY_DEFS] + missing


def wiki_root(root: Path, config: dict[str, Any]) -> Path:
    wiki = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    relative = str(wiki.get("root") or ".codestable/wiki")
    return resolve_inside(root, relative)


def parse_front_matter_text(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise KnowledgeError("unterminated Markdown front matter")
    raw = normalized[4:end]
    metadata: dict[str, Any] = {}
    for number, line in enumerate(raw.splitlines(), start=2):
        if not line.strip():
            continue
        if ":" not in line:
            raise KnowledgeError(f"invalid front matter line {number}: missing ':'")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            raise KnowledgeError(f"invalid front matter line {number}: empty key")
        if not raw_value:
            metadata[key] = ""
            continue
        try:
            metadata[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            metadata[key] = raw_value
    return metadata, normalized[end + 5 :]


def read_markdown(path: Path) -> tuple[dict[str, Any], str, str]:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_front_matter_text(text)
    return metadata, body, text


def render_front_matter(metadata: dict[str, Any], body: str) -> str:
    keys = [key for key in FRONT_MATTER_ORDER if key in metadata]
    keys.extend(sorted(key for key in metadata if key not in keys))
    lines = ["---"]
    for key in keys:
        lines.append(f"{key}: {json.dumps(metadata[key], ensure_ascii=False, sort_keys=True)}")
    lines.extend(("---", "", body.rstrip(), ""))
    return "\n".join(lines)


def extract_heading(body: str, fallback: str) -> str:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", body)
    return normalize_space(match.group(1)) if match else fallback


def extract_section(body: str, headings: Sequence[str]) -> str:
    escaped = "|".join(re.escape(value) for value in headings)
    match = re.search(rf"(?ms)^##\s+(?:{escaped})\s*$\n(.*?)(?=^##\s+|\Z)", body)
    if not match:
        return ""
    content = match.group(1).strip()
    content = re.sub(r"(?m)^[-*]\s+", "", content)
    return normalize_space(content)


def extract_canonical(text: str) -> str:
    match = re.search(
        r"<!--\s*codestable:canonical:start\s*-->(.*?)<!--\s*codestable:canonical:end\s*-->",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""
    content = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL).strip()
    return normalize_space(content)


def markdown_bullets(values: Sequence[str], empty: str = "- 无") -> str:
    cleaned = [normalize_space(value) for value in values if normalize_space(value)]
    return "\n".join(f"- {value}" for value in cleaned) if cleaned else empty


def recursive_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from recursive_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from recursive_strings(item)


def detect_secret(value: Any) -> str | None:
    for text in recursive_strings(value):
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                return name
    return None


def normalize_task(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("learning payload task must be an object")
    title = normalize_space(raw.get("title"))
    summary = normalize_space(raw.get("summary"))
    result = normalize_space(raw.get("result"))
    status = normalize_space(raw.get("status") or "completed").lower()
    if not title:
        raise KnowledgeError("task.title is required")
    if not summary:
        raise KnowledgeError("task.summary is required")
    if not result:
        raise KnowledgeError("task.result is required")
    if status not in TASK_STATUSES:
        raise KnowledgeError(f"task.status must be one of {sorted(TASK_STATUSES)}")
    source = raw.get("source") or {}
    if not isinstance(source, dict):
        raise KnowledgeError("task.source must be an object")
    task_id = normalize_space(raw.get("id"))
    raw_update_existing = raw.get("update_existing", False)
    if not isinstance(raw_update_existing, bool):
        raise KnowledgeError("task.update_existing must be a boolean")
    update_existing = raw_update_existing
    expected_revision = raw.get("expected_revision")
    if update_existing:
        if not re.fullmatch(r"T-[A-Za-z0-9-]+", task_id):
            raise KnowledgeError("task.id must be an existing T-* identifier when task.update_existing is true")
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise KnowledgeError("task.expected_revision must be a positive integer when updating a task")
    elif task_id or expected_revision is not None:
        raise KnowledgeError("task.id and task.expected_revision require task.update_existing=true")
    return {
        "id": task_id,
        "update_existing": update_existing,
        "expected_revision": expected_revision,
        "title": title,
        "kind": normalize_space(raw.get("kind") or "task"),
        "status": status,
        "request": normalize_space(raw.get("request")),
        "summary": summary,
        "result": result,
        "paths": unique_strings(raw.get("paths")),
        "symbols": unique_strings(raw.get("symbols")),
        "tags": unique_strings(raw.get("tags")),
        "verification": unique_strings(raw.get("verification")),
        "deliverable": normalize_space(raw.get("deliverable")),
        "knowledge_summary": normalize_space(raw.get("knowledge_summary")),
        "source": source,
    }


def normalize_item(raw: Any, task: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("every learning item must be an object")
    category = normalize_space(raw.get("category"))
    if category not in CATEGORY_DEFS:
        raise KnowledgeError(f"item.category must be one of {sorted(CATEGORY_DEFS)}")
    title = normalize_space(raw.get("title"))
    knowledge = normalize_space(raw.get("knowledge"))
    if not title:
        raise KnowledgeError("item.title is required")
    if not knowledge:
        raise KnowledgeError("item.knowledge is required")
    confidence = normalize_space(raw.get("confidence") or "accepted").lower()
    if confidence not in CONFIDENCE_LEVELS:
        raise KnowledgeError(f"item.confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
    status = normalize_space(raw.get("status") or "current").lower()
    if status not in INPUT_CARD_STATUSES:
        raise KnowledgeError(f"item.status must be one of {sorted(INPUT_CARD_STATUSES)}")
    evidence = unique_strings(raw.get("evidence"))
    if confidence == "verified" and not evidence and not task["verification"]:
        raise KnowledgeError(f"verified item '{title}' requires item.evidence or task.verification")
    rationale = normalize_space(raw.get("rationale"))
    implications = unique_strings(raw.get("implications"))
    if category == "decisions" and not rationale:
        raise KnowledgeError(f"decision item '{title}' requires rationale")
    return {
        "category": category,
        "title": title,
        "knowledge": knowledge,
        "rationale": rationale,
        "implications": implications,
        "paths": unique_strings(raw.get("paths")) or list(task["paths"]),
        "symbols": unique_strings(raw.get("symbols")) or list(task["symbols"]),
        "tags": unique_strings(raw.get("tags")) or list(task["tags"]),
        "evidence": evidence or list(task["verification"]),
        "confidence": confidence,
        "status": status,
        "supersedes": unique_strings(raw.get("supersedes")),
        "pinned": bool(raw.get("pinned", False)),
    }


def normalize_learning_payload(raw: Any, config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        raise KnowledgeError("learning payload must be a JSON object")
    if set(raw) - {"task", "items"}:
        unknown = ", ".join(sorted(set(raw) - {"task", "items"}))
        raise KnowledgeError(f"unknown top-level learning fields: {unknown}")
    task = normalize_task(raw.get("task"))
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        raise KnowledgeError("learning payload items must be an array")
    items = [normalize_item(item, task) for item in raw_items]
    if task["status"] != "completed" and items:
        raise KnowledgeError("only completed tasks may create or reuse durable knowledge cards; keep items empty until final acceptance")
    capture = config.get("capture") if isinstance(config.get("capture"), dict) else {}
    if bool(capture.get("secret_scan", True)):
        secret = detect_secret({"task": task, "items": items})
        if secret:
            raise KnowledgeError(f"learning payload appears to contain a {secret}; remove secrets before capture")
    return task, items


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def item_fingerprint(item: dict[str, Any]) -> str:
    material = {
        "category": item["category"],
        "title": item["title"],
        "knowledge": item["knowledge"],
        "rationale": item["rationale"],
        "implications": item["implications"],
        "paths": item["paths"],
        "symbols": item["symbols"],
        "tags": item["tags"],
        "evidence": item["evidence"],
        "confidence": item["confidence"],
        "status": item["status"],
        "supersedes": item["supersedes"],
        "pinned": item["pinned"],
    }
    return sha256_text(stable_json(material))


def task_fingerprint(task: dict[str, Any], items: Sequence[dict[str, Any]]) -> str:
    task_content = {
        key: value
        for key, value in task.items()
        if key not in {"id", "update_existing", "expected_revision"}
    }
    material = {
        "task": task_content,
        "items": [item_fingerprint(item) for item in items],
    }
    return sha256_text(stable_json(material))


def legacy_task_fingerprint(task: dict[str, Any], items: Sequence[dict[str, Any]]) -> str:
    """Fingerprint produced before task update controls and deliverable existed."""
    task_content = {
        key: value
        for key, value in task.items()
        if key not in {"id", "update_existing", "expected_revision", "deliverable", "knowledge_summary"}
    }
    return sha256_text(stable_json({"task": task_content, "items": [item_fingerprint(item) for item in items]}))


def make_id(prefix: str, fingerprint: str, timestamp: datetime, sequence: int = 0) -> str:
    base = timestamp.strftime("%Y%m%d-%H%M%S")
    suffix = fingerprint[:8]
    return f"{prefix}-{base}-{sequence:02d}-{suffix}" if sequence else f"{prefix}-{base}-{suffix}"


def render_card_body(item: dict[str, Any], task: dict[str, Any], task_id: str) -> str:
    source = task.get("source") or {}
    source_text = json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) if source else "{}"
    return f"""# {item['title']}

## 结论

{item['knowledge']}

## 背景与理由

{item['rationale'] or '未单独记录；参见来源任务。'}

## 影响

{markdown_bullets(item['implications'])}

## 适用范围

- 路径：{', '.join(item['paths']) or '未限定'}
- 符号：{', '.join(item['symbols']) or '未限定'}
- 标签：{', '.join(item['tags']) or '无'}

## 验证与依据

{markdown_bullets(item['evidence'])}

## 来源任务

- 任务：{task['title']}
- 任务记录：`{task_id}`
- 状态：{task['status']}
- 结果：{task['result']}

```json
{source_text}
```
"""


def render_task_body(task: dict[str, Any], task_id: str, card_ids: Sequence[str]) -> str:
    source = task.get("source") or {}
    source_text = json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) if source else "{}"
    linked = markdown_bullets([f"`{card_id}`" for card_id in card_ids], empty="- 本任务没有产生独立的长期知识卡片。")
    return f"""# {task['title']}

## 请求

{task['request'] or '未单独记录。'}

## 处理摘要

{task['summary']}

## 最终结果

{task['result']}

## 验证

{markdown_bullets(task['verification'])}

## 变更范围

- 路径：{', '.join(task['paths']) or '未记录'}
- 符号：{', '.join(task['symbols']) or '未记录'}
- 标签：{', '.join(task['tags']) or '无'}
- 主要交付物：{task['deliverable'] or '未单独记录'}

## 沉淀的知识卡片

{linked}

## 知识处置

{task['knowledge_summary'] or '未说明；完成任务前应写明新增、复用、取代了哪些知识，或为什么没有长期知识。'}

## 来源

```json
{source_text}
```
"""


def card_paths(wiki: Path, categories: Sequence[str]) -> Iterator[Path]:
    for category in categories:
        directory = wiki / category
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name in {"README.md", "INDEX.md"}:
                continue
            yield path


def task_note_paths(wiki: Path) -> Iterator[Path]:
    directory = wiki / "task-notes"
    if not directory.is_dir():
        return
    for path in sorted(directory.rglob("*.md")):
        yield path


def scan_existing_records(wiki: Path, categories: Sequence[str]) -> tuple[dict[str, tuple[Path, dict[str, Any], str]], dict[str, tuple[Path, dict[str, Any], str]]]:
    cards: dict[str, tuple[Path, dict[str, Any], str]] = {}
    tasks: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for path in card_paths(wiki, categories):
        metadata, body, _ = read_markdown(path)
        identifier = normalize_space(metadata.get("id"))
        if identifier:
            cards[identifier] = (path, metadata, body)
    for path in task_note_paths(wiki):
        metadata, body, _ = read_markdown(path)
        identifier = normalize_space(metadata.get("id"))
        if identifier:
            tasks[identifier] = (path, metadata, body)
    return cards, tasks


def task_note_filename(task: dict[str, Any], task_id: str, timestamp: datetime) -> Path:
    slug = slugify(task["title"], "task")
    return Path("task-notes") / timestamp.strftime("%Y") / f"{timestamp.strftime('%Y-%m-%d')}-{slug}-{task_id[-8:].lower()}.md"


def card_filename(item: dict[str, Any], card_id: str) -> Path:
    return Path(item["category"]) / f"{card_id.lower()}-{slugify(item['title'], 'knowledge')}.md"


def update_card_supersession(path: Path, new_id: str, timestamp: str, dry_run: bool) -> None:
    metadata, body, _ = read_markdown(path)
    metadata["status"] = "superseded"
    metadata["updated_at"] = timestamp
    values = unique_strings(metadata.get("superseded_by"))
    if new_id not in values:
        values.append(new_id)
    metadata["superseded_by"] = values
    if not dry_run:
        atomic_write_text(path, render_front_matter(metadata, body))


def index_entry_for(
    path: Path,
    root: Path,
    metadata: dict[str, Any],
    body: str,
    rendered_text: str | None = None,
) -> dict[str, Any]:
    source_type = normalize_space(metadata.get("type") or "unknown")
    excerpt = extract_section(body, ("结论", "处理摘要", "最终结果")) or clip(body, 400)
    return {
        "id": normalize_space(metadata.get("id")),
        "type": source_type,
        "category": normalize_space(metadata.get("category")) or None,
        "title": normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
        "status": normalize_space(metadata.get("status") or metadata.get("task_status") or "current"),
        "confidence": normalize_space(metadata.get("confidence") or "accepted"),
        "path": path.relative_to(root).as_posix(),
        "created_at": normalize_space(metadata.get("created_at")),
        "updated_at": normalize_space(metadata.get("updated_at")),
        "tags": unique_strings(metadata.get("tags")),
        "paths": unique_strings(metadata.get("paths")),
        "symbols": unique_strings(metadata.get("symbols")),
        "supersedes": unique_strings(metadata.get("supersedes")),
        "superseded_by": unique_strings(metadata.get("superseded_by")),
        "card_ids": unique_strings(metadata.get("card_ids")),
        "pinned": bool(metadata.get("pinned", False)),
        "fingerprint": normalize_space(metadata.get("fingerprint")),
        "sha256": sha256_text(rendered_text) if rendered_text is not None else sha256_file(path),
        "excerpt": clip(excerpt, 400),
    }


def collect_index_entries(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    entries: list[dict[str, Any]] = []
    for path in card_paths(wiki, configured_categories(config)):
        metadata, body, _ = read_markdown(path)
        entries.append(index_entry_for(path, root, metadata, body))
    for path in task_note_paths(wiki):
        metadata, body, _ = read_markdown(path)
        entries.append(index_entry_for(path, root, metadata, body))
    return sorted(
        entries,
        key=lambda item: (
            0 if item["type"] == "knowledge-card" else 1,
            item.get("category") or "",
            item.get("created_at") or "",
            item.get("id") or "",
        ),
    )


def relative_link(from_path: Path, target_path: Path) -> str:
    return Path(os.path.relpath(target_path, from_path.parent)).as_posix()


def render_root_index(root: Path, config: dict[str, Any], entries: Sequence[dict[str, Any]]) -> str:
    wiki = wiki_root(root, config)
    cards = [entry for entry in entries if entry["type"] == "knowledge-card"]
    tasks = [entry for entry in entries if entry["type"] == "task-note"]
    lines = [
        "# CodeStable Wiki Index",
        "",
        f"- 当前知识卡片：{sum(1 for entry in cards if entry['status'] in {'current', 'proposed'})}",
        f"- 已取代/弃用卡片：{sum(1 for entry in cards if entry['status'] in {'superseded', 'deprecated'})}",
        f"- 任务记录：{len(tasks)}",
        "",
        "## 知识分区",
        "",
        "| 分区 | 当前 | 提议 | 历史 |",
        "|---|---:|---:|---:|",
    ]
    for category in configured_categories(config):
        category_cards = [entry for entry in cards if entry.get("category") == category]
        current = sum(entry["status"] == "current" for entry in category_cards)
        proposed = sum(entry["status"] == "proposed" for entry in category_cards)
        history = sum(entry["status"] in {"superseded", "deprecated"} for entry in category_cards)
        label = CATEGORY_DEFS[category]["label"]
        lines.append(f"| [{label}]({category}/INDEX.md) | {current} | {proposed} | {history} |")
    lines.extend(("", "## 最近任务", ""))
    recent = sorted(tasks, key=lambda item: (item.get("created_at") or "", item.get("id") or ""), reverse=True)[:20]
    if not recent:
        lines.append("- 暂无任务记录。")
    else:
        index_path = wiki / "INDEX.md"
        for entry in recent:
            target = root / entry["path"]
            lines.append(
                f"- [{entry['title']}]({relative_link(index_path, target)}) · "
                f"{entry['status']} · {entry.get('created_at') or 'unknown time'}"
            )
    lines.extend(("", "参见 [Wiki 使用说明](README.md) 和 [项目总览](PROJECT.md)。", ""))
    return "\n".join(lines)


def render_category_index(root: Path, config: dict[str, Any], category: str, entries: Sequence[dict[str, Any]]) -> str:
    wiki = wiki_root(root, config)
    path = wiki / category / "INDEX.md"
    label = CATEGORY_DEFS[category]["label"]
    cards = [entry for entry in entries if entry["type"] == "knowledge-card" and entry.get("category") == category]
    lines = [f"# {label} · Index", "", CATEGORY_DEFS[category]["description"], ""]
    groups = (
        ("当前知识", {"current"}),
        ("提议知识", {"proposed"}),
        ("已弃用", {"deprecated"}),
        ("已被取代", {"superseded"}),
    )
    for heading, statuses in groups:
        group = sorted(
            [entry for entry in cards if entry["status"] in statuses],
            key=lambda item: (bool(item.get("pinned")), item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        lines.extend((f"## {heading}", ""))
        if not group:
            lines.append("- 无")
        else:
            for entry in group:
                target = root / entry["path"]
                suffixes = [entry.get("confidence") or "accepted"]
                if entry.get("pinned"):
                    suffixes.append("pinned")
                lines.append(
                    f"- [{entry['title']}]({relative_link(path, target)}) · {' · '.join(suffixes)}  \n"
                    f"  {entry.get('excerpt') or ''}"
                )
        lines.append("")
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成；人工摘要请维护在 [README.md](README.md)。")
    lines.append("")
    return "\n".join(lines)


def render_index_outputs(
    root: Path,
    config: dict[str, Any],
    entries: Sequence[dict[str, Any]],
) -> dict[Path, str]:
    wiki = wiki_root(root, config)
    jsonl = "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)
    outputs: dict[Path, str] = {
        wiki / "index.jsonl": jsonl,
        wiki / "INDEX.md": render_root_index(root, config, entries),
    }
    for category in configured_categories(config):
        outputs[wiki / category / "INDEX.md"] = render_category_index(root, config, category, entries)
    return outputs


def build_index_outputs(root: Path, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[Path, str]]:
    root = root.expanduser().resolve()
    entries = collect_index_entries(root, config)
    return entries, render_index_outputs(root, config, entries)


def rebuild_indexes(root: Path, config: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    entries, outputs = build_index_outputs(root, config)
    changed: list[str] = []
    for path, content in outputs.items():
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
        if existing != content:
            changed.append(path.relative_to(root).as_posix())
            if not dry_run:
                atomic_write_text(path, content)
    return {"entries": len(entries), "changed": changed, "dry_run": dry_run}


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def restore_recovery_journal(root: Path, transaction: Path) -> None:
    ready = transaction / "READY"
    committed = transaction / "COMMITTED"
    manifest_path = transaction / "manifest.json"
    if committed.is_file() or not ready.is_file():
        shutil.rmtree(transaction)
        return
    manifest = read_json(manifest_path)
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise KnowledgeError(f"invalid recovery journal: {manifest_path}")
    for entry in entries:
        if not isinstance(entry, dict):
            raise KnowledgeError(f"invalid recovery entry in {manifest_path}")
        target = resolve_inside(root, normalize_space(entry.get("path")))
        backup = normalize_space(entry.get("backup"))
        if backup:
            source = transaction / backup
            atomic_write_text(target, source.read_text(encoding="utf-8"))
        elif target.is_file():
            target.unlink()
    shutil.rmtree(transaction)


def recover_transactions(root: Path, wiki: Path) -> None:
    transactions = wiki / ".transactions"
    if transactions.is_dir():
        for transaction in sorted(path for path in transactions.iterdir() if path.is_dir()):
            restore_recovery_journal(root, transaction)
        try:
            transactions.rmdir()
        except OSError:
            pass


def recover_abandoned_write(root: Path, wiki: Path, lock: Path) -> None:
    try:
        lock_data = read_json(lock)
    except KnowledgeError as exc:
        raise KnowledgeError(f"cannot inspect existing wiki write lock {lock}: {exc}") from exc
    pid = int(lock_data.get("pid", 0) or 0) if isinstance(lock_data, dict) else 0
    if process_is_alive(pid):
        raise KnowledgeError(f"wiki write lock already exists: {lock}; writer pid {pid} is active")
    recover_transactions(root, wiki)
    lock.unlink()


def acquire_lock(root: Path, wiki: Path) -> Path:
    lock = wiki / ".write.lock"
    wiki.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        recover_abandoned_write(root, wiki, lock)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise KnowledgeError(f"wiki write lock already exists: {lock}; inspect and remove it only if no writer is active") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(json_dump({"pid": os.getpid(), "created_at": now_iso()}))
    try:
        recover_transactions(root, wiki)
    except Exception:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        raise
    return lock


def create_recovery_journal(
    root: Path,
    wiki: Path,
    task_id: str,
    snapshot: dict[Path, str | None],
) -> Path:
    transactions = wiki / ".transactions"
    transaction = transactions / task_id.lower()
    if transaction.exists():
        raise KnowledgeError(f"knowledge transaction already exists: {transaction}")
    transaction.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    try:
        for number, (path, content) in enumerate(sorted(snapshot.items(), key=lambda item: str(item[0])), start=1):
            backup = ""
            if content is not None:
                backup = f"files/{number:04d}.txt"
                atomic_write_text(transaction / backup, content)
            entries.append({"path": path.relative_to(root).as_posix(), "backup": backup})
        atomic_write_text(
            transaction / "manifest.json",
            json_dump({"schema_version": 1, "task_id": task_id, "entries": entries}),
        )
        atomic_write_text(transaction / "READY", "ready\n")
    except Exception:
        shutil.rmtree(transaction, ignore_errors=True)
        try:
            transactions.rmdir()
        except OSError:
            pass
        raise
    return transaction


def remove_recovery_journal(transaction: Path) -> None:
    transactions = transaction.parent
    shutil.rmtree(transaction)
    try:
        transactions.rmdir()
    except OSError:
        pass


def restore_snapshot(snapshot: dict[Path, str | None], wiki: Path) -> None:
    errors: list[str] = []
    for path, content in snapshot.items():
        try:
            if content is None:
                if path.is_file():
                    path.unlink()
            else:
                atomic_write_text(path, content)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    task_root = wiki / "task-notes"
    for path, content in snapshot.items():
        if content is not None:
            continue
        parent = path.parent
        while parent != task_root and task_root in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    if errors:
        raise KnowledgeError("failed to roll back knowledge write: " + "; ".join(errors))


def projected_index_plan(
    root: Path,
    config: dict[str, Any],
    cards: dict[str, tuple[Path, dict[str, Any], str]],
    tasks: dict[str, tuple[Path, dict[str, Any], str]],
    created_plan: Sequence[tuple[str, Path, dict[str, Any], str, dict[str, Any]]],
    task_path: Path,
    task_metadata: dict[str, Any],
    task_body: str,
    supersession_plan: Sequence[tuple[str, str]],
    timestamp_text: str,
    replaced_task_id: str | None = None,
) -> dict[str, Any]:
    superseded_by: dict[str, list[str]] = {}
    for old_id, new_id in supersession_plan:
        superseded_by.setdefault(old_id, []).append(new_id)

    entries: list[dict[str, Any]] = []
    for identifier, (path, metadata, body) in cards.items():
        projected = dict(metadata)
        if identifier in superseded_by:
            projected["status"] = "superseded"
            projected["updated_at"] = timestamp_text
            values = unique_strings(projected.get("superseded_by"))
            for new_id in superseded_by[identifier]:
                if new_id not in values:
                    values.append(new_id)
            projected["superseded_by"] = values
        rendered = render_front_matter(projected, body)
        entries.append(index_entry_for(path, root, projected, body, rendered))
    for identifier, (path, metadata, body) in tasks.items():
        if identifier == replaced_task_id:
            continue
        rendered = render_front_matter(metadata, body)
        entries.append(index_entry_for(path, root, metadata, body, rendered))
    for _, path, metadata, body, _ in created_plan:
        rendered = render_front_matter(metadata, body)
        entries.append(index_entry_for(path, root, metadata, body, rendered))
    rendered_task = render_front_matter(task_metadata, task_body)
    entries.append(index_entry_for(task_path, root, task_metadata, task_body, rendered_task))
    entries.sort(
        key=lambda item: (
            0 if item["type"] == "knowledge-card" else 1,
            item.get("category") or "",
            item.get("created_at") or "",
            item.get("id") or "",
        )
    )
    outputs = render_index_outputs(root, config, entries)
    changed = [
        path.relative_to(root).as_posix()
        for path, content in outputs.items()
        if (path.read_text(encoding="utf-8") if path.is_file() else None) != content
    ]
    return {"entries": len(entries), "changed": changed, "dry_run": True}


def task_similarity_candidates(
    task: dict[str, Any],
    tasks: dict[str, tuple[Path, dict[str, Any], str]],
    root: Path,
) -> list[dict[str, Any]]:
    title = normalize_space(task["title"]).casefold()
    paths = set(task["paths"])
    deliverable = normalize_space(task.get("deliverable")).casefold()
    candidates: list[dict[str, Any]] = []
    for identifier, (path, metadata, _) in tasks.items():
        reasons: list[str] = []
        if title and normalize_space(metadata.get("title")).casefold() == title:
            reasons.append("same-title")
        shared_paths = sorted(paths & set(unique_strings(metadata.get("paths"))))
        if shared_paths:
            reasons.append("shared-paths")
        existing_deliverable = normalize_space(metadata.get("deliverable")).casefold()
        if deliverable and existing_deliverable == deliverable:
            reasons.append("same-deliverable")
        if "same-title" in reasons or "same-deliverable" in reasons or len(shared_paths) >= 2:
            candidates.append(
                {
                    "task_id": identifier,
                    "task_note": path.relative_to(root).as_posix(),
                    "task_status": normalize_space(metadata.get("task_status") or "completed"),
                    "revision": int(metadata.get("revision", 1) or 1),
                    "reasons": reasons,
                }
            )
    return candidates


def card_similarity_candidates(
    items: Sequence[dict[str, Any]],
    cards: dict[str, tuple[Path, dict[str, Any], str]],
    root: Path,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items:
        title = normalize_space(item["title"]).casefold()
        fingerprint = item_fingerprint(item)
        for identifier, (path, metadata, _) in cards.items():
            if normalize_space(metadata.get("status") or "current") == "superseded":
                continue
            if normalize_space(metadata.get("category")) != item["category"]:
                continue
            if normalize_space(metadata.get("fingerprint")) == fingerprint:
                continue
            if normalize_space(metadata.get("title")).casefold() != title:
                continue
            if identifier in item["supersedes"]:
                continue
            candidates.append(
                {
                    "item_title": item["title"],
                    "card_id": identifier,
                    "card_path": path.relative_to(root).as_posix(),
                    "reason": "same-category-and-title",
                    "action": "reuse, merge into the existing card, or explicitly supersede it",
                }
            )
    return candidates


def knowledge_state_fingerprint(root: Path, config: dict[str, Any]) -> str:
    wiki = wiki_root(root, config)
    paths: set[Path] = set(card_paths(wiki, configured_categories(config)))
    paths.update(task_note_paths(wiki))
    _, outputs = build_index_outputs(root, config)
    paths.update(outputs)
    paths.add(root / ".codestable" / "config.json")
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def workspace_state_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    git_probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    if git_probe.returncode == 0:
        head = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=str(root), capture_output=True, check=False)
        if head.returncode == 0:
            digest.update(head.stdout)
            diff = subprocess.run(
                ["git", "diff", "--binary", "HEAD", "--", ".", ":(exclude).codestable/**"],
                cwd=str(root),
                capture_output=True,
                check=False,
            )
            if diff.returncode != 0:
                raise KnowledgeError(normalize_space(diff.stderr.decode("utf-8", errors="replace")) or "cannot fingerprint Git worktree")
            digest.update(diff.stdout)
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard", "-z"],
                cwd=str(root),
                capture_output=True,
                check=False,
            )
            if untracked.returncode != 0:
                raise KnowledgeError(normalize_space(untracked.stderr.decode("utf-8", errors="replace")) or "cannot fingerprint untracked files")
            for raw_path in sorted(value for value in untracked.stdout.split(b"\0") if value):
                relative = raw_path.decode("utf-8", errors="surrogateescape")
                if relative == ".codestable" or relative.startswith(".codestable/"):
                    continue
                path = root / relative
                digest.update(raw_path)
                digest.update(b"\0")
                if path.is_file():
                    digest.update(path.read_bytes())
                digest.update(b"\0")
            return digest.hexdigest()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in {".codestable", ".git"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def encode_plan_token(
    task_fingerprint_value: str,
    state_fingerprint: str,
    workspace_fingerprint: str,
    timestamp: datetime,
) -> str:
    payload = stable_json(
        {
            "schema_version": 1,
            "task_fingerprint": task_fingerprint_value,
            "state_fingerprint": state_fingerprint,
            "workspace_fingerprint": workspace_fingerprint,
            "timestamp": timestamp.isoformat(timespec="seconds"),
        }
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_plan_token(token: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError("invalid learn plan token") from exc
    if not isinstance(value, dict) or int(value.get("schema_version", 0) or 0) != 1:
        raise KnowledgeError("unsupported learn plan token")
    return value


def _learn_locked(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    task, items = normalize_learning_payload(payload, config)
    wiki = wiki_root(root, config)
    categories = configured_categories(config)
    workspace_before_scan = workspace_state_fingerprint(root)
    state_before_scan = knowledge_state_fingerprint(root, config)
    cards, tasks = scan_existing_records(wiki, categories)
    task_fp = task_fingerprint(task, items)
    legacy_task_fp = legacy_task_fingerprint(task, items)
    state_fp = knowledge_state_fingerprint(root, config)
    workspace_fp = workspace_state_fingerprint(root)
    if state_before_scan != state_fp:
        raise KnowledgeError("project knowledge changed while planning learn; retry the command")
    if workspace_before_scan != workspace_fp:
        raise KnowledgeError("project workspace changed while planning learn; retry the command")
    plan: dict[str, Any] | None = None
    if plan_token:
        plan = decode_plan_token(plan_token)
        if normalize_space(plan.get("task_fingerprint")) != task_fp:
            raise KnowledgeError("learn plan token does not match this payload")
        try:
            timestamp = datetime.fromisoformat(normalize_space(plan.get("timestamp")))
        except ValueError as exc:
            raise KnowledgeError("learn plan token has an invalid timestamp") from exc
    else:
        timestamp = now_local()
    if plan and normalize_space(plan.get("state_fingerprint")) != state_fp:
        raise KnowledgeError("project knowledge changed after dry-run; run learn --dry-run again")
    if plan and normalize_space(plan.get("workspace_fingerprint")) != workspace_fp:
        raise KnowledgeError("project workspace changed after dry-run; run learn --dry-run again")
    generated_plan_token = encode_plan_token(task_fp, state_fp, workspace_fp, timestamp)
    update_existing = bool(task["update_existing"])
    target_task_id = task["id"] if update_existing else ""
    target_record = tasks.get(target_task_id) if target_task_id else None
    if update_existing and target_record is None:
        raise KnowledgeError(f"task.update_existing references unknown task {target_task_id}")

    idempotency_scope = [(target_task_id, target_record)] if target_record else list(tasks.items())
    for existing_id, record in idempotency_scope:
        if record is None:
            continue
        path, metadata, _ = record
        existing_fingerprint = normalize_space(metadata.get("fingerprint"))
        legacy_noop = (
            not update_existing
            and not task["deliverable"]
            and not task["knowledge_summary"]
            and existing_fingerprint == legacy_task_fp
        )
        if existing_fingerprint == task_fp or legacy_noop:
            return {
                "ok": True,
                "idempotent": True,
                "dry_run": dry_run,
                "task_id": existing_id,
                "task_revision": int(metadata.get("revision", 1) or 1),
                "task_note": path.relative_to(root).as_posix(),
                "created_cards": [],
                "reused_cards": unique_strings(metadata.get("card_ids")),
                "superseded_cards": [],
                "task_candidates": [],
                "card_candidates": [],
                "index": rebuild_indexes(root, config, dry_run=dry_run),
                "plan_token": generated_plan_token if dry_run else None,
            }
    current_revision = 0
    if target_record:
        current_revision = int(target_record[1].get("revision", 1) or 1)
        if task["expected_revision"] != current_revision:
            raise KnowledgeError(
                f"task {target_task_id} revision changed: expected {task['expected_revision']}, current {current_revision}; "
                "read the current task-note and run learn --dry-run again"
            )
    previous_metadata = target_record[1] if target_record else {}
    previous_source = previous_metadata.get("source") if isinstance(previous_metadata.get("source"), dict) else {}
    merged_source = {**previous_source, **task["source"]}
    rendered_task = {**task, "source": merged_source}
    fingerprint_to_id: dict[str, str] = {}
    for identifier, (_, metadata, _) in cards.items():
        fingerprint = normalize_space(metadata.get("fingerprint"))
        status = normalize_space(metadata.get("status") or "current")
        if fingerprint and status != "superseded":
            fingerprint_to_id[fingerprint] = identifier

    for item in items:
        for superseded_id in item["supersedes"]:
            if superseded_id not in cards:
                raise KnowledgeError(f"item '{item['title']}' supersedes unknown card {superseded_id}")
            if normalize_space(cards[superseded_id][1].get("status")) == "superseded":
                raise KnowledgeError(f"item '{item['title']}' supersedes already-superseded card {superseded_id}")

    timestamp_text = timestamp.isoformat(timespec="seconds")
    task_id = target_task_id or make_id("T", task_fp, timestamp)
    created_plan: list[tuple[str, Path, dict[str, Any], str, dict[str, Any]]] = []
    reused_cards: list[str] = []
    new_card_ids: list[str] = []
    supersession_plan: list[tuple[str, str]] = []

    deduplicate = bool((config.get("capture") or {}).get("deduplicate", True)) if isinstance(config.get("capture"), dict) else True
    for sequence, item in enumerate(items, start=1):
        fingerprint = item_fingerprint(item)
        if deduplicate and fingerprint in fingerprint_to_id:
            card_id = fingerprint_to_id[fingerprint]
            if card_id in cards and card_id not in reused_cards:
                reused_cards.append(card_id)
            if card_id not in new_card_ids:
                new_card_ids.append(card_id)
            continue
        card_id = make_id("K", fingerprint, timestamp, sequence)
        metadata = {
            "id": card_id,
            "type": "knowledge-card",
            "category": item["category"],
            "title": item["title"],
            "status": item["status"],
            "confidence": item["confidence"],
            "created_at": timestamp_text,
            "updated_at": timestamp_text,
            "task_id": task_id,
            "fingerprint": fingerprint,
            "pinned": item["pinned"],
            "tags": item["tags"],
            "paths": item["paths"],
            "symbols": item["symbols"],
            "supersedes": item["supersedes"],
            "superseded_by": [],
        }
        relative = card_filename(item, card_id)
        body = render_card_body(item, rendered_task, task_id)
        created_plan.append((card_id, wiki / relative, metadata, body, item))
        new_card_ids.append(card_id)
        fingerprint_to_id[fingerprint] = card_id
        for old_id in item["supersedes"]:
            supersession_plan.append((old_id, card_id))

    previous_card_ids = unique_strings(previous_metadata.get("card_ids"))
    all_card_ids = unique_strings([*previous_card_ids, *new_card_ids])
    task_revision = current_revision + 1
    task_metadata = {
        "id": task_id,
        "type": "task-note",
        "title": task["title"],
        "task_status": task["status"],
        "created_at": normalize_space(previous_metadata.get("created_at")) or timestamp_text,
        "updated_at": timestamp_text,
        "revision": task_revision,
        "fingerprint": task_fp,
        "tags": task["tags"],
        "paths": task["paths"],
        "symbols": task["symbols"],
        "card_ids": all_card_ids,
        "deliverable": task["deliverable"],
        "knowledge_summary": task["knowledge_summary"],
        "source": merged_source,
    }
    task_path = target_record[0] if target_record else wiki / task_note_filename(task, task_id, timestamp)
    task_body = render_task_body(rendered_task, task_id, all_card_ids)

    planned_new_paths = [path for _, path, _, _, _ in created_plan]
    if not target_record:
        planned_new_paths.append(task_path)
    collisions = [path.relative_to(root).as_posix() for path in planned_new_paths if path.exists()]
    if collisions:
        raise KnowledgeError("planned knowledge paths already exist: " + ", ".join(collisions))

    result = {
        "ok": True,
        "idempotent": False,
        "dry_run": dry_run,
        "task_id": task_id,
        "task_revision": task_revision,
        "updated_existing_task": update_existing,
        "task_note": task_path.relative_to(root).as_posix(),
        "created_cards": [
            {"id": card_id, "path": path.relative_to(root).as_posix(), "category": item["category"], "title": item["title"]}
            for card_id, path, _, _, item in created_plan
        ],
        "reused_cards": reused_cards,
        "superseded_cards": [{"id": old_id, "superseded_by": new_id} for old_id, new_id in supersession_plan],
        "task_candidates": [] if update_existing else task_similarity_candidates(task, tasks, root),
        "card_candidates": card_similarity_candidates(items, cards, root),
        "plan_token": generated_plan_token if dry_run else None,
    }
    if result["task_candidates"]:
        result["recommendation"] = "update-existing-task"
    if dry_run:
        result["index"] = projected_index_plan(
            root,
            config,
            cards,
            tasks,
            created_plan,
            task_path,
            task_metadata,
            task_body,
            supersession_plan,
            timestamp_text,
            replaced_task_id=target_task_id or None,
        )
        return result

    _, current_index_outputs = build_index_outputs(root, config)
    mutation_paths = set(planned_new_paths)
    mutation_paths.add(task_path)
    mutation_paths.update(cards[old_id][0] for old_id, _ in supersession_plan)
    mutation_paths.update(current_index_outputs)
    snapshot = {
        path: path.read_text(encoding="utf-8") if path.is_file() else None
        for path in mutation_paths
    }
    transaction = create_recovery_journal(root, wiki, task_id, snapshot)
    try:
        for _, path, metadata, body, _ in created_plan:
            atomic_write_text(path, render_front_matter(metadata, body))
        atomic_write_text(task_path, render_front_matter(task_metadata, task_body))
        for old_id, new_id in supersession_plan:
            old_path = cards[old_id][0]
            update_card_supersession(old_path, new_id, timestamp_text, dry_run=False)
        result["index"] = rebuild_indexes(root, config, dry_run=False)
        atomic_write_text(transaction / "COMMITTED", "committed\n")
    except Exception:
        restore_snapshot(snapshot, wiki)
        remove_recovery_journal(transaction)
        raise
    remove_recovery_journal(transaction)
    return result


def learn(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if dry_run:
        if plan_token:
            raise KnowledgeError("plan_token is only valid when applying learn")
        return _learn_locked(root, config, payload, dry_run=True)
    wiki = wiki_root(root, config)
    lock = acquire_lock(root, wiki)
    try:
        return _learn_locked(root, config, payload, dry_run=False, plan_token=plan_token)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def lexical_tokens(value: str) -> set[str]:
    text = value.lower()
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9][a-z0-9_.:/-]*", text):
        for part in re.split(r"[_.:/-]+", token):
            if len(part) >= 2 and part not in STOPWORDS:
                tokens.add(part)
        if len(token) >= 2 and token not in STOPWORDS:
            tokens.add(token)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if run not in STOPWORDS and 1 < len(run) <= 16:
            tokens.add(run)
        if len(run) >= 2:
            for width in (2, 3):
                if len(run) >= width:
                    for index in range(len(run) - width + 1):
                        token = run[index : index + width]
                        if token not in STOPWORDS:
                            tokens.add(token)
    return tokens


def inferred_categories(text: str, include_default_acceptance: bool = True) -> set[str]:
    lowered = text.lower()
    categories: set[str] = set()
    for category, definition in CATEGORY_DEFS.items():
        for alias in definition["aliases"]:
            if str(alias).lower() in lowered:
                categories.add(category)
                break
    # Every implementation should have an observable acceptance contract.
    if include_default_acceptance and normalize_space(text):
        categories.add("acceptance")
    return categories


def infer_legacy_category(path: Path, content: str) -> str | None:
    value = f"{path.as_posix()} {content[:2000]}".lower()
    direct = {
        "decisions": ("decision", "decisions", "adr", "决策"),
        "requirements": ("requirement", "requirements", "需求"),
        "interfaces": ("contract", "contracts", "api", "interface", "接口"),
        "architecture": ("architecture", "domain", "vision", "架构"),
        "acceptance": ("acceptance", "验收"),
    }
    for category, aliases in direct.items():
        if any(alias in value for alias in aliases):
            return category
    hinted = inferred_categories(value)
    return sorted(hinted)[0] if hinted else None


def safe_read_text(path: Path, maximum_bytes: int = 512 * 1024) -> str:
    try:
        if path.stat().st_size > maximum_bytes:
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def collect_search_documents(root: Path, config: dict[str, Any], include_superseded: bool) -> tuple[list[SearchDocument], list[str]]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    categories = configured_categories(config)
    documents: list[SearchDocument] = []
    warnings: list[str] = []

    project_path = wiki / "PROJECT.md"
    if project_path.is_file():
        content = extract_canonical(safe_read_text(project_path))
        if content:
            documents.append(
                SearchDocument(
                    source_type="project-overview",
                    source_path=project_path.relative_to(root).as_posix(),
                    title="Project Overview",
                    content=content,
                    pinned=True,
                )
            )

    for category in categories:
        readme = wiki / category / "README.md"
        if readme.is_file():
            content = extract_canonical(safe_read_text(readme))
            if content:
                documents.append(
                    SearchDocument(
                        source_type="canonical-page",
                        source_path=readme.relative_to(root).as_posix(),
                        title=f"{CATEGORY_DEFS[category]['label']}人工摘要",
                        content=content,
                        category=category,
                        pinned=True,
                    )
                )

    for path in card_paths(wiki, categories):
        try:
            metadata, body, _ = read_markdown(path)
        except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
            warnings.append(f"cannot read card {path.relative_to(root).as_posix()}: {exc}")
            continue
        status = normalize_space(metadata.get("status") or "current")
        if status == "superseded" and not include_superseded:
            continue
        documents.append(
            SearchDocument(
                source_type="knowledge-card",
                source_path=path.relative_to(root).as_posix(),
                title=normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
                content=extract_section(body, ("结论",)) or body,
                category=normalize_space(metadata.get("category")) or None,
                identifier=normalize_space(metadata.get("id")) or None,
                status=status,
                confidence=normalize_space(metadata.get("confidence") or "accepted"),
                tags=tuple(unique_strings(metadata.get("tags"))),
                paths=tuple(unique_strings(metadata.get("paths"))),
                symbols=tuple(unique_strings(metadata.get("symbols"))),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
                pinned=bool(metadata.get("pinned", False)),
            )
        )

    for path in task_note_paths(wiki):
        try:
            metadata, body, _ = read_markdown(path)
        except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
            warnings.append(f"cannot read task note {path.relative_to(root).as_posix()}: {exc}")
            continue
        content = " ".join(
            filter(
                None,
                (
                    extract_section(body, ("请求",)),
                    extract_section(body, ("处理摘要",)),
                    extract_section(body, ("最终结果",)),
                ),
            )
        )
        documents.append(
            SearchDocument(
                source_type="task-note",
                source_path=path.relative_to(root).as_posix(),
                title=normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
                content=content or body,
                identifier=normalize_space(metadata.get("id")) or None,
                status=normalize_space(metadata.get("task_status") or "completed"),
                tags=tuple(unique_strings(metadata.get("tags"))),
                paths=tuple(unique_strings(metadata.get("paths"))),
                symbols=tuple(unique_strings(metadata.get("symbols"))),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
            )
        )

    wiki_config = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    legacy_roots = unique_strings(wiki_config.get("legacy_read_roots"))
    max_files = safe_int(wiki_config.get("max_scan_files"), 2000, minimum=1, maximum=20_000)
    scanned = 0
    for relative in legacy_roots:
        try:
            legacy_root = resolve_inside(root, relative)
        except KnowledgeError as exc:
            warnings.append(str(exc))
            continue
        if not legacy_root.is_dir():
            continue
        for path in sorted(legacy_root.rglob("*.md")):
            scanned += 1
            if scanned > max_files:
                warnings.append(f"legacy scan stopped at configured max_scan_files={max_files}")
                break
            content = safe_read_text(path)
            if not content:
                continue
            documents.append(
                SearchDocument(
                    source_type="legacy-page",
                    source_path=path.relative_to(root).as_posix(),
                    title=extract_heading(content, path.stem),
                    content=content,
                    category=infer_legacy_category(path, content),
                    status="legacy",
                )
            )
        if scanned > max_files:
            break
    return documents, warnings


def scope_path_match(query_path: str, scoped_path: str) -> bool:
    left = query_path.strip("./")
    right = scoped_path.strip("./")
    return bool(left and right and (left == right or left.startswith(right + "/") or right.startswith(left + "/")))


def score_document_details(
    document: SearchDocument,
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
) -> tuple[float, bool]:
    query_text = " ".join((task, *paths, *symbols))
    query_tokens = lexical_tokens(query_text)
    title_tokens = lexical_tokens(document.title)
    content_tokens = lexical_tokens(document.content)
    tag_tokens = lexical_tokens(" ".join(document.tags))
    symbol_tokens = lexical_tokens(" ".join(document.symbols))
    scoped_path_tokens = lexical_tokens(" ".join(document.paths))
    source_path_tokens = lexical_tokens(document.source_path)
    path_tokens = scoped_path_tokens | source_path_tokens
    title_overlap = query_tokens & title_tokens
    content_overlap = query_tokens & content_tokens
    tag_overlap = query_tokens & tag_tokens
    symbol_overlap = query_tokens & symbol_tokens
    scoped_path_overlap = query_tokens & scoped_path_tokens
    meaningful_path_overlap = scoped_path_overlap - PATH_SIGNAL_STOPWORDS
    score = 0.0
    score += 7.0 * len(title_overlap)
    score += 5.0 * len(tag_overlap)
    score += 9.0 * len(symbol_overlap)
    score += 6.0 * len(query_tokens & path_tokens)
    score += 1.25 * len(content_overlap)
    exact_path_match = False
    for query_path in paths:
        if any(scope_path_match(query_path, scoped) for scoped in document.paths):
            score += 24.0
            exact_path_match = True
        elif scope_path_match(query_path, document.source_path):
            score += 10.0
            exact_path_match = True
    lowered_symbols = {symbol.lower() for symbol in symbols}
    exact_symbol_match = bool(lowered_symbols & {symbol.lower() for symbol in document.symbols})
    if exact_symbol_match:
        score += 24.0
    # The implicit acceptance category is useful for gap analysis, but must not
    # make every acceptance card relevant to every task.
    hints = inferred_categories(query_text, include_default_acceptance=False)
    if document.category in hints:
        score += 8.0
    if document.pinned:
        score += 2.5
    if document.source_type == "canonical-page":
        score += 1.5
    if document.source_type == "legacy-page":
        score -= 0.5
    if document.source_type == "task-note":
        score -= 1.0
    if document.status in {"deprecated", "superseded"}:
        score -= 5.0
    qualifies = bool(
        document.pinned
        or exact_path_match
        or exact_symbol_match
        or title_overlap
        or tag_overlap
        or symbol_overlap
        or meaningful_path_overlap
        or len(content_overlap) >= 2
    )
    return score, qualifies


def score_document(document: SearchDocument, task: str, paths: Sequence[str], symbols: Sequence[str]) -> float:
    return score_document_details(document, task, paths, symbols)[0]


def selected_brief_payload(
    root: Path,
    config: dict[str, Any],
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    limit_override: int | None,
    include_superseded: bool,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    documents, warnings = collect_search_documents(root, config, include_superseded)
    brief_config = config.get("brief") if isinstance(config.get("brief"), dict) else {}
    max_items = limit_override or safe_int(brief_config.get("max_items"), 18, minimum=1, maximum=100)
    per_category = safe_int(brief_config.get("max_items_per_category"), 3, minimum=1, maximum=20)
    related_limit = safe_int(brief_config.get("max_related_tasks"), 3, minimum=1, maximum=20)
    excerpt_limit = safe_int(brief_config.get("max_excerpt_chars"), 700, minimum=120, maximum=5000)
    recent_decisions = safe_int(brief_config.get("include_recent_decisions"), 2, minimum=1, maximum=10)

    overview = [document for document in documents if document.source_type == "project-overview"]
    primary_docs = [
        document
        for document in documents
        if document.source_type not in {"task-note", "project-overview", "legacy-page"}
    ]
    legacy_docs = [document for document in documents if document.source_type == "legacy-page"]
    task_docs = [document for document in documents if document.source_type == "task-note"]
    scored = []
    primary_matches: dict[str, tuple[float, bool]] = {}
    for document in primary_docs:
        score, qualifies = score_document_details(document, task, paths, symbols)
        primary_matches[document.source_path] = (score, qualifies)
        if qualifies:
            scored.append((score, document))
    scored.sort(key=lambda pair: (pair[0], pair[1].pinned, pair[1].updated_at or pair[1].created_at), reverse=True)

    selected: list[tuple[float, SearchDocument]] = []
    per_category_counts: dict[str, int] = {}
    selected_paths: set[str] = set()
    for score, document in scored:
        category = document.category or "uncategorized"
        if per_category_counts.get(category, 0) >= per_category:
            continue
        selected.append((score, document))
        selected_paths.add(document.source_path)
        per_category_counts[category] = per_category_counts.get(category, 0) + 1
        if len(selected) >= max_items:
            break

    # Recent decisions remain useful context, but only after a real relevance
    # signal (or explicit pinning) qualifies them.
    decision_docs = sorted(
        [
            document
            for document in primary_docs
            if document.source_type == "knowledge-card"
            if document.category == "decisions"
            and document.status in {"current", "proposed"}
            and document.source_path not in selected_paths
            and primary_matches[document.source_path][1]
        ],
        key=lambda document: document.updated_at or document.created_at,
        reverse=True,
    )
    for document in decision_docs[:recent_decisions]:
        if len(selected) >= max_items:
            break
        selected.append((score_document(document, task, paths, symbols), document))
        selected_paths.add(document.source_path)

    related_candidates: list[tuple[float, SearchDocument]] = []
    for document in task_docs:
        score, qualifies = score_document_details(document, task, paths, symbols)
        if qualifies:
            related_candidates.append((score, document))
    related = sorted(
        related_candidates,
        key=lambda pair: (pair[0], pair[1].updated_at or pair[1].created_at),
        reverse=True,
    )[:related_limit]

    def is_current_knowledge(document: SearchDocument) -> bool:
        return document.source_type == "canonical-page" or (
            document.source_type == "knowledge-card" and document.status == "current"
        )

    legacy_selected: list[tuple[float, SearchDocument]] = []
    if not any(is_current_knowledge(document) for _, document in selected):
        legacy_scored = []
        for document in legacy_docs:
            score, qualifies = score_document_details(document, task, paths, symbols)
            if qualifies:
                legacy_scored.append((score, document))
        legacy_scored.sort(
            key=lambda pair: (pair[0], pair[1].updated_at or pair[1].created_at),
            reverse=True,
        )
        legacy_category_counts: dict[str, int] = {}
        for score, document in legacy_scored:
            category = document.category or "uncategorized"
            if legacy_category_counts.get(category, 0) >= per_category:
                continue
            legacy_selected.append((score, document))
            legacy_category_counts[category] = legacy_category_counts.get(category, 0) + 1
            if len(legacy_selected) >= 3:
                break

    coverage: dict[str, dict[str, int]] = {}
    current_docs = [document for document in primary_docs if is_current_knowledge(document)]
    for category in configured_categories(config):
        available = sum(document.category == category for document in current_docs)
        matched = sum(document.category == category and is_current_knowledge(document) for _, document in selected)
        coverage[category] = {"available": available, "matched": matched}

    relevant = inferred_categories(" ".join((task, *paths, *symbols)))
    gaps = [category for category in configured_categories(config) if category in relevant and coverage[category]["matched"] == 0]

    current_cards = [
        document
        for document in primary_docs
        if document.source_type == "knowledge-card" and document.status == "current"
    ]
    title_groups: dict[tuple[str | None, str], list[SearchDocument]] = {}
    for document in current_cards:
        key = (document.category, normalize_space(document.title).lower())
        title_groups.setdefault(key, []).append(document)
    conflicts = [
        {
            "category": category,
            "title": title,
            "sources": [document.source_path for document in group],
        }
        for (category, title), group in title_groups.items()
        if title and len(group) > 1 and len({normalize_space(document.content) for document in group}) > 1
    ]

    def serialize(document: SearchDocument, score: float | None = None) -> dict[str, Any]:
        value = {
            "id": document.identifier,
            "type": document.source_type,
            "category": document.category,
            "title": document.title,
            "status": document.status,
            "confidence": document.confidence,
            "source": document.source_path,
            "excerpt": clip(document.content, excerpt_limit),
            "paths": list(document.paths),
            "symbols": list(document.symbols),
            "tags": list(document.tags),
        }
        if score is not None:
            value["score"] = round(score, 3)
        return value

    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "task": task,
        "paths": list(paths),
        "symbols": list(symbols),
        "generated_at": now_iso(),
        "project_overview": [serialize(document) for document in overview],
        "knowledge": [serialize(document, score) for score, document in selected],
        "legacy_clues": [serialize(document, score) for score, document in legacy_selected],
        "related_tasks": [serialize(document, score) for score, document in related],
        "coverage": coverage,
        "gaps": gaps,
        "conflicts": conflicts,
        "warnings": warnings,
        "read_only": True,
    }


def render_brief_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# CodeStable 项目知识简报",
        "",
        f"**任务**：{payload['task']}",
    ]
    if payload["paths"]:
        lines.append(f"**已知路径**：{', '.join(payload['paths'])}")
    if payload["symbols"]:
        lines.append(f"**已知符号**：{', '.join(payload['symbols'])}")
    lines.extend(
        (
            "",
            "> 这些内容用于知识导航。accepted 目标与 verified 行为承担不同作用；冲突必须沿 scope、证据和来源查明，不能机械选择 Wiki 或代码一方。",
            "",
        )
    )

    if payload["project_overview"]:
        lines.extend(("## 项目总览", ""))
        for item in payload["project_overview"]:
            lines.append(item["excerpt"])
            lines.append(f"\n来源：`{item['source']}`\n")

    lines.extend(("## 相关知识", ""))
    if not payload["knowledge"]:
        lines.append("未检索到匹配的 current Wiki 知识。")
        if not payload["legacy_clues"]:
            lines.append("Agent 应从用户要求、公共契约、测试和源码建立事实，并在任务结束后沉淀可复用结论。")
        lines.append("")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in payload["knowledge"]:
        grouped.setdefault(item.get("category") or "uncategorized", []).append(item)
    for category in configured_categories({"wiki": {"categories": list(CATEGORY_DEFS)}}):
        if category not in grouped:
            continue
        lines.extend((f"### {CATEGORY_DEFS[category]['label']}", ""))
        for item in grouped[category]:
            identifier = f" · `{item['id']}`" if item.get("id") else ""
            lines.append(f"#### {item['title']}{identifier}")
            lines.append("")
            lines.append(item["excerpt"])
            lines.append("")
            metadata = [item["type"], item["status"], item["confidence"], f"source `{item['source']}`"]
            if item["paths"]:
                metadata.append("paths " + ", ".join(f"`{path}`" for path in item["paths"]))
            if item["symbols"]:
                metadata.append("symbols " + ", ".join(f"`{symbol}`" for symbol in item["symbols"]))
            lines.append("- " + " · ".join(metadata))
            lines.append("")
    if "uncategorized" in grouped:
        lines.extend(("### 其他来源", ""))
        for item in grouped["uncategorized"]:
            lines.append(f"- **{item['title']}**：{item['excerpt']}（`{item['source']}`）")
        lines.append("")

    if payload["legacy_clues"]:
        lines.extend(("## Legacy 线索（需核验）", ""))
        lines.append("current Wiki 没有合格命中；以下旧页只用于定位证据，不代表当前事实，也不计入知识覆盖。")
        lines.append("")
        for item in payload["legacy_clues"]:
            category = CATEGORY_DEFS.get(item.get("category") or "", {}).get("label", "其他")
            lines.append(f"### {item['title']}")
            lines.append("")
            lines.append(item["excerpt"])
            lines.append("")
            lines.append(
                f"- {category} · legacy clue · source `{item['source']}`"
            )
            lines.append("")

    lines.extend(("## 相关历史任务", ""))
    if not payload["related_tasks"]:
        lines.append("- 无匹配记录。")
    else:
        for item in payload["related_tasks"]:
            identifier = f" `{item['id']}`" if item.get("id") else ""
            lines.append(f"- **{item['title']}**{identifier} · {item['status']}  \n  {item['excerpt']}  \n  来源：`{item['source']}`")
    lines.append("")

    lines.extend(("## 覆盖与空白", ""))
    lines.append("| 分类 | 已有当前知识 | 本次匹配 |")
    lines.append("|---|---:|---:|")
    for category, counts in payload["coverage"].items():
        lines.append(f"| {CATEGORY_DEFS[category]['label']} | {counts['available']} | {counts['matched']} |")
    lines.append("")
    if payload["gaps"]:
        lines.append("本任务可能相关但尚无匹配知识：" + "、".join(CATEGORY_DEFS[item]["label"] for item in payload["gaps"]) + "。")
    else:
        lines.append("未发现由任务文本直接触发的知识空白。")
    if payload["conflicts"]:
        lines.append("")
        lines.append("检测到可能冲突的当前卡片：")
        for conflict in payload["conflicts"]:
            label = CATEGORY_DEFS.get(conflict["category"] or "", {}).get("label", conflict["category"] or "其他")
            lines.append(f"- {label} / {conflict['title']}：{', '.join(f'`{source}`' for source in conflict['sources'])}")
    if payload["warnings"]:
        lines.append("")
        lines.append("读取警告：")
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    lines.extend(("", f"_只读生成于 {payload['generated_at']}_", ""))
    return "\n".join(lines)


def run_git(root: Path, arguments: Sequence[str], allow_difference: bool = False) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        text=True,
        capture_output=True,
        check=False,
    )
    allowed = {0, 1} if allow_difference else {0}
    if process.returncode not in allowed:
        detail = normalize_space(process.stderr) or normalize_space(process.stdout) or "git command failed"
        raise KnowledgeError(detail)
    return process


def git_diff_arguments(cached: bool, base: str | None) -> list[str]:
    if cached and base:
        raise KnowledgeError("drift accepts either --cached or --base, not both")
    if cached:
        return ["diff", "--cached"]
    if base:
        return ["diff", f"{base}...HEAD"]
    return ["diff", "HEAD"]


def git_changes(root: Path, cached: bool, base: str | None) -> tuple[list[GitChange], str, bool]:
    arguments = git_diff_arguments(cached, base)
    names = run_git(root, [*arguments, "--name-status", "-z", "-M", "--"]).stdout
    tokens = names.split("\0")
    if tokens and not tokens[-1]:
        tokens.pop()
    changes: list[GitChange] = []
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise KnowledgeError("git returned an incomplete rename/copy record")
            old_path, new_path = tokens[index], tokens[index + 1]
            index += 2
        else:
            if index >= len(tokens):
                raise KnowledgeError("git returned an incomplete change record")
            old_path = new_path = tokens[index]
            index += 1
        changes.append(GitChange(status=status, old_path=old_path, new_path=new_path))
    if not cached and not base:
        untracked = run_git(root, ["ls-files", "--others", "--exclude-standard", "-z"]).stdout
        for path in sorted(value for value in untracked.split("\0") if value):
            changes.append(GitChange(status="?", old_path=path, new_path=path))
        deleted_changes = [change for change in changes if change.status == "D"]
        untracked_changes = [change for change in changes if change.status == "?"]
        inferred: list[tuple[GitChange, GitChange]] = []
        for deleted_change in deleted_changes:
            try:
                old_hash = run_git(root, ["rev-parse", f"HEAD:{deleted_change.old_path}"]).stdout.strip()
            except KnowledgeError:
                continue
            for untracked_change in untracked_changes:
                try:
                    new_hash = run_git(root, ["hash-object", untracked_change.new_path]).stdout.strip()
                except KnowledgeError:
                    continue
                if old_hash and old_hash == new_hash:
                    inferred.append((deleted_change, untracked_change))
                    untracked_changes.remove(untracked_change)
                    break
        for deleted_change, untracked_change in inferred:
            changes.remove(deleted_change)
            changes.remove(untracked_change)
            changes.append(GitChange(status="R100", old_path=deleted_change.old_path, new_path=untracked_change.new_path))
    patch = run_git(root, [*arguments, "--unified=0", "--"]).stdout
    whitespace = run_git(
        root,
        [*arguments, "-w", "--ignore-blank-lines", "--quiet", "--"],
        allow_difference=True,
    )
    whitespace_only = bool(changes) and whitespace.returncode == 0 and all(
        not change.status.startswith(("R", "C", "D", "?")) for change in changes
    )
    return changes, patch, whitespace_only


def unstaged_wiki_paths(root: Path) -> list[str]:
    changed = run_git(root, ["diff", "--name-only", "-z", "--", ".codestable/wiki"]).stdout
    untracked = run_git(
        root,
        ["ls-files", "--others", "--exclude-standard", "-z", "--", ".codestable/wiki"],
    ).stdout
    return sorted(set(value for value in [*changed.split("\0"), *untracked.split("\0")] if value))


def reference_path_policy(root: Path, value: str) -> tuple[str, Path | None]:
    path = normalize_space(value).replace("\\", "/")
    lowered = path.casefold()
    if re.match(r"^[a-z][a-z0-9+.-]*://", lowered) or lowered.startswith("external:"):
        return "external", None
    if lowered.startswith("generated:"):
        return "generated", None
    if lowered.startswith("legacy:") or lowered in {
        ".codestable/model",
        ".codestable/knowledge",
        ".codestable/backups",
    } or lowered.startswith((".codestable/model/", ".codestable/knowledge/", ".codestable/backups/")):
        return "legacy", None
    if lowered in {".codestable/wiki/index.md", ".codestable/wiki/index.jsonl"} or (
        lowered.startswith(".codestable/wiki/") and lowered.endswith("/index.md")
    ):
        return "generated", None
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            return "external", None
        return "repository", candidate.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return "external", None
    return "repository", resolved


def candidate_source_files(root: Path, paths: Sequence[Path], limit: int) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = [path] if path.is_file() else sorted(path.rglob("*")) if path.is_dir() else []
        for candidate in candidates:
            if len(files) >= limit:
                return files
            if not candidate.is_file() or candidate in seen or ".git" in candidate.parts:
                continue
            seen.add(candidate)
            files.append(candidate)
    if files:
        return files
    try:
        tracked = run_git(root, ["ls-files", "-z"]).stdout
    except KnowledgeError:
        return []
    for value in tracked.split("\0"):
        if not value or value.startswith(".codestable/"):
            continue
        candidate = root / value
        if candidate.is_file():
            files.append(candidate)
            if len(files) >= limit:
                break
    return files


def symbol_present(symbol: str, files: Sequence[Path]) -> tuple[bool, bool]:
    texts: list[str] = []
    checked = False
    for path in files:
        try:
            if path.stat().st_size > 2_000_000:
                continue
            texts.append(path.read_text(encoding="utf-8", errors="ignore"))
            checked = True
        except OSError:
            continue
    content = "\n".join(texts)
    if not checked:
        return False, False
    if symbol in content:
        return True, True
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u3400-\u9fff]+", symbol)
    return bool(parts) and all(re.search(rf"(?<!\w){re.escape(part)}(?!\w)", content) for part in parts), True


def current_reference_drift(
    root: Path,
    config: dict[str, Any],
    changes: Sequence[GitChange] = (),
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    rename_map = {change.old_path: change.new_path for change in changes if change.status.startswith("R")}
    deleted = {change.old_path for change in changes if change.status == "D"}
    findings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    scan_limit = safe_int((config.get("wiki") or {}).get("max_scan_files"), 2000, minimum=1, maximum=20_000)
    for card_id, (_, metadata, _) in sorted(cards.items()):
        if normalize_space(metadata.get("status")) != "current":
            continue
        common = {
            "card_id": card_id,
            "category": normalize_space(metadata.get("category")),
            "title": normalize_space(metadata.get("title")),
        }
        repository_paths: list[Path] = []
        for raw_path in unique_strings(metadata.get("paths")):
            policy, resolved = reference_path_policy(root, raw_path)
            if policy != "repository":
                skipped.append(
                    {
                        **common,
                        "issue_type": "path-policy-skipped",
                        "value": raw_path,
                        "policy": policy,
                        "suggested_action": "keep the explicit path policy or replace it with a repository-relative path if source checking is required",
                    }
                )
                continue
            assert resolved is not None
            relative = resolved.relative_to(root).as_posix()
            if relative in rename_map:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-renamed",
                        "value": relative,
                        "renamed_to": rename_map[relative],
                        "suggested_action": "review the card against the renamed implementation, then update its scope or supersede it",
                    }
                )
            elif relative in deleted:
                findings.append(
                    {
                        **common,
                        "issue_type": "current-path-deleted",
                        "value": relative,
                        "suggested_action": "review whether the conclusion still applies elsewhere; update or supersede the current card",
                    }
                )
            elif not resolved.exists():
                findings.append(
                    {
                        **common,
                        "issue_type": "missing-path",
                        "value": relative,
                        "suggested_action": "locate the replacement implementation and update scope, or supersede the card after semantic review",
                    }
                )
            else:
                repository_paths.append(resolved)
        symbols = unique_strings(metadata.get("symbols"))
        if symbols:
            files = candidate_source_files(root, repository_paths, scan_limit)
            for symbol in symbols:
                present, checked = symbol_present(symbol, files)
                if not checked:
                    skipped.append(
                        {
                            **common,
                            "issue_type": "symbol-check-skipped",
                            "value": symbol,
                            "policy": "no-readable-source",
                            "suggested_action": "provide a repository path for deterministic symbol checking",
                        }
                    )
                elif not present:
                    findings.append(
                        {
                            **common,
                            "issue_type": "missing-symbol",
                            "value": symbol,
                            "suggested_action": "review rename/removal and update or supersede the card; text scanning is only a drift candidate",
                        }
                    )
    title_groups: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for card_id, (_, metadata, _) in cards.items():
        if normalize_space(metadata.get("status")) != "current":
            continue
        key = (normalize_space(metadata.get("category")), normalize_space(metadata.get("title")).casefold())
        title_groups.setdefault(key, []).append((card_id, metadata))
    for (category, _), group in sorted(title_groups.items()):
        if len(group) < 2:
            continue
        scoped = [set(unique_strings(metadata.get("paths"))) for _, metadata in group]
        overlaps = any(not left or not right or bool(left & right) for index, left in enumerate(scoped) for right in scoped[index + 1 :])
        if not overlaps:
            continue
        first_id, first_metadata = group[0]
        findings.append(
            {
                "card_id": first_id,
                "related_card_ids": [card_id for card_id, _ in group[1:]],
                "category": category,
                "title": normalize_space(first_metadata.get("title")),
                "issue_type": "overlapping-current-cards",
                "value": ", ".join(card_id for card_id, _ in group),
                "suggested_action": "reuse or merge an equivalent current card, or explicitly supersede the replaced conclusion",
            }
        )
    return {"findings": findings, "skipped": skipped, "checked_current_cards": sum(1 for _, metadata, _ in cards.values() if normalize_space(metadata.get("status")) == "current")}


def is_generated_or_knowledge_path(path: str) -> bool:
    lowered = path.casefold()
    return (
        lowered.startswith(".codestable/wiki/")
        or lowered in {"validation/release-report.json", "validation/release-report.md"}
        or lowered.endswith((".generated.md", ".generated.json", ".min.js", ".min.css"))
    )


def is_docs_only_path(path: str) -> bool:
    return Path(path).suffix.casefold() in {".md", ".rst", ".txt", ".adoc"}


def path_is_covered(scope: str, changed: str) -> bool:
    normalized = scope.rstrip("/")
    return changed == normalized or changed.startswith(normalized + "/")


def task_note_drift(root: Path, changes: Sequence[GitChange], patch: str, whitespace_only: bool) -> dict[str, Any]:
    changed_notes = [
        change.new_path
        for change in changes
        if change.status != "D" and change.new_path.startswith(".codestable/wiki/task-notes/") and change.new_path.endswith(".md")
    ]
    semantic_changes = [
        change
        for change in changes
        if not is_generated_or_knowledge_path(change.new_path) and not is_docs_only_path(change.new_path)
    ]
    if whitespace_only:
        semantic_changes = []
    primary_paths = [change.new_path for change in semantic_changes if not re.search(r"(^|/)(tests?|fixtures?)(/|$)", change.new_path)]
    if not primary_paths:
        primary_paths = [change.new_path for change in semantic_changes]
    primary_paths = sorted(set(primary_paths))
    findings: list[dict[str, Any]] = []
    if not semantic_changes:
        return {
            "semantic_change": False,
            "classification": "mechanical-or-docs-only",
            "primary_paths": [],
            "task_notes": changed_notes,
            "findings": findings,
        }
    if not changed_notes:
        findings.append(
            {
                "issue_type": "missing-task-note",
                "value": ", ".join(primary_paths),
                "suggested_action": "complete CodeStable learn dry-run/apply before commit; a durable card is not required when no reusable fact exists",
            }
        )
        return {
            "semantic_change": True,
            "classification": "semantic-candidate",
            "primary_paths": primary_paths,
            "task_notes": [],
            "findings": findings,
        }
    candidates: list[tuple[int, str, dict[str, Any], str]] = []
    for relative in changed_notes:
        path = root / relative
        if not path.is_file():
            continue
        metadata, body, _ = read_markdown(path)
        scopes = unique_strings(metadata.get("paths"))
        coverage = sum(any(path_is_covered(scope, changed) for scope in scopes) for changed in primary_paths)
        if not coverage and any(symbol and symbol in patch for symbol in unique_strings(metadata.get("symbols"))):
            coverage = 1
        candidates.append((coverage, relative, metadata, body))
    if not candidates:
        findings.append(
            {
                "issue_type": "missing-readable-task-note",
                "value": ", ".join(changed_notes),
                "suggested_action": "restore or regenerate the changed task-note before commit",
            }
        )
    else:
        coverage, relative, metadata, body = max(candidates, key=lambda item: (item[0], item[1]))
        common = {"task_id": normalize_space(metadata.get("id")), "task_note": relative, "title": normalize_space(metadata.get("title"))}
        scopes = unique_strings(metadata.get("paths"))
        uncovered = [changed for changed in primary_paths if not any(path_is_covered(scope, changed) for scope in scopes)]
        if uncovered and not any(symbol and symbol in patch for symbol in unique_strings(metadata.get("symbols"))):
            findings.append(
                {
                    **common,
                    "issue_type": "task-scope-mismatch",
                    "value": ", ".join(uncovered),
                    "suggested_action": "update task paths or symbols to cover the main semantic change scope",
                }
            )
        if normalize_space(metadata.get("task_status")) != "completed":
            findings.append(
                {
                    **common,
                    "issue_type": "task-not-completed",
                    "value": normalize_space(metadata.get("task_status")),
                    "suggested_action": "record the final outcome and update the logical task to completed after acceptance",
                }
            )
        result = extract_section(body, ("最终结果",))
        if not result or re.search(r"(?:TODO|TBD|待完成|计划|将要|尚未完成)", result, re.IGNORECASE):
            findings.append(
                {
                    **common,
                    "issue_type": "task-final-result-missing",
                    "value": result or "missing",
                    "suggested_action": "replace plans with the final observable result",
                }
            )
        verification = extract_section(body, ("验证",))
        if not verification or verification in {"无", "未记录"}:
            findings.append(
                {
                    **common,
                    "issue_type": "task-verification-missing",
                    "value": verification or "missing",
                    "suggested_action": "record the verification actually run; do not claim evidence that was not obtained",
                }
            )
        knowledge_summary = normalize_space(metadata.get("knowledge_summary")) or extract_section(body, ("知识处置",))
        if not knowledge_summary or knowledge_summary.startswith("未说明"):
            findings.append(
                {
                    **common,
                    "issue_type": "task-knowledge-disposition-missing",
                    "value": "missing",
                    "suggested_action": "state which cards were created, reused or superseded, or why no durable card was needed",
                }
            )
    return {
        "semantic_change": True,
        "classification": "semantic-candidate",
        "primary_paths": primary_paths,
        "task_notes": changed_notes,
        "findings": findings,
    }


def drift_payload(
    root: Path,
    config: dict[str, Any],
    cached: bool = False,
    base: str | None = None,
    references_only: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    changes: list[GitChange] = []
    patch = ""
    whitespace_only = False
    if not references_only:
        changes, patch, whitespace_only = git_changes(root, cached, base)
    references = current_reference_drift(root, config, changes)
    task_check = (
        {"semantic_change": False, "classification": "references-only", "primary_paths": [], "task_notes": [], "findings": []}
        if references_only
        else task_note_drift(root, changes, patch, whitespace_only)
    )
    findings = [*references["findings"], *task_check["findings"]]
    if cached:
        unstaged_wiki = unstaged_wiki_paths(root)
        if unstaged_wiki:
            findings.append(
                {
                    "issue_type": "unstaged-wiki-changes",
                    "value": ", ".join(unstaged_wiki),
                    "suggested_action": "stage the complete CodeStable writeback before relying on staged drift",
                }
            )
    mode = "references-only" if references_only else "cached" if cached else f"base:{base}" if base else "working-tree"
    return {
        "ok": not findings,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "mode": mode,
        "exit_code": 0 if not findings else 1,
        "summary": {
            "findings": len(findings),
            "skipped_references": len(references["skipped"]),
            "current_cards_checked": references["checked_current_cards"],
            "git_changes": len(changes),
            "semantic_change": task_check["semantic_change"],
        },
        "findings": findings,
        "skipped_references": references["skipped"],
        "git": {
            "classification": task_check["classification"],
            "primary_paths": task_check["primary_paths"],
            "task_notes": task_check["task_notes"],
            "changes": [change.__dict__ for change in changes],
        },
        "limits": [
            "drift reports deterministic candidates; it does not decide whether a business conclusion is true",
            "symbol checks are conservative text scans and do not replace implementation/test review",
        ],
    }


def render_drift_text(payload: dict[str, Any]) -> str:
    lines = [
        f"CodeStable drift · {payload['mode']}",
        f"result: {'PASS' if payload['ok'] else 'ACTION REQUIRED'} · findings={payload['summary']['findings']} · git_changes={payload['summary']['git_changes']}",
    ]
    if payload["findings"]:
        lines.append("")
        for finding in payload["findings"]:
            owner = finding.get("card_id") or finding.get("task_id") or "git"
            if finding.get("card_id"):
                owner = f"{owner} {finding.get('category') or 'uncategorized'} / {finding.get('title') or 'untitled'}"
            elif finding.get("task_id") and finding.get("title"):
                owner = f"{owner} / {finding['title']}"
            value = finding.get("value") or ""
            lines.append(f"- [{finding['issue_type']}] {owner}: {value}")
            lines.append(f"  action: {finding['suggested_action']}")
    if payload["skipped_references"]:
        lines.extend(("", f"skipped by explicit path policy: {len(payload['skipped_references'])}"))
    lines.extend(("", "drift is read-only and reports candidates; semantic truth still requires requirement, code and test review.", ""))
    return "\n".join(lines)


def doctor(root: Path, config: dict[str, Any], check_current_references: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    categories = configured_categories(config)
    if not wiki.is_dir():
        errors.append({"code": "wiki.missing", "detail": f"missing wiki directory: {wiki}"})
        return {
            "ok": False,
            "scope": "structure-only",
            "current_knowledge_validated": False,
            "current_references_checked": False,
            "next_check": "run drift to compare current references and Git changes",
            "errors": errors,
            "warnings": warnings,
            "stats": {},
        }
    for required in ("README.md", "INDEX.md", "PROJECT.md", "learning.schema.json", "index.jsonl"):
        if not (wiki / required).is_file():
            errors.append({"code": "wiki.file.missing", "detail": f"missing {wiki / required}"})
    for category in categories:
        directory = wiki / category
        if not directory.is_dir():
            errors.append({"code": "wiki.category.missing", "detail": f"missing category directory {directory}"})
            continue
        for required in ("README.md", "INDEX.md"):
            if not (directory / required).is_file():
                errors.append({"code": "wiki.category.file.missing", "detail": f"missing {directory / required}"})

    identifiers: dict[str, Path] = {}
    cards: dict[str, tuple[Path, dict[str, Any], str]] = {}
    tasks: dict[str, tuple[Path, dict[str, Any], str]] = {}
    for kind, paths in (("knowledge-card", card_paths(wiki, categories)), ("task-note", task_note_paths(wiki))):
        for path in paths:
            relative = path.relative_to(root).as_posix()
            try:
                metadata, body, _ = read_markdown(path)
            except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
                errors.append({"code": "markdown.invalid", "detail": f"{relative}: {exc}"})
                continue
            identifier = normalize_space(metadata.get("id"))
            if not identifier:
                errors.append({"code": "record.id.missing", "detail": f"{relative} has no id"})
                continue
            if identifier in identifiers:
                errors.append({"code": "record.id.duplicate", "detail": f"{identifier} appears in {identifiers[identifier]} and {path}"})
            identifiers[identifier] = path
            if normalize_space(metadata.get("type")) != kind:
                errors.append({"code": "record.type", "detail": f"{relative} must have type {kind}"})
            if kind == "knowledge-card":
                category = normalize_space(metadata.get("category"))
                if category not in CATEGORY_DEFS:
                    errors.append({"code": "card.category", "detail": f"{relative} has invalid category {category!r}"})
                elif path.parent.name != category:
                    errors.append({"code": "card.category.path", "detail": f"{relative} is not stored under category {category}"})
                status = normalize_space(metadata.get("status"))
                confidence = normalize_space(metadata.get("confidence"))
                if status not in CARD_STATUSES:
                    errors.append({"code": "card.status", "detail": f"{relative} has invalid status {status!r}"})
                if confidence not in CONFIDENCE_LEVELS:
                    errors.append({"code": "card.confidence", "detail": f"{relative} has invalid confidence {confidence!r}"})
                if not extract_section(body, ("结论",)):
                    errors.append({"code": "card.knowledge.missing", "detail": f"{relative} has no 结论 section"})
                cards[identifier] = (path, metadata, body)
            else:
                status = normalize_space(metadata.get("task_status"))
                if status not in TASK_STATUSES:
                    errors.append({"code": "task.status", "detail": f"{relative} has invalid task_status {status!r}"})
                tasks[identifier] = (path, metadata, body)

    for identifier, (path, metadata, _) in cards.items():
        for old_id in unique_strings(metadata.get("supersedes")):
            if old_id not in cards:
                errors.append({"code": "card.supersedes.missing", "detail": f"{identifier} supersedes missing card {old_id}"})
            elif identifier not in unique_strings(cards[old_id][1].get("superseded_by")):
                errors.append({"code": "card.supersedes.asymmetric", "detail": f"{old_id} does not point back to {identifier}"})
        for new_id in unique_strings(metadata.get("superseded_by")):
            if new_id not in cards:
                errors.append({"code": "card.superseded_by.missing", "detail": f"{identifier} points to missing card {new_id}"})
        if normalize_space(metadata.get("status")) == "superseded" and not unique_strings(metadata.get("superseded_by")):
            warnings.append({"code": "card.superseded.unlinked", "detail": f"{identifier} is superseded without superseded_by"})

    for identifier, (_, metadata, _) in tasks.items():
        for card_id in unique_strings(metadata.get("card_ids")):
            if card_id not in cards:
                errors.append({"code": "task.card.missing", "detail": f"task {identifier} references missing card {card_id}"})

    try:
        _, outputs = build_index_outputs(root, config)
        for path, expected in outputs.items():
            actual = path.read_text(encoding="utf-8") if path.is_file() else None
            if actual != expected:
                errors.append({"code": "index.stale", "detail": f"{path.relative_to(root).as_posix()} is stale; run reindex"})
    except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
        errors.append({"code": "index.invalid", "detail": str(exc)})

    lock = wiki / ".write.lock"
    if lock.exists():
        warnings.append({"code": "write.lock.present", "detail": f"write lock exists: {lock}"})
    transactions = wiki / ".transactions"
    pending_transactions = sorted(path.name for path in transactions.iterdir()) if transactions.is_dir() else []
    if pending_transactions:
        errors.append(
            {
                "code": "write.transaction.pending",
                "detail": "pending recovery transactions: " + ", ".join(pending_transactions),
            }
        )

    legacy_tools = [
        name
        for name in (
            "cs_context.py", "cs_eval.py", "cs_evolve.py", "cs_feedback.py", "cs_fixture.py",
            "cs_harness.py", "cs_meta.py", "cs_observe.py", "cs_policy.py",
        )
        if (root / ".codestable" / "tools" / name).exists()
    ]
    if legacy_tools:
        warnings.append({"code": "legacy.tools.present", "detail": "retired tools remain: " + ", ".join(legacy_tools)})

    stats = {
        "cards": len(cards),
        "current_cards": sum(normalize_space(metadata.get("status")) in {"current", "proposed"} for _, metadata, _ in cards.values()),
        "task_notes": len(tasks),
        "categories": len(categories),
    }
    result: dict[str, Any] = {
        "ok": not errors,
        "tool_version": TOOL_VERSION,
        "scope": "structure+current-references" if check_current_references else "structure-only",
        "current_knowledge_validated": False,
        "current_references_checked": check_current_references,
        "next_check": "run drift to compare current references and Git changes",
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }
    if check_current_references:
        reference_check = current_reference_drift(root, config)
        result["current_references"] = reference_check
        result["ok"] = result["ok"] and not reference_check["findings"]
        result["next_check"] = "reference candidates checked; run drift with a Git scope for task-note coverage"
    return result


def status_payload(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = root.expanduser().resolve()
    entries = collect_index_entries(root, config)
    cards = [entry for entry in entries if entry["type"] == "knowledge-card"]
    tasks = [entry for entry in entries if entry["type"] == "task-note"]
    category_counts: dict[str, dict[str, int]] = {}
    for category in configured_categories(config):
        values = [entry for entry in cards if entry.get("category") == category]
        category_counts[category] = {
            "current": sum(entry["status"] == "current" for entry in values),
            "proposed": sum(entry["status"] == "proposed" for entry in values),
            "deprecated": sum(entry["status"] == "deprecated" for entry in values),
            "superseded": sum(entry["status"] == "superseded" for entry in values),
        }
    recent = sorted(tasks, key=lambda item: item.get("created_at") or "", reverse=True)[:10]
    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "categories": category_counts,
        "cards": len(cards),
        "task_notes": len(tasks),
        "recent_tasks": recent,
    }


def template_payload(title: str, kind: str) -> dict[str, Any]:
    return {
        "task": {
            "title": title or "任务标题",
            "kind": kind or "task",
            "status": "completed",
            "request": "用户最初要求",
            "summary": "实际做了什么；不要写计划或完整日志",
            "result": "最终可观察结果",
            "paths": ["src/example.py"],
            "symbols": ["ExampleService"],
            "tags": ["example"],
            "verification": ["python3 -m unittest tests.test_example"],
            "deliverable": "src/example.py",
            "knowledge_summary": "新增一张经验证的架构卡；未发现可复用的等义 current 卡。",
            "source": {"commit": "optional", "issue": "optional"},
        },
        "items": [
            {
                "category": "architecture",
                "title": "一个未来任务会复用的架构结论",
                "knowledge": "用当前时态写清楚稳定事实、约束或边界。",
                "rationale": "为什么采用这个结论，或它来自什么事实。",
                "implications": ["对未来实现、测试或运维的具体影响。"],
                "paths": ["src/example.py"],
                "symbols": ["ExampleService"],
                "tags": ["example"],
                "evidence": ["tests.test_example passes"],
                "confidence": "verified",
                "status": "current",
                "supersedes": [],
                "pinned": False,
            }
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project root or a path inside the project")
    subparsers = parser.add_subparsers(dest="command", required=True)

    brief_parser = subparsers.add_parser("brief", help="read-only task-oriented knowledge brief")
    brief_parser.add_argument("--task", required=True, help="current user request or task description")
    brief_parser.add_argument("--path", action="append", default=[], help="relevant project path; repeatable")
    brief_parser.add_argument("--symbol", action="append", default=[], help="relevant symbol; repeatable")
    brief_parser.add_argument("--limit", type=int, help="override maximum selected knowledge items")
    brief_parser.add_argument("--include-superseded", action="store_true", help="include superseded cards for history analysis")
    brief_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")

    learn_parser = subparsers.add_parser("learn", help="validate and persist a task note plus durable knowledge cards")
    learn_parser.add_argument("--file", required=True, help="learning JSON file, or '-' for stdin")
    learn_parser.add_argument("--dry-run", action="store_true", help="validate and show the write plan without filesystem changes")
    learn_parser.add_argument("--plan-token", help="apply the exact state and identifiers validated by a prior dry-run")

    doctor_parser = subparsers.add_parser("doctor", help="read-only structural integrity check; does not validate semantic truth")
    doctor_parser.add_argument("--check-current-references", action="store_true", help="also run deterministic current path/symbol checks")
    subparsers.add_parser("status", help="read-only knowledge inventory")

    drift_parser = subparsers.add_parser("drift", help="read-only current-reference and Git knowledge-writeback checks")
    drift_scope = drift_parser.add_mutually_exclusive_group()
    drift_scope.add_argument("--cached", action="store_true", help="check staged changes")
    drift_scope.add_argument("--base", help="check committed changes from <base>...HEAD")
    drift_scope.add_argument("--references-only", action="store_true", help="check current card paths and symbols without Git")
    drift_parser.add_argument("--format", choices=("text", "json"), default="text")

    reindex_parser = subparsers.add_parser("reindex", help="rebuild generated Markdown and JSONL indexes")
    reindex_parser.add_argument("--dry-run", action="store_true", help="show stale indexes without writing")

    template_parser = subparsers.add_parser("template", help="print a valid learning JSON template")
    template_parser.add_argument("--title", default="", help="task title")
    template_parser.add_argument("--kind", default="task", help="task kind")
    template_parser.add_argument("--output", help="explicit output file; stdout when omitted")
    return parser


def command_main(args: argparse.Namespace) -> tuple[int, str]:
    root = find_project_root(Path(args.root))
    config = load_config(root)
    if args.command == "brief":
        payload = selected_brief_payload(
            root,
            config,
            normalize_space(args.task),
            unique_strings(args.path),
            unique_strings(args.symbol),
            args.limit,
            bool(args.include_superseded),
        )
        return 0, json_dump(payload) if args.format == "json" else render_brief_markdown(payload)
    if args.command == "learn":
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid learning JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        return 0, json_dump(
            learn(
                root,
                config,
                raw,
                dry_run=bool(args.dry_run),
                plan_token=normalize_space(args.plan_token) or None,
            )
        )
    if args.command == "doctor":
        payload = doctor(root, config, check_current_references=bool(args.check_current_references))
        return (0 if payload["ok"] else 1), json_dump(payload)
    if args.command == "drift":
        payload = drift_payload(
            root,
            config,
            cached=bool(args.cached),
            base=normalize_space(args.base) or None,
            references_only=bool(args.references_only),
        )
        output = json_dump(payload) if args.format == "json" else render_drift_text(payload)
        return int(payload["exit_code"]), output
    if args.command == "status":
        return 0, json_dump(status_payload(root, config))
    if args.command == "reindex":
        return 0, json_dump({"ok": True, **rebuild_indexes(root, config, dry_run=bool(args.dry_run))})
    if args.command == "template":
        content = json_dump(template_payload(args.title, args.kind))
        if args.output:
            output = Path(args.output).expanduser().resolve()
            atomic_write_text(output, content)
            return 0, json_dump({"ok": True, "output": str(output)})
        return 0, content
    raise KnowledgeError(f"unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code, output = command_main(args)
    except (KnowledgeError, OSError, UnicodeDecodeError, ValueError) as exc:
        print(json_dump({"ok": False, "error": str(exc)}), end="")
        return 2
    print(output, end="" if output.endswith("\n") else "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
