# Drift checks

`drift` is a read-only consistency candidate check. It reuses the Wiki's
Markdown cards and task-notes and does not create another index.

## Commands

```bash
# Working tree, staged changes and untracked files
python3 .codestable/tools/cs_knowledge.py drift

# Staged changes for pre-commit or a Git commit helper
python3 .codestable/tools/cs_knowledge.py drift --cached

# Committed branch changes for CI
python3 .codestable/tools/cs_knowledge.py drift \
  --base origin/main \
  --format json

# Current card references without Git
python3 .codestable/tools/cs_knowledge.py drift --references-only

# Structural doctor plus the same reference check
python3 .codestable/tools/cs_knowledge.py doctor --check-current-references
```

Exit codes are stable:

| Code | Meaning |
|---:|---|
| 0 | No actionable candidate was detected |
| 1 | Drift or missing writeback needs review |
| 2 | Invalid arguments, unavailable Git scope or read failure |

Text is the default for humans. `--format json` returns `findings`, explicit
`skipped_references`, Git classification and the same `exit_code` for CI.

## Reference policy

Only `current` cards can fail current-reference checks.

| Path form | Policy |
|---|---|
| Repository-relative path | Check existence and use it for symbol scanning |
| URL or `external:` | Skip as external |
| `legacy:` or `.codestable/model`, `.codestable/knowledge`, backups | Skip as historical/legacy |
| `generated:` or generated Wiki indexes | Skip as generated |
| Absolute path outside the project | Skip as external |

Symbols use conservative bounded text scans over applicable repository files.
A missing symbol is a review candidate, not proof that a business rule is false.
Current cards with the same category/title and overlapping scope are also
reported so a commit can reuse, merge or explicitly supersede instead of
leaving two competing current records. No fuzzy semantic merge is attempted.

## Git and task-note policy

Wiki output, generated release reports, docs-only changes and whitespace-only
changes do not require a task-note. Other changed files are semantic candidates.
The staged/base diff must include a completed task-note that records:

- final observable result rather than a plan;
- verification actually obtained;
- paths or symbols covering the primary changed scope;
- cards created, reused or superseded, or why no durable card was needed.

`--cached` also fails when `.codestable/wiki` has unstaged changes, because the
working copy could otherwise make a staged commit appear to contain a card or
supersession that is not actually in the index.

No knowledge card is required when the task produced no stable reusable fact.
Deleting or renaming a path referenced by a current card requires review, but
`drift` never changes card status. If the conclusion was replaced, a verified
new card must explicitly `supersedes` the old one.

## Integration

Minimal pre-commit hook:

```sh
#!/bin/sh
exec python3 .codestable/tools/cs_knowledge.py drift --cached
```

Minimal CI step:

```sh
git fetch origin main
python3 .codestable/tools/cs_knowledge.py drift \
  --base origin/main \
  --format json
```

A Git commit helper should invoke staged drift after the implementation and
CodeStable Wiki changes have both been staged. It must not silently create,
supersede or edit knowledge.
