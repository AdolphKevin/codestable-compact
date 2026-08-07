## CodeStable knowledge

- Start every development task with `python3 .codestable/tools/cs_knowledge.py brief --task '<request>'`.
- `$cs` context does not automatically carry into a later task or Agent turn.
- Before completing a development task, run `learn --dry-run`, apply its plan token, then run `doctor`.
- Record created, reused or superseded cards in `task.knowledge_summary`; explain why when no durable card is needed.
- A strong existing-task candidate must be updated by ID/revision unless an independent goal is explicitly justified.
- Use `consolidate` for historical duplicate task-notes; do not delete or hand-edit them.
- Treat `knowledge_use` as optional strong evidence of concrete design/test/review impact, not as a citation quota.
- Review current cards when deleting, renaming or replacing implementation paths or symbols.
- Before commit, stage both implementation and Wiki output, then run `python3 .codestable/tools/cs_knowledge.py drift --cached`.
- Git commit tools do not replace CodeStable writeback. `doctor` passing proves structure only; `drift` reports candidates and does not replace semantic review.
