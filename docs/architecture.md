# Architecture

## Purpose

CodeStable is a project-local knowledge adapter for implementation Agents. It has two boundaries:

```text
read boundary  = produce relevant project context without writes
write boundary = create/update one logical task note and persist selected durable knowledge after acceptance
```

It does not orchestrate software delivery.

## Components

### `$cs` Skill

`skills/cs/SKILL.md` defines the Agent behavior:

1. bootstrap when needed, or run structural upgrade plus page-by-page legacy knowledge audit;
2. run a read-only task brief;
3. let the Agent perform normal implementation and verification;
4. produce a structured learning payload from actual results;
5. dry-run, apply and doctor the knowledge write.

### Bootstrap

`skills/cs/scripts/bootstrap.py` copies the canonical runtime from `skills/cs/assets/project` into a target project.

Files are classified by `.codestable/manifest.json`:

- **managed files** may be refreshed on upgrade after backup;
- **seed files** are created only when missing and then become project-authored;
- **retired files** are known old control-plane tools removed only during `--upgrade`, after backup;
- **preserve roots** document project data boundaries that structural bootstrap
  never deletes and that later semantic migration must keep recoverable.
- **legacy knowledge roots** declare the old Markdown sources that structural
  upgrade inventories and backs up without semantically promoting or removing.

Structural upgrade is deliberately content-agnostic. `$cs upgrade` owns the
semantic continuation: one old page at a time, compare it with current
implementation/tests, check current Wiki coverage, learn only missing durable
facts, then remove the audited source page only after its byte-identical backup
and task-note provenance are durable.

### Knowledge tool

`.codestable/tools/cs_knowledge.py` is dependency-free and supports:

- `brief`: read-only retrieval;
- `learn`: validated task note/card write;
- `doctor`: read-only schema, link and index validation;
- `status`: read-only inventory;
- `reindex`: deterministic generated-index rebuild;
- `drift`: read-only current-reference and Git/task-note candidate checks;
- `template`: learning payload template.

## Storage model

### Task note

One task note is maintained for each logical task: the same user goal, primary
deliverable and continuous debugging/acceptance chain. An initial interrupted
snapshot may be partial; later payloads update the stable task ID using an
optimistic revision. Updates replace the compact snapshot instead of appending
turn-by-turn text. Only completed tasks can attach durable cards.

Task notes are historical provenance, not automatically current truth.

### Knowledge card

A card expresses one durable project fact, constraint, risk, acceptance rule or decision. It belongs to one of 11 categories and includes:

- current/proposed/deprecated/superseded status;
- verified/accepted/inferred confidence;
- path, symbol and tag scope;
- evidence and rationale;
- source task;
- fingerprint for deduplication;
- supersedes/superseded-by links.

### Human pages

`PROJECT.md` and each category `README.md` contain explicit canonical markers. Text inside those markers is always eligible for retrieval and may be curated manually.

### Generated indexes

`index.jsonl`, root `INDEX.md`, and category `INDEX.md` files are deterministic projections of cards and task notes. They contain hashes and can be checked or rebuilt. They are not the source of truth.

## Retrieval

`brief` scans the current filesystem rather than trusting a possibly stale index. It scores documents using:

- lexical overlap for English and CJK text;
- exact or prefix path scope;
- symbol scope;
- tags and titles;
- category hints;
- pinned/manual summaries;
- status and source type.

Current Wiki sources, task notes and legacy pages are separate retrieval pools.
Superseded cards are excluded by default. A document must have a real relevance
signal such as pinned scope, path/symbol scope, title/tag/path overlap or
multiple content-token matches; category hints only affect ranking. Recent
decisions must satisfy the same relevance rule unless pinned.

Legacy `.codestable/model` and `.codestable/knowledge` Markdown remains
read-only and lower authority. It is returned as explicitly labeled clues only
when no authoritative current Wiki result qualifies. Legacy clues never count
as current coverage or close a current knowledge gap.

## Conflict model

Current cards with the same normalized title but different conclusions are
reported as possible conflicts. Conflict resolution depends on what the
knowledge claims:

1. current user authority wins;
2. accepted requirements, constraints and decisions describe the intended
   state, so a mismatch may be an implementation defect;
3. verified behavioral facts describe confirmed current behavior, so a
   mismatch requires checking for regression, changed scope or stale knowledge;
4. proposed, inferred, deprecated, superseded, task-note and legacy material
   cannot independently resolve the conflict;
5. after determining which conclusion is stale, write the replacement card,
   list old card IDs in `supersedes`, and retain provenance.

## Write safety

`learn` validates the full payload and supersession targets before writing. Applied writes use:

- an exclusive wiki lock;
- atomic replacement for each file;
- a dry-run plan token binding payload, identifiers, timestamp and pre-write knowledge state;
- a workspace fingerprint binding the plan to the implementation state reviewed by dry-run;
- a recovery journal prepared before project knowledge is mutated;
- automatic rollback for in-process failures and abandoned-transaction recovery on the next write;
- idempotent task fingerprints;
- stable task IDs with optimistic revisions for same-task updates;
- deterministic duplicate-task and same-title-card suggestions in dry-run;
- card fingerprints for duplicate reuse;
- index rebuild after card/task writes.

The transaction is marked committed only after cards, task note, supersession links and indexes are durable. If a process terminates before that marker, the next `learn` detects the dead writer and restores the pre-write snapshot before planning new work.

Exact duplicate payloads remain backward compatible. Older task-notes without a
`revision` are read as revision 1 and can be updated through the new protocol.
Legacy duplicate notes are never deleted automatically; consolidation must keep
their provenance and be an explicit maintenance operation. Fuzzy matching is
advisory because paths discovered during debugging are not a safe task identity.

## Drift boundary

`doctor` validates Wiki structure, links, indexes and transaction recovery. It
explicitly does not claim that current knowledge matches the implementation.
`drift` reuses the same Markdown record scan and adds two read-only inputs:

- repository path existence and conservative symbol text checks for current cards;
- Git working-tree, staged or `<base>...HEAD` name-status/diff information.

Repository-relative paths are checked. URL/`external:`, legacy model/knowledge
and backup paths, and generated Wiki indexes use explicit non-blocking skip
policies. Only current cards can block the reference check. Git deletion and
rename are review signals, not automatic semantic invalidation.

The Git check classifies Wiki/generated output, docs-only changes and
whitespace-only changes as mechanical. Other changes are semantic candidates
and require a changed completed task-note with final result, verification,
scope coverage and knowledge disposition. Exit codes are 0 for no finding, 1
for actionable candidates and 2 for command/input failure.
