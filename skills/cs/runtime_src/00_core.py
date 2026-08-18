#!/usr/bin/env python3
"""Read and maintain the CodeStable project knowledge wiki.

The tool is intentionally dependency-free. Read commands never write. The only
commands that mutate the wiki are ``learn``, ``consolidate``, ``topics update``, ``reindex`` and
``template`` when an explicit output path is supplied.
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
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence

TOOL_VERSION = "1.2.0"
SCHEMA_VERSION = 3
CURRENT_ENTRY = ".codestable/wiki/INDEX.md"
HISTORY_ENTRY = ".codestable/wiki/HISTORY.md"
TOPICS_ENTRY = ".codestable/wiki/TOPICS.md"
REPOSITORY_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*")
ENTRY_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:\./)?\.codestable/(?:wiki|model|knowledge)/[A-Za-z0-9_.\-/]+\.md)"
)

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
        "label": "决策",
        "description": "已接受或提议的决策、理由、后果、替代方案与取代关系",
        "aliases": ("决策", "decision", "adr", "rationale", "选择", "历史", "替代方案", "why"),
    },
}

CARD_STATUSES = {"current", "proposed", "deprecated", "superseded"}
INPUT_CARD_STATUSES = {"current", "proposed", "deprecated"}
CONFIDENCE_LEVELS = {"verified", "accepted", "inferred"}
TASK_STATUSES = {"completed", "in-progress", "partial", "blocked", "cancelled"}
TASK_VISIBILITIES = {"active", "archived"}
KNOWLEDGE_USE_KINDS = {"adopted", "changed-design", "implemented", "tested", "reviewed", "scope-adjusted"}
KNOWLEDGE_EVIDENCE_KINDS = {"implementation", "test", "design", "review", "scope", "contract"}
CARD_EVIDENCE_KINDS = {"implementation", "test", "contract", "compatibility", "accepted-decision"}
PLACEHOLDER_PATTERN = re.compile(
    r"(?:__REPLACE__|待填写|\bTODO\b|\bTBD\b|src/example\.py|tests?\.test_example)",
    re.IGNORECASE,
)
GENERIC_DURABLE_TEXT = {
    "用当前时态写清楚稳定事实、约束或边界。",
    "为什么采用这个结论，或它来自什么事实。",
    "对未来实现、测试或运维的具体影响。",
    "未来修改该模块边界时复核。",
    "未来替换依赖或补充集成测试时复核。",
}
GENERIC_KNOWLEDGE_USE = re.compile(
    r"^(?:已?)?(?:读取|查看|参考|引用|检索)(?:了)?(?:历史)?(?:知识|卡片|决策)?[。.!]?$|^(?:checked|reviewed|read|referenced)(?: the)? card[.!]?$",
    re.IGNORECASE,
)
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
    "scope_history",
    "topic_history",
    "task_id",
    "task_status",
    "fingerprint",
    "pinned",
    "tags",
    "topics",
    "scopes",
    "paths",
    "symbols",
    "supersedes",
    "supersession_reason",
    "superseded_by",
    "card_ids",
    "deliverable",
    "new_task_reason",
    "knowledge_summary",
    "knowledge_use",
    "future_use",
    "evidence",
    "source",
    "visibility",
    "consolidated_from",
    "consolidated_into",
    "consolidation_fingerprint",
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
    topics: tuple[str, ...] = ()
    scopes: tuple[tuple[str, str, str], ...] = ()
    paths: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    revision: int = 0
    content_hash: str = ""
    pinned: bool = False


@dataclass(frozen=True)
class MatchDetails:
    score: float
    qualifies: bool
    precedence: int
    reasons: tuple[tuple[str, str, str], ...] = ()


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
            f"unsupported config schema {data.get('schema_version')!r}; expected {SCHEMA_VERSION}; "
            "run bootstrap.py --upgrade before using this runtime"
        )
    return data


def configured_categories(config: dict[str, Any]) -> list[str]:
    wiki = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    values = wiki.get("categories") if isinstance(wiki, dict) else None
    categories = unique_strings(values if isinstance(values, list) else list(CATEGORY_DEFS))
    missing = [category for category in CATEGORY_DEFS if category not in categories]
    return [category for category in categories if category in CATEGORY_DEFS] + missing


def configured_topics(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    wiki = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    raw = wiki.get("topics") if isinstance(wiki, dict) else {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, value in raw.items():
        topic = normalize_space(name).casefold()
        if not REPOSITORY_NAME_PATTERN.fullmatch(topic) or not isinstance(value, dict):
            continue
        result[topic] = {
            "label": normalize_space(value.get("label")) or topic,
            "summary": normalize_space(value.get("summary")),
            "aliases": [item.casefold() for item in unique_strings(value.get("aliases"))],
            "replaces": [item.casefold() for item in unique_strings(value.get("replaces"))],
        }
    return result


def topic_aliases(config: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for name, topic in configured_topics(config).items():
        aliases[name] = name
        for alias in topic.get("aliases") or []:
            if REPOSITORY_NAME_PATTERN.fullmatch(alias) and alias not in aliases:
                aliases[alias] = name
    return aliases


def topic_governance(config: dict[str, Any]) -> dict[str, Any]:
    wiki = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    raw = wiki.get("topic_governance") if isinstance(wiki, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    mode = normalize_space(raw.get("mode") or "disabled").lower()
    if mode not in {"disabled", "manual", "required"}:
        mode = "disabled"
    try:
        coverage = float(raw.get("minimum_coverage", 0.0) or 0.0)
    except (TypeError, ValueError):
        coverage = 0.0
    return {
        "mode": mode,
        "minimum_coverage": min(1.0, max(0.0, coverage)),
        "review_max_age_days": safe_int(raw.get("review_max_age_days"), 180, minimum=1, maximum=3650),
    }


def configured_repositories(root: Path, config: dict[str, Any]) -> dict[str, Path]:
    wiki = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    raw = wiki.get("repositories") if isinstance(wiki, dict) else {}
    result = {"self": root.expanduser().resolve()}
    if not isinstance(raw, dict):
        return result
    for name, value in raw.items():
        repository = normalize_space(name).casefold()
        if repository == "self" or not REPOSITORY_NAME_PATTERN.fullmatch(repository) or not isinstance(value, dict):
            continue
        configured_root = normalize_space(value.get("root"))
        if not configured_root:
            continue
        candidate = Path(configured_root).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        result[repository] = candidate.resolve()
    return result


def normalize_topics(value: Any, config: dict[str, Any]) -> list[str]:
    topics = [item.casefold() for item in unique_strings(value)]
    aliases = topic_aliases(config)
    unknown = [item for item in topics if item not in aliases]
    if unknown:
        raise KnowledgeError("unknown knowledge topics: " + ", ".join(unknown))
    return unique_strings([aliases[item] for item in topics])


def normalize_scopes(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise KnowledgeError("scopes must be an array")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise KnowledgeError("every scope must be an object")
        if set(raw) - {"repository", "path", "symbol"}:
            raise KnowledgeError("scope accepts only repository, path, and symbol")
        repository = normalize_space(raw.get("repository") or "self").casefold()
        path = normalize_space(raw.get("path")).replace("\\", "/")
        symbol = normalize_space(raw.get("symbol"))
        if not REPOSITORY_NAME_PATTERN.fullmatch(repository):
            raise KnowledgeError(f"invalid scope repository name: {repository!r}")
        if not path and not symbol:
            raise KnowledgeError("scope requires path or symbol")
        if path:
            pure = PurePosixPath(path)
            if pure.is_absolute() or ".." in pure.parts:
                raise KnowledgeError(f"scope path must be repository-relative: {path}")
            path = pure.as_posix()
        key = (repository, path, symbol)
        if key in seen:
            continue
        seen.add(key)
        result.append({"repository": repository, "path": path, "symbol": symbol})
    return result


def scope_tuple(value: dict[str, str]) -> tuple[str, str, str]:
    return (value.get("repository") or "self", value.get("path") or "", value.get("symbol") or "")


def scope_paths(scopes: Sequence[dict[str, str]]) -> list[str]:
    return unique_strings([value.get("path") for value in scopes])


def scope_symbols(scopes: Sequence[dict[str, str]]) -> list[str]:
    return unique_strings([value.get("symbol") for value in scopes])


def legacy_scopes(paths: Sequence[str], symbols: Sequence[str]) -> list[dict[str, str]]:
    result = [{"repository": "self", "path": path, "symbol": ""} for path in paths]
    result.extend({"repository": "self", "path": "", "symbol": symbol} for symbol in symbols)
    return result


def normalize_evidence_objects(value: Any, use: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise KnowledgeError(f"task.knowledge_use '{use}' requires structured evidence")
    result: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise KnowledgeError("task.knowledge_use.evidence entries must be objects")
        if set(raw) - {"kind", "artifact", "result", "supports"}:
            raise KnowledgeError("knowledge-use evidence accepts only kind, artifact, result, and supports")
        kind = normalize_space(raw.get("kind")).lower()
        artifact = normalize_space(raw.get("artifact"))
        observed = normalize_space(raw.get("result"))
        supports = normalize_space(raw.get("supports"))
        if kind not in KNOWLEDGE_EVIDENCE_KINDS:
            raise KnowledgeError(f"knowledge-use evidence kind must be one of {sorted(KNOWLEDGE_EVIDENCE_KINDS)}")
        if not artifact or not observed or not supports:
            raise KnowledgeError("knowledge-use evidence requires artifact, result, and supports")
        result.append({"kind": kind, "artifact": artifact, "result": observed, "supports": supports})
    required_kind = {
        "tested": {"test"},
        "implemented": {"implementation", "design"},
        "reviewed": {"review"},
        "changed-design": {"design", "implementation"},
        "scope-adjusted": {"scope", "design", "implementation"},
        "adopted": {"design", "contract", "implementation"},
    }[use]
    if not any(value["kind"] in required_kind for value in result):
        raise KnowledgeError(f"task.knowledge_use '{use}' evidence type does not match the claimed use")
    return result


def reject_placeholder(value: str, field: str) -> None:
    if PLACEHOLDER_PATTERN.search(value) or value in GENERIC_DURABLE_TEXT:
        raise KnowledgeError(f"{field} contains placeholder or generic template text; replace it with project evidence")


def normalize_card_evidence(value: Any, strict: bool) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise KnowledgeError("item.evidence must be an array")
    result: list[Any] = []
    seen: set[str] = set()
    for raw in value:
        if isinstance(raw, str):
            text = normalize_space(raw)
            if not text:
                continue
            if strict:
                raise KnowledgeError(
                    "strict durable cards require structured item.evidence with kind, artifact, result, and supports"
                )
            key = stable_json(text)
            normalized: Any = text
        elif isinstance(raw, dict):
            if set(raw) - {"kind", "artifact", "result", "supports"}:
                raise KnowledgeError("item.evidence accepts only kind, artifact, result, and supports")
            kind = normalize_space(raw.get("kind")).lower()
            artifact = normalize_space(raw.get("artifact"))
            observed = normalize_space(raw.get("result"))
            supports = normalize_space(raw.get("supports"))
            if kind not in CARD_EVIDENCE_KINDS:
                raise KnowledgeError(f"item.evidence kind must be one of {sorted(CARD_EVIDENCE_KINDS)}")
            if not artifact or not observed or not supports:
                raise KnowledgeError("item.evidence requires artifact, result, and supports")
            for field, text in (("artifact", artifact), ("result", observed), ("supports", supports)):
                reject_placeholder(text, f"item.evidence.{field}")
            normalized = {"kind": kind, "artifact": artifact, "result": observed, "supports": supports}
            key = stable_json(normalized)
        else:
            raise KnowledgeError("item.evidence entries must be strings or structured evidence objects")
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def normalize_future_use(value: Any, strict: bool) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise KnowledgeError("item.future_use must be an array")
    result: list[Any] = []
    seen: set[str] = set()
    for raw in value:
        if isinstance(raw, str):
            text = normalize_space(raw)
            if not text:
                continue
            if strict:
                raise KnowledgeError(
                    "strict durable cards require structured item.future_use with change, actor, and constraint"
                )
            normalized: Any = text
        elif isinstance(raw, dict):
            if set(raw) - {"change", "actor", "constraint"}:
                raise KnowledgeError("item.future_use accepts only change, actor, and constraint")
            change = normalize_space(raw.get("change"))
            actor = normalize_space(raw.get("actor"))
            constraint = normalize_space(raw.get("constraint"))
            if not change or not actor or not constraint:
                raise KnowledgeError("item.future_use requires change, actor, and constraint")
            for field, text in (("change", change), ("actor", actor), ("constraint", constraint)):
                reject_placeholder(text, f"item.future_use.{field}")
            normalized = {"change": change, "actor": actor, "constraint": constraint}
        else:
            raise KnowledgeError("item.future_use entries must be strings or structured scenario objects")
        key = stable_json(normalized)
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def render_card_evidence(values: Sequence[Any]) -> str:
    lines: list[str] = []
    for value in values:
        if isinstance(value, dict):
            lines.append(
                f"- {value.get('kind')} `{value.get('artifact')}`：{value.get('result')}；支持：{value.get('supports')}"
            )
        elif normalize_space(value):
            lines.append(f"- {normalize_space(value)}（旧格式）")
    return "\n".join(lines) if lines else "- 无"


def render_future_use(values: Sequence[Any]) -> str:
    lines: list[str] = []
    for value in values:
        if isinstance(value, dict):
            lines.append(
                f"- 变更：{value.get('change')}；执行者：{value.get('actor')}；需复核约束：{value.get('constraint')}"
            )
        elif normalize_space(value):
            lines.append(f"- {normalize_space(value)}（旧格式）")
    return "\n".join(lines) if lines else "- 无"


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


def validate_knowledge_migration_source(source: dict[str, Any]) -> bool:
    migration = source.get("knowledge_migration")
    if migration is None:
        return False
    if not isinstance(migration, dict):
        raise KnowledgeError("task.source.knowledge_migration must be an object")
    pages = migration.get("pages")
    complete = migration.get("complete")
    if not isinstance(complete, bool):
        raise KnowledgeError("task.source.knowledge_migration.complete must be a boolean")
    if not isinstance(pages, list) or not pages:
        raise KnowledgeError("task.source.knowledge_migration.pages must be a non-empty audit ledger")
    seen: set[str] = set()
    pending = False
    for page in pages:
        if not isinstance(page, dict):
            raise KnowledgeError("every knowledge migration page audit must be an object")
        path = normalize_space(page.get("path"))
        digest = normalize_space(page.get("sha256")).lower()
        backup_path = normalize_space(page.get("backup_path"))
        outcome = normalize_space(page.get("outcome")).lower()
        disposition = normalize_space(page.get("disposition"))
        evidence = unique_strings(page.get("evidence"))
        if not path or path in seen:
            raise KnowledgeError("every knowledge migration page must have a unique path")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise KnowledgeError(f"knowledge migration page {path} must retain its inventory SHA-256")
        if not backup_path:
            raise KnowledgeError(f"knowledge migration page {path} must retain its backup path")
        if outcome not in {"migrated", "covered", "obsolete", "pending"}:
            raise KnowledgeError(f"knowledge migration page {path} has invalid outcome {outcome!r}")
        if not disposition:
            raise KnowledgeError(f"knowledge migration page {path} requires a compact disposition")
        if outcome != "pending" and not evidence:
            raise KnowledgeError(f"knowledge migration page {path} requires current implementation, test, or Wiki evidence")
        pending = pending or outcome == "pending"
        seen.add(path)
    if complete and pending:
        raise KnowledgeError("knowledge migration cannot be complete while a page remains pending")
    return True
