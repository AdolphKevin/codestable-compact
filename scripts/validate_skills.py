#!/usr/bin/env python3
"""Validate the portable CodeStable Compact release without third-party deps."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
ASSET_ROOT = SKILLS / "cs" / "assets" / "project"
CS_ASSET = ASSET_ROOT / ".codestable"
EXPECTED_SKILLS = {"cs", "cs-feat", "cs-issue", "cs-refactor", "cs-roadmap", "cs-model"}
FORBIDDEN_PHASE_SKILLS = {
    "cs-feat-design", "cs-feat-design-review", "cs-feat-impl", "cs-code-review",
    "cs-feat-qa", "cs-feat-accept", "cs-feat-ff", "cs-issue-report",
    "cs-issue-analyze", "cs-issue-fix", "cs-refactor-ff", "cs-roadmap-review",
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
    if section.get(field) is not expected:
        errors.append(f"{prefix}.{field} must be {str(expected).lower()}, got {section.get(field)!r}")


def validate_skills(errors: list[str], warnings: list[str]) -> None:
    if not SKILLS.is_dir():
        errors.append("skills directory is missing")
        return
    actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
    if actual != EXPECTED_SKILLS:
        errors.append(f"skill set mismatch: expected {sorted(EXPECTED_SKILLS)}, got {sorted(actual)}")
    if actual & FORBIDDEN_PHASE_SKILLS:
        errors.append(f"internal phases must not be user-visible skills: {sorted(actual & FORBIDDEN_PHASE_SKILLS)}")
    for skill_name in sorted(actual):
        skill_file = SKILLS / skill_name / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"{skill_name}: missing SKILL.md")
            continue
        try:
            metadata, body = parse_frontmatter(skill_file)
        except ValidationError as exc:
            errors.append(f"{skill_name}: {exc}")
            continue
        declared = metadata.get("name", "")
        if declared != skill_name or len(declared) > 64 or not NAME_PATTERN.fullmatch(declared):
            errors.append(f"{skill_name}: invalid Agent Skills name")
        if not 20 <= len(metadata.get("description", "")) <= 1024:
            errors.append(f"{skill_name}: description must contain 20-1024 characters")
        if len(metadata.get("compatibility", "")) > 500:
            errors.append(f"{skill_name}: compatibility exceeds 500 characters")
        if metadata.get("license") != "MIT":
            errors.append(f"{skill_name}: license must be MIT")
        line_count = len(skill_file.read_text(encoding="utf-8").splitlines())
        if line_count > 500:
            errors.append(f"{skill_name}: SKILL.md exceeds 500 lines")
        elif line_count > 360:
            warnings.append(f"{skill_name}: SKILL.md exceeds 360 lines")
        for relative in set(re.findall(r"`?(references/[A-Za-z0-9_.-]+\.md)`?", body)):
            if not (skill_file.parent / relative).is_file():
                errors.append(f"{skill_name}: missing referenced file {relative}")

    cs_text = (SKILLS / "cs" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in (
        "normal /cs = delivery lifecycle + best-effort observation write",
        "explicit /cs meta = selected production evidence + offline Harness maintenance",
        "Never recursively scan `.codestable/`",
        "No fixture coverage, no evolution",
    ):
        if phrase not in cs_text:
            errors.append(f"cs/SKILL.md is missing invariant: {phrase}")


def validate_config(errors: list[str]) -> None:
    try:
        config = read_json(CS_ASSET / "config.json")
    except ValidationError as exc:
        errors.append(str(exc)); return
    if config.get("schema_version") != 3:
        errors.append("config.schema_version must be 3")
    if config.get("entry", {}).get("mode") != "auto":
        errors.append("default entry.mode must be auto")
    if config.get("execution", {}).get("mode") != "continuous_until_gate":
        errors.append("default execution.mode must be continuous_until_gate")
    context = config.get("context", {})
    if context.get("archive_default") != "off":
        errors.append("default archive retrieval must be off")
    excluded = set(context.get("excluded_normal_roots") or [])
    for required in (
        ".codestable/observations", ".codestable/evolution", ".codestable/evals",
        ".codestable/harness/versions", ".codestable/meta",
    ):
        if required not in excluded:
            errors.append(f"normal context exclusion missing: {required}")
    observe = config.get("observability", {})
    if observe.get("enabled") is not True or observe.get("mode") != "passive":
        errors.append("observability must default to enabled passive mode")
    require_bool(observe, "best_effort", True, errors, "observability")
    require_bool(observe, "read_during_normal_runs", False, errors, "observability")
    for field in ("raw_prompts", "raw_model_responses", "source_or_diffs", "full_tool_output"):
        require_bool(observe.get("capture", {}), field, False, errors, "observability.capture")
    evolution = config.get("evolution", {})
    if evolution.get("enabled") is not True or evolution.get("mode") != "manual":
        errors.append("evolution must default to enabled manual mode")
    for field in ("run_during_normal_work", "auto_diagnose", "auto_propose", "auto_evaluate", "auto_promote"):
        require_bool(evolution, field, False, errors, "evolution")
    for field in ("require_selected_cases", "require_private_holdout", "require_validity_prepass", "require_fixture_covered_policy"):
        require_bool(evolution, field, True, errors, "evolution")
    if evolution.get("promotion_authority") != "owner_checkpoint_by_policy":
        errors.append("evolution.promotion_authority must be owner_checkpoint_by_policy")
    meta = config.get("meta", {})
    require_bool(meta, "normal_runs_may_import_meta", False, errors, "meta")
    trigger = meta.get("trigger", {})
    if trigger.get("mode") != "scan_only_by_default":
        errors.append("meta.trigger.mode must be scan_only_by_default")
    try:
        if int(trigger.get("minimum_matching_signals", 0)) < 2:
            errors.append("meta.trigger.minimum_matching_signals must be at least 2")
        if int(meta.get("validity", {}).get("minimum_stochastic_repeats", 0)) < 5:
            errors.append("meta.validity.minimum_stochastic_repeats must be at least 5")
    except (TypeError, ValueError):
        errors.append("Meta trigger/validity budgets must be integers")
    evaluator = config.get("evaluator", {})
    if evaluator.get("mode") != "external_signed_aggregate":
        errors.append("evaluator.mode must be external_signed_aggregate")
    require_bool(evaluator, "require_signed_results", True, errors, "evaluator")
    if evaluator.get("private_holdout_location") != "outside_candidate_workspace":
        errors.append("private holdout must stay outside candidate workspace")


def validate_runtime_assets(errors: list[str]) -> None:
    required = (
        ".codestable/tools/cs_context.py", ".codestable/tools/cs_harness.py",
        ".codestable/tools/cs_observe.py", ".codestable/tools/cs_feedback.py",
        ".codestable/tools/cs_policy.py", ".codestable/tools/cs_meta.py",
        ".codestable/tools/cs_fixture.py", ".codestable/tools/cs_evolve.py",
        ".codestable/tools/cs_eval.py", ".codestable/meta/README.md",
        ".codestable/meta/policy-registry.json", ".codestable/meta/trace.schema.json",
        ".codestable/meta/feedback.schema.json", ".codestable/meta/proposal.schema.json",
        ".codestable/meta/campaign.schema.json", ".codestable/evals/fixtures/index.json",
        ".codestable/evals/protocol.json", ".codestable/harness/manifest.json",
        ".codestable/harness/registry.json", ".codestable/harness/playbook.jsonl",
        ".codestable/reference/routing.md", ".codestable/reference/retrieval.md",
        ".codestable/reference/gates.md", ".codestable/reference/minimality.md",
        ".codestable/reference/lifecycle.md", ".codestable/reference/evolution.md",
    )
    for relative in required:
        if not (ASSET_ROOT / relative).is_file():
            errors.append(f"runtime asset missing: {relative}")
    harness_source = (CS_ASSET / "tools" / "cs_harness.py").read_text(encoding="utf-8")
    for forbidden in ("import cs_meta", "import cs_feedback", "import cs_evolve", "import cs_eval", ".codestable/observations", ".codestable/evolution"):
        if forbidden in harness_source:
            errors.append(f"normal read-only harness tool imports control plane: {forbidden}")
    cs_text = (SKILLS / "cs" / "SKILL.md").read_text(encoding="utf-8")
    if "cs_harness.py playbook-query" not in cs_text:
        errors.append("normal /cs must use the read-only playbook query")
    if "cs_meta.py" in cs_text.split("## Explicit Meta boundary", 1)[0]:
        errors.append("normal /cs section may not invoke cs_meta.py")


def validate_manifest(errors: list[str]) -> None:
    try:
        manifest = read_json(CS_ASSET / "harness" / "manifest.json")
    except ValidationError as exc:
        errors.append(str(exc)); return
    if manifest.get("schema_version") != 3:
        errors.append("Harness manifest schema_version must be 3")
    if manifest.get("promotion_policy") != "owner_checkpoint_by_policy":
        errors.append("Harness promotion policy must be owner_checkpoint_by_policy")
    editable = manifest.get("editable_surfaces")
    if not isinstance(editable, list) or not editable:
        errors.append("Harness manifest must declare editable surfaces"); return
    ids: list[str] = []
    paths: list[str] = []
    for item in editable:
        if not isinstance(item, dict):
            errors.append("editable surface must be an object"); continue
        ids.append(str(item.get("id") or "")); paths.append(str(item.get("path") or ""))
        if item.get("promotion") not in {"owner_checkpoint", "agent_after_evidence"}:
            errors.append(f"invalid promotion mode for {item.get('id')}")
        if not (ASSET_ROOT / str(item.get("path") or "")).is_file():
            errors.append(f"editable surface file missing: {item.get('path')}")
    if len(ids) != len(set(ids)) or "" in ids:
        errors.append("editable surface ids must be unique/non-empty")
    if len(paths) != len(set(paths)) or "" in paths:
        errors.append("editable surface paths must be unique/non-empty")
    protected = set(manifest.get("protected_paths") or [])
    for required in (
        ".codestable/config.json", ".codestable/tools/cs_observe.py",
        ".codestable/tools/cs_feedback.py", ".codestable/tools/cs_policy.py",
        ".codestable/tools/cs_meta.py", ".codestable/tools/cs_fixture.py",
        ".codestable/tools/cs_evolve.py", ".codestable/tools/cs_eval.py",
        ".codestable/evals/**", ".codestable/evolution/**", ".codestable/observations/**",
        ".codestable/meta/**", ".codestable/harness/manifest.json",
        ".codestable/harness/registry.json", ".codestable/harness/versions/**",
    ):
        if required not in protected:
            errors.append(f"protected Harness path missing: {required}")


def validate_protocol(errors: list[str]) -> None:
    try:
        protocol = read_json(CS_ASSET / "evals" / "protocol.json")
    except ValidationError as exc:
        errors.append(str(exc)); return
    if protocol.get("schema_version") != 3:
        errors.append("evaluation protocol schema_version must be 3")
    if set(protocol.get("required_splits") or []) != {"held_in", "held_out", "safety"}:
        errors.append("evaluation protocol must require held_in, held_out and safety")
    try:
        if int(protocol.get("repeats", 0)) < 5:
            errors.append("evaluation protocol must require k>=5")
    except (TypeError, ValueError):
        errors.append("evaluation repeats must be an integer")
    proposal = protocol.get("proposal", {})
    for field in ("agent_authored_required", "fixture_coverage_required", "scripts_measure_only"):
        require_bool(proposal, field, True, errors, "protocol.proposal")
    validity = protocol.get("validity_prepass", {})
    require_bool(validity, "required", True, errors, "protocol.validity_prepass")
    if validity.get("negative_verdict_requires_status") != "pass" or validity.get("promotion_requires_status") != "pass":
        errors.append("negative verdict and promotion must require a passing validity pre-pass")
    promotion = protocol.get("promotion", {})
    if promotion.get("authority") != "owner_checkpoint_by_policy":
        errors.append("protocol promotion authority must be policy-scoped")
    if promotion.get("owner_checkpoint_rule") != "policy_registry":
        errors.append("protocol owner checkpoint rule must come from policy registry")
    if promotion.get("human_gate_always") is not None:
        errors.append("obsolete human_gate_always must not coexist with policy-scoped authority")


def validate_policy_registry(errors: list[str]) -> None:
    tool = CS_ASSET / "tools" / "cs_policy.py"
    completed = subprocess.run(
        [sys.executable, str(tool), "--root", str(ASSET_ROOT), "audit"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        errors.append(f"policy audit did not emit JSON: {completed.stderr or completed.stdout}"); return
    if completed.returncode != 0 or payload.get("ok") is not True:
        errors.append(f"policy/fixture audit failed: {payload}")
    if payload.get("policy_count") != 9:
        errors.append(f"expected 9 first-class policies, got {payload.get('policy_count')}")
    if int(payload.get("fixture_count", 0)) < 12:
        errors.append("expected at least 12 shipped fixtures")
    for policy_id, coverage in (payload.get("coverage") or {}).items():
        if coverage.get("evolvable") is not True:
            errors.append(f"whitelisted policy lacks fixture coverage: {policy_id}")


def validate_links(errors: list[str]) -> None:
    root_resolved = ROOT.resolve()
    for markdown in sorted(ROOT.rglob("*.md")):
        if "__pycache__" in markdown.parts:
            continue
        for raw_target in MARKDOWN_LINK_PATTERN.findall(markdown.read_text(encoding="utf-8")):
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
                errors.append(f"{markdown.relative_to(ROOT)}: local link escapes package: {raw_target}"); continue
            if not destination.exists():
                errors.append(f"{markdown.relative_to(ROOT)}: broken local link: {raw_target}")


def validate_python(errors: list[str]) -> None:
    for script in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in script.parts:
            continue
        try:
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        except SyntaxError as exc:
            errors.append(f"Python compile failed for {script.relative_to(ROOT)}: {exc}")
    for script in sorted((CS_ASSET / "tools").glob("*.py")):
        completed = subprocess.run([sys.executable, str(script), "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if completed.returncode != 0:
            errors.append(f"tool CLI --help failed for {script.relative_to(ROOT)}: {completed.stderr}")


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else ""
    if version != "0.4.0":
        errors.append(f"VERSION must be 0.4.0, got {version!r}")
    validate_skills(errors, warnings)
    validate_config(errors)
    validate_runtime_assets(errors)
    validate_manifest(errors)
    validate_protocol(errors)
    validate_policy_registry(errors)
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
    print("OK: 6 skills, passive traces, feedback pipeline, fixture-covered policies, validity pre-pass, scoped owner checkpoints, trusted evaluation and rollback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
