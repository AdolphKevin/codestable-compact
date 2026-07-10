#!/usr/bin/env python3
"""Validate the portable CodeStable Compact release without dependencies."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
ASSET_ROOT = SKILLS / "cs" / "assets" / "project"
CS_ASSET = ASSET_ROOT / ".codestable"
EXPECTED_SKILLS = {"cs", "cs-feat", "cs-issue", "cs-refactor", "cs-roadmap", "cs-model"}
FORBIDDEN_PHASE_SKILLS = {
    "cs-feat-design",
    "cs-feat-design-review",
    "cs-feat-impl",
    "cs-code-review",
    "cs-feat-qa",
    "cs-feat-accept",
    "cs-feat-ff",
    "cs-issue-report",
    "cs-issue-analyze",
    "cs-issue-fix",
    "cs-refactor-ff",
    "cs-roadmap-review",
}
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


class ValidationError(RuntimeError):
    pass


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError("missing opening frontmatter delimiter")
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValidationError("missing closing frontmatter delimiter") from exc
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValidationError(f"invalid frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"\'')
    return metadata, "\n".join(lines[end + 1 :])


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"JSON root must be an object: {path.relative_to(ROOT)}")
    return value


def require_bool(section: dict, field: str, expected: bool, errors: list[str], prefix: str) -> None:
    actual = section.get(field)
    if actual is not expected:
        errors.append(f"{prefix}.{field} must be {str(expected).lower()}, got {actual!r}")


def validate_skills(errors: list[str], warnings: list[str]) -> None:
    if not SKILLS.is_dir():
        errors.append("skills directory is missing")
        return
    actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
    if actual != EXPECTED_SKILLS:
        errors.append(f"skill set mismatch: expected {sorted(EXPECTED_SKILLS)}, got {sorted(actual)}")
    phase_dirs = actual & FORBIDDEN_PHASE_SKILLS
    if phase_dirs:
        errors.append(f"internal phases must not be user-visible skills: {sorted(phase_dirs)}")

    for skill_name in sorted(actual):
        skill_dir = SKILLS / skill_name
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{skill_name}: missing SKILL.md")
            continue
        try:
            metadata, body = parse_frontmatter(skill_file)
        except ValidationError as exc:
            errors.append(f"{skill_name}: {exc}")
            continue
        declared_name = metadata.get("name", "")
        if declared_name != skill_name:
            errors.append(f"{skill_name}: frontmatter name must equal directory name")
        if len(declared_name) > 64 or not NAME_PATTERN.fullmatch(declared_name):
            errors.append(f"{skill_name}: name violates Agent Skills naming constraints")
        description = metadata.get("description", "")
        if not 20 <= len(description) <= 1024:
            errors.append(f"{skill_name}: description must contain 20-1024 characters")
        compatibility = metadata.get("compatibility", "")
        if len(compatibility) > 500:
            errors.append(f"{skill_name}: compatibility exceeds 500 characters")
        if metadata.get("license") != "MIT":
            errors.append(f"{skill_name}: license must be MIT")
        line_count = len(skill_file.read_text(encoding="utf-8").splitlines())
        if line_count > 500:
            errors.append(f"{skill_name}: SKILL.md exceeds 500 lines")
        elif line_count > 360:
            warnings.append(f"{skill_name}: SKILL.md exceeds 360 lines; consider references")
        referenced = set(re.findall(r"`?(references/[A-Za-z0-9_.-]+\.md)`?", body))
        for relative in referenced:
            if not (skill_dir / relative).is_file():
                errors.append(f"{skill_name}: missing referenced file {relative}")

    cs_skill = SKILLS / "cs" / "SKILL.md"
    if cs_skill.is_file():
        body = cs_skill.read_text(encoding="utf-8")
        required_phrases = (
            "normal /cs = delivery lifecycle + best-effort observation write",
            "explicit /cs evolve = selected evidence + Harness maintenance",
            "Never recursively scan `.codestable/`",
            "promotion of a changed Harness version",
        )
        for phrase in required_phrases:
            if phrase not in body:
                errors.append(f"cs/SKILL.md is missing control-plane invariant: {phrase}")


def validate_config(errors: list[str]) -> None:
    try:
        config = read_json(CS_ASSET / "config.json")
    except ValidationError as exc:
        errors.append(str(exc))
        return
    if config.get("schema_version") != 2:
        errors.append("config.schema_version must be 2")
    if config.get("entry", {}).get("mode") != "auto":
        errors.append("default entry.mode must be auto")
    if config.get("execution", {}).get("mode") != "continuous_until_gate":
        errors.append("default execution.mode must be continuous_until_gate")

    context = config.get("context", {})
    if context.get("archive_default") != "off":
        errors.append("default archive retrieval must be off")
    try:
        if int(context.get("max_index_lines", 0)) <= 0:
            errors.append("context.max_index_lines must be positive")
    except (TypeError, ValueError):
        errors.append("context.max_index_lines must be an integer")
    excluded = set(context.get("excluded_normal_roots", []))
    for required in (
        ".codestable/observations",
        ".codestable/evolution",
        ".codestable/evals",
        ".codestable/harness/versions",
    ):
        if required not in excluded:
            errors.append(f"normal context exclusion missing: {required}")

    observe = config.get("observability", {})
    if observe.get("enabled") is not True or observe.get("mode") != "passive":
        errors.append("observability must default to enabled passive mode")
    require_bool(observe, "best_effort", True, errors, "observability")
    require_bool(observe, "read_during_normal_runs", False, errors, "observability")
    capture = observe.get("capture", {})
    for field in ("raw_prompts", "raw_model_responses", "source_or_diffs", "full_tool_output"):
        require_bool(capture, field, False, errors, "observability.capture")
    for field in ("event_metadata", "verification_evidence", "user_corrections"):
        require_bool(capture, field, True, errors, "observability.capture")
    for field in ("max_run_size_kb", "max_events", "max_event_payload_bytes", "max_string_chars"):
        try:
            if int(observe.get("limits", {}).get(field, 0)) <= 0:
                errors.append(f"observability.limits.{field} must be positive")
        except (TypeError, ValueError):
            errors.append(f"observability.limits.{field} must be an integer")

    evolution = config.get("evolution", {})
    if evolution.get("enabled") is not True or evolution.get("mode") != "manual":
        errors.append("evolution must default to enabled manual mode")
    for field in ("run_during_normal_work", "auto_diagnose", "auto_propose", "auto_evaluate", "auto_promote"):
        require_bool(evolution, field, False, errors, "evolution")
    for field in ("require_selected_cases", "require_human_promotion_gate", "require_private_holdout"):
        require_bool(evolution, field, True, errors, "evolution")

    evaluator = config.get("evaluator", {})
    if evaluator.get("mode") != "external_signed_aggregate":
        errors.append("evaluator.mode must be external_signed_aggregate")
    require_bool(evaluator, "require_signed_results", True, errors, "evaluator")
    if evaluator.get("signing_algorithm") != "hmac-sha256":
        errors.append("evaluator.signing_algorithm must be hmac-sha256")
    if evaluator.get("private_holdout_location") != "outside_candidate_workspace":
        errors.append("private holdout must live outside the candidate workspace")


def validate_runtime_assets(errors: list[str]) -> None:
    required_runtime = (
        ".codestable/tools/cs_context.py",
        ".codestable/tools/cs_harness.py",
        ".codestable/tools/cs_harness.py",
        ".codestable/tools/cs_observe.py",
        ".codestable/tools/cs_evolve.py",
        ".codestable/tools/cs_eval.py",
        ".codestable/reference/routing.md",
        ".codestable/reference/retrieval.md",
        ".codestable/reference/gates.md",
        ".codestable/reference/minimality.md",
        ".codestable/reference/lifecycle.md",
        ".codestable/reference/evolution.md",
        ".codestable/observations/README.md",
        ".codestable/observations/index.jsonl",
        ".codestable/evolution/README.md",
        ".codestable/evolution/index.jsonl",
        ".codestable/harness/manifest.json",
        ".codestable/harness/registry.json",
        ".codestable/harness/playbook.jsonl",
        ".codestable/evals/protocol.json",
    )
    for relative in required_runtime:
        if not (ASSET_ROOT / relative).is_file():
            errors.append(f"runtime asset missing: {relative}")
    for forbidden in (
        CS_ASSET / "telemetry",
        CS_ASSET / "evolution" / "campaigns",
    ):
        if forbidden.exists():
            errors.append(f"obsolete automatic-evolution runtime must not ship: {forbidden.relative_to(ASSET_ROOT)}")

    cs_skill = SKILLS / "cs" / "SKILL.md"
    if cs_skill.is_file():
        source = cs_skill.read_text(encoding="utf-8")
        if "cs_harness.py playbook-query" not in source:
            errors.append("normal /cs must query promoted playbook rules through read-only cs_harness.py")
        if "cs_evolve.py playbook-query" in source:
            errors.append("normal /cs must not call the evolution control plane for playbook reads")

    harness_tool = CS_ASSET / "tools" / "cs_harness.py"
    if harness_tool.is_file():
        source = harness_tool.read_text(encoding="utf-8")
        for forbidden in (
            ".codestable/observations",
            ".codestable/evolution",
            ".codestable/evals",
            ".codestable/harness/versions",
            "import cs_observe",
            "import cs_evolve",
            "import cs_eval",
        ):
            if forbidden in source:
                errors.append(f"read-only cs_harness.py contains control-plane dependency: {forbidden}")

    evolve_tool = CS_ASSET / "tools" / "cs_evolve.py"
    if evolve_tool.is_file() and "playbook-query" in evolve_tool.read_text(encoding="utf-8"):
        errors.append("cs_evolve.py must not expose a normal-run playbook query command")

    eval_tool = CS_ASSET / "tools" / "cs_eval.py"
    if eval_tool.is_file():
        source = eval_tool.read_text(encoding="utf-8")
        for required in (
            "baseline_content_sha256",
            "candidate_definition_sha256",
            "verify_local_candidate_lock",
            "verify_challenge_integrity",
        ):
            if required not in source:
                errors.append(f"trusted evaluator is missing integrity lock: {required}")

    observe_tool = CS_ASSET / "tools" / "cs_observe.py"
    if observe_tool.is_file():
        source = observe_tool.read_text(encoding="utf-8")
        for required in ('"stdout"', '"stderr"', '"tool_output"', '"raw_output"', '"full_output"'):
            if required not in source:
                errors.append(f"passive recorder forbidden field missing: {required}")

    retrieval = CS_ASSET / "reference" / "retrieval.md"
    if retrieval.is_file():
        text = retrieval.read_text(encoding="utf-8")
        if "--session <live-conversation-key>" not in text:
            errors.append("retrieval receipt example must include the live-conversation session key")
        for excluded in ("observations/", "evolution/", "evals/", "harness/versions/"):
            if excluded not in text:
                errors.append(f"retrieval rules must explicitly exclude {excluded} from normal work")


def validate_manifest(errors: list[str]) -> None:
    try:
        manifest = read_json(CS_ASSET / "harness" / "manifest.json")
    except ValidationError as exc:
        errors.append(str(exc))
        return
    if manifest.get("schema_version") != 2:
        errors.append("harness manifest schema_version must be 2")
    if manifest.get("promotion_policy") != "human_gate_always":
        errors.append("harness promotion policy must be human_gate_always")
    editable = manifest.get("editable_surfaces", [])
    protected = set(manifest.get("protected_paths", []))
    if not isinstance(editable, list) or not editable:
        errors.append("harness manifest must declare editable surfaces")
        return
    ids: list[str] = []
    paths: list[str] = []
    for item in editable:
        if not isinstance(item, dict):
            errors.append("every editable surface must be an object")
            continue
        ids.append(str(item.get("id") or ""))
        paths.append(str(item.get("path") or ""))
        if item.get("promotion") != "human_gate":
            errors.append(f"editable surface {item.get('id')} may not bypass the human Gate")
        path = ROOT / str(item.get("path") or "")
        asset_path = ASSET_ROOT / str(item.get("path") or "")
        if path.is_absolute() and not asset_path.is_file():
            errors.append(f"editable surface file missing from runtime assets: {item.get('path')}")
    if len(ids) != len(set(ids)) or "" in ids:
        errors.append("editable surface ids must be unique and non-empty")
    if len(paths) != len(set(paths)) or "" in paths:
        errors.append("editable surface paths must be unique and non-empty")
    if any(path in protected for path in paths):
        errors.append("an editable surface exactly overlaps a protected path")
    for required in (
        ".codestable/config.json",
        ".codestable/reference/gates.md",
        ".codestable/reference/evolution.md",
        ".codestable/tools/cs_observe.py",
        ".codestable/tools/cs_evolve.py",
        ".codestable/tools/cs_eval.py",
        ".codestable/evals/**",
        ".codestable/evolution/**",
        ".codestable/observations/**",
        ".codestable/harness/manifest.json",
        ".codestable/harness/registry.json",
        ".codestable/harness/versions/**",
    ):
        if required not in protected:
            errors.append(f"protected Harness path missing: {required}")


def validate_protocol(errors: list[str]) -> None:
    try:
        protocol = read_json(CS_ASSET / "evals" / "protocol.json")
    except ValidationError as exc:
        errors.append(str(exc))
        return
    if protocol.get("schema_version") != 2:
        errors.append("evaluation protocol schema_version must be 2")
    if set(protocol.get("required_splits", [])) != {"held_in", "held_out", "safety"}:
        errors.append("evaluation protocol must require held_in, held_out and safety")
    try:
        if int(protocol.get("repeats", 0)) < 3:
            errors.append("evaluation protocol must require at least three repeats")
    except (TypeError, ValueError):
        errors.append("evaluation protocol repeats must be an integer")
    locks = protocol.get("locks", {})
    for required in (
        "baseline_version",
        "baseline_content",
        "candidate_content",
        "candidate_definition",
        "model_profile",
        "adapter",
        "evaluator",
        "budget",
        "task_splits",
    ):
        if locks.get(required) is not True:
            errors.append(f"evaluation protocol lock must be true: {required}")
    holdout = protocol.get("holdout", {})
    if holdout.get("visibility") != "evaluator_only":
        errors.append("held-out visibility must be evaluator_only")
    if holdout.get("location") != "outside_candidate_workspace":
        errors.append("held-out tasks must be outside the candidate workspace")
    if holdout.get("expose_only_aggregate_results") is not True:
        errors.append("project-side evaluator results must be aggregate-only")
    trusted = protocol.get("trusted_results", {})
    if trusted.get("require_signature") is not True or trusted.get("algorithm") != "hmac-sha256":
        errors.append("trusted evaluator results must require hmac-sha256 signatures")
    if trusted.get("reject_raw_task_traces") is not True:
        errors.append("trusted evaluator must reject raw task traces")
    if trusted.get("one_result_per_challenge") is not True:
        errors.append("evaluation protocol must allow only one result per challenge")
    if protocol.get("promotion", {}).get("human_gate_always") is not True:
        errors.append("evaluation protocol must require a human promotion Gate")


def validate_links(errors: list[str]) -> None:
    root_resolved = ROOT.resolve()
    for markdown in sorted(ROOT.rglob("*.md")):
        if "__pycache__" in markdown.parts:
            continue
        text = markdown.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            destination = (markdown.parent / target).resolve()
            try:
                destination.relative_to(root_resolved)
            except ValueError:
                errors.append(f"{markdown.relative_to(ROOT)}: local link escapes package: {raw_target}")
                continue
            if not destination.exists():
                errors.append(f"{markdown.relative_to(ROOT)}: broken local link: {raw_target}")


def validate_python(errors: list[str]) -> None:
    required = {
        SKILLS / "cs" / "scripts" / "bootstrap.py",
        CS_ASSET / "tools" / "cs_context.py",
        CS_ASSET / "tools" / "cs_harness.py",
        CS_ASSET / "tools" / "cs_observe.py",
        CS_ASSET / "tools" / "cs_evolve.py",
        CS_ASSET / "tools" / "cs_eval.py",
        ROOT / "scripts" / "migrate_legacy.py",
        ROOT / "scripts" / "migrate_alpha_observations.py",
    }
    for script in sorted(required):
        if not script.is_file():
            errors.append(f"script missing: {script.relative_to(ROOT)}")
    for script in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in script.parts:
            continue
        try:
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        except SyntaxError as exc:
            errors.append(f"Python compile failed for {script.relative_to(ROOT)}: {exc}")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else ""
    if version != "0.3.0":
        errors.append(f"VERSION must be 0.3.0, got {version!r}")

    validate_skills(errors, warnings)
    validate_config(errors)
    validate_runtime_assets(errors)
    validate_manifest(errors)
    validate_protocol(errors)
    validate_links(errors)
    validate_python(errors)

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    if errors:
        print("Errors:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK: validated 6 skills, passive observations, manual evolution, trusted evaluator boundary, links and Python")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
