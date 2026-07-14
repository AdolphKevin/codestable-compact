# Promote evidence-state evaluation knowledge

- Work: `2026-07-14-evidence-state-evaluation-knowledge`
- Kind: `model`
- Lane: `standard`

## 1. Intent and acceptance

- Outcome: Promote a reusable rule for interpreting tool-call and token reductions without confusing them with delivery quality.
- Acceptance: One indexed knowledge note states the trigger, quality-first decision rule, exact measured boundary and evidence links; it makes no cross-task claim.
- Non-goals: Rewriting vision/domain, promoting a Harness policy, or copying campaign traces into knowledge.

## 2. Evidence

- Repository observations: The knowledge index had no existing note for evidence-state efficiency or Host campaign interpretation.
- Relevant current model / executable contracts: Harness completion requires source-valid evidence, risk-adaptive verification, Git-visible side-effect checks and integrity-safe archive.
- Baseline or reproduction: Release manifest binds candidate 67/67, control 22/22, mutant 13/13 and the real Codex 5+5 campaign to source SHA-256 `3523f2156c3c77328402e1dfe4758a782c438fe5ccd03f622312a5707594e406`.

## 3. Design or root cause

- Chosen mechanism / root cause: A single knowledge note separates quality Gates from adapter-specific resource proxies and records the current evidence ceiling.
- Existing path reused: `.codestable/knowledge/notes/` plus the existing compact `knowledge/INDEX.md`.
- Alternatives rejected and why: No model/domain edit because this is reusable evaluation guidance, not product terminology or an accepted system requirement; no separate notes per metric because they share one decision rule.
- Compatibility / rollback / rollout (when relevant):

## 4. Plan

- [x] Inspect current indexes and duplicate terms.
- [x] Extract current truth from control, Meta, Host and release evidence.
- [x] Add one minimal note and one index pointer.
- [x] Validate links, wording boundaries and index consistency.

## 5. Changes and decisions

- Changed: Added `knowledge/notes/evidence-state-evaluation.md` and indexed it.
- Decisions made during execution: Tool calls remain a non-Gate resource proxy; single-task Host metrics remain point estimates even when measured directly.

## 6. Verification and review

- Commands and results: `python3 scripts/validate_skills.py` — PASS.
- Commands and results: `python3 .codestable/tools/cs_context.py doctor` — 0 errors, 0 warnings.
- Commands and results: targeted Markdown-link/index/source-identity check — 4/4 links resolved, 9 index lines, source identity matched.
- Commands and results: `git diff --check` — PASS.
- Observable acceptance evidence: The note points to the current Host, control, Meta and release artifacts and preserves source SHA-256 `3523f2156c3c77328402e1dfe4758a782c438fe5ccd03f622312a5707594e406`.
- Internal review findings and repairs: No duplicate note or model statement existed; single-task point estimates remain explicitly bounded and uncached-token regression remains visible.

## 7. Promotion and closure

- Model updates: None; no vision, domain, requirement, contract or decision changed.
- Knowledge promoted: `.codestable/knowledge/notes/evidence-state-evaluation.md` with one concise index entry.
- Remaining follow-ups: Extend evidence only when multi-task/cross-Host or trusted held-out campaigns are actually executed.
- Closure summary: Current reusable evaluation guidance is indexed, evidence-linked and validated without promoting task history or a policy change.
