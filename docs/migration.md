# Migration and Schema 3 upgrade

Version 1.2.0 uses configuration Schema 3. Older runtimes must be upgraded
before ordinary commands run; stored cards using legacy `paths`, `symbols`,
free-text evidence and free-text future-use scenarios remain readable. Upgrade
does not invent structured evidence or rewrite old scopes.

The Wiki-wide generic `README.md` is now a managed, versioned file. Upgrade
backs up and refreshes it. `PROJECT.md`, category `README.md` files, cards,
task-notes, unknown files and project directories remain project-owned seeds or
data and are preserved.

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

The new `$cs` Skill ignores old control-plane state. Markdown under
`.codestable/model` and `.codestable/knowledge` remains retained, lower
authority data. Ordinary `brief` does not scan it; migration or history work
must explicitly use `--include-legacy`.

The bootstrap result separates `layout.current`, `layout.audited_history`, and
`layout.preserved_not_for_normal_reads`. It checks `AGENTS.md` for missing,
retired or conflicting CodeStable entries but never modifies that file.

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
6. Treat the whole upgrade as one logical `kind: knowledge-migration` task.
   Create or update one compact task-note, never one ordinary note per page.
   Keep a complete `task.source.knowledge_migration.pages` ledger with each
   legacy path, inventory SHA-256, backup path, outcome, compact disposition
   and current evidence. `items` contains only confirmed, reusable, missing
   facts. Use `learn --dry-run` and its `plan_token`; later batches update the
   same task ID and revision.
7. Run `doctor`. If learn and doctor succeed, confirm that the source hash still
   matches the inventory and the backup copy exists with the same hash. Keep the
   original page as retained compatibility data; do not make it a normal entry.
8. Repeat steps 3–7 for the next page. Do not bulk-copy pages or claims.
9. Run a final `doctor` and representative `brief`. The knowledge migration is
   complete only when every inventoried page is classified and no `pending`
   page remains. Otherwise keep
   `knowledge_migration.complete: false` and the aggregate task `partial`.

Use these page outcomes:

| Outcome | Meaning | Create cards? | Legacy page disposition |
|---|---|---:|---|
| `migrated` | Current code/tests confirm a durable fact absent from current Wiki | Only the missing facts | Retain; exclude from normal reads |
| `covered` | Current Wiki already expresses every still-valid durable fact | No | Retain; exclude from normal reads |
| `obsolete` | Current behavior disproves it or it has no durable future value | No | Retain for traceability; exclude from normal reads |
| `pending` | Current truth or coverage cannot be established | No | Retain and report migration incomplete |

The aggregate source ledger is structured and deliberately contains no legacy
body, raw prompt or command transcript:

```json
{
  "knowledge_migration": {
    "complete": false,
    "pages": [
      {
        "path": ".codestable/model/decisions/example.md",
        "sha256": "<64 lowercase hex characters>",
        "backup_path": ".codestable/model/decisions/example.md",
        "outcome": "pending",
        "disposition": "Current authority could not be established.",
        "evidence": []
      }
    ]
  }
}
```

The original page and its upgrade backup remain recoverable, while the aggregate
task-note records every audit result and source provenance. Existing cards are
never deleted to resolve a conflict; a replacement card uses `supersedes`.

The Agent must report the upgrade as partial if any page is `pending`, or a
backup or hash check fails.

A partial migration may still create cards for individually verified pages;
those items must be accepted/verified and carry concrete current evidence. This
does not make the aggregate upgrade complete. Re-running the same audit snapshot
is idempotent, and later progress updates the same task-note rather than adding
one note per page.

## Configuration and repository mappings

A legacy mode config is backed up and replaced with the compact
`knowledge_wiki` schema. Project `custom`, `project` and `extensions` keys are
preserved when present. A Schema 1 `knowledge_wiki` config is merged into Schema
2, preserving unknown project keys and legacy read roots while adding the fixed
current/history/topic entries and empty topic/repository mappings. Existing
paths are never rewritten by guessing.
