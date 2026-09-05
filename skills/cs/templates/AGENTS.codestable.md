## CodeStable knowledge

- Treat `.codestable/wiki/INDEX.md` as the only current entry. Start every development task with the current Skill's read-only bootstrap `--check`, then run `python3 <current-skill-directory>/scripts/cs_knowledge.py --root <project-root> brief --task '<request>'`; add repository scopes when known.
- Never guess a business-topic name. Omit `--topic` when uncertain or use read-only `topics list` first; an unknown brief topic is only a warning.
- `$cs` context does not automatically carry into a later task or Agent turn.
- Before completing a development task, run `learn --dry-run`, apply its plan token, then run `doctor`.
- Record created, reused or superseded cards in `task.knowledge_summary`; explain why when no durable card is needed.
- A strong existing-task candidate must be updated by ID/revision unless an independent goal is explicitly justified.
- Use `consolidate` for historical duplicate task-notes; do not delete or hand-edit them.
- Treat `knowledge_use` as optional traceable evidence of a concrete design, scope, implementation, test or review effect; each claim needs the card revision, an artifact, result and card-to-evidence mapping. A brief receipt proves display only.
- Only the current knowledge format is supported. Old data requires an explicitly authorized `$cs rebuild`; never infer deletion authorization from an ordinary task or tool update. Rebuild from current code, tests and accepted requirements; an empty layout is not completed knowledge.
- Review current cards when deleting, renaming or replacing implementation paths or symbols.
- Before commit, stage both implementation and Wiki output, then run `python3 <current-skill-directory>/scripts/cs_knowledge.py --root <project-root> drift --cached`.
- Git commit tools do not replace CodeStable writeback. `doctor` passing proves structure only; `drift` reports candidates and does not replace semantic review.
- Use read-only `audit` for combined structure, current-reference, governance and delivery checks; it does not prove business truth.
