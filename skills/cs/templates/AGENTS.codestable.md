## CodeStable knowledge

- Treat `.codestable/wiki/INDEX.md` as the only current entry. Start every development task with `python3 .codestable/tools/cs_knowledge.py brief --task '<request>'`; add configured topics or repository scopes when known.
- `$cs` context does not automatically carry into a later task or Agent turn.
- Before completing a development task, run `learn --dry-run`, apply its plan token, then run `doctor`.
- Record created, reused or superseded cards in `task.knowledge_summary`; explain why when no durable card is needed.
- A strong existing-task candidate must be updated by ID/revision unless an independent goal is explicitly justified.
- Use `consolidate` for historical duplicate task-notes; do not delete or hand-edit them.
- Treat `knowledge_use` as optional traceable evidence of a concrete design, scope, implementation, test or review effect; each claim needs an artifact, result and card-to-evidence mapping.
- Do not read retained legacy directories in ordinary tasks; use `--include-legacy` only for explicit migration, conflict or history work.
- Review current cards when deleting, renaming or replacing implementation paths or symbols.
- Before commit, stage both implementation and Wiki output, then run `python3 .codestable/tools/cs_knowledge.py drift --cached`.
- Git commit tools do not replace CodeStable writeback. `doctor` passing proves structure only; `drift` reports candidates and does not replace semantic review.
