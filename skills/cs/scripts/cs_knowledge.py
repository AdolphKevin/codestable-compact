#!/usr/bin/env python3
# Generated from skills/cs/runtime_src; source-sha256: 7672a7edf88c6c54ccc77177a8cec5deaf6d574b5aa380da117bb71bc6615c4d
"""Read and maintain the CodeStable project knowledge wiki.

The tool is intentionally dependency-free. Read commands never write. The only
commands that mutate the wiki are ``learn``, ``consolidate``, ``topics update``, ``reindex`` and
``template`` when an explicit output path is supplied.
"""

from __future__ import annotations

import argparse
import base64
import difflib
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

TOOL_VERSION = "1.2.2"
SCHEMA_VERSION = 3
RUNTIME_MODE = "knowledge_wiki"
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
    if data.get("mode") != RUNTIME_MODE:
        raise KnowledgeError(f"project data is not in {RUNTIME_MODE} mode; run bootstrap.py --upgrade")
    try:
        actual_schema = int(data.get("schema_version", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise KnowledgeError(
            f"unsupported config schema {data.get('schema_version')!r}; expected {SCHEMA_VERSION}; "
            "run bootstrap.py --upgrade before using this runtime"
        ) from exc
    if actual_schema != SCHEMA_VERSION:
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


def topic_name_suggestions(value: str, config: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Return deterministic, explainable canonical-topic suggestions."""
    query = normalize_space(value).casefold()
    if not query:
        return []
    query_parts = {part for part in re.split(r"[._-]+", query) if part}
    ranked: list[tuple[float, str, str]] = []
    for name, definition in configured_topics(config).items():
        candidates = [name, normalize_space(definition.get("label")).casefold(), *(definition.get("aliases") or [])]
        best_score = 0.0
        best_value = name
        for candidate in candidates:
            candidate = normalize_space(candidate).casefold()
            if not candidate:
                continue
            ratio = difflib.SequenceMatcher(None, query, candidate).ratio()
            candidate_parts = {part for part in re.split(r"[._-]+", candidate) if part}
            overlap = len(query_parts & candidate_parts) / max(1, len(query_parts | candidate_parts))
            score = max(ratio, overlap)
            if score > best_score or (score == best_score and candidate < best_value):
                best_score = score
                best_value = candidate
        if best_score >= 0.45:
            ranked.append((best_score, name, best_value))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    definitions = configured_topics(config)
    return [
        {
            "name": name,
            "label": definitions[name]["label"],
            "similarity": round(score, 3),
            "matched_by": matched_by,
        }
        for score, name, matched_by in ranked[: max(1, limit)]
    ]


def resolve_brief_topics(value: Any, config: dict[str, Any]) -> dict[str, Any]:
    """Resolve optional brief topics without letting an unknown hint abort retrieval."""
    requested = [item.casefold() for item in unique_strings(value)]
    aliases = topic_aliases(config)
    resolved = unique_strings([aliases[item] for item in requested if item in aliases])
    unknown = [item for item in requested if item not in aliases]
    warnings: list[dict[str, Any]] = []
    for item in unknown:
        suggestions = topic_name_suggestions(item, config)
        names = [suggestion["name"] for suggestion in suggestions]
        if names:
            action = "omit --topic or retry with one of: " + ", ".join(names)
        elif aliases:
            action = "omit --topic or run topics list to inspect configured names"
        else:
            action = "omit --topic; no topics are configured, so rely on task, path, symbol, and repository scope"
        warnings.append(
            {
                "code": "brief.topic.unknown",
                "topic": item,
                "detail": f"unknown topic {item!r} was ignored; retrieval continued with the other query signals",
                "suggestions": suggestions,
                "action": action,
            }
        )
    return {
        "requested": requested,
        "resolved": resolved,
        "unknown": unknown,
        "warnings": warnings,
    }


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
        outcome = normalize_space(page.get("outcome")).lower()
        disposition = normalize_space(page.get("disposition"))
        evidence = unique_strings(page.get("evidence"))
        if not path or path in seen:
            raise KnowledgeError("every knowledge migration page must have a unique path")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise KnowledgeError(f"knowledge migration page {path} must retain its inventory SHA-256")
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

def normalize_task(raw: Any, config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("learning payload task must be an object")
    allowed = {
        "title", "kind", "id", "update_existing", "expected_revision", "status", "request", "summary",
        "result", "paths", "symbols", "scopes", "topics", "tags", "verification", "deliverable",
        "new_task_reason", "knowledge_summary", "knowledge_use", "source",
    }
    if set(raw) - allowed:
        raise KnowledgeError("unknown task fields: " + ", ".join(sorted(set(raw) - allowed)))
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
    raw_knowledge_use = raw.get("knowledge_use") or []
    if not isinstance(raw_knowledge_use, list):
        raise KnowledgeError("task.knowledge_use must be an array")
    knowledge_use: list[dict[str, Any]] = []
    for value in raw_knowledge_use:
        if not isinstance(value, dict):
            raise KnowledgeError("every task.knowledge_use entry must be an object")
        if set(value) - {"card_id", "card_revision", "use", "detail", "before", "after", "evidence"}:
            raise KnowledgeError("task.knowledge_use contains unknown fields")
        card_id = normalize_space(value.get("card_id"))
        card_revision = value.get("card_revision")
        use = normalize_space(value.get("use")).lower()
        detail = normalize_space(value.get("detail"))
        before = normalize_space(value.get("before"))
        after = normalize_space(value.get("after"))
        if not re.fullmatch(r"K-[A-Za-z0-9-]+", card_id):
            raise KnowledgeError("task.knowledge_use.card_id must be an existing K-* identifier")
        if not isinstance(card_revision, int) or isinstance(card_revision, bool) or card_revision < 1:
            raise KnowledgeError("task.knowledge_use.card_revision must be a positive integer from the brief receipt")
        if use not in KNOWLEDGE_USE_KINDS:
            raise KnowledgeError(f"task.knowledge_use.use must be one of {sorted(KNOWLEDGE_USE_KINDS)}")
        if not detail or GENERIC_KNOWLEDGE_USE.fullmatch(detail):
            raise KnowledgeError("task.knowledge_use.detail must state the concrete design or review effect")
        evidence = normalize_evidence_objects(value.get("evidence"), use)
        if use == "changed-design" and (not before or not after):
            raise KnowledgeError("task.knowledge_use 'changed-design' requires public before and after descriptions")
        knowledge_use.append(
            {
                "card_id": card_id,
                "card_revision": card_revision,
                "use": use,
                "detail": detail,
                "before": before,
                "after": after,
                "evidence": evidence,
            }
        )
    migration_task = validate_knowledge_migration_source(source)
    if migration_task and normalize_space(raw.get("kind") or "task") != "knowledge-migration":
        raise KnowledgeError("task.source.knowledge_migration requires task.kind=knowledge-migration")
    paths = unique_strings(raw.get("paths"))
    symbols = unique_strings(raw.get("symbols"))
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
        "paths": paths,
        "symbols": symbols,
        "scopes": normalize_scopes(raw.get("scopes")),
        "topics": normalize_topics(raw.get("topics"), config),
        "tags": unique_strings(raw.get("tags")),
        "verification": unique_strings(raw.get("verification")),
        "deliverable": normalize_space(raw.get("deliverable")),
        "new_task_reason": normalize_space(raw.get("new_task_reason")),
        "knowledge_summary": normalize_space(raw.get("knowledge_summary")),
        "knowledge_use": knowledge_use,
        "source": source,
        "knowledge_migration": migration_task,
    }


def normalize_item(raw: Any, task: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("every learning item must be an object")
    allowed = {
        "operation", "card_id", "expected_revision", "category", "title", "knowledge", "context",
        "rationale", "alternatives", "consequences", "future_use", "implications", "paths", "symbols",
        "scopes", "topics", "tags", "evidence", "confidence", "status", "supersedes",
        "supersession_reason", "new_card_reason", "pinned",
    }
    if set(raw) - allowed:
        raise KnowledgeError("unknown knowledge item fields: " + ", ".join(sorted(set(raw) - allowed)))
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
    capture = config.get("capture") if isinstance(config.get("capture"), dict) else {}
    strict = bool(capture.get("strict_durable_cards", True))
    evidence = normalize_card_evidence(raw.get("evidence"), strict)
    final_evidence = evidence or ([] if strict else list(task["verification"]))
    if confidence == "verified" and not final_evidence:
        raise KnowledgeError(f"verified item '{title}' requires item.evidence")
    if strict and confidence == "verified" and not any(
        isinstance(value, dict) and value.get("kind") in {"implementation", "test", "contract", "compatibility"}
        for value in final_evidence
    ):
        raise KnowledgeError(
            f"verified item '{title}' requires implementation, test, contract, or compatibility evidence; "
            "an accepted-decision record alone supports confidence=accepted"
        )
    rationale = normalize_space(raw.get("rationale"))
    implications = unique_strings(raw.get("implications"))
    context = normalize_space(raw.get("context"))
    alternatives = unique_strings(raw.get("alternatives"))
    consequences = unique_strings(raw.get("consequences"))
    future_use = normalize_future_use(raw.get("future_use"), strict)
    paths = unique_strings(raw.get("paths")) or list(task["paths"])
    symbols = unique_strings(raw.get("symbols")) or list(task["symbols"])
    scopes = normalize_scopes(raw.get("scopes")) or list(task["scopes"])
    topics = normalize_topics(raw.get("topics"), config) or list(task["topics"])
    supersedes = unique_strings(raw.get("supersedes"))
    supersession_reason = normalize_space(raw.get("supersession_reason"))
    operation = normalize_space(raw.get("operation") or "create").lower()
    card_id = normalize_space(raw.get("card_id"))
    expected_revision = raw.get("expected_revision")
    if operation not in {"create", "update"}:
        raise KnowledgeError("item.operation must be create or update")
    if operation == "update":
        if not re.fullmatch(r"K-[A-Za-z0-9-]+", card_id):
            raise KnowledgeError("item.card_id must be an existing K-* identifier for update")
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
            raise KnowledgeError("item.expected_revision must be a positive integer for update")
        if supersedes:
            raise KnowledgeError("updating an unchanged conclusion cannot add supersedes; create a replacement card instead")
    elif card_id or expected_revision is not None:
        raise KnowledgeError("item.card_id and expected_revision require item.operation=update")
    if strict and status == "current":
        for field, value in (("title", title), ("knowledge", knowledge), ("rationale", rationale)):
            if value:
                reject_placeholder(value, f"item.{field}")
        if not final_evidence:
            raise KnowledgeError(f"current item '{title}' requires implementation, test, compatibility, or accepted-decision evidence")
        if not scopes and not paths and not symbols:
            raise KnowledgeError(f"current item '{title}' requires an applicability scope")
        if len(future_use) < 2:
            raise KnowledgeError(f"current item '{title}' requires at least two concrete future-use scenarios")
        if len({stable_json(value) for value in future_use}) < 2:
            raise KnowledgeError(f"current item '{title}' requires two distinct future-use scenarios")
    if category == "decisions":
        if not rationale:
            raise KnowledgeError(f"decision item '{title}' requires rationale")
        if strict and (not context or not alternatives or not consequences):
            raise KnowledgeError(f"decision item '{title}' requires context, alternatives, and consequences")
    if strict and supersedes and not supersession_reason:
        raise KnowledgeError(f"item '{title}' requires supersession_reason because it replaces a long-term conclusion")
    return {
        "operation": operation,
        "card_id": card_id,
        "expected_revision": expected_revision,
        "category": category,
        "title": title,
        "knowledge": knowledge,
        "rationale": rationale,
        "implications": implications,
        "context": context,
        "alternatives": alternatives,
        "consequences": consequences,
        "future_use": future_use,
        "paths": paths,
        "symbols": symbols,
        "scopes": scopes,
        "topics": topics,
        "tags": unique_strings(raw.get("tags")) or list(task["tags"]),
        "evidence": final_evidence,
        "confidence": confidence,
        "status": status,
        "supersedes": supersedes,
        "supersession_reason": supersession_reason,
        "new_card_reason": normalize_space(raw.get("new_card_reason")),
        "pinned": bool(raw.get("pinned", False)),
    }


def normalize_learning_payload(raw: Any, config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        raise KnowledgeError("learning payload must be a JSON object")
    if set(raw) - {"task", "items"}:
        unknown = ", ".join(sorted(set(raw) - {"task", "items"}))
        raise KnowledgeError(f"unknown top-level learning fields: {unknown}")
    task = normalize_task(raw.get("task"), config)
    raw_items = raw.get("items")
    if not isinstance(raw_items, list):
        raise KnowledgeError("learning payload items must be an array")
    items = [normalize_item(item, task, config) for item in raw_items]
    if task["status"] != "completed" and items:
        partial_migration = task["status"] == "partial" and task["knowledge_migration"]
        if not partial_migration or any(not item["evidence"] or item["confidence"] == "inferred" for item in items):
            raise KnowledgeError(
                "only completed tasks may create or reuse durable knowledge cards; a partial knowledge-migration "
                "may capture only individually evidenced accepted/verified facts"
            )
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
        "context": item["context"],
        "alternatives": item["alternatives"],
        "consequences": item["consequences"],
        "future_use": item["future_use"],
        "scopes": item["scopes"],
        "topics": item["topics"],
        "paths": item["paths"],
        "symbols": item["symbols"],
        "tags": item["tags"],
        "evidence": item["evidence"],
        "confidence": item["confidence"],
        "status": item["status"],
        "supersedes": item["supersedes"],
        "supersession_reason": item["supersession_reason"],
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
        "items": [
            {
                "fingerprint": item_fingerprint(item),
                "operation": item.get("operation") or "create",
                "card_id": item.get("card_id") or "",
                "expected_revision": item.get("expected_revision"),
            }
            for item in items
        ],
    }
    return sha256_text(stable_json(material))


def legacy_task_fingerprint(task: dict[str, Any], items: Sequence[dict[str, Any]]) -> str:
    """Fingerprint produced before task update controls and deliverable existed."""
    task_content = {
        key: value
        for key, value in task.items()
        if key not in {
            "id", "update_existing", "expected_revision", "deliverable", "new_task_reason",
            "knowledge_summary", "knowledge_use", "knowledge_migration",
        }
    }
    return sha256_text(stable_json({"task": task_content, "items": [item_fingerprint(item) for item in items]}))


def make_id(prefix: str, fingerprint: str, timestamp: datetime, sequence: int = 0) -> str:
    base = timestamp.strftime("%Y%m%d-%H%M%S")
    suffix = fingerprint[:8]
    return f"{prefix}-{base}-{sequence:02d}-{suffix}" if sequence else f"{prefix}-{base}-{suffix}"


def render_card_body(item: dict[str, Any], task: dict[str, Any], task_id: str) -> str:
    source = task.get("source") or {}
    if task.get("knowledge_migration"):
        source = {"knowledge_migration_task": task_id, "audit_ledger": "task-note"}
    source_text = json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) if source else "{}"
    scope_lines = [
        f"- 仓库 `{scope['repository']}` · 路径 `{scope['path'] or '未限定'}` · 符号 `{scope['symbol'] or '未限定'}`"
        for scope in item["scopes"]
    ]
    if not scope_lines:
        scope_lines = [
            f"- 旧格式路径：{', '.join(item['paths']) or '未限定'}",
            f"- 旧格式符号：{', '.join(item['symbols']) or '未限定'}",
        ]
    return f"""# {item['title']}

## 结论

{item['knowledge']}

## 背景

{item['context'] or '未单独记录；参见来源任务。'}

## 理由

{item['rationale'] or '未单独记录；参见来源任务。'}

## 影响

{markdown_bullets(item['implications'])}

## 主要替代方案

{markdown_bullets(item['alternatives'])}

## 后果

{markdown_bullets(item['consequences'])}

## 未来复用场景

{render_future_use(item['future_use'])}

## 适用范围

- 结构化范围：
{chr(10).join(scope_lines)}
- 标签：{', '.join(item['tags']) or '无'}
- 主题：{', '.join(item['topics']) or '无'}

## 取代说明

{item['supersession_reason'] or '未取代其他长期结论。'}

## 验证与依据

{render_card_evidence(item['evidence'])}

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
    use_lines = []
    for value in task.get("knowledge_use") or []:
        delta = ""
        if value.get("before") or value.get("after"):
            delta = f" · 调整前：{value.get('before') or '未记录'} · 调整后：{value.get('after') or '未记录'}"
        evidence = "; ".join(
            f"{item['kind']} `{item['artifact']}`：{item['result']}；对应约束：{item['supports']}"
            for item in value["evidence"]
        )
        use_lines.append(
            f"`{value['card_id']}` revision {value['card_revision']} · {value['use']} · "
            f"{value['detail']}{delta} · 依据：{evidence}"
        )
    knowledge_use = markdown_bullets(use_lines, empty="- 未声明历史知识对本任务产生了可证明的设计、实现、测试或 review 影响。")
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
- 结构化范围：{json.dumps(task['scopes'], ensure_ascii=False) if task['scopes'] else '未记录'}
- 标签：{', '.join(task['tags']) or '无'}
- 主题：{', '.join(task['topics']) or '无'}
- 主要交付物：{task['deliverable'] or '未单独记录'}
- 独立任务理由：{task['new_task_reason'] or '无；本记录不是在强候选之外另建的任务'}

## 沉淀的知识卡片

{linked}

## 知识处置

{task['knowledge_summary'] or '未说明；完成任务前应写明新增、复用、取代了哪些知识，或为什么没有长期知识。'}

## 历史知识使用证据

{knowledge_use}

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
    visibility = normalize_space(metadata.get("visibility") or "active")
    excerpt = "" if visibility == "archived" else extract_section(body, ("结论", "处理摘要", "最终结果")) or clip(body, 400)
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
        "topics": unique_strings(metadata.get("topics")),
        "scopes": metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [],
        "paths": unique_strings(metadata.get("paths")),
        "symbols": unique_strings(metadata.get("symbols")),
        "supersedes": unique_strings(metadata.get("supersedes")),
        "superseded_by": unique_strings(metadata.get("superseded_by")),
        "card_ids": unique_strings(metadata.get("card_ids")),
        "knowledge_use_card_ids": unique_strings([
            value.get("card_id")
            for value in (metadata.get("knowledge_use") or [])
            if isinstance(value, dict)
        ]),
        "visibility": visibility,
        "consolidated_from": unique_strings(metadata.get("consolidated_from")),
        "consolidated_into": normalize_space(metadata.get("consolidated_into")) or None,
        "pinned": bool(metadata.get("pinned", False)),
        "revision": int(metadata.get("revision", 1) or 1),
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
    active_tasks = [entry for entry in tasks if entry.get("visibility") != "archived"]
    archived_tasks = [entry for entry in tasks if entry.get("visibility") == "archived"]
    current_cards = [entry for entry in cards if entry["status"] == "current"]
    proposed_cards = [entry for entry in cards if entry["status"] == "proposed"]
    topic_definitions = configured_topics(config)
    lines = [
        "# CodeStable Wiki 当前入口",
        "",
        "> 这是 CodeStable Wiki 的唯一当前入口。分类和主题页只提供导航；知识卡片是结论正文的唯一来源。",
        "",
        f"- 当前知识卡片：{len(current_cards)}",
        f"- 提议知识卡片：{len(proposed_cards)}",
        f"- 已取代/弃用卡片：{sum(1 for entry in cards if entry['status'] in {'superseded', 'deprecated'})}",
        f"- 默认任务记录：{len(active_tasks)}",
        f"- 已折叠历史记录：{len(archived_tasks)}",
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
    lines.extend(("", "## 业务主题", ""))
    topic_counts: dict[str, int] = {}
    aliases = topic_aliases(config)
    for entry in current_cards:
        for topic in entry.get("topics") or []:
            canonical = aliases.get(topic, topic)
            topic_counts[canonical] = topic_counts.get(canonical, 0) + 1
    if not topic_counts:
        lines.append("- 暂无带业务主题的当前卡片；未带主题元数据的当前卡片仍可通过分类、路径和符号检索。")
    else:
        lines.extend(("| 主题 | 当前卡片 | 导航说明 |", "|---|---:|---|"))
        for topic in sorted(topic_counts):
            definition = topic_definitions.get(topic, {"label": topic, "summary": ""})
            lines.append(
                f"| [{definition['label']}](TOPICS.md#{slugify(definition['label'], topic)}) | "
                f"{topic_counts[topic]} | {definition['summary'] or '未填写主题说明'} |"
            )
    lines.extend(("", "历史卡片、取代链和归档任务见 [历史索引](HISTORY.md)。", ""))
    lines.extend(("## 最近完成任务", ""))
    completed = sorted(
        [entry for entry in active_tasks if entry["status"] == "completed"],
        key=lambda item: (item.get("updated_at") or item.get("created_at") or "", item.get("id") or ""),
        reverse=True,
    )[:20]
    if not completed:
        lines.append("- 暂无任务记录。")
    else:
        index_path = wiki / "INDEX.md"
        for entry in completed:
            target = root / entry["path"]
            lines.append(
                f"- [{entry['title']}]({relative_link(index_path, target)}) · "
                f"{entry['status']} · {entry.get('created_at') or 'unknown time'}"
            )
    lines.extend(("", "## 未完成任务", ""))
    incomplete = sorted(
        [entry for entry in active_tasks if entry["status"] in {"in-progress", "partial", "blocked"}],
        key=lambda item: (item.get("updated_at") or item.get("created_at") or "", item.get("id") or ""),
        reverse=True,
    )
    if not incomplete:
        lines.append("- 无未完成任务。")
    else:
        index_path = wiki / "INDEX.md"
        for entry in incomplete:
            target = root / entry["path"]
            lines.append(f"- [{entry['title']}]({relative_link(index_path, target)}) · {entry['status']}")
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
                lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {' · '.join(suffixes)}")
                lines.append(f"  - {entry.get('excerpt') or ''}")
        lines.append("")
    lines.append(f"已弃用和被取代的卡片见 [历史索引](../HISTORY.md#{slugify(label, category)})。")
    lines.append("")
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成；人工摘要请维护在 [README.md](README.md)。")
    lines.append("")
    return "\n".join(lines)


def render_topics_index(root: Path, config: dict[str, Any], entries: Sequence[dict[str, Any]]) -> str:
    wiki = wiki_root(root, config)
    path = wiki / "TOPICS.md"
    cards = [entry for entry in entries if entry["type"] == "knowledge-card" and entry["status"] == "current"]
    definitions = configured_topics(config)
    aliases = topic_aliases(config)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in cards:
        for topic in entry.get("topics") or []:
            grouped.setdefault(aliases.get(topic, topic), []).append(entry)
    lines = [
        "# CodeStable 业务主题",
        "",
        "本页只组织当前卡片的链接和导航摘要；卡片正文是结论的唯一来源。",
        "",
    ]
    if not grouped:
        lines.extend(("暂无带业务主题的当前知识卡片。", ""))
    for topic in sorted(grouped):
        definition = definitions.get(topic, {"label": topic, "summary": ""})
        lines.extend((f"## {definition['label']}", ""))
        if definition["summary"]:
            lines.extend((definition["summary"], ""))
        for entry in sorted(grouped[topic], key=lambda item: (item.get("category") or "", item["title"], item["id"])):
            target = root / entry["path"]
            label = CATEGORY_DEFS.get(entry.get("category") or "", {}).get("label", entry.get("category") or "其他")
            lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {label}")
        lines.append("")
    ungrouped = sum(not entry.get("topics") for entry in cards)
    if ungrouped:
        lines.extend(("## 未分主题", "", f"- {ungrouped} 张当前卡片没有主题元数据，仍可通过分类、路径和符号检索。", ""))
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成。")
    lines.append("")
    return "\n".join(lines)


def render_history_index(root: Path, config: dict[str, Any], entries: Sequence[dict[str, Any]]) -> str:
    wiki = wiki_root(root, config)
    path = wiki / "HISTORY.md"
    cards = [
        entry for entry in entries
        if entry["type"] == "knowledge-card" and entry["status"] in {"deprecated", "superseded"}
    ]
    tasks = [
        entry for entry in entries
        if entry["type"] == "task-note" and (entry.get("visibility") == "archived" or entry["status"] == "cancelled")
    ]
    lines = [
        "# CodeStable 历史索引",
        "",
        "这里保留已弃用、被取代和归档记录的链接。原卡片、任务记录、来源和取代关系不会被删除。",
        "",
    ]
    for category in configured_categories(config):
        group = [entry for entry in cards if entry.get("category") == category]
        if not group:
            continue
        label = CATEGORY_DEFS[category]["label"]
        lines.extend((f"## {label}", ""))
        for entry in sorted(group, key=lambda item: (item.get("updated_at") or "", item["id"]), reverse=True):
            target = root / entry["path"]
            relation = []
            if entry.get("supersedes"):
                relation.append("取代 " + ", ".join(f"`{value}`" for value in entry["supersedes"]))
            if entry.get("superseded_by"):
                relation.append("被 " + ", ".join(f"`{value}`" for value in entry["superseded_by"]) + " 取代")
            suffix = " · " + "；".join(relation) if relation else ""
            lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {entry['status']}{suffix}")
        lines.append("")
    if tasks:
        lines.extend(("## 归档与取消任务", ""))
        for entry in sorted(tasks, key=lambda item: (item.get("updated_at") or "", item["id"]), reverse=True):
            target = root / entry["path"]
            relation = f" · 合并到 `{entry['consolidated_into']}`" if entry.get("consolidated_into") else ""
            lines.append(f"- [{entry['title']}]({relative_link(path, target)}) · {entry['status']}{relation}")
        lines.append("")
    if not cards and not tasks:
        lines.extend(("暂无已弃用、被取代或归档的记录。", ""))
    lines.append("本页由 `cs_knowledge.py reindex` 或 `learn` 生成。")
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
        wiki / "TOPICS.md": render_topics_index(root, config, entries),
        wiki / "HISTORY.md": render_history_index(root, config, entries),
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
    updated_card_plan: Sequence[tuple[str, Path, dict[str, Any], str, dict[str, Any]]],
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
    updated_cards = {identifier: (path, metadata, body) for identifier, path, metadata, body, _ in updated_card_plan}
    for identifier, (path, metadata, body) in cards.items():
        if identifier in updated_cards:
            path, projected, body = updated_cards[identifier]
            projected = dict(projected)
        else:
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
        if normalize_space(metadata.get("visibility") or "active") == "archived":
            continue
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
        if item.get("operation") == "update":
            continue
        title = normalize_space(item["title"]).casefold()
        fingerprint = item_fingerprint(item)
        item_tokens = lexical_tokens(f"{item['title']} {item['knowledge']}")
        item_paths = set(item["paths"]) | set(scope_paths(item["scopes"]))
        item_topics = set(item["topics"])
        for identifier, (path, metadata, body) in cards.items():
            if normalize_space(metadata.get("status") or "current") != "current":
                continue
            if normalize_space(metadata.get("category")) != item["category"]:
                continue
            if normalize_space(metadata.get("fingerprint")) == fingerprint:
                continue
            if identifier in item["supersedes"]:
                continue
            same_title = normalize_space(metadata.get("title")).casefold() == title
            existing_tokens = lexical_tokens(
                f"{normalize_space(metadata.get('title'))} {extract_section(body, ('结论',))}"
            )
            union = item_tokens | existing_tokens
            similarity = len(item_tokens & existing_tokens) / len(union) if union else 0.0
            try:
                existing_scopes = normalize_scopes(
                    metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
                )
            except KnowledgeError:
                existing_scopes = []
            existing_paths = set(unique_strings(metadata.get("paths"))) | set(scope_paths(existing_scopes))
            existing_topics = set(unique_strings(metadata.get("topics")))
            scope_related = bool(item_paths & existing_paths) or bool(item_topics & existing_topics) or (
                not item_paths and not existing_paths
            )
            if not same_title and not (similarity >= 0.72 and scope_related):
                continue
            blocking = not item["new_card_reason"]
            candidates.append(
                {
                    "item_title": item["title"],
                    "card_id": identifier,
                    "card_path": path.relative_to(root).as_posix(),
                    "reason": "same-category-and-title" if same_title else "high-conclusion-overlap",
                    "similarity": round(similarity, 3),
                    "blocking": blocking,
                    "action": "reuse or update the existing card; provide new_card_reason only for a genuinely orthogonal conclusion",
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
            "schema_version": 3,
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
    if not isinstance(value, dict) or int(value.get("schema_version", 0) or 0) != 3:
        raise KnowledgeError("unsupported mutation plan token")
    return value

def knowledge_use_entry_key(value: dict[str, Any]) -> str:
    return stable_json(value)


def merge_task_knowledge_use(
    previous: Sequence[dict[str, Any]],
    current: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep historical use evidence immutable while allowing new evidence to append."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in [*previous, *current]:
        if not isinstance(value, dict):
            continue
        key = knowledge_use_entry_key(value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


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
    update_existing = bool(task["update_existing"])
    target_task_id = task["id"] if update_existing else ""
    target_record = tasks.get(target_task_id) if target_task_id else None
    if update_existing and target_record is None:
        raise KnowledgeError(f"task.update_existing references unknown task {target_task_id}")
    if target_record and normalize_space(target_record[1].get("visibility") or "active") == "archived":
        raise KnowledgeError(
            f"task {target_task_id} is archived into {normalize_space(target_record[1].get('consolidated_into'))}; "
            "update the canonical task instead"
        )
    previous_metadata = target_record[1] if target_record else {}
    previous_knowledge_use = [
        value
        for value in (previous_metadata.get("knowledge_use") or [])
        if isinstance(value, dict)
    ]
    previous_knowledge_use_keys = {
        knowledge_use_entry_key(value)
        for value in previous_knowledge_use
    }
    for value in task["knowledge_use"]:
        if value["card_id"] not in cards:
            raise KnowledgeError(f"task.knowledge_use references unknown card {value['card_id']}")
        current_revision = int(cards[value["card_id"]][1].get("revision", 1) or 1)
        historical_entry = knowledge_use_entry_key(value) in previous_knowledge_use_keys
        if value["card_revision"] != current_revision and not historical_entry:
            raise KnowledgeError(
                f"task.knowledge_use card {value['card_id']} revision changed: expected "
                f"{value['card_revision']}, current {current_revision}; run brief again and re-check the evidence"
            )
    if update_existing:
        task["knowledge_use"] = merge_task_knowledge_use(previous_knowledge_use, task["knowledge_use"])
    reference_check = learning_reference_check(root, config, task, items)
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
                "reference_check": reference_check,
            }
    current_revision = 0
    if target_record:
        current_revision = int(target_record[1].get("revision", 1) or 1)
        if task["expected_revision"] != current_revision:
            raise KnowledgeError(
                f"task {target_task_id} revision changed: expected {task['expected_revision']}, current {current_revision}; "
                "read the current task-note and run learn --dry-run again"
            )
    previous_source = previous_metadata.get("source") if isinstance(previous_metadata.get("source"), dict) else {}
    merged_source = {**previous_source, **task["source"]}
    merged_new_task_reason = task["new_task_reason"] or normalize_space(previous_metadata.get("new_task_reason"))
    rendered_task = {**task, "source": merged_source, "new_task_reason": merged_new_task_reason}
    fingerprint_to_id: dict[str, str] = {}
    for identifier, (_, metadata, _) in cards.items():
        fingerprint = normalize_space(metadata.get("fingerprint"))
        status = normalize_space(metadata.get("status") or "current")
        if fingerprint and status != "superseded":
            fingerprint_to_id[fingerprint] = identifier

    for item in items:
        if item["operation"] == "update":
            target = cards.get(item["card_id"])
            if target is None:
                raise KnowledgeError(f"item '{item['title']}' updates unknown card {item['card_id']}")
            _, metadata, body = target
            current_card_revision = int(metadata.get("revision", 1) or 1)
            if item["expected_revision"] != current_card_revision:
                raise KnowledgeError(
                    f"card {item['card_id']} revision changed: expected {item['expected_revision']}, "
                    f"current {current_card_revision}; read the card and run learn --dry-run again"
                )
            if normalize_space(metadata.get("status")) != "current":
                raise KnowledgeError(f"only a current card may be updated in place: {item['card_id']}")
            if normalize_space(metadata.get("category")) != item["category"]:
                raise KnowledgeError("card category cannot change during an in-place update")
            if normalize_space(metadata.get("title")) != item["title"]:
                raise KnowledgeError("card title cannot change during an in-place update")
            if normalize_space(extract_section(body, ("结论",))) != normalize_space(item["knowledge"]):
                raise KnowledgeError("card conclusion cannot change during an in-place update; create a replacement with supersedes")
        for superseded_id in item["supersedes"]:
            if superseded_id not in cards:
                raise KnowledgeError(f"item '{item['title']}' supersedes unknown card {superseded_id}")
            if normalize_space(cards[superseded_id][1].get("status")) == "superseded":
                raise KnowledgeError(f"item '{item['title']}' supersedes already-superseded card {superseded_id}")

    timestamp_text = timestamp.isoformat(timespec="seconds")
    task_id = target_task_id or make_id("T", task_fp, timestamp)
    created_plan: list[tuple[str, Path, dict[str, Any], str, dict[str, Any]]] = []
    updated_card_plan: list[tuple[str, Path, dict[str, Any], str, dict[str, Any]]] = []
    reused_cards: list[str] = []
    new_card_ids: list[str] = []
    supersession_plan: list[tuple[str, str]] = []

    deduplicate = bool((config.get("capture") or {}).get("deduplicate", True)) if isinstance(config.get("capture"), dict) else True
    for sequence, item in enumerate(items, start=1):
        fingerprint = item_fingerprint(item)
        if item["operation"] == "update":
            card_id = item["card_id"]
            path, existing_metadata, _ = cards[card_id]
            metadata = dict(existing_metadata)
            old_scope = {
                "revision": int(metadata.get("revision", 1) or 1),
                "updated_at": normalize_space(metadata.get("updated_at")),
                "task_id": normalize_space(metadata.get("task_id")),
                "scopes": metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [],
                "paths": unique_strings(metadata.get("paths")),
                "symbols": unique_strings(metadata.get("symbols")),
                "topics": unique_strings(metadata.get("topics")),
            }
            new_scope = {
                "scopes": item["scopes"],
                "paths": item["paths"],
                "symbols": item["symbols"],
                "topics": item["topics"],
            }
            scope_history = metadata.get("scope_history") if isinstance(metadata.get("scope_history"), list) else []
            if any(old_scope[key] != new_scope[key] for key in ("scopes", "paths", "symbols", "topics")):
                scope_history = [*scope_history, old_scope]
            metadata.update(
                {
                    "updated_at": timestamp_text,
                    "revision": int(metadata.get("revision", 1) or 1) + 1,
                    "scope_history": scope_history,
                    "updated_by_task_id": task_id,
                    "fingerprint": fingerprint,
                    "confidence": item["confidence"],
                    "pinned": item["pinned"],
                    "tags": item["tags"],
                    "topics": item["topics"],
                    "scopes": item["scopes"],
                    "paths": item["paths"],
                    "symbols": item["symbols"],
                    "future_use": item["future_use"],
                    "evidence": item["evidence"],
                }
            )
            body = render_card_body(item, rendered_task, task_id)
            updated_card_plan.append((card_id, path, metadata, body, item))
            new_card_ids.append(card_id)
            continue
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
            "revision": 1,
            "scope_history": [],
            "task_id": task_id,
            "fingerprint": fingerprint,
            "pinned": item["pinned"],
            "tags": item["tags"],
            "topics": item["topics"],
            "scopes": item["scopes"],
            "paths": item["paths"],
            "symbols": item["symbols"],
            "future_use": item["future_use"],
            "evidence": item["evidence"],
            "supersedes": item["supersedes"],
            "supersession_reason": item["supersession_reason"],
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
        "kind": task["kind"],
        "task_status": task["status"],
        "created_at": normalize_space(previous_metadata.get("created_at")) or timestamp_text,
        "updated_at": timestamp_text,
        "revision": task_revision,
        "visibility": normalize_space(previous_metadata.get("visibility") or "active"),
        "fingerprint": task_fp,
        "tags": task["tags"],
        "topics": task["topics"],
        "scopes": task["scopes"],
        "paths": task["paths"],
        "symbols": task["symbols"],
        "card_ids": all_card_ids,
        "deliverable": task["deliverable"],
        "new_task_reason": merged_new_task_reason,
        "knowledge_summary": task["knowledge_summary"],
        "knowledge_use": task["knowledge_use"],
        "consolidated_from": unique_strings(previous_metadata.get("consolidated_from")),
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

    task_candidates = [] if update_existing else task_similarity_candidates(task, tasks, root)
    requires_new_task_reason = bool(task_candidates and not task["new_task_reason"])
    card_candidates = card_similarity_candidates(items, cards, root)
    requires_new_card_reason = any(value.get("blocking") for value in card_candidates)
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
        "updated_cards": [
            {"id": card_id, "path": path.relative_to(root).as_posix(), "revision": metadata["revision"]}
            for card_id, path, metadata, _, _ in updated_card_plan
        ],
        "reused_cards": reused_cards,
        "superseded_cards": [{"id": old_id, "superseded_by": new_id} for old_id, new_id in supersession_plan],
        "task_candidates": task_candidates,
        "card_candidates": card_candidates,
        "requires_new_task_reason": requires_new_task_reason,
        "requires_new_card_reason": requires_new_card_reason,
        "apply_allowed": not requires_new_task_reason and not requires_new_card_reason,
        "plan_token": generated_plan_token if dry_run and not requires_new_task_reason and not requires_new_card_reason else None,
        "reference_check": reference_check,
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
            updated_card_plan,
            task_path,
            task_metadata,
            task_body,
            supersession_plan,
            timestamp_text,
            replaced_task_id=target_task_id or None,
        )
        return result

    if requires_new_task_reason:
        raise KnowledgeError(
            "a likely continuation task already exists; update it by id/revision or provide task.new_task_reason "
            "explaining the independent goal before applying"
        )
    if requires_new_card_reason:
        raise KnowledgeError(
            "a likely equivalent current card already exists; reuse or update it, or provide item.new_card_reason "
            "explaining the orthogonal long-term conclusion before applying"
        )

    _, current_index_outputs = build_index_outputs(root, config)
    mutation_paths = set(planned_new_paths)
    mutation_paths.update(path for _, path, _, _, _ in updated_card_plan)
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
        for _, path, metadata, body, _ in updated_card_plan:
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


def normalize_consolidation_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("consolidation payload must be a JSON object")
    unknown = set(raw) - {"canonical_task_id", "expected_revision", "duplicates", "reason"}
    if unknown:
        raise KnowledgeError("unknown consolidation fields: " + ", ".join(sorted(unknown)))
    canonical_id = normalize_space(raw.get("canonical_task_id"))
    expected_revision = raw.get("expected_revision")
    reason = normalize_space(raw.get("reason"))
    duplicates_raw = raw.get("duplicates")
    if not re.fullmatch(r"T-[A-Za-z0-9-]+", canonical_id):
        raise KnowledgeError("canonical_task_id must be a T-* identifier")
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
        raise KnowledgeError("expected_revision must be a positive integer")
    if not reason:
        raise KnowledgeError("reason is required")
    if not isinstance(duplicates_raw, list) or not duplicates_raw:
        raise KnowledgeError("duplicates must be a non-empty array")
    duplicates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in duplicates_raw:
        if not isinstance(value, dict) or set(value) - {"id", "expected_revision"}:
            raise KnowledgeError("each duplicate must contain only id and expected_revision")
        identifier = normalize_space(value.get("id"))
        revision = value.get("expected_revision")
        if not re.fullmatch(r"T-[A-Za-z0-9-]+", identifier):
            raise KnowledgeError("duplicate id must be a T-* identifier")
        if identifier == canonical_id:
            raise KnowledgeError("canonical task cannot also be a duplicate")
        if identifier in seen:
            raise KnowledgeError(f"duplicate task listed more than once: {identifier}")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise KnowledgeError(f"duplicate {identifier} expected_revision must be a positive integer")
        seen.add(identifier)
        duplicates.append({"id": identifier, "expected_revision": revision})
    payload = {
        "canonical_task_id": canonical_id,
        "expected_revision": expected_revision,
        "duplicates": duplicates,
        "reason": reason,
    }
    secret = detect_secret(payload)
    if secret:
        raise KnowledgeError(f"consolidation payload appears to contain a {secret}")
    return payload


def render_consolidated_task_body(body: str, duplicate_ids: Sequence[str], reason: str) -> str:
    retained = re.sub(r"\n## 已折叠的历史任务\n.*\Z", "", body.rstrip(), flags=re.DOTALL)
    lines = [retained, "", "## 已折叠的历史任务", "", f"整理理由：{reason}", ""]
    lines.extend(f"- `{identifier}`" for identifier in duplicate_ids)
    return "\n".join(lines) + "\n"


def render_archived_task_body(
    title: str,
    identifier: str,
    canonical_id: str,
    metadata: dict[str, Any],
    original_body: str,
    reason: str,
) -> str:
    verification = extract_section(original_body, ("验证",))
    request = extract_section(original_body, ("请求",))
    result = extract_section(original_body, ("最终结果",))
    source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}
    return f"""# {title}

> 本记录已折叠到逻辑任务 `{canonical_id}`；默认 brief、recent tasks 与根索引不再展示本记录。

## 整理依据

{reason}

## 保留的审计信息

- 原任务 ID：`{identifier}`
- canonical task：`{canonical_id}`
- 原正文 SHA-256：`{sha256_text(original_body)}`
- 关联知识卡片：{', '.join(f'`{value}`' for value in unique_strings(metadata.get('card_ids'))) or '无'}

### 原验证依据

{verification or '- 未记录'}

### 原请求与结果

- 请求：{request or '未记录'}
- 结果：{result or '未记录'}

### 原来源

```json
{json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True)}
```
"""


def _consolidate_locked(
    root: Path,
    config: dict[str, Any],
    raw: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    payload = normalize_consolidation_payload(raw)
    wiki = wiki_root(root, config)
    workspace_before = workspace_state_fingerprint(root)
    state_before = knowledge_state_fingerprint(root, config)
    cards, tasks = scan_existing_records(wiki, configured_categories(config))
    operation_fp = sha256_text(stable_json(payload))
    state_fp = knowledge_state_fingerprint(root, config)
    workspace_fp = workspace_state_fingerprint(root)
    if state_before != state_fp or workspace_before != workspace_fp:
        raise KnowledgeError("project state changed while planning consolidate; retry the command")
    plan: dict[str, Any] | None = None
    if plan_token:
        plan = decode_plan_token(plan_token)
        if normalize_space(plan.get("task_fingerprint")) != operation_fp:
            raise KnowledgeError("consolidate plan token does not match this payload")
        if normalize_space(plan.get("state_fingerprint")) != state_fp:
            raise KnowledgeError("project knowledge changed after consolidate --dry-run; run it again")
        if normalize_space(plan.get("workspace_fingerprint")) != workspace_fp:
            raise KnowledgeError("project workspace changed after consolidate --dry-run; run it again")
        try:
            timestamp = datetime.fromisoformat(normalize_space(plan.get("timestamp")))
        except ValueError as exc:
            raise KnowledgeError("consolidate plan token has an invalid timestamp") from exc
    else:
        timestamp = now_local()
    token = encode_plan_token(operation_fp, state_fp, workspace_fp, timestamp)
    canonical_id = payload["canonical_task_id"]
    canonical = tasks.get(canonical_id)
    if canonical is None:
        raise KnowledgeError(f"unknown canonical task {canonical_id}")
    if normalize_space(canonical[1].get("visibility") or "active") == "archived":
        raise KnowledgeError(f"canonical task {canonical_id} is archived")
    duplicate_ids = [value["id"] for value in payload["duplicates"]]
    duplicate_records: list[tuple[str, Path, dict[str, Any], str]] = []
    already_archived = True
    for value in payload["duplicates"]:
        record = tasks.get(value["id"])
        if record is None:
            raise KnowledgeError(f"unknown duplicate task {value['id']}")
        visibility = normalize_space(record[1].get("visibility") or "active")
        consolidated_into = normalize_space(record[1].get("consolidated_into"))
        if visibility == "archived" and consolidated_into != canonical_id:
            raise KnowledgeError(f"task {value['id']} is already archived into {consolidated_into}")
        if visibility != "archived":
            already_archived = False
        duplicate_records.append((value["id"], record[0], record[1], record[2]))
    consolidated_from = unique_strings(canonical[1].get("consolidated_from"))
    if already_archived and all(identifier in consolidated_from for identifier in duplicate_ids):
        return {
            "ok": True, "idempotent": True, "dry_run": dry_run,
            "canonical_task_id": canonical_id, "archived_task_ids": duplicate_ids,
            "plan_token": token if dry_run else None,
        }
    canonical_revision = int(canonical[1].get("revision", 1) or 1)
    if canonical_revision != payload["expected_revision"]:
        raise KnowledgeError(f"canonical task {canonical_id} revision changed: expected {payload['expected_revision']}, current {canonical_revision}")
    for expected, record in zip(payload["duplicates"], duplicate_records):
        revision = int(record[2].get("revision", 1) or 1)
        if normalize_space(record[2].get("visibility") or "active") != "archived" and revision != expected["expected_revision"]:
            raise KnowledgeError(f"duplicate task {expected['id']} revision changed: expected {expected['expected_revision']}, current {revision}")

    timestamp_text = timestamp.isoformat(timespec="seconds")
    canonical_metadata = dict(canonical[1])
    canonical_metadata["revision"] = canonical_revision + 1
    canonical_metadata["updated_at"] = timestamp_text
    canonical_metadata["visibility"] = "active"
    canonical_metadata["consolidated_from"] = unique_strings([*consolidated_from, *duplicate_ids])
    canonical_metadata["card_ids"] = unique_strings([
        *unique_strings(canonical_metadata.get("card_ids")),
        *(card_id for _, _, metadata, _ in duplicate_records for card_id in unique_strings(metadata.get("card_ids"))),
    ])
    canonical_metadata["consolidation_fingerprint"] = operation_fp
    canonical_body = render_consolidated_task_body(canonical[2], canonical_metadata["consolidated_from"], payload["reason"])
    mutations: list[tuple[Path, dict[str, Any], str]] = [(canonical[0], canonical_metadata, canonical_body)]
    for identifier, path, metadata, body in duplicate_records:
        archived_metadata = dict(metadata)
        archived_metadata["updated_at"] = timestamp_text
        archived_metadata["revision"] = int(metadata.get("revision", 1) or 1) + 1
        archived_metadata["visibility"] = "archived"
        archived_metadata["consolidated_into"] = canonical_id
        archived_metadata["consolidation_fingerprint"] = operation_fp
        archived_body = render_archived_task_body(
            normalize_space(metadata.get("title")) or identifier,
            identifier, canonical_id, metadata, body, payload["reason"],
        )
        mutations.append((path, archived_metadata, archived_body))

    projected_entries = []
    mutation_by_path = {path: (metadata, body) for path, metadata, body in mutations}
    for entry in collect_index_entries(root, config):
        path = root / entry["path"]
        if path in mutation_by_path:
            metadata, body = mutation_by_path[path]
            projected_entries.append(index_entry_for(path, root, metadata, body, render_front_matter(metadata, body)))
        else:
            projected_entries.append(entry)
    projected_entries.sort(key=lambda item: (0 if item["type"] == "knowledge-card" else 1, item.get("category") or "", item.get("created_at") or "", item.get("id") or ""))
    projected_outputs = render_index_outputs(root, config, projected_entries)
    changed_indexes = [
        path.relative_to(root).as_posix()
        for path, content in projected_outputs.items()
        if (path.read_text(encoding="utf-8") if path.is_file() else None) != content
    ]
    result = {
        "ok": True, "idempotent": False, "dry_run": dry_run,
        "canonical_task_id": canonical_id,
        "canonical_revision": canonical_metadata["revision"],
        "archived_task_ids": duplicate_ids,
        "changed_task_notes": [path.relative_to(root).as_posix() for path, _, _ in mutations],
        "index": {"entries": len(projected_entries), "changed": changed_indexes, "dry_run": dry_run},
        "plan_token": token if dry_run else None,
    }
    if dry_run:
        return result

    current_outputs = build_index_outputs(root, config)[1]
    mutation_paths = {path for path, _, _ in mutations} | set(current_outputs)
    snapshot = {path: path.read_text(encoding="utf-8") if path.is_file() else None for path in mutation_paths}
    transaction = create_recovery_journal(root, wiki, f"C-{operation_fp[:16]}", snapshot)
    try:
        for path, metadata, body in mutations:
            atomic_write_text(path, render_front_matter(metadata, body))
        result["index"] = rebuild_indexes(root, config, dry_run=False)
        atomic_write_text(transaction / "COMMITTED", "committed\n")
    except Exception:
        restore_snapshot(snapshot, wiki)
        remove_recovery_journal(transaction)
        raise
    remove_recovery_journal(transaction)
    return result


def consolidate(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if dry_run:
        if plan_token:
            raise KnowledgeError("plan_token is only valid when applying consolidate")
        return _consolidate_locked(root, config, payload, dry_run=True)
    wiki = wiki_root(root, config)
    lock = acquire_lock(root, wiki)
    try:
        return _consolidate_locked(root, config, payload, dry_run=False, plan_token=plan_token)
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


def conclusion_similarity(left: str, right: str) -> float:
    """Return deterministic lexical overlap for two non-empty conclusions."""
    left_tokens = lexical_tokens(normalize_space(left))
    right_tokens = lexical_tokens(normalize_space(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


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


def collect_search_documents(
    root: Path,
    config: dict[str, Any],
    include_history: bool,
    include_legacy: bool = False,
) -> tuple[list[SearchDocument], list[str]]:
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
                    status="navigation",
                    confidence="not-applicable",
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
                        status="navigation",
                        confidence="not-applicable",
                        content_hash=sha256_text(content),
                    )
                )

    for path in card_paths(wiki, categories):
        try:
            metadata, body, _ = read_markdown(path)
        except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
            warnings.append(f"cannot read card {path.relative_to(root).as_posix()}: {exc}")
            continue
        status = normalize_space(metadata.get("status") or "current")
        if status in {"deprecated", "superseded"} and not include_history:
            continue
        raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            scopes = normalize_scopes(raw_scopes)
        except KnowledgeError as exc:
            warnings.append(f"invalid scopes on card {path.relative_to(root).as_posix()}: {exc}")
            scopes = []
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
                topics=tuple(unique_strings(metadata.get("topics"))),
                scopes=tuple(scope_tuple(value) for value in scopes),
                paths=tuple(unique_strings([*unique_strings(metadata.get("paths")), *scope_paths(scopes)])),
                symbols=tuple(unique_strings([*unique_strings(metadata.get("symbols")), *scope_symbols(scopes)])),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
                revision=safe_int(metadata.get("revision"), 1, minimum=0),
                content_hash=sha256_text(normalize_space(extract_section(body, ("结论",)) or body)),
                pinned=bool(metadata.get("pinned", False)),
            )
        )

    for path in task_note_paths(wiki):
        try:
            metadata, body, _ = read_markdown(path)
        except (OSError, UnicodeDecodeError, KnowledgeError) as exc:
            warnings.append(f"cannot read task note {path.relative_to(root).as_posix()}: {exc}")
            continue
        if normalize_space(metadata.get("visibility") or "active") == "archived":
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
        raw_task_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            task_scopes = normalize_scopes(raw_task_scopes)
        except KnowledgeError as exc:
            warnings.append(f"invalid scopes on task note {path.relative_to(root).as_posix()}: {exc}")
            task_scopes = []
        documents.append(
            SearchDocument(
                source_type="task-note",
                source_path=path.relative_to(root).as_posix(),
                title=normalize_space(metadata.get("title")) or extract_heading(body, path.stem),
                content=content or body,
                identifier=normalize_space(metadata.get("id")) or None,
                status=normalize_space(metadata.get("task_status") or "completed"),
                tags=tuple(unique_strings(metadata.get("tags"))),
                topics=tuple(unique_strings(metadata.get("topics"))),
                scopes=tuple(scope_tuple(value) for value in task_scopes),
                paths=tuple(unique_strings(metadata.get("paths"))),
                symbols=tuple(unique_strings(metadata.get("symbols"))),
                created_at=normalize_space(metadata.get("created_at")),
                updated_at=normalize_space(metadata.get("updated_at")),
            )
        )

    if include_legacy:
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


def parse_scope_argument(value: str) -> dict[str, str]:
    text = normalize_space(value)
    if ":" not in text:
        raise KnowledgeError("brief --scope must use <repository>:<path>#<symbol>")
    repository, remainder = text.split(":", 1)
    if "#" in remainder:
        path, symbol = remainder.split("#", 1)
    else:
        path, symbol = remainder, ""
    scopes = normalize_scopes([{"repository": repository, "path": path, "symbol": symbol}])
    return scopes[0]


def score_document_details(
    document: SearchDocument,
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    topics: Sequence[str] = (),
    scopes: Sequence[dict[str, str]] = (),
) -> MatchDetails:
    query_text = " ".join((task, *paths, *symbols, *topics))
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
    reasons: list[tuple[str, str, str]] = []
    precedence = 0
    exact_path_match = False
    hierarchical_path_match = False
    for query_path in paths:
        normalized_query = query_path.strip("./")
        exact_candidates = [value for value in document.paths if normalized_query == value.strip("./")]
        hierarchy_candidates = [
            value for value in document.paths
            if normalized_query != value.strip("./") and scope_path_match(query_path, value)
        ]
        if exact_candidates:
            score += 24.0
            exact_path_match = True
            precedence = max(precedence, 6)
            reasons.append(("exact-path", query_path, exact_candidates[0]))
        elif hierarchy_candidates:
            score += 16.0
            hierarchical_path_match = True
            precedence = max(precedence, 5)
            reasons.append(("path-hierarchy", query_path, hierarchy_candidates[0]))
        elif scope_path_match(query_path, document.source_path):
            score += 10.0
            hierarchical_path_match = True
            precedence = max(precedence, 5)
            reasons.append(("source-path-hierarchy", query_path, document.source_path))
    lowered_symbols = {symbol.lower() for symbol in symbols}
    matched_symbols = lowered_symbols & {symbol.lower() for symbol in document.symbols}
    exact_symbol_match = bool(matched_symbols)
    if exact_symbol_match:
        score += 24.0
        precedence = max(precedence, 6)
        matched = sorted(matched_symbols)[0]
        original = next(value for value in document.symbols if value.lower() == matched)
        reasons.append(("exact-symbol", original, original))
    matched_topics = set(topics) & set(document.topics)
    exact_topic_match = bool(matched_topics)
    if exact_topic_match:
        score += 18.0
        precedence = max(precedence, 4)
        topic = sorted(matched_topics)[0]
        reasons.append(("topic", topic, topic))
    exact_scope_match = False
    hierarchical_scope_match = False
    document_scopes = set(document.scopes)
    for scope in scopes:
        repository, path, symbol = scope_tuple(scope)
        for candidate_repository, candidate_path, candidate_symbol in document_scopes:
            if repository != candidate_repository:
                continue
            path_exact = not path or path.strip("./") == candidate_path.strip("./")
            path_matches = not path or scope_path_match(path, candidate_path)
            symbol_matches = not symbol or symbol.casefold() == candidate_symbol.casefold()
            if path_exact and symbol_matches:
                exact_scope_match = True
                score += 30.0
                precedence = max(precedence, 6)
                query_value = f"{repository}:{path}#{symbol}".rstrip("#")
                matched_value = f"{candidate_repository}:{candidate_path}#{candidate_symbol}".rstrip("#")
                reasons.append(("exact-scope", query_value, matched_value))
                break
            if path_matches and symbol_matches:
                hierarchical_scope_match = True
                score += 20.0
                precedence = max(precedence, 5)
                query_value = f"{repository}:{path}#{symbol}".rstrip("#")
                matched_value = f"{candidate_repository}:{candidate_path}#{candidate_symbol}".rstrip("#")
                reasons.append(("scope-hierarchy", query_value, matched_value))
                break
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
    if title_overlap:
        precedence = max(precedence, 3)
        reasons.append(("title-text", " ".join(sorted(title_overlap)), document.title))
    if tag_overlap:
        precedence = max(precedence, 3)
        reasons.append(("tag", " ".join(sorted(tag_overlap)), " ".join(document.tags)))
    if symbol_overlap and not exact_symbol_match:
        precedence = max(precedence, 3)
        reasons.append(("symbol-text", " ".join(sorted(symbol_overlap)), " ".join(document.symbols)))
    if meaningful_path_overlap and not (exact_path_match or hierarchical_path_match):
        precedence = max(precedence, 3)
        reasons.append(("path-text", " ".join(sorted(meaningful_path_overlap)), " ".join(document.paths)))
    if len(content_overlap) >= 2:
        precedence = max(precedence, 2)
        reasons.append(("body-text", " ".join(sorted(content_overlap)), ""))
    if document.pinned and precedence == 0:
        precedence = 1
        reasons.append(("pinned", "", ""))
    qualifies = bool(
        document.pinned
        or exact_path_match
        or hierarchical_path_match
        or exact_symbol_match
        or exact_topic_match
        or exact_scope_match
        or hierarchical_scope_match
        or title_overlap
        or tag_overlap
        or symbol_overlap
        or meaningful_path_overlap
        or len(content_overlap) >= 2
    )
    return MatchDetails(
        score=score,
        qualifies=qualifies,
        precedence=precedence,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def score_document(
    document: SearchDocument,
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    topics: Sequence[str] = (),
    scopes: Sequence[dict[str, str]] = (),
) -> float:
    return score_document_details(document, task, paths, symbols, topics, scopes).score


def selected_brief_payload(
    root: Path,
    config: dict[str, Any],
    task: str,
    paths: Sequence[str],
    symbols: Sequence[str],
    limit_override: int | None,
    include_history: bool,
    topics: Sequence[str] = (),
    scopes: Sequence[dict[str, str]] = (),
    include_legacy: bool = False,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    documents, warnings = collect_search_documents(root, config, include_history, include_legacy)
    brief_config = config.get("brief") if isinstance(config.get("brief"), dict) else {}
    max_items = limit_override or safe_int(brief_config.get("max_items"), 18, minimum=1, maximum=100)
    per_category = safe_int(brief_config.get("max_items_per_category"), 3, minimum=1, maximum=20)
    summary_limit = safe_int(brief_config.get("max_summaries"), 3, minimum=1, maximum=11)
    related_limit = safe_int(brief_config.get("max_related_tasks"), 3, minimum=1, maximum=20)
    excerpt_limit = safe_int(brief_config.get("max_excerpt_chars"), 700, minimum=120, maximum=5000)
    recent_decisions = safe_int(brief_config.get("include_recent_decisions"), 2, minimum=1, maximum=10)

    overview = [document for document in documents if document.source_type == "project-overview"]
    primary_docs = [
        document
        for document in documents
        if document.source_type == "knowledge-card"
    ]
    summary_docs = [document for document in documents if document.source_type == "canonical-page"]
    legacy_docs = [document for document in documents if document.source_type == "legacy-page"]
    task_docs = [document for document in documents if document.source_type == "task-note"]
    scored = []
    primary_matches: dict[str, MatchDetails] = {}
    for document in primary_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        primary_matches[document.source_path] = match
        if match.qualifies:
            scored.append((match, document))
    scored.sort(
        key=lambda pair: (
            pair[0].precedence,
            pair[0].score,
            pair[1].pinned,
            pair[1].updated_at or pair[1].created_at,
            pair[1].identifier or pair[1].source_path,
        ),
        reverse=True,
    )

    summary_scored: list[tuple[MatchDetails, SearchDocument]] = []
    for document in summary_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        if match.qualifies:
            summary_scored.append((match, document))
    summary_scored.sort(
        key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].category or ""),
        reverse=True,
    )
    selected_summaries = summary_scored[:summary_limit]

    selected: list[tuple[MatchDetails, SearchDocument]] = []
    per_category_counts: dict[str, int] = {}
    selected_paths: set[str] = set()
    for match, document in [pair for pair in scored if pair[1].status in {"current", "proposed"}]:
        category = document.category or "uncategorized"
        if per_category_counts.get(category, 0) >= per_category:
            continue
        selected.append((match, document))
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
            and primary_matches[document.source_path].qualifies
        ],
        key=lambda document: document.updated_at or document.created_at,
        reverse=True,
    )
    for document in decision_docs[:recent_decisions]:
        if len(selected) >= max_items:
            break
        selected.append((score_document_details(document, task, paths, symbols, topics, scopes), document))
        selected_paths.add(document.source_path)

    related_candidates: list[tuple[MatchDetails, SearchDocument]] = []
    for document in task_docs:
        match = score_document_details(document, task, paths, symbols, topics, scopes)
        if match.qualifies:
            related_candidates.append((match, document))
    related = sorted(
        related_candidates,
        key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].updated_at or pair[1].created_at),
        reverse=True,
    )[:related_limit]

    def is_current_knowledge(document: SearchDocument) -> bool:
        return document.source_type == "knowledge-card" and document.status == "current"

    legacy_selected: list[tuple[MatchDetails, SearchDocument]] = []
    if include_legacy:
        legacy_scored = []
        for document in legacy_docs:
            match = score_document_details(document, task, paths, symbols, topics, scopes)
            if match.qualifies:
                legacy_scored.append((match, document))
        legacy_scored.sort(
            key=lambda pair: (pair[0].precedence, pair[0].score, pair[1].updated_at or pair[1].created_at),
            reverse=True,
        )
        legacy_category_counts: dict[str, int] = {}
        for match, document in legacy_scored:
            category = document.category or "uncategorized"
            if legacy_category_counts.get(category, 0) >= per_category:
                continue
            legacy_selected.append((match, document))
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

    def serialize(document: SearchDocument, match: MatchDetails | None = None) -> dict[str, Any]:
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
            "topics": list(document.topics),
            "scopes": [
                {"repository": repository, "path": path, "symbol": symbol}
                for repository, path, symbol in document.scopes
            ],
        }
        if document.revision:
            value["revision"] = document.revision
        if document.content_hash:
            value["content_hash"] = document.content_hash
        if match is not None:
            value["score"] = round(match.score, 3)
            value["match_precedence"] = match.precedence
            value["match_reasons"] = [
                {"kind": kind, "query": query, "matched": matched}
                for kind, query, matched in match.reasons
            ]
        return value

    current_selected = [(score, document) for score, document in selected if document.status == "current"]
    proposed_selected = [(score, document) for score, document in selected if document.status == "proposed"]
    history_selected = [
        (match, document) for match, document in scored
        if include_history and document.status in {"deprecated", "superseded"}
    ][:max_items]
    displayed_cards = [
        {
            "id": document.identifier,
            "revision": document.revision,
            "status": document.status,
            "source": document.source_path,
            "content_hash": document.content_hash,
        }
        for _, document in [*current_selected, *proposed_selected, *history_selected]
        if document.identifier
    ]
    generated_at = now_iso()
    receipt_core = {
        "task": task,
        "paths": list(paths),
        "symbols": list(symbols),
        "topics": list(topics),
        "scopes": list(scopes),
        "include_history": include_history,
        "knowledge_state": knowledge_state_fingerprint(root, config),
        "generated_at": generated_at,
        "displayed_cards": displayed_cards,
    }
    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "task": task,
        "paths": list(paths),
        "symbols": list(symbols),
        "topics": list(topics),
        "scopes": list(scopes),
        "generated_at": generated_at,
        "receipt": {
            "kind": "brief-display",
            "claim": "displayed-only",
            "receipt_id": sha256_text(stable_json(receipt_core)),
            **receipt_core,
        },
        "project_overview": [serialize(document) for document in overview],
        "category_summaries": [serialize(document, match) for match, document in selected_summaries],
        "knowledge": [serialize(document, match) for match, document in current_selected],
        "proposed_knowledge": [serialize(document, match) for match, document in proposed_selected],
        "history": [serialize(document, match) for match, document in history_selected],
        "legacy_clues": [serialize(document, match) for match, document in legacy_selected],
        "related_tasks": [serialize(document, match) for match, document in related],
        "coverage": coverage,
        "gaps": gaps,
        "conflicts": conflicts,
        "warnings": warnings,
        "read_only": True,
    }


