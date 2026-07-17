# Repository guidance

This repository contains one public Agent Skill: `skills/cs`.

When changing it:

1. Keep `$cs` knowledge-only. Do not reintroduce feature/issue/refactor/roadmap/model routing, delivery stages, evidence gates, telemetry, Meta, evaluation or self-evolution.
2. `brief`, `status`, `doctor`, and `reindex --dry-run` must perform zero filesystem writes.
3. `learn --dry-run` must validate the complete plan without writes.
4. Every applied `learn` writes one compact task note; only durable future-facing facts become knowledge cards.
5. Preserve the 11 canonical categories and their stable slugs.
6. Keep current truth, proposed truth, deprecated truth and superseded history distinguishable.
7. Never delete history to resolve conflict; use `supersedes` and preserve provenance.
8. Do not capture raw prompts, model responses, full command output, full diffs, secrets or personal data.
9. Use Python standard library only and remain compatible with Python 3.10+.
10. Fresh bootstrap and upgrade must preserve project-authored Wiki/model/knowledge/work data.
11. Upgrade may retire only files declared in the release manifest, and must back them up first.
12. Generated indexes must be deterministic and repairable with `reindex`.
13. Run `python3 -m unittest discover -s tests -v` and `python3 scripts/validate_release.py --source .` before release.
