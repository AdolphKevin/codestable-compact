# Migration from CodeStable 0.x

Version 1.0.0 is intentionally a breaking simplification.

## Removed behavior

The release no longer ships:

- `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap`, `cs-model`;
- active task state/evidence completion tools;
- Harness policies and risk levels;
- observations, feedback, Meta campaigns, evaluation or evolution tools.

The package does not route or gate implementation work.

## Upgrade command

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project \
  --upgrade
```

## What is replaced

Only files declared as managed or retired in the new release manifest are changed. Replaced and retired files are copied to:

```text
.codestable/backups/YYYYMMDD-HHMMSS/
```

Known old tool files are retired from `.codestable/tools/` so an Agent cannot accidentally invoke the obsolete control plane. The backup preserves them.

## What is preserved

The upgrader does not delete project-authored content under:

- `.codestable/wiki`;
- `.codestable/model`;
- `.codestable/knowledge`;
- `.codestable/work`;
- `.codestable/observations`;
- `.codestable/feedback`;
- `.codestable/evals`;
- `.codestable/evolution`;
- `.codestable/meta`;
- `.codestable/harness`.

Old directories may remain as historical data. The new `$cs` Skill ignores old control-plane state. Markdown under `.codestable/model` and `.codestable/knowledge` remains available as lower-authority, read-only search input.

## Recommended migration sequence

1. Commit or otherwise snapshot the project.
2. Run bootstrap with `--upgrade`.
3. Inspect the returned backup path.
4. Run `python3 .codestable/tools/cs_knowledge.py doctor`.
5. Run a representative `brief` and confirm old model/knowledge is visible where relevant.
6. Complete one real task through `$cs` and inspect the generated task note/cards.
7. Gradually promote important old knowledge into current cards; do not bulk-copy stale work logs.

## Config migration

A legacy config is backed up and replaced with the compact `knowledge_wiki` schema. Project `custom`, `project` and `extensions` keys are preserved when present. The previous schema/mode is recorded in `migration` metadata; the complete old config remains in the backup.
