# Migration from CodeStable 0.x

Version 1.0.0 is intentionally a breaking simplification.

## Removed behavior

The release no longer ships:

- `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap`, `cs-model`;
- active task state/evidence completion tools;
- Harness policies and risk levels;
- observations, feedback, Meta campaigns, evaluation or evolution tools.

The package does not route or gate implementation work.

## Upgrade entry point

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project \
  --upgrade
```

This command is the deterministic structural stage used by `$cs upgrade`; it
is not the complete knowledge migration.

## What is replaced

Only files declared as managed or retired in the new release manifest are changed. Replaced and retired files are copied to:

```text
.codestable/backups/YYYYMMDD-HHMMSS/
```

Known old tool files are retired from `.codestable/tools/` so an Agent cannot accidentally invoke the obsolete control plane. The backup preserves them.

The structural stage also inventories every Markdown page under
`.codestable/model` and `.codestable/knowledge`, records its SHA-256 in
`knowledge_migration.pages`, and copies the page to the same backup. It neither
promotes nor removes those pages.

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

The new `$cs` Skill ignores old control-plane state. Until a legacy knowledge
page has been audited, Markdown under `.codestable/model` and
`.codestable/knowledge` remains available as lower-authority, read-only search
input.

## Required page-by-page knowledge migration

1. Commit or otherwise snapshot the project.
2. Run the structural command with `--upgrade` and inspect its backup path and
   `knowledge_migration.pages`.
3. Audit the first legacy page. Split it into candidate durable claims; do not
   assume the page is current merely because it exists.
4. Follow its paths, symbols and contracts into the current implementation and
   executable tests. A legacy page is a lead, not verification evidence.
5. Search the current Wiki with `brief` and inspect the relevant category
   summary/cards. Mark each confirmed claim as already covered or truly missing.
6. Apply one `learn` payload for that page. It always writes one compact
   task-note; `items` contains only confirmed, reusable, missing facts. Record
   the legacy path, inventory SHA-256, backup path and audit outcome in
   `task.source`. Use `learn --dry-run` and its `plan_token`.
7. Run `doctor`. If learn and doctor succeed, the source hash still matches the
   inventory, and the backup copy exists with the same hash, remove that audited
   page from its original legacy directory.
8. Repeat steps 3–7 for the next page. Do not bulk-copy pages or claims.
9. Run a final `doctor` and representative `brief`. The knowledge migration is
   complete only when every inventoried page is classified and no `pending`
   page remains.

Use these page outcomes:

| Outcome | Meaning | Create cards? | Remove old page? |
|---|---|---:|---:|
| `migrated` | Current code/tests confirm a durable fact absent from current Wiki | Only the missing facts | Yes, after learn/doctor/hash/backup checks |
| `covered` | Current Wiki already expresses every still-valid durable fact | No | Yes, after the same checks |
| `obsolete` | Current behavior disproves it or it has no durable future value | No | Yes, after the same checks |
| `pending` | Current truth or coverage cannot be established | No | No |

Removing an audited source page does not delete history: the exact bytes remain
in the upgrade backup, while the task-note records the audit result and the
source provenance. Existing cards are never deleted to resolve a conflict; a
replacement card uses `supersedes`.

The Agent must report the upgrade as partial if any page is `pending`, a backup
or hash check fails, or an audited page cannot be removed.

## Config migration

A legacy config is backed up and replaced with the compact `knowledge_wiki` schema. Project `custom`, `project` and `extensions` keys are preserved when present. The previous schema/mode is recorded in `migration` metadata; the complete old config remains in the backup.
