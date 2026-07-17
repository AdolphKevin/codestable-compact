# Changelog

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
