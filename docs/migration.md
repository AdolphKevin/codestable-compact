# Migration and Schema 3 upgrade

Version 1.2.2 uses configuration Schema 3 and runs the knowledge command from
the installed Skill. Projects keep knowledge, configuration and Wiki data, but
do not install or maintain another copy of the command program.

Stored cards using legacy `paths`, `symbols`, free-text evidence and free-text
future-use scenarios remain readable. Upgrade does not invent structured
evidence or rewrite old scopes.

The Wiki-wide generic `README.md` is a managed, versioned file and is refreshed
in place. `PROJECT.md`, category `README.md` files, cards, task notes, unknown
files and project directories remain project-authored data and are preserved.

## Removed behavior

The release no longer ships:

- `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap`, `cs-model`;
- active task state or evidence-completion tools;
- Harness policies and risk levels;
- observations, feedback, Meta campaigns, evaluation or evolution tools.

The package does not route or gate implementation work.

## Upgrade entry point

First run the read-only layout and command-contract check:

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project \
  --check
```

The check validates the project's data structure and the shared Skill command.
It does not require or execute a project-local knowledge program.

```bash
python3 /path/to/codestable-compact/skills/cs/scripts/bootstrap.py \
  --root /path/to/project \
  --upgrade
```

This command is the deterministic structural stage used by `$cs upgrade`; it
is not the complete knowledge migration. It refreshes release-owned files in
place, retires only files declared in the release manifest, inventories legacy
knowledge pages and verifies the shared command contract.

## In-place file handling

Upgrade does not create `.codestable/backups` or copy files into an automatic
backup tree.

- Release-owned managed files are updated in place.
- Release-owned retired files are removed in place only during explicit
  upgrade.
- Project-authored knowledge and work data stay at their existing paths.
- Existing historical `.codestable/backups` directories are ignored and left
  untouched.
- An invalid `.codestable/config.json` stops the upgrade and is preserved for
  explicit repair; it is not silently replaced.

Known old tool files are retired from `.codestable/tools/` so the project uses
the current shared Skill command instead of a stale local copy.

The structural stage inventories every Markdown page under
`.codestable/model` and `.codestable/knowledge`. Each inventory item records the
original path, SHA-256 and byte count. The page stays in place until its meaning
is checked against current code, tests and Wiki knowledge. The upgrader never
promotes, rewrites or removes these legacy pages automatically.

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
- `.codestable/harness`;
- existing `.codestable/backups`.

The new `$cs` Skill ignores old control-plane state. Markdown under
`.codestable/model` and `.codestable/knowledge` remains retained, lower
authority data. Ordinary `brief` does not scan it; migration or history work
must explicitly use `--include-legacy`.

The bootstrap result separates `layout.current`, `layout.audited_history`, and
`layout.preserved_not_for_normal_reads`. It checks `AGENTS.md` for missing,
retired or conflicting CodeStable entries but never modifies that file.

## Required page-by-page knowledge migration

1. Run the structural command with `--upgrade` and inspect
   `knowledge_migration.pages`.
2. Audit the first legacy page. Split it into candidate durable claims; do not
   assume the page is current merely because it exists.
3. Follow its paths, symbols and contracts into the current implementation and
   executable tests. A legacy page is a lead, not verification evidence.
4. Search the current Wiki with `brief` and inspect the relevant category
   summary and cards. Mark each confirmed claim as already covered or truly
   missing.
5. Treat the whole upgrade as one logical `kind: knowledge-migration` task.
   Create or update one compact task note, never one ordinary note per page.
   Keep a complete `task.source.knowledge_migration.pages` ledger with each
   legacy path, inventory SHA-256, byte count, outcome, compact disposition and
   current evidence. `items` contains only confirmed, reusable, missing facts.
   Use `learn --dry-run` and its `plan_token`; later batches update the same task
   ID and revision.
6. Run `doctor`. If learn and doctor succeed, confirm that the source path still
   exists and its SHA-256 and byte count still match the inventory.
7. Repeat the audit for the next page. Do not bulk-copy pages or claims.
8. Run a final `doctor` and representative `brief`. The knowledge migration is
   complete only when every inventoried page is classified and no `pending`
   page remains. Otherwise keep `knowledge_migration.complete: false` and the
   aggregate task `partial`.

Use these page outcomes:

| Outcome | Meaning | Create cards? | Legacy page disposition |
|---|---|---:|---|
| `migrated` | Current code/tests confirm a durable fact absent from current Wiki | Only the missing facts | Retain in place; exclude from normal reads |
| `covered` | Current Wiki already expresses every still-valid durable fact | No | Retain in place; exclude from normal reads |
| `obsolete` | Current behavior disproves it or it has no durable future value | No | Retain in place for traceability; exclude from normal reads |
| `pending` | Current truth or coverage cannot be established | No | Retain in place and report migration incomplete |

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
        "bytes": 123,
        "outcome": "pending",
        "disposition": "Current authority could not be established.",
        "evidence": []
      }
    ]
  }
}
```

The original page remains available at its recorded path, while the aggregate
task note records every audit result and source provenance. Existing cards are
never deleted to resolve a conflict; a replacement card uses `supersedes`.

The Agent must report the upgrade as partial if any page is `pending`, or if a
source path, hash or byte-count check fails. A partial migration may still
create cards for individually verified pages; those items must carry concrete
current evidence. Re-running the same audit snapshot is idempotent, and later
progress updates the same task note rather than adding one note per page.

## Configuration and repository mappings

A valid legacy mode config is normalized to the compact `knowledge_wiki`
schema during explicit upgrade. Project `custom`, `project` and `extensions`
keys are preserved when present. A Schema 1 `knowledge_wiki` config is merged
into Schema 3, preserving unknown project keys and legacy read roots while
adding the fixed current/history/topic entries and empty topic/repository
mappings. Existing paths are never rewritten by guessing.

An invalid config is not eligible for automatic normalization. Upgrade reports
the error and leaves the file unchanged so the project owner can repair it with
full context.
