# Knowledge storage and scoped validation

The project owns its Markdown knowledge, task history, configuration, summaries
and unknown files. One stable conclusion remains one card under its canonical
category. Topics link those cards across categories; they never duplicate the
conclusion. Status and supersession express history without moving or deleting
source files.

## Source and derived files

New installs use `wiki.index_storage: local`. Source records are committed;
dynamic category, topic, history and task directories plus `index.jsonl` live in
`.codestable/cache/wiki/`. The cache directory contains a small `.gitignore`;
keep that file when clearing `cache/wiki/`. Stable Markdown entry pages stay in
the Wiki and do not change after every task. A normal `learn` changes only its
task note, new or updated cards, and any explicitly superseded cards in Git.

`brief` reads source documents. `doctor` validates their structure and relations,
and separately reports an absent or stale cache as rebuildable. Both work after
the cache is removed. `reindex --dry-run` lists the deterministic reconstruction
without writing; `reindex` applies it. Cache regeneration does not invalidate a
learning plan when the source knowledge and implementation have not changed.
Source and cache writes still share the existing recovery transaction.

## Exact Git input

`drift --cached` and `audit --cached` read the Git index, including partially
staged files. Configuration, record enumeration, metadata, referenced source
and runtime assembly use that same view. `--base <ref>` compares the merge base
to HEAD and reads HEAD contents. Checks never create a temporary checkout or
write files or Git objects.

Unrelated working edits can neither satisfy nor break the staged check. A
completed working note cannot hide a partial staged note; staging only one side
of a supersession fails. Missing referenced files and symbols are evaluated
against the checked source version. Configured external repositories remain
explicit external working sources; the report does not claim their contents
belong to this repository's Git snapshot.

`audit` retains the selected project policy while labeling governance findings
as existing or introduced/changed against the baseline. It still cannot decide
whether a business conclusion is true.

## Complete rebuild

The current format uses Schema 4 and local indexes. Old configurations, record
migration and versioned indexes are unsupported. An explicitly authorized rebuild
replaces the target `.codestable`, then the Agent fills it from current code,
tests and requirements. See [rebuild](rebuild.md).

New writes omit empty sections and keep evidence, scope, source and reuse
information once in front matter. Normal updates preserve the current knowledge
base's IDs and supersession history; a full rebuild starts a new knowledge base.

## Validation

`tests/test_compact_storage.py` covers source-only Git changes, deterministic
cache repair, zero-write reads, cache-independent plans, compact update round
trips, focused retrieval, partial staging, source-version checks, incomplete
supersession, committed checks, baseline classification, rebuild isolation
and rollback after cache-write failure.
