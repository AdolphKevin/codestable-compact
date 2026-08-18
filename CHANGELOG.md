# Changelog

## Unreleased

- No unreleased changes.

## 1.1.0 — 2026-08-18

- Declared `.codestable/wiki/INDEX.md` as the only current entry and added
  non-mutating bootstrap/doctor warnings for missing, retired or conflicting
  `AGENTS.md` entries.
- Added deterministic current-only business-topic navigation, a separate
  history index, current/proposed/history retrieval groups and explicit legacy
  opt-in.
- Added Schema 2 structured repository/path/symbol scopes while retaining reads
  and checks for legacy `paths` and `symbols`.
- Split reference results into confirmed missing/rename findings, unconfigured
  or unavailable repositories, conservative symbol scan misses, verified
  references and historical skips.
- Added targeted non-blocking reference checks to `learn`, full current-reference
  checks to doctor/drift, and empty category-summary warnings.
- Required traceable structured evidence for `knowledge_use`, including evidence
  type, artifact, observed result and correspondence to the card conclusion.
- Raised the durable-card threshold to require evidence, applicability and at
  least two future-use scenarios; decisions also require context, alternatives
  and consequences.
- Added synonymous-card blocking, explicit orthogonal-card reasons, safe
  in-place scope updates with revision checks and retained `scope_history`.
- Kept compatibility data during upgrade, clearly separated it from normal task
  reads, and preserved all unknown or project-owned data.
- Added the fully synthetic D-0007 shipment/outbox acceptance fixture and tests
  for all new navigation, upgrade, scope, evidence, reference and idempotency
  behavior.
- Added transactional `consolidate`, stable task/card revisions, state-bound
  plan tokens, rollback journals and Git/task-note drift checks developed since
  1.0.0.

## 1.0.0 — 2026-07-17

- Rebuilt CodeStable Compact as a single project-knowledge Skill.
- Removed the public `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap` and `cs-model` Skills.
- Removed the delivery control plane, active-work state machine, evidence completion gate, risk levels, passive observations, feedback, Meta campaigns, evaluation and self-evolution runtime from release assets.
- Added a Markdown Wiki covering requirements, architecture, interfaces, data model, error handling, transaction boundaries, compatibility, performance risks, security boundaries, acceptance criteria and historical decisions.
- Added read-only task-oriented retrieval by task text, paths and symbols, including project overview, manually curated category summaries, current cards, related tasks, recent decisions and legacy model/knowledge pages.
- Added structured task notes and durable knowledge cards with scope, evidence, confidence, status, provenance, deduplication and supersession.
- Added deterministic JSONL and Markdown indexes, read-only integrity checks, explicit reindexing and secret-pattern rejection.
- Added non-destructive bootstrap/upgrade behavior that backs up refreshed or retired shipped files and preserves all project-authored data.
- Added regression coverage for zero-write reads/dry-runs, all knowledge categories, search, idempotency, supersession, legacy retrieval, stale-index repair, fresh install and legacy upgrade preservation.
- Added canonical symlink-root handling, exact dry-run plan tokens, lock-scoped planning and recovery journals covering ordinary write failures and abrupt process termination.

## Previous releases

Versions 0.1.0 through 0.5.0 implemented a software-delivery control plane. Those behaviors are intentionally retired in 1.0.0; upgrade backups preserve the previous project-local tools and data for recovery or manual migration.
