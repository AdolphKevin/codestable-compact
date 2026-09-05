# Repository guidance

This repository contains one public Agent Skill: `skills/cs`.

When changing it:

1. Keep `$cs` knowledge-only. Do not reintroduce feature/issue/refactor/roadmap/model routing, delivery stages, evidence gates, telemetry, Meta, evaluation or self-evolution.
2. `brief`, `status`, `doctor`, and `reindex --dry-run` must perform zero filesystem writes.
3. `learn --dry-run` must validate the complete plan without writes.
4. Every applied `learn` writes one compact task note; only durable future-facing facts become knowledge cards.
5. Preserve the 11 canonical categories and their stable slugs.
6. Keep current truth, proposed truth, deprecated truth and superseded history distinguishable.
7. Within the current knowledge base, resolve conflicts with `supersedes` and retain provenance. Only an explicitly authorized complete rebuild resets its history.
8. Do not capture raw prompts, model responses, full command output, full diffs, secrets or personal data.
9. Use Python standard library only and remain compatible with Python 3.10+.
10. Support only the current knowledge format. Bootstrap creates a fresh database; an explicitly authorized rebuild replaces the complete target `.codestable` without migrating old records.
11. Rebuild must preview its full scope without writes, bind apply to that plan, and leave everything outside the target `.codestable` untouched. Do not create automatic backup directories or follow a symlinked knowledge root.
12. Generated indexes must be deterministic and repairable with `reindex`.
13. Run `python3 -m unittest discover -s tests -v` and `python3 scripts/validate_release.py --source .` before release.