def attach_brief_topic_resolution(payload: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    """Attach optional-topic diagnostics while preserving a receipt for the actual query."""
    payload["requested_topics"] = list(resolution.get("requested") or [])
    payload["ignored_topics"] = list(resolution.get("unknown") or [])
    payload["topic_resolution"] = resolution
    payload["warnings"] = [
        *(warning.get("detail") or str(warning) for warning in resolution.get("warnings") or []),
        *(payload.get("warnings") or []),
    ]
    receipt = payload.get("receipt")
    if isinstance(receipt, dict):
        receipt["requested_topics"] = list(resolution.get("requested") or [])
        receipt["ignored_topics"] = list(resolution.get("unknown") or [])
        receipt_core = {
            key: value
            for key, value in receipt.items()
            if key not in {"kind", "claim", "receipt_id"}
        }
        receipt["receipt_id"] = sha256_text(stable_json(receipt_core))
    return payload


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
    if payload["topics"]:
        lines.append(f"**业务主题**：{', '.join(payload['topics'])}")
    if payload.get("ignored_topics"):
        lines.append(f"**已忽略的未知主题**：{', '.join(payload['ignored_topics'])}")
    if payload["scopes"]:
        lines.append(f"**结构化范围**：{json.dumps(payload['scopes'], ensure_ascii=False)}")
    topic_warnings = (payload.get("topic_resolution") or {}).get("warnings") or []
    if topic_warnings:
        lines.extend(("", "## 主题提示", ""))
        for warning in topic_warnings:
            suggestions = warning.get("suggestions") or []
            suffix = ""
            if suggestions:
                suffix = "；近似主题：" + "、".join(f"`{item['name']}`" for item in suggestions)
            lines.append(f"- `{warning['topic']}` 不存在，已忽略并继续检索{suffix}。")
        lines.append("- 不确定主题名时请省略 `--topic`，或先运行 `topics list`。")
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

    if payload.get("category_summaries"):
        lines.extend(("## 相关分类摘要（不占卡片配额）", ""))
        for item in payload["category_summaries"]:
            reasons = ", ".join(reason["kind"] for reason in item.get("match_reasons", [])) or "summary"
            lines.append(f"- **{item['title']}**：{item['excerpt']}（匹配：`{reasons}`；来源 `{item['source']}`）")
        lines.append("")

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
            if item.get("match_reasons"):
                metadata.append("matches " + ", ".join(reason["kind"] for reason in item["match_reasons"]))
            lines.append("- " + " · ".join(metadata))
            lines.append("")
    if "uncategorized" in grouped:
        lines.extend(("### 其他来源", ""))
        for item in grouped["uncategorized"]:
            lines.append(f"- **{item['title']}**：{item['excerpt']}（`{item['source']}`）")
        lines.append("")

    if payload["proposed_knowledge"]:
        lines.extend(("## 相关提议（不能视为当前约束）", ""))
        for item in payload["proposed_knowledge"]:
            lines.append(f"- **{item['title']}** · `{item['id']}` · {item['excerpt']} · 来源 `{item['source']}`")
        lines.append("")

    if payload["history"]:
        lines.extend(("## 显式历史结果", ""))
        lines.append("以下内容仅因本次启用了历史检索而返回，不属于当前知识。")
        lines.append("")
        for item in payload["history"]:
            lines.append(f"- **{item['title']}** · `{item['id']}` · {item['status']} · 来源 `{item['source']}`")
        lines.append("")

    if payload["legacy_clues"]:
        lines.extend(("## Legacy 线索（需核验）", ""))
        lines.append("以下旧页只因显式启用旧资料检索而返回；它们只用于迁移或历史调查，不代表当前事实，也不计入知识覆盖。")
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
            lines.append(f"- **{item['title']}**{identifier} · {item['status']}")
            lines.append(f"  - {item['excerpt']}")
            lines.append(f"  - 来源：`{item['source']}`")
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
    receipt = payload.get("receipt") or {}
    if receipt:
        lines.extend(
            (
                "",
                "## 只读回执",
                "",
                f"- 回执：`{receipt.get('receipt_id', '')}`",
                "- 声明：只证明这些卡片在本次查询中被展示，不证明它们影响了设计、实现、测试或评审。",
            )
        )
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
    card_ids: Sequence[str] = (),
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    rename_map = {change.old_path: change.new_path for change in changes if change.status.startswith("R")}
    deleted = {change.old_path for change in changes if change.status == "D"}
    findings: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    historical_skipped: list[dict[str, Any]] = []
    repositories = configured_repositories(root, config)
    scan_limit = safe_int((config.get("wiki") or {}).get("max_scan_files"), 2000, minimum=1, maximum=20_000)
    for card_id, (_, metadata, _) in sorted(cards.items()):
        if card_ids and card_id not in card_ids:
            continue
        status = normalize_space(metadata.get("status"))
        if status != "current":
            historical_skipped.append(
                {
                    "card_id": card_id,
                    "issue_type": "historical-card-skipped",
                    "status": status,
                    "disposition": "non-blocking",
                    "detail": "historical cards do not participate in current-reference blocking",
                }
            )
            continue
        common = {
            "card_id": card_id,
            "category": normalize_space(metadata.get("category")),
            "title": normalize_space(metadata.get("title")),
        }
        repository_paths: list[Path] = []
        raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            scopes = normalize_scopes(raw_scopes)
        except KnowledgeError as exc:
            unverified.append(
                {
                    **common,
                    "issue_type": "scope-invalid",
                    "certainty": "unverified",
                    "detail": str(exc),
                    "suggested_action": "repair the structured scope before relying on reference validation",
                }
            )
            scopes = []
        for scope in scopes:
            repository = scope["repository"]
            scoped_path = scope["path"]
            symbol = scope["symbol"]
            repository_root = repositories.get(repository)
            if repository_root is None:
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unconfigured",
                        "repository": repository,
                        "value": scoped_path or symbol,
                        "certainty": "unverified",
                        "suggested_action": f"configure wiki.repositories.{repository}.root to enable validation",
                    }
                )
                continue
            if not repository_root.is_dir():
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unavailable",
                        "repository": repository,
                        "value": scoped_path or symbol,
                        "certainty": "unverified",
                        "suggested_action": "make the configured repository available or correct its local mapping",
                    }
                )
                continue
            resolved = repository_root / scoped_path if scoped_path else repository_root
            relative = scoped_path
            if repository == "self" and relative in rename_map:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-renamed",
                        "repository": repository,
                        "value": relative,
                        "renamed_to": rename_map[relative],
                        "certainty": "likely",
                        "suggested_action": "review the unchanged conclusion and update its scope, or supersede it only if the conclusion changed",
                    }
                )
                continue
            if repository == "self" and relative in deleted:
                findings.append(
                    {
                        **common,
                        "issue_type": "path-deleted",
                        "repository": repository,
                        "value": relative,
                        "certainty": "confirmed",
                        "suggested_action": "review the conclusion and update its scope or supersede it after semantic review",
                    }
                )
                continue
            if scoped_path and not resolved.exists():
                findings.append(
                    {
                        **common,
                        "issue_type": "path-missing",
                        "repository": repository,
                        "value": scoped_path,
                        "certainty": "confirmed",
                        "suggested_action": "locate the replacement implementation and update scope, or supersede the card only if its conclusion changed",
                    }
                )
                continue
            if scoped_path:
                repository_paths.append(resolved)
                verified.append(
                    {
                        **common,
                        "issue_type": "path-verified",
                        "repository": repository,
                        "value": scoped_path,
                        "reference_format": "structured",
                    }
                )
            if symbol:
                files = candidate_source_files(repository_root, [resolved] if scoped_path else [], scan_limit)
                present, checked = symbol_present(symbol, files)
                if present:
                    verified.append(
                        {**common, "issue_type": "symbol-verified", "repository": repository, "value": symbol}
                    )
                else:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable" if not checked else "symbol-text-not-found",
                            "repository": repository,
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                            "suggested_action": "review the implementation or rename; text scanning alone cannot prove the knowledge wrong",
                        }
                    )
        legacy_path_values = unique_strings(metadata.get("paths"))
        for raw_path in legacy_path_values:
            policy, resolved = reference_path_policy(root, raw_path)
            if policy != "repository":
                unverified.append(
                    {
                        **common,
                        "issue_type": "legacy-reference-unverified",
                        "value": raw_path,
                        "policy": policy,
                        "certainty": "unverified",
                        "reference_format": "legacy",
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
                        "issue_type": "path-deleted",
                        "value": relative,
                        "certainty": "confirmed",
                        "suggested_action": "review whether the conclusion still applies elsewhere; update or supersede the current card",
                    }
                )
            elif not resolved.exists():
                findings.append(
                    {
                        **common,
                        "issue_type": "path-missing",
                        "value": relative,
                        "certainty": "confirmed",
                        "suggested_action": "locate the replacement implementation and update scope, or supersede the card after semantic review",
                    }
                )
            else:
                repository_paths.append(resolved)
                verified.append(
                    {
                        **common,
                        "issue_type": "path-verified",
                        "repository": "self",
                        "value": relative,
                        "reference_format": "legacy-relative",
                    }
                )
        symbols = unique_strings(metadata.get("symbols"))
        if symbols:
            files = (
                candidate_source_files(root, repository_paths, scan_limit)
                if repository_paths or not legacy_path_values
                else []
            )
            for symbol in symbols:
                present, checked = symbol_present(symbol, files)
                if not checked:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable",
                            "value": symbol,
                            "policy": "no-readable-source",
                            "suggested_action": "provide a repository path for deterministic symbol checking",
                        }
                    )
                elif not present:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-text-not-found",
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                            "suggested_action": "review rename/removal and update or supersede the card; text scanning is only a drift candidate",
                        }
                    )
                else:
                    verified.append(
                        {**common, "issue_type": "symbol-verified", "repository": "self", "value": symbol}
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
        scoped = []
        for _, metadata in group:
            values = set(unique_strings(metadata.get("paths")))
            try:
                values.update(
                    f"{scope['repository']}:{scope['path']}"
                    for scope in normalize_scopes(metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [])
                    if scope["path"]
                )
            except KnowledgeError:
                pass
            scoped.append(values)
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
    skipped.extend(unverified)
    skipped.extend(historical_skipped)
    return {
        "findings": findings,
        "unverified": unverified,
        "verified": verified,
        "skipped": skipped,
        "historical_cards_skipped": historical_skipped,
        "checked_current_cards": sum(
            1 for identifier, (_, metadata, _) in cards.items()
            if normalize_space(metadata.get("status")) == "current" and (not card_ids or identifier in card_ids)
        ),
    }


def learning_reference_check(
    root: Path,
    config: dict[str, Any],
    task: dict[str, Any],
    items: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    repositories = configured_repositories(root, config)
    scan_limit = safe_int((config.get("wiki") or {}).get("max_scan_files"), 2000, minimum=1, maximum=20_000)
    findings: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    verified: list[dict[str, Any]] = []
    task_deleted_paths: set[str] = set()
    task_renamed_paths: dict[str, str] = {}
    try:
        task_changes, _, _ = git_changes(root, cached=False, base=None)
        task_deleted_paths = {change.old_path for change in task_changes if change.status == "D"}
        task_renamed_paths = {
            change.old_path: change.new_path
            for change in task_changes
            if change.status.startswith("R")
        }
    except KnowledgeError:
        pass
    records = [
        {
            "record_type": "task",
            "title": task["title"],
            "scopes": task["scopes"],
            "paths": task["paths"],
            "symbols": task["symbols"],
        },
        *[
            {
                "record_type": "planned-card",
                "title": item["title"],
                "scopes": item["scopes"],
                "paths": item["paths"],
                "symbols": item["symbols"],
            }
            for item in items
        ],
    ]
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        common = {"record_type": record["record_type"], "title": record["title"]}
        checked_files: list[Path] = []
        for scope in record["scopes"]:
            repository = scope["repository"]
            path = scope["path"]
            symbol = scope["symbol"]
            key = (record["record_type"], repository, path, symbol)
            if key in seen:
                continue
            seen.add(key)
            repository_root = repositories.get(repository)
            if repository_root is None:
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unconfigured",
                        "repository": repository,
                        "value": path or symbol,
                        "certainty": "unverified",
                    }
                )
                continue
            if not repository_root.is_dir():
                unverified.append(
                    {
                        **common,
                        "issue_type": "repository-unavailable",
                        "repository": repository,
                        "value": path or symbol,
                        "certainty": "unverified",
                    }
                )
                continue
            resolved = repository_root / path if path else repository_root
            if path and not resolved.exists():
                if record["record_type"] == "task" and repository == "self" and path in task_deleted_paths:
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-deletion-verified",
                            "repository": repository,
                            "value": path,
                            "change_status": "deleted",
                        }
                    )
                    continue
                if record["record_type"] == "task" and repository == "self" and path in task_renamed_paths:
                    renamed_to = task_renamed_paths[path]
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-rename-verified",
                            "repository": repository,
                            "value": path,
                            "renamed_to": renamed_to,
                            "change_status": "renamed",
                        }
                    )
                    resolved = repository_root / renamed_to
                else:
                    findings.append(
                        {
                            **common,
                            "issue_type": "path-missing",
                            "repository": repository,
                            "value": path,
                            "certainty": "confirmed",
                            "suggested_action": "review this task or card scope before relying on it",
                        }
                    )
                    continue
            if path:
                checked_files.append(resolved)
                if path not in task_renamed_paths or record["record_type"] != "task" or repository != "self":
                    verified.append({**common, "issue_type": "path-verified", "repository": repository, "value": path})
            if symbol:
                files = candidate_source_files(repository_root, [resolved] if path else [], scan_limit)
                present, checked = symbol_present(symbol, files)
                if present:
                    verified.append({**common, "issue_type": "symbol-verified", "repository": repository, "value": symbol})
                else:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable" if not checked else "symbol-text-not-found",
                            "repository": repository,
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                        }
                    )
        legacy_paths: list[Path] = []
        for value in record["paths"]:
            policy, resolved = reference_path_policy(root, value)
            if policy != "repository":
                unverified.append(
                    {
                        **common,
                        "issue_type": "legacy-reference-unverified",
                        "value": value,
                        "policy": policy,
                        "certainty": "unverified",
                    }
                )
            elif resolved is not None and resolved.exists():
                legacy_paths.append(resolved)
                verified.append(
                    {
                        **common,
                        "issue_type": "path-verified",
                        "repository": "self",
                        "value": resolved.relative_to(root).as_posix(),
                        "reference_format": "legacy-relative",
                    }
                )
            elif resolved is not None:
                relative = resolved.relative_to(root).as_posix()
                if record["record_type"] == "task" and relative in task_deleted_paths:
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-deletion-verified",
                            "repository": "self",
                            "value": relative,
                            "change_status": "deleted",
                            "reference_format": "legacy-relative",
                        }
                    )
                elif record["record_type"] == "task" and relative in task_renamed_paths:
                    renamed_to = task_renamed_paths[relative]
                    renamed_path = root / renamed_to
                    legacy_paths.append(renamed_path)
                    verified.append(
                        {
                            **common,
                            "issue_type": "path-rename-verified",
                            "repository": "self",
                            "value": relative,
                            "renamed_to": renamed_to,
                            "change_status": "renamed",
                            "reference_format": "legacy-relative",
                        }
                    )
                else:
                    findings.append(
                        {
                            **common,
                            "issue_type": "path-missing",
                            "repository": "self",
                            "value": relative,
                            "certainty": "confirmed",
                        }
                    )
        if record["symbols"]:
            files = (
                candidate_source_files(root, legacy_paths, scan_limit)
                if legacy_paths or not record["paths"]
                else []
            )
            for symbol in record["symbols"]:
                present, checked = symbol_present(symbol, files)
                if present:
                    verified.append({**common, "issue_type": "symbol-verified", "repository": "self", "value": symbol})
                else:
                    unverified.append(
                        {
                            **common,
                            "issue_type": "symbol-check-unavailable" if not checked else "symbol-text-not-found",
                            "repository": "self",
                            "value": symbol,
                            "certainty": "unverified",
                            "method": "bounded-text-scan",
                        }
                    )
    used_cards = current_reference_drift(
        root,
        config,
        card_ids=[value["card_id"] for value in task["knowledge_use"]],
    ) if task["knowledge_use"] else {"findings": [], "unverified": [], "verified": [], "historical_cards_skipped": []}
    findings.extend(used_cards["findings"])
    unverified.extend(used_cards["unverified"])
    verified.extend(used_cards["verified"])
    return {
        "blocking": False,
        "review_required": bool(findings or unverified),
        "findings": findings,
        "unverified": unverified,
        "verified": verified,
        "historical_cards_skipped": used_cards["historical_cards_skipped"],
    }


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


