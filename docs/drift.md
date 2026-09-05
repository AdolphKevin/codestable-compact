# Drift checks

`drift` is a read-only consistency candidate check. It reuses the Wiki's
Markdown cards and task-notes and does not create another index.

## Commands

```bash
# Working tree, staged changes and untracked files
python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project drift

# Staged changes for pre-commit or a Git commit helper
python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project drift --cached

# Committed branch changes for CI
python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project drift \
  --base origin/main \
  --format json

# Current card references without Git
python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project drift --references-only

# Structural doctor plus the same reference check
python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project doctor --check-current-references
```

Exit codes are stable:

| Code | Meaning |
|---:|---|
| 0 | No actionable candidate was detected |
| 1 | Drift or missing writeback needs review |
| 2 | Invalid arguments, unavailable Git scope or read failure |

Text is the default for humans. `--format json` separates confirmed/actionable
`findings`, `unverified` references, verified references, historical skips, Git
classification and the same `exit_code` for CI.

## Reference policy

Only `current` cards can fail current-reference checks.

| Scope form | Policy |
|---|---|
| `{repository: self, path, symbol}` | Check in the current repository |
| Configured repository alias plus repository-relative path | Check under the configured repository root |
| Unconfigured repository alias | Report `repository-unconfigured`; do not claim that the file is missing |
| Legacy repository-relative `paths` / `symbols` | Continue checking in the current repository |
| URL or `external:` legacy path | Mark unverified as external |
| `legacy:` or `.codestable/model`, `.codestable/knowledge`, historical backups | Skip as historical/legacy; complete rebuilds remove the old knowledge tree |
| `generated:` or generated Wiki indexes | Skip as generated |
| Absolute path outside the project | Mark unverified as external |

Symbols use conservative bounded text scans over applicable repository files.
`symbol-text-not-found` means only that bounded text scanning did not find the
name. It is unverified, not proof that a business rule or card is wrong.
Current cards with the same category/title and overlapping scope are also
reported so a commit can reuse, merge or explicitly supersede instead of
leaving two competing current records. No fuzzy semantic merge is attempted.

## Git and task-note policy

Wiki output, generated release reports, docs-only changes and whitespace-only
changes do not require a task-note. Other changed files are semantic candidates.
The staged/base diff must include a completed task-note that records:

- final observable result rather than a plan;
- verification actually obtained;
- at least one representative path, structured `self` scope or changed symbol
  directly overlapping the primary semantic change;
- cards created, reused or superseded, or why no durable card was needed.

`--cached` reads configuration, records and referenced source directly from the Git index. It builds indexes in memory, so unrelated unstaged work cannot block or satisfy the check. A partial staged supersession still fails. `--base` reads the committed HEAD snapshot and ignores staged and working changes. Neither mode writes a checkout or changes Git state.

The task note is not a complete Git file manifest; a large refactor should keep
compact representative scope instead of enumerating every touched file. A
Git-confirmed deleted or renamed path is accepted as task scope by `learn`.
No knowledge card is required when the task produced no stable reusable fact.
Deleting or renaming a path referenced by a current card still requires review,
and `drift` never changes card status. If the conclusion was replaced, a
verified new card must explicitly `supersedes` the old one.

Normal `doctor` remains a structure check and reports entry/configuration
warnings without making historical reference debt block all work.
`doctor --check-current-references` adds the complete current-reference scan.
`learn` returns a non-blocking `reference_check` scoped to the task, planned
cards and cards named by `knowledge_use`. Its default compact JSON keeps
actionable findings, unverified references and counts without the full
verified-reference list; use `learn --full` only for complete diagnostics. `drift`
additionally compares Git changes and representative task-note coverage.

## Integration

Minimal pre-commit hook:

```sh
#!/bin/sh
exec python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project drift --cached
```

Minimal CI step:

```sh
git fetch origin main
python3 /path/to/cs/scripts/cs_knowledge.py --root /path/to/project drift \
  --base origin/main \
  --format json
```

A Git commit helper should invoke staged drift after the implementation and
CodeStable Wiki changes have both been staged. It must not silently create,
supersede or edit knowledge.