def task_note_scope_paths(metadata: dict[str, Any]) -> list[str]:
    values = list(unique_strings(metadata.get("paths")))
    raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
    try:
        values.extend(
            scope["path"]
            for scope in normalize_scopes(raw_scopes)
            if scope["repository"] == "self" and scope["path"]
        )
    except KnowledgeError:
        pass
    return unique_strings(values)


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
        scopes = task_note_scope_paths(metadata)
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
        scopes = task_note_scope_paths(metadata)
        symbol_overlap = any(symbol and symbol in patch for symbol in unique_strings(metadata.get("symbols")))
        if coverage == 0 and not symbol_overlap:
            findings.append(
                {
                    **common,
                    "issue_type": "task-scope-mismatch",
                    "value": ", ".join(primary_paths),
                    "suggested_action": "record at least one representative task path, structured self scope, or changed symbol",
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
        "unverified_references": references["unverified"],
        "verified_references": references["verified"],
        "historical_cards_skipped": references["historical_cards_skipped"],
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
        lines.extend(("", f"unverified or historical references: {len(payload['skipped_references'])}"))
    lines.extend(("", "drift is read-only and reports candidates; semantic truth still requires requirement, code and test review.", ""))
    return "\n".join(lines)


def agents_entry_check(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    wiki_config = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    current_entry = normalize_space(wiki_config.get("current_entry") or CURRENT_ENTRY)
    legacy_roots = unique_strings(wiki_config.get("legacy_read_roots"))
    files: list[str] = []
    findings: list[dict[str, Any]] = []
    declared: set[str] = set()
    for path in sorted(root.rglob("AGENTS.md")):
        relative = path.relative_to(root).as_posix()
        if any(part == ".git" for part in path.parts) or relative.startswith(".codestable/backups/"):
            continue
        content = safe_read_text(path)
        if not content:
            continue
        files.append(relative)
        for number, line in enumerate(content.splitlines(), start=1):
            for match in ENTRY_PATH_PATTERN.finditer(line):
                entry = match.group(1).removeprefix("./")
                if not entry.casefold().endswith(("/index.md", "/readme.md")):
                    continue
                declared.add(entry)
                common = {"file": relative, "line": number, "entry": entry}
                if not (root / entry).is_file():
                    findings.append(
                        {
                            "code": "agents.entry.missing",
                            **common,
                            "detail": f"AGENTS.md points to a missing CodeStable entry: {entry}",
                            "action": f"replace it with {current_entry}",
                        }
                    )
                if any(entry == value or entry.startswith(value.rstrip("/") + "/") for value in legacy_roots):
                    findings.append(
                        {
                            "code": "agents.entry.retired",
                            **common,
                            "detail": f"AGENTS.md points to retained legacy knowledge: {entry}",
                            "action": f"use {current_entry}; legacy data requires explicit migration or history access",
                        }
                    )
    if len(declared) > 1:
        findings.append(
            {
                "code": "agents.entry.conflict",
                "entries": sorted(declared),
                "detail": "AGENTS.md declares multiple CodeStable knowledge entries",
                "action": f"keep only {current_entry} as the current entry",
            }
        )
    return {"current_entry": current_entry, "files_checked": files, "findings": findings, "modified": False}

def topics_list_payload(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """List configured canonical topic names without reading card conclusions."""
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    aliases = topic_aliases(config)
    counts: dict[str, int] = {}
    categories: dict[str, set[str]] = {}
    for _, (_, metadata, _) in cards.items():
        if normalize_space(metadata.get("status")) != "current":
            continue
        category = normalize_space(metadata.get("category"))
        for raw_topic in unique_strings(metadata.get("topics")):
            topic = aliases.get(raw_topic.casefold())
            if not topic:
                continue
            counts[topic] = counts.get(topic, 0) + 1
            categories.setdefault(topic, set()).add(category)
    topics = []
    for name, definition in sorted(configured_topics(config).items()):
        topics.append(
            {
                "name": name,
                "label": definition["label"],
                "summary": definition["summary"],
                "aliases": list(definition.get("aliases") or []),
                "replaces": list(definition.get("replaces") or []),
                "current_cards": counts.get(name, 0),
                "categories": sorted(categories.get(name, set())),
            }
        )
    return {
        "ok": True,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "governance": topic_governance(config),
        "count": len(topics),
        "topics": topics,
        "usage": "pass a listed name or alias to brief --topic; omit --topic when uncertain",
    }


def render_topics_list_text(payload: dict[str, Any]) -> str:
    lines = ["# CodeStable business topics", ""]
    governance = payload.get("governance") or {}
    lines.append(f"Governance: {governance.get('mode', 'disabled')} · configured: {payload.get('count', 0)}")
    lines.append("")
    if not payload.get("topics"):
        lines.append("No business topics are configured. Omit --topic and rely on task, path, symbol, and repository scope.")
    for topic in payload.get("topics") or []:
        label = topic.get("label") or topic["name"]
        lines.append(f"- `{topic['name']}` — {label}")
        if topic.get("summary"):
            lines.append(f"  - {topic['summary']}")
        if topic.get("aliases"):
            lines.append("  - aliases: " + ", ".join(f"`{value}`" for value in topic["aliases"]))
        lines.append(
            f"  - current cards: {topic.get('current_cards', 0)}; categories: "
            + (", ".join(topic.get("categories") or []) or "none")
        )
    lines.extend(("", "Use only a listed name or alias. If uncertain, omit --topic; brief will still use its other query signals.", ""))
    return "\n".join(lines)


def topics_suggest_payload(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Suggest reproducible topic candidates from structured tags and scope prefixes."""
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, tasks = scan_existing_records(wiki, configured_categories(config))
    known = topic_aliases(config)
    signals: dict[tuple[str, str], set[str]] = {}
    categories: dict[tuple[str, str], set[str]] = {}
    for card_id, (_, metadata, _) in cards.items():
        if normalize_space(metadata.get("status")) != "current":
            continue
        category = normalize_space(metadata.get("category"))
        for tag in unique_strings(metadata.get("tags")):
            name = slugify(tag).casefold()
            if REPOSITORY_NAME_PATTERN.fullmatch(name):
                signals.setdefault(("shared-tag", name), set()).add(card_id)
                categories.setdefault(("shared-tag", name), set()).add(category)
        raw_scopes = metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else []
        try:
            scopes = normalize_scopes(raw_scopes)
        except KnowledgeError:
            scopes = []
        for scope in scopes or legacy_scopes(unique_strings(metadata.get("paths")), []):
            parts = [part for part in PurePosixPath(scope.get("path") or "").parts if part not in PATH_SIGNAL_STOPWORDS]
            if not parts:
                continue
            name = slugify(parts[0]).casefold()
            if REPOSITORY_NAME_PATTERN.fullmatch(name):
                signals.setdefault(("shared-scope-prefix", name), set()).add(card_id)
                categories.setdefault(("shared-scope-prefix", name), set()).add(category)
    for task_id, (_, metadata, _) in tasks.items():
        linked = [card_id for card_id in unique_strings(metadata.get("card_ids")) if card_id in cards]
        linked_current = [
            card_id for card_id in linked if normalize_space(cards[card_id][1].get("status")) == "current"
        ]
        linked_categories = {normalize_space(cards[card_id][1].get("category")) for card_id in linked_current}
        if len(linked_current) < 2 or len(linked_categories) < 2:
            continue
        stable_tags = unique_strings(metadata.get("tags"))
        name = slugify(stable_tags[0] if stable_tags else f"task-{task_id[-8:]}").casefold()
        if not REPOSITORY_NAME_PATTERN.fullmatch(name):
            continue
        signals.setdefault(("shared-task-link", name), set()).update(linked_current)
        categories.setdefault(("shared-task-link", name), set()).update(linked_categories)
    suggestions: list[dict[str, Any]] = []
    for (basis, name), card_ids in sorted(signals.items()):
        if name in known or len(card_ids) < 2 or len(categories[(basis, name)]) < 2:
            continue
        suggestions.append(
            {
                "name": name,
                "basis": basis,
                "card_ids": sorted(card_ids),
                "categories": sorted(categories[(basis, name)]),
                "proposal": {
                    "name": name,
                    "label": name.replace("-", " ").title(),
                    "summary": f"Review and replace: deterministic candidate from {basis} '{name}'.",
                    "aliases": [],
                    "replaces": [],
                },
            }
        )
    return {
        "ok": True,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "governance": topic_governance(config),
        "suggestions": suggestions,
        "method": "shared structured tags, repository-relative scope prefixes, or source-task links across at least two categories",
        "limits": [
            "suggestions are navigation candidates, not semantic conclusions",
            "no card or configuration is modified; a human must edit and dry-run an update payload",
        ],
    }


def normalize_topics_update_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeError("topics update payload must be an object")
    unknown = set(raw) - {"mode", "minimum_coverage", "review_max_age_days", "upsert_topics", "assignments"}
    if unknown:
        raise KnowledgeError("unknown topics update fields: " + ", ".join(sorted(unknown)))
    mode = normalize_space(raw.get("mode")).lower()
    if mode and mode not in {"disabled", "manual", "required"}:
        raise KnowledgeError("topics update mode must be disabled, manual, or required")
    minimum = raw.get("minimum_coverage")
    if minimum is not None:
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not 0 <= float(minimum) <= 1:
            raise KnowledgeError("topics update minimum_coverage must be between 0 and 1")
        minimum = float(minimum)
    review_age = raw.get("review_max_age_days")
    if review_age is not None and (
        not isinstance(review_age, int) or isinstance(review_age, bool) or review_age < 1 or review_age > 3650
    ):
        raise KnowledgeError("topics update review_max_age_days must be an integer from 1 to 3650")
    raw_topics = raw.get("upsert_topics") or []
    if not isinstance(raw_topics, list):
        raise KnowledgeError("topics update upsert_topics must be an array")
    upserts: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for value in raw_topics:
        if not isinstance(value, dict) or set(value) - {"name", "label", "summary", "aliases", "replaces"}:
            raise KnowledgeError("each topic upsert accepts name, label, summary, aliases, and replaces")
        name = normalize_space(value.get("name")).casefold()
        label = normalize_space(value.get("label"))
        summary = normalize_space(value.get("summary"))
        aliases = [item.casefold() for item in unique_strings(value.get("aliases"))]
        replaces = [item.casefold() for item in unique_strings(value.get("replaces"))]
        if not REPOSITORY_NAME_PATTERN.fullmatch(name) or name in seen_topics:
            raise KnowledgeError(f"invalid or duplicate topic name: {name!r}")
        if not label or not summary:
            raise KnowledgeError(f"topic {name} requires a human-readable label and navigation summary")
        reject_placeholder(summary, f"topic {name} summary")
        for alias in [*aliases, *replaces]:
            if not REPOSITORY_NAME_PATTERN.fullmatch(alias) or alias == name:
                raise KnowledgeError(f"topic {name} has invalid alias or replacement: {alias!r}")
        seen_topics.add(name)
        upserts.append(
            {"name": name, "label": label, "summary": summary, "aliases": aliases, "replaces": replaces}
        )
    raw_assignments = raw.get("assignments") or []
    if not isinstance(raw_assignments, list):
        raise KnowledgeError("topics update assignments must be an array")
    assignments: list[dict[str, Any]] = []
    seen_cards: set[str] = set()
    for value in raw_assignments:
        if not isinstance(value, dict) or set(value) - {"card_id", "expected_revision", "topics"}:
            raise KnowledgeError("each topic assignment accepts card_id, expected_revision, and topics")
        card_id = normalize_space(value.get("card_id"))
        revision = value.get("expected_revision")
        if not re.fullmatch(r"K-[A-Za-z0-9-]+", card_id) or card_id in seen_cards:
            raise KnowledgeError(f"invalid or duplicate topic assignment card_id: {card_id!r}")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise KnowledgeError(f"topic assignment {card_id} requires a positive expected_revision")
        seen_cards.add(card_id)
        assignments.append(
            {"card_id": card_id, "expected_revision": revision, "topics": [item.casefold() for item in unique_strings(value.get("topics"))]}
        )
    normalized = {
        "mode": mode,
        "minimum_coverage": minimum,
        "review_max_age_days": review_age,
        "upsert_topics": upserts,
        "assignments": assignments,
    }
    secret = detect_secret(normalized)
    if secret:
        raise KnowledgeError(f"topics update payload appears to contain a {secret}")
    return normalized


def _topics_update_locked(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool,
    plan_token: str | None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    normalized = normalize_topics_update_payload(payload)
    operation_fp = sha256_text(stable_json(normalized))
    state_fp = knowledge_state_fingerprint(root, config)
    workspace_fp = workspace_state_fingerprint(root)
    plan = decode_plan_token(plan_token) if plan_token else None
    if plan and normalize_space(plan.get("task_fingerprint")) != f"topics:{operation_fp}":
        raise KnowledgeError("topics plan token does not match this payload")
    if plan and normalize_space(plan.get("state_fingerprint")) != state_fp:
        raise KnowledgeError("project knowledge changed after topics dry-run; run it again")
    if plan and normalize_space(plan.get("workspace_fingerprint")) != workspace_fp:
        raise KnowledgeError("project workspace changed after topics dry-run; run it again")
    if plan:
        try:
            timestamp = datetime.fromisoformat(normalize_space(plan.get("timestamp")))
        except ValueError as exc:
            raise KnowledgeError("topics plan token has an invalid timestamp") from exc
    else:
        timestamp = now_local()
    token = encode_plan_token(f"topics:{operation_fp}", state_fp, workspace_fp, timestamp)
    projected_config = json.loads(json.dumps(config))
    wiki_config = projected_config.setdefault("wiki", {})
    definitions = wiki_config.setdefault("topics", {})
    if not isinstance(definitions, dict):
        definitions = {}
        wiki_config["topics"] = definitions
    topic_history = wiki_config.setdefault("topic_history", [])
    if not isinstance(topic_history, list):
        topic_history = []
        wiki_config["topic_history"] = topic_history
    existing_names = set(configured_topics(projected_config))
    for topic in normalized["upsert_topics"]:
        missing_replacements = [value for value in topic["replaces"] if value not in existing_names]
        if missing_replacements:
            raise KnowledgeError(
                f"topic {topic['name']} replaces unknown topics: {', '.join(missing_replacements)}"
            )
        aliases = unique_strings([*topic["aliases"], *topic["replaces"]])
        for replaced in topic["replaces"]:
            previous = definitions.pop(replaced)
            topic_history.append(
                {
                    "name": replaced,
                    "definition": previous,
                    "replaced_by": topic["name"],
                    "changed_at": timestamp.isoformat(timespec="seconds"),
                }
            )
        definitions[topic["name"]] = {
            "label": topic["label"],
            "summary": topic["summary"],
            "aliases": aliases,
            "replaces": topic["replaces"],
        }
        existing_names.add(topic["name"])
    alias_owners: dict[str, str] = {}
    for name, definition in configured_topics(projected_config).items():
        for alias in [name, *(definition.get("aliases") or [])]:
            owner = alias_owners.get(alias)
            if owner and owner != name:
                raise KnowledgeError(f"topic alias {alias!r} is claimed by both {owner} and {name}")
            alias_owners[alias] = name
    governance = wiki_config.setdefault("topic_governance", {})
    if not isinstance(governance, dict):
        governance = {}
        wiki_config["topic_governance"] = governance
    if normalized["mode"]:
        governance["mode"] = normalized["mode"]
    if normalized["minimum_coverage"] is not None:
        governance["minimum_coverage"] = normalized["minimum_coverage"]
    if normalized["review_max_age_days"] is not None:
        governance["review_max_age_days"] = normalized["review_max_age_days"]

    aliases = topic_aliases(projected_config)
    cards, _ = scan_existing_records(wiki_root(root, config), configured_categories(config))
    timestamp_text = timestamp.isoformat(timespec="seconds")
    updates: list[tuple[str, Path, dict[str, Any], str]] = []
    for assignment in normalized["assignments"]:
        record = cards.get(assignment["card_id"])
        if record is None:
            raise KnowledgeError(f"topics assignment references unknown card {assignment['card_id']}")
        path, metadata, body = record
        revision = int(metadata.get("revision", 1) or 1)
        if revision != assignment["expected_revision"]:
            raise KnowledgeError(
                f"card {assignment['card_id']} revision changed: expected {assignment['expected_revision']}, current {revision}"
            )
        if normalize_space(metadata.get("status")) != "current":
            raise KnowledgeError(f"topics bulk assignment only updates current cards: {assignment['card_id']}")
        unknown_topics = [value for value in assignment["topics"] if value not in aliases]
        if unknown_topics:
            raise KnowledgeError("topic assignment uses unknown topics: " + ", ".join(unknown_topics))
        assigned_topics = unique_strings([aliases[value] for value in assignment["topics"]])
        old_topics = unique_strings(metadata.get("topics"))
        if old_topics == assigned_topics:
            continue
        updated = dict(metadata)
        history = updated.get("topic_history") if isinstance(updated.get("topic_history"), list) else []
        updated["topic_history"] = [
            *history,
            {"revision": revision, "updated_at": normalize_space(metadata.get("updated_at")), "topics": old_topics},
        ]
        updated["topics"] = assigned_topics
        updated["updated_at"] = timestamp_text
        updated["revision"] = revision + 1
        updated["fingerprint"] = sha256_text(
            stable_json({"previous": normalize_space(metadata.get("fingerprint")), "topics": assigned_topics})
        )
        updates.append((assignment["card_id"], path, updated, body))

    config_path = root / ".codestable" / "config.json"
    config_changed = json_dump(projected_config) != config_path.read_text(encoding="utf-8")
    projected_entries = collect_index_entries(root, config)
    updates_by_id = {card_id: (path, metadata, body) for card_id, path, metadata, body in updates}
    for index, entry in enumerate(projected_entries):
        replacement = updates_by_id.get(entry.get("id"))
        if replacement:
            path, metadata, body = replacement
            projected_entries[index] = index_entry_for(path, root, metadata, body, render_front_matter(metadata, body))
    outputs = render_index_outputs(root, projected_config, projected_entries)
    index_changed = [
        path.relative_to(root).as_posix()
        for path, content in outputs.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != content
    ]
    result = {
        "ok": True,
        "dry_run": dry_run,
        "read_only": dry_run,
        "tool_version": TOOL_VERSION,
        "plan_token": token if dry_run else None,
        "configuration_changed": config_changed,
        "updated_cards": [
            {"id": card_id, "path": path.relative_to(root).as_posix(), "revision": metadata["revision"]}
            for card_id, path, metadata, _ in updates
        ],
        "index": {"changed": index_changed, "dry_run": dry_run},
        "idempotent": not config_changed and not updates and not index_changed,
    }
    if dry_run:
        return result
    mutation_paths = {path for _, path, _, _ in updates}
    mutation_paths.update(outputs)
    if config_changed:
        mutation_paths.add(config_path)
    snapshot = {path: path.read_text(encoding="utf-8") if path.is_file() else None for path in mutation_paths}
    transaction = create_recovery_journal(root, wiki_root(root, config), f"TOPICS-{operation_fp[:16]}", snapshot)
    try:
        if config_changed:
            atomic_write_text(config_path, json_dump(projected_config))
        for _, path, metadata, body in updates:
            atomic_write_text(path, render_front_matter(metadata, body))
        for path, content in outputs.items():
            atomic_write_text(path, content)
        atomic_write_text(transaction / "COMMITTED", "committed\n")
    except Exception:
        restore_snapshot(snapshot, wiki_root(root, config))
        remove_recovery_journal(transaction)
        raise
    remove_recovery_journal(transaction)
    return result


def topics_update(
    root: Path,
    config: dict[str, Any],
    payload: Any,
    dry_run: bool = False,
    plan_token: str | None = None,
) -> dict[str, Any]:
    if dry_run:
        if plan_token:
            raise KnowledgeError("plan_token is only valid when applying a topics update")
        return _topics_update_locked(root, config, payload, dry_run=True, plan_token=None)
    if not plan_token:
        raise KnowledgeError("topics update apply requires the plan_token returned by --dry-run")
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    lock = acquire_lock(root, wiki)
    try:
        return _topics_update_locked(root, config, payload, dry_run=False, plan_token=plan_token)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def local_runtime_alignment(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Report project-data compatibility separately from release provenance."""
    manifest_path = root / ".codestable" / "manifest.json"
    manifest_error: str | None = None
    try:
        manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    except KnowledgeError as exc:
        manifest = {}
        manifest_error = str(exc)
    raw_schema = config.get("schema_version")
    try:
        actual_schema: Any = int(raw_schema)
    except (TypeError, ValueError):
        actual_schema = raw_schema
    mode = config.get("mode")
    compatible = mode == RUNTIME_MODE and actual_schema == SCHEMA_VERSION
    versions = {
        "runtime": TOOL_VERSION,
        "config": normalize_space(config.get("version")),
        "version_file": normalize_space(safe_read_text(root / ".codestable" / "VERSION")),
        "manifest": normalize_space(manifest.get("version")) if isinstance(manifest, dict) else "",
    }
    versions_aligned = all(value == TOOL_VERSION for value in versions.values())
    version_status = (
        "aligned"
        if versions_aligned
        else "compatible-release-drift"
        if compatible
        else "incompatible"
    )
    version_action = (
        "none"
        if versions_aligned
        else "optional: run bootstrap.py --check and upgrade only when the installed release should refresh managed project files"
        if compatible
        else "required: run bootstrap.py --check and follow its compatibility action"
    )
    return {
        "ok": compatible,
        "runtime_source": "skill",
        "runtime_path": str(Path(__file__).resolve()),
        "mode": {"expected": RUNTIME_MODE, "actual": mode},
        "schema": {"expected": SCHEMA_VERSION, "actual": actual_schema},
        "versions": versions,
        "versions_aligned": versions_aligned,
        "version_status": version_status,
        "version_action": version_action,
        "manifest_error": manifest_error,
        "detail": (
            "project data is compatible with the shared Skill runtime; release metadata drift is informational"
            if compatible and not versions_aligned
            else "project data is compatible with the shared Skill runtime"
            if compatible
            else "project data is incompatible with the shared Skill runtime"
        ),
        "distribution_reference_checked": False,
        "distribution_check": "run bootstrap.py --check from the installed CodeStable Skill for a read-only compatibility report",
    }


def doctor(root: Path, config: dict[str, Any], check_current_references: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    categories = configured_categories(config)
    runtime_alignment = local_runtime_alignment(root, config)
    if not runtime_alignment["ok"]:
        warnings.append(
            {
                "code": "runtime.data.incompatible",
                "detail": runtime_alignment["detail"],
                "action": "run the installed CodeStable Skill bootstrap.py --check, then use --upgrade if it reports needs-upgrade",
            }
        )
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
    wiki_config = config.get("wiki") if isinstance(config.get("wiki"), dict) else {}
    configured_entry = normalize_space(wiki_config.get("current_entry") or CURRENT_ENTRY)
    if configured_entry != CURRENT_ENTRY:
        errors.append(
            {
                "code": "wiki.entry.invalid",
                "detail": f"the only supported current entry is {CURRENT_ENTRY}, configured {configured_entry}",
            }
        )
    for required in ("README.md", "INDEX.md", "HISTORY.md", "TOPICS.md", "PROJECT.md", "learning.schema.json", "index.jsonl"):
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
                try:
                    normalize_scopes(metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [])
                except KnowledgeError as exc:
                    errors.append({"code": "card.scopes", "detail": f"{relative}: {exc}"})
                known_topic_names = topic_aliases(config)
                unknown_topics = [value for value in unique_strings(metadata.get("topics")) if value not in known_topic_names]
                if unknown_topics:
                    warnings.append(
                        {
                            "code": "card.topic.unconfigured",
                            "detail": f"{relative} uses unconfigured topics: {', '.join(unknown_topics)}",
                        }
                    )
                cards[identifier] = (path, metadata, body)
            else:
                status = normalize_space(metadata.get("task_status"))
                if status not in TASK_STATUSES:
                    errors.append({"code": "task.status", "detail": f"{relative} has invalid task_status {status!r}"})
                visibility = normalize_space(metadata.get("visibility") or "active")
                if visibility not in TASK_VISIBILITIES:
                    errors.append({"code": "task.visibility", "detail": f"{relative} has invalid visibility {visibility!r}"})
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
        for value in metadata.get("knowledge_use") or []:
            if not isinstance(value, dict) or normalize_space(value.get("card_id")) not in cards:
                errors.append({"code": "task.knowledge_use.missing", "detail": f"task {identifier} has invalid knowledge-use card reference"})
        visibility = normalize_space(metadata.get("visibility") or "active")
        consolidated_into = normalize_space(metadata.get("consolidated_into"))
        if visibility == "archived":
            if not consolidated_into or consolidated_into not in tasks:
                errors.append({"code": "task.consolidated_into.missing", "detail": f"archived task {identifier} has no valid canonical task"})
            elif identifier not in unique_strings(tasks[consolidated_into][1].get("consolidated_from")):
                errors.append({"code": "task.consolidation.asymmetric", "detail": f"canonical task {consolidated_into} does not point back to {identifier}"})
        for duplicate_id in unique_strings(metadata.get("consolidated_from")):
            if duplicate_id not in tasks:
                errors.append({"code": "task.consolidated_from.missing", "detail": f"task {identifier} references missing duplicate {duplicate_id}"})
            elif normalize_space(tasks[duplicate_id][1].get("consolidated_into")) != identifier:
                errors.append({"code": "task.consolidation.asymmetric", "detail": f"duplicate task {duplicate_id} does not point to {identifier}"})

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

    entry_check = agents_entry_check(root, config)
    warnings.extend(
        {"code": value["code"], "detail": value["detail"], "action": value.get("action", "")}
        for value in entry_check["findings"]
    )
    for category in categories:
        has_current = any(
            normalize_space(metadata.get("category")) == category and normalize_space(metadata.get("status")) == "current"
            for _, metadata, _ in cards.values()
        )
        readme = wiki / category / "README.md"
        if has_current and readme.is_file() and not extract_canonical(safe_read_text(readme)):
            warnings.append(
                {
                    "code": "wiki.category.summary.empty",
                    "detail": f"{readme.relative_to(root).as_posix()} has current cards but no maintained summary; use TOPICS.md for navigation or add a concise summary",
                }
            )

    governance = topic_governance(config)
    configured_topic_count = len(configured_topics(config))
    current_card_count = sum(
        normalize_space(metadata.get("status")) == "current" for _, metadata, _ in cards.values()
    )
    themed_current_count = sum(
        normalize_space(metadata.get("status")) == "current" and bool(unique_strings(metadata.get("topics")))
        for _, metadata, _ in cards.values()
    )
    topic_coverage = themed_current_count / current_card_count if current_card_count else 1.0
    if governance["mode"] == "manual" and not configured_topic_count:
        warnings.append(
            {
                "code": "topic.manual.unconfigured",
                "detail": "topic governance is manual but no business topics are configured; this is not a healthy enabled topic view",
                "action": "run topics suggest, review the proposal, then apply it with a dry-run token; or set mode=disabled",
            }
        )
    if governance["mode"] == "required" and topic_coverage < governance["minimum_coverage"]:
        warnings.append(
            {
                "code": "topic.required.coverage",
                "detail": (
                    f"current topic coverage {topic_coverage:.1%} is below required "
                    f"{governance['minimum_coverage']:.1%}"
                ),
                "action": "assign reviewed topics to current cards or lower the explicit threshold",
            }
        )

    stats = {
        "cards": len(cards),
        "current_cards": sum(normalize_space(metadata.get("status")) == "current" for _, metadata, _ in cards.values()),
        "proposed_cards": sum(normalize_space(metadata.get("status")) == "proposed" for _, metadata, _ in cards.values()),
        "task_notes": len(tasks),
        "active_task_notes": sum(normalize_space(metadata.get("visibility") or "active") != "archived" for _, metadata, _ in tasks.values()),
        "archived_task_notes": sum(normalize_space(metadata.get("visibility") or "active") == "archived" for _, metadata, _ in tasks.values()),
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
        "runtime_alignment": runtime_alignment,
        "entry_check": entry_check,
        "topic_governance": {
            **governance,
            "configured_topics": configured_topic_count,
            "current_cards": current_card_count,
            "themed_current_cards": themed_current_count,
            "coverage": round(topic_coverage, 4),
        },
        "stats": stats,
    }
    if check_current_references:
        reference_check = current_reference_drift(root, config)
        result["current_references"] = reference_check
        result["ok"] = result["ok"] and not reference_check["findings"]
        result["next_check"] = "reference candidates checked; run drift with a Git scope for task-note coverage"
    return result


def summary_review_metadata(text: str) -> dict[str, str]:
    match = re.search(r"<!--\s*codestable:summary-review\s+(\{.*?\})\s*-->", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        "knowledge_hash": normalize_space(value.get("knowledge_hash")),
        "reviewed_at": normalize_space(value.get("reviewed_at")),
    }


def category_knowledge_hash(cards: Sequence[tuple[str, dict[str, Any], str]]) -> str:
    material = [
        {
            "id": identifier,
            "revision": int(metadata.get("revision", 1) or 1),
            "knowledge": normalize_space(extract_section(body, ("结论",))),
        }
        for identifier, metadata, body in cards
    ]
    return sha256_text(stable_json(sorted(material, key=lambda value: value["id"])))


def governance_audit(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    root = root.expanduser().resolve()
    wiki = wiki_root(root, config)
    cards, _ = scan_existing_records(wiki, configured_categories(config))
    current = [
        (identifier, path, metadata, body)
        for identifier, (path, metadata, body) in cards.items()
        if normalize_space(metadata.get("status")) == "current"
    ]
    review_days = topic_governance(config)["review_max_age_days"]
    now = now_local()
    findings: list[dict[str, Any]] = []
    for identifier, path, metadata, body in current:
        relative = path.relative_to(root).as_posix()
        evidence = metadata.get("evidence")
        future_use = metadata.get("future_use")
        if not isinstance(evidence, list) or not evidence or any(not isinstance(value, dict) for value in evidence):
            findings.append(
                {
                    "issue_type": "card-evidence-unstructured",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "review the current card and update it with structured evidence; do not infer evidence during upgrade",
                }
            )
        elif any(PLACEHOLDER_PATTERN.search(text) or text in GENERIC_DURABLE_TEXT for text in recursive_strings(evidence)):
            findings.append(
                {
                    "issue_type": "card-evidence-generic",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "replace generic evidence with a specific artifact, observed result, and supported conclusion",
                }
            )
        if not isinstance(future_use, list) or len(future_use) < 2 or any(not isinstance(value, dict) for value in future_use):
            findings.append(
                {
                    "issue_type": "future-use-unstructured",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "record two distinct future changes with actor and constraint; keep legacy text readable until reviewed",
                }
            )
        elif any(PLACEHOLDER_PATTERN.search(text) or text in GENERIC_DURABLE_TEXT for text in recursive_strings(future_use)):
            findings.append(
                {
                    "issue_type": "future-use-generic",
                    "card_id": identifier,
                    "path": relative,
                    "suggested_action": "replace template language with concrete future review scenarios",
                }
            )
        updated_at = normalize_space(metadata.get("updated_at") or metadata.get("created_at"))
        if updated_at:
            try:
                age_days = (now - datetime.fromisoformat(updated_at).astimezone()).days
            except ValueError:
                age_days = review_days + 1
            if age_days > review_days:
                findings.append(
                    {
                        "issue_type": "card-review-old",
                        "card_id": identifier,
                        "path": relative,
                        "age_days": age_days,
                        "suggested_action": "review the card against current implementation, tests, contracts, and accepted decisions",
                    }
                )

    by_category: dict[str, list[tuple[str, Path, dict[str, Any], str]]] = {}
    for value in current:
        by_category.setdefault(normalize_space(value[2].get("category")), []).append(value)
    for category, values in sorted(by_category.items()):
        for left_index, left in enumerate(values):
            for right in values[left_index + 1 :]:
                same_title = normalize_space(left[2].get("title")).casefold() == normalize_space(right[2].get("title")).casefold()
                similarity = conclusion_similarity(
                    extract_section(left[3], ("结论",)), extract_section(right[3], ("结论",))
                )
                if same_title or similarity >= 0.82:
                    findings.append(
                        {
                            "issue_type": "possible-equivalent-current-cards",
                            "card_ids": [left[0], right[0]],
                            "category": category,
                            "similarity": round(similarity, 3),
                            "suggested_action": "review for semantic equivalence; reuse/update one card or preserve both with a documented orthogonal scope",
                        }
                    )

    policy = topic_governance(config)
    topics = configured_topics(config)
    themed = sum(bool(unique_strings(metadata.get("topics"))) for _, _, metadata, _ in current)
    coverage = themed / len(current) if current else 1.0
    topic_view_healthy = bool(topics) and policy["mode"] in {"manual", "required"} and (
        policy["mode"] == "manual" or coverage >= policy["minimum_coverage"]
    )
    for category in configured_categories(config):
        values = by_category.get(category, [])
        if not values:
            continue
        readme = wiki / category / "README.md"
        text = safe_read_text(readme)
        summary = extract_canonical(text)
        if not summary:
            if topic_view_healthy and all(bool(unique_strings(value[2].get("topics"))) for value in values):
                continue
            findings.append(
                {
                    "issue_type": "category-summary-empty",
                    "category": category,
                    "path": readme.relative_to(root).as_posix(),
                    "suggested_action": "add a concise reviewed summary or rely on an explicitly healthy topic view",
                }
            )
            continue
        review = summary_review_metadata(text)
        expected_hash = category_knowledge_hash([(value[0], value[2], value[3]) for value in values])
        if not review.get("knowledge_hash"):
            findings.append(
                {
                    "issue_type": "category-summary-review-missing",
                    "category": category,
                    "path": readme.relative_to(root).as_posix(),
                    "expected_knowledge_hash": expected_hash,
                    "suggested_action": "review the summary against current cards and add the codestable:summary-review marker",
                }
            )
        elif review["knowledge_hash"] != expected_hash:
            findings.append(
                {
                    "issue_type": "category-summary-stale",
                    "category": category,
                    "path": readme.relative_to(root).as_posix(),
                    "expected_knowledge_hash": expected_hash,
                    "suggested_action": "review the changed current cards, update the summary if needed, then refresh its review hash",
                }
            )
        reviewed_at = review.get("reviewed_at")
        if reviewed_at:
            try:
                age_days = (now - datetime.fromisoformat(reviewed_at).astimezone()).days
            except ValueError:
                age_days = review_days + 1
            if age_days > review_days:
                findings.append(
                    {
                        "issue_type": "category-summary-review-old",
                        "category": category,
                        "path": readme.relative_to(root).as_posix(),
                        "age_days": age_days,
                        "suggested_action": "review the summary against current cards and refresh reviewed_at",
                    }
                )

    topic_status = "not-applicable" if policy["mode"] == "disabled" else "pass"
    if policy["mode"] == "manual" and not topics:
        topic_status = "incomplete"
        findings.append(
            {
                "issue_type": "topic-governance-not-configured",
                "suggested_action": "run topics suggest and review an update, or explicitly choose disabled mode",
            }
        )
    if policy["mode"] == "required" and coverage < policy["minimum_coverage"]:
        topic_status = "incomplete"
        findings.append(
            {
                "issue_type": "topic-coverage-below-policy",
                "coverage": round(coverage, 4),
                "required": policy["minimum_coverage"],
                "suggested_action": "assign reviewed topics to current cards before treating the topic view as healthy",
            }
        )
    return {
        "status": "needs-attention" if findings else topic_status,
        "topic_status": topic_status,
        "topic_policy": policy,
        "topic_coverage": round(coverage, 4),
        "current_cards": len(current),
        "themed_current_cards": themed,
        "unthemed_current_cards": len(current) - themed,
        "findings": findings,
    }


def delivery_audit(
    root: Path,
    config: dict[str, Any],
    cached: bool = False,
    base: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    findings: list[dict[str, Any]] = []
    version_path = root / ".codestable" / "VERSION"
    manifest_path = root / ".codestable" / "manifest.json"
    try:
        manifest = read_json(manifest_path) if manifest_path.is_file() else {}
    except KnowledgeError as exc:
        manifest = {}
        findings.append(
            {
                "issue_type": "release-manifest-invalid",
                "detail": str(exc),
                "suggested_action": "restore or upgrade the managed CodeStable manifest",
            }
        )
    versions = {
        "runtime": TOOL_VERSION,
        "config": normalize_space(config.get("version")),
        "version_file": normalize_space(safe_read_text(version_path)),
        "manifest": normalize_space(manifest.get("version")) if isinstance(manifest, dict) else "",
    }
    versions_aligned = all(value == TOOL_VERSION for value in versions.values())
    _, outputs = build_index_outputs(root, config)
    for path, content in outputs.items():
        bad_lines = [number for number, line in enumerate(content.splitlines(), start=1) if line.rstrip() != line]
        if bad_lines:
            findings.append(
                {
                    "issue_type": "generated-markdown-trailing-whitespace",
                    "path": path.relative_to(root).as_posix(),
                    "lines": bad_lines[:20],
                    "suggested_action": "fix the renderer and run reindex; do not hand-edit generated indexes",
                }
            )
    git_probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=str(root), text=True, capture_output=True, check=False
    )
    git_result: dict[str, Any]
    if git_probe.returncode == 0:
        try:
            drift = drift_payload(root, config, cached=cached, base=base)
        except KnowledgeError as exc:
            git_result = {"status": "incomplete", "detail": str(exc)}
            findings.append(
                {
                    "issue_type": "git-writeback-check-incomplete",
                    "detail": str(exc),
                    "suggested_action": "provide a valid Git baseline or run the narrower reference check",
                }
            )
        else:
            git_result = {"status": "pass" if drift["ok"] else "needs-attention", "detail": drift}
            findings.extend({"source": "drift", **value} for value in drift["findings"])
    else:
        git_result = {"status": "not-applicable", "detail": "not a Git worktree"}
    build_script = root / "scripts" / "build_runtime.py"
    build_result: dict[str, Any]
    if build_script.is_file():
        process = subprocess.run(
            [sys.executable, str(build_script), "--check"], cwd=str(root), text=True, capture_output=True, check=False
        )
        build_result = {
            "status": "pass" if process.returncode == 0 else "needs-attention",
            "detail": normalize_space(process.stdout or process.stderr),
        }
        if process.returncode != 0:
            findings.append(
                {
                    "issue_type": "generated-runtime-out-of-sync",
                    "suggested_action": "run scripts/build_runtime.py and review the generated shared runtime",
                }
            )
    else:
        build_result = {"status": "not-applicable", "detail": "maintenance build script not present in installed project"}
    return {
        "status": "needs-attention" if findings else "pass",
        "findings": findings,
        "git_writeback": git_result,
        "runtime_asset": build_result,
        "versions": versions,
        "versions_aligned": versions_aligned,
    }


def audit_payload(
    root: Path,
    config: dict[str, Any],
    cached: bool = False,
    base: str | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    structure = doctor(root, config)
    references = current_reference_drift(root, config)
    governance = governance_audit(root, config)
    delivery = delivery_audit(root, config, cached=cached, base=base)
    structural_warnings = [
        value
        for value in structure.get("warnings", [])
        if not normalize_space(value.get("code")).startswith(("wiki.category.summary.", "topic."))
    ]
    structural_findings = [*structure.get("errors", []), *structural_warnings]
    sections = {
        "structure": {
            "status": "pass" if not structural_findings else "needs-attention",
            "findings": structural_findings,
            "detail": structure,
        },
        "current_references": {
            "status": "needs-attention" if references["findings"] else "incomplete" if references["unverified"] else "pass",
            "detail": references,
        },
        "governance": governance,
        "delivery": delivery,
    }
    blocking_statuses = {"needs-attention", "incomplete"}
    ok = all(section.get("status") not in blocking_statuses for section in sections.values())
    return {
        "ok": ok,
        "read_only": True,
        "tool_version": TOOL_VERSION,
        "exit_code": 0 if ok else 1,
        "business_truth": "not-evaluated",
        "sections": sections,
        "limits": [
            "audit verifies structure, current references, governance evidence, generated outputs, and Git knowledge writeback",
            "audit does not prove that implementation satisfies business requirements",
        ],
    }


def render_audit_text(payload: dict[str, Any]) -> str:
    lines = [
        "CodeStable audit",
        f"result: {'PASS' if payload['ok'] else 'ACTION REQUIRED'}",
        "business truth: not evaluated",
        "",
    ]
    for name, section in payload["sections"].items():
        findings = section.get("findings")
        if findings is None and isinstance(section.get("detail"), dict):
            detail = section["detail"]
            findings = detail.get("findings") or detail.get("errors") or []
        lines.append(f"- {name}: {section.get('status')} · findings={len(findings or [])}")
    lines.extend(("", "This command is read-only and does not claim that business requirements are satisfied.", ""))
    return "\n".join(lines)


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
    active_tasks = [entry for entry in tasks if entry.get("visibility") != "archived"]
    archived_tasks = [entry for entry in tasks if entry.get("visibility") == "archived"]
    recent = sorted(active_tasks, key=lambda item: item.get("created_at") or "", reverse=True)[:10]
    return {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "categories": category_counts,
        "cards": len(cards),
        "task_notes": len(tasks),
        "active_task_notes": len(active_tasks),
        "archived_task_notes": len(archived_tasks),
        "recent_tasks": recent,
    }

def template_payload(title: str, kind: str) -> dict[str, Any]:
    return {
        "task": {
            "title": title or "__REPLACE__: 任务标题",
            "kind": kind or "task",
            "status": "completed",
            "request": "__REPLACE__: 用户最初要求",
            "summary": "__REPLACE__: 实际做了什么；不要写计划或完整日志",
            "result": "__REPLACE__: 最终可观察结果",
            "scopes": [{"repository": "self", "path": "__REPLACE__/path.py", "symbol": "__REPLACE__"}],
            "topics": [],
            "tags": ["__REPLACE__"],
            "verification": ["__REPLACE__: 实际执行的验证命令或检查"],
            "deliverable": "__REPLACE__: 公开产物路径",
            "knowledge_summary": "__REPLACE__: 说明为何新增、复用、更新或不创建长期卡片",
            "source": {},
            "knowledge_use": [],
        },
        "items": [
            {
                "category": "architecture",
                "title": "__REPLACE__: 一个未来任务会复用的架构结论",
                "knowledge": "__REPLACE__: 用当前时态写清楚稳定事实、约束或边界",
                "rationale": "__REPLACE__: 说明依据和选择理由",
                "implications": ["__REPLACE__: 对未来实现、测试或运维的具体影响"],
                "future_use": [
                    {
                        "change": "__REPLACE__: 会触发复核的变更",
                        "actor": "__REPLACE__: 未来执行者",
                        "constraint": "__REPLACE__: 必须复核的本卡约束",
                    },
                    {
                        "change": "__REPLACE__: 另一类变更",
                        "actor": "__REPLACE__: 另一未来执行者",
                        "constraint": "__REPLACE__: 必须复核的本卡约束",
                    },
                ],
                "scopes": [{"repository": "self", "path": "__REPLACE__/path.py", "symbol": "__REPLACE__"}],
                "topics": [],
                "tags": ["__REPLACE__"],
                "evidence": [
                    {
                        "kind": "test",
                        "artifact": "__REPLACE__: 测试标识",
                        "result": "__REPLACE__: 可核查结果",
                        "supports": "__REPLACE__: 该产物支持的卡片结论",
                    }
                ],
                "confidence": "verified",
                "status": "current",
                "supersedes": [],
                "pinned": False,
            }
        ],
    }


def markdown_bullet_values(value: str) -> list[str]:
    result: list[str] = []
    for line in value.splitlines():
        line = normalize_space(line)
        if line.startswith("- "):
            line = normalize_space(line[2:])
        if line and line not in {"无", "未记录"}:
            result.append(line)
    return unique_strings(result)


def raw_markdown_section(body: str, headings: Sequence[str]) -> str:
    escaped = "|".join(re.escape(value) for value in headings)
    match = re.search(rf"(?ms)^##\s+(?:{escaped})\s*$\n(.*?)(?=^##\s+|\Z)", body)
    return match.group(1).strip() if match else ""


def task_update_template(root: Path, config: dict[str, Any], task_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"T-[A-Za-z0-9-]+", normalize_space(task_id)):
        raise KnowledgeError("template --task-id requires an existing T-* identifier")
    _, tasks = scan_existing_records(wiki_root(root, config), configured_categories(config))
    record = tasks.get(task_id)
    if record is None:
        raise KnowledgeError(f"template --task-id references unknown task {task_id}")
    _, metadata, body = record
    if normalize_space(metadata.get("visibility") or "active") == "archived":
        raise KnowledgeError(
            f"task {task_id} is archived into {normalize_space(metadata.get('consolidated_into'))}; "
            "update the canonical task instead"
        )
    request = extract_section(body, ("请求",))
    if request == "未单独记录。":
        request = ""
    knowledge_summary = normalize_space(metadata.get("knowledge_summary")) or extract_section(body, ("知识处置",))
    if knowledge_summary.startswith("未说明"):
        knowledge_summary = ""
    return {
        "task": {
            "id": task_id,
            "update_existing": True,
            "expected_revision": int(metadata.get("revision", 1) or 1),
            "title": normalize_space(metadata.get("title")),
            "kind": normalize_space(metadata.get("kind") or "task"),
            "status": normalize_space(metadata.get("task_status") or "completed"),
            "request": request,
            "summary": extract_section(body, ("处理摘要",)),
            "result": extract_section(body, ("最终结果",)),
            "scopes": metadata.get("scopes") if isinstance(metadata.get("scopes"), list) else [],
            "paths": unique_strings(metadata.get("paths")),
            "symbols": unique_strings(metadata.get("symbols")),
            "topics": unique_strings(metadata.get("topics")),
            "tags": unique_strings(metadata.get("tags")),
            "verification": markdown_bullet_values(raw_markdown_section(body, ("验证",))),
            "deliverable": normalize_space(metadata.get("deliverable")),
            "new_task_reason": normalize_space(metadata.get("new_task_reason")),
            "knowledge_summary": knowledge_summary,
            "knowledge_use": metadata.get("knowledge_use") if isinstance(metadata.get("knowledge_use"), list) else [],
            "source": metadata.get("source") if isinstance(metadata.get("source"), dict) else {},
        },
        "items": [],
    }


def compact_learn_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in payload.items() if key != "reference_check"}
    reference = payload.get("reference_check") if isinstance(payload.get("reference_check"), dict) else {}
    findings = reference.get("findings") if isinstance(reference.get("findings"), list) else []
    unverified = reference.get("unverified") if isinstance(reference.get("unverified"), list) else []
    verified = reference.get("verified") if isinstance(reference.get("verified"), list) else []
    historical = (
        reference.get("historical_cards_skipped")
        if isinstance(reference.get("historical_cards_skipped"), list)
        else []
    )
    result["reference_check"] = {
        "blocking": bool(reference.get("blocking", False)),
        "review_required": bool(reference.get("review_required", False)),
        "finding_count": len(findings),
        "unverified_count": len(unverified),
        "verified_count": len(verified),
        "historical_cards_skipped_count": len(historical),
        "findings": findings,
        "unverified": unverified,
    }
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project root or a path inside the project")
    subparsers = parser.add_subparsers(dest="command", required=True)

    brief_parser = subparsers.add_parser("brief", help="read-only task-oriented knowledge brief")
    brief_parser.add_argument("--task", required=True, help="current user request or task description")
    brief_parser.add_argument("--path", action="append", default=[], help="relevant project path; repeatable")
    brief_parser.add_argument("--symbol", action="append", default=[], help="relevant symbol; repeatable")
    brief_parser.add_argument("--topic", action="append", default=[], help="configured business topic; repeatable")
    brief_parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="structured scope as <repository>:<path>#<symbol>; repeatable",
    )
    brief_parser.add_argument("--limit", type=int, help="override maximum selected knowledge items")
    brief_parser.add_argument("--include-history", action="store_true", help="return deprecated and superseded cards separately")
    brief_parser.add_argument("--include-legacy", action="store_true", help="read retained legacy pages for migration or history work")
    brief_parser.add_argument("--include-superseded", action="store_true", help=argparse.SUPPRESS)
    brief_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")

    learn_parser = subparsers.add_parser("learn", help="validate and persist a task note plus durable knowledge cards")
    learn_parser.add_argument("--file", required=True, help="learning JSON file, or '-' for stdin")
    learn_parser.add_argument("--dry-run", action="store_true", help="validate and show the write plan without filesystem changes")
    learn_parser.add_argument("--plan-token", help="apply the exact state and identifiers validated by a prior dry-run")
    learn_parser.add_argument(
        "--compact",
        action="store_true",
        help="keep actionable reference details and counts while omitting the full verified-reference list",
    )

    consolidate_parser = subparsers.add_parser("consolidate", help="archive duplicate task notes into one canonical logical task")
    consolidate_parser.add_argument("--file", required=True, help="consolidation JSON file, or '-' for stdin")
    consolidate_parser.add_argument("--dry-run", action="store_true", help="validate the complete consolidation without writes")
    consolidate_parser.add_argument("--plan-token", help="apply the exact consolidation validated by a prior dry-run")

    doctor_parser = subparsers.add_parser("doctor", help="read-only structural integrity check; does not validate semantic truth")
    doctor_parser.add_argument("--check-current-references", action="store_true", help="also run deterministic current path/symbol checks")
    subparsers.add_parser("status", help="read-only knowledge inventory")

    audit_parser = subparsers.add_parser("audit", help="read-only structure, reference, governance, and delivery acceptance")
    audit_parser.add_argument("--format", choices=("text", "json"), default="text")
    audit_scope = audit_parser.add_mutually_exclusive_group()
    audit_scope.add_argument("--cached", action="store_true", help="audit staged Git delivery")
    audit_scope.add_argument("--base", help="audit committed delivery from <base>...HEAD")

    topics_parser = subparsers.add_parser("topics", help="suggest or safely update business-topic navigation")
    topic_commands = topics_parser.add_subparsers(dest="topics_command", required=True)
    topics_list_parser = topic_commands.add_parser("list", help="list configured canonical topics and aliases")
    topics_list_parser.add_argument("--format", choices=("text", "json"), default="text")
    topics_suggest = topic_commands.add_parser("suggest", help="read-only deterministic topic suggestions")
    topics_suggest.add_argument("--format", choices=("json",), default="json")
    topics_update_parser = topic_commands.add_parser("update", help="reviewed bulk topic configuration and assignment update")
    topics_update_parser.add_argument("--file", required=True, help="topic update JSON file, or '-' for stdin")
    topics_update_parser.add_argument("--dry-run", action="store_true", help="validate the complete update without writes")
    topics_update_parser.add_argument("--plan-token", help="apply the exact update validated by a prior dry-run")

    drift_parser = subparsers.add_parser("drift", help="read-only current-reference and Git knowledge-writeback checks")
    drift_scope = drift_parser.add_mutually_exclusive_group()
    drift_scope.add_argument("--cached", action="store_true", help="check staged changes")
    drift_scope.add_argument("--base", help="check committed changes from <base>...HEAD")
    drift_scope.add_argument("--references-only", action="store_true", help="check current card paths and symbols without Git")
    drift_parser.add_argument("--format", choices=("text", "json"), default="text")

    reindex_parser = subparsers.add_parser("reindex", help="rebuild generated Markdown and JSONL indexes")
    reindex_parser.add_argument("--dry-run", action="store_true", help="show stale indexes without writing")

    template_parser = subparsers.add_parser("template", help="print a fill-required learning JSON template")
    template_parser.add_argument("--title", default="", help="task title")
    template_parser.add_argument("--kind", default="task", help="task kind")
    template_parser.add_argument("--task-id", help="prefill an update snapshot from an existing task note")
    template_parser.add_argument("--output", help="explicit output file; stdout when omitted")
    return parser


def command_main(args: argparse.Namespace) -> tuple[int, str]:
    root = find_project_root(Path(args.root))
    config = load_config(root)
    if args.command == "brief":
        topic_resolution = resolve_brief_topics(args.topic, config)
        topics = topic_resolution["resolved"]
        scopes = [parse_scope_argument(value) for value in args.scope]
        payload = selected_brief_payload(
            root,
            config,
            normalize_space(args.task),
            unique_strings(args.path),
            unique_strings(args.symbol),
            args.limit,
            bool(args.include_history or args.include_superseded),
            topics,
            scopes,
            bool(args.include_legacy),
        )
        attach_brief_topic_resolution(payload, topic_resolution)
        return 0, json_dump(payload) if args.format == "json" else render_brief_markdown(payload)
    if args.command == "learn":
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid learning JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        payload = learn(
            root,
            config,
            raw,
            dry_run=bool(args.dry_run),
            plan_token=normalize_space(args.plan_token) or None,
        )
        return 0, json_dump(compact_learn_result(payload) if args.compact else payload)
    if args.command == "consolidate":
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid consolidation JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        return 0, json_dump(
            consolidate(
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
    if args.command == "audit":
        payload = audit_payload(
            root,
            config,
            cached=bool(args.cached),
            base=normalize_space(args.base) or None,
        )
        output = json_dump(payload) if args.format == "json" else render_audit_text(payload)
        return int(payload["exit_code"]), output
    if args.command == "topics":
        if args.topics_command == "list":
            payload = topics_list_payload(root, config)
            return 0, json_dump(payload) if args.format == "json" else render_topics_list_text(payload)
        if args.topics_command == "suggest":
            return 0, json_dump(topics_suggest_payload(root, config))
        if args.file == "-":
            try:
                raw = json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise KnowledgeError(f"invalid topics JSON from stdin: line {exc.lineno}, column {exc.colno}") from exc
        else:
            raw = read_json(Path(args.file).expanduser().resolve())
        return 0, json_dump(
            topics_update(
                root,
                config,
                raw,
                dry_run=bool(args.dry_run),
                plan_token=normalize_space(args.plan_token) or None,
            )
        )
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
        payload = task_update_template(root, config, args.task_id) if args.task_id else template_payload(args.title, args.kind)
        content = json_dump(payload)
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
