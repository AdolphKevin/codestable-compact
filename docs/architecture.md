# Architecture

## Purpose

CodeStable is a project-local knowledge adapter for implementation Agents. It has two boundaries:

```text
read boundary  = produce relevant project context without writes
write boundary = create/update one logical task note and persist selected durable knowledge after acceptance
```

It does not orchestrate software delivery.

## Current-format design choices

- Keep the 11 stable categories as storage and coverage axes; add a generated
  topic link view. Moving cards into topic folders would break stable category
  coverage, while copying conclusions into topic pages would create a second
  source of truth.
- Use explicit `{repository, path, symbol}` scopes. Prefix-encoded path strings
  are ambiguous across repositories, and guessing repository identities could corrupt a scope.
- Keep ordinary doctor structural and make complete current-reference checking
  explicit. Making every historical or external reference block all work would
  turn migration debt into an unrelated development outage.
- Require authored, artifact-linked `knowledge_use` evidence. Inferring use from
  retrieval logs, text similarity or diffs cannot distinguish “seen” from
  “changed the work” and would reintroduce telemetry-like behavior.
- Build knowledge from current source, tests and accepted requirements. Only an
  explicitly authorized full rebuild replaces `.codestable`; ordinary commands
  never delete it or migrate old records.
- Keep one standard-library distribution file while maintaining ordered source
  sections under `skills/cs/runtime_src`. `scripts/build_runtime.py --check`
  makes the source/distribution boundary deterministic and release-testable.
- Keep `doctor` structural and add a separate read-only `audit` for current
  references, evidence/topic governance, generated artifacts, and Git writeback.
  The audit explicitly leaves business truth unevaluated.
- Keep project-local `doctor` responsible for internal bundle consistency, and
  use the current Skill's read-only bootstrap preflight for cross-version
  comparison. An old local runtime cannot reliably know what a newer Skill
  contains, so the external reference remains explicit and auditable.

## Components

### `$cs` Skill

`skills/cs/SKILL.md` defines the Agent behavior:

1. initialize when absent, or explicitly rebuild the selected knowledge base from current evidence;
2. run a read-only task brief;
3. let the Agent perform normal implementation and verification;
4. produce a structured learning payload from actual results;
5. dry-run, apply and doctor the knowledge write.

### Bootstrap

`skills/cs/scripts/bootstrap.py` installs project metadata and Wiki assets while
keeping the executable knowledge runtime in the shared Skill.

The release manifest declares the complete file set used for a new knowledge
base. Existing data is not merged. `--rebuild --dry-run` lists the complete
replacement scope without writes; apply requires the exact plan token, bound to
the project path, current directory and release assets. New assets are prepared
and checked before the old `.codestable` directory is replaced. No automatic
backup is retained, and code or configuration outside that directory is untouched.

Bootstrap creates an empty current-format Wiki, not project knowledge. The Agent
continues by inspecting current code, tests and accepted requirements, writing the
project overview, scoped durable cards and one rebuild task, then checking actual
retrieval and references. See [rebuild](rebuild.md).

### Knowledge tool

`skills/cs/runtime_src` is the maintenance source. The deterministic build
assembles it into dependency-free `skills/cs/scripts/cs_knowledge.py`, which supports:

- `brief`: read-only retrieval;
- `learn`: validated task note/card write;
- `consolidate`: transactional duplicate-task archival into one canonical note;
- `doctor`: read-only schema, link and index validation;
- `status`: read-only inventory;
- `reindex`: deterministic generated-index rebuild;
- `drift`: read-only current-reference and Git/task-note candidate checks;
- `audit`: read-only structure, current-reference, governance and delivery acceptance;
- `topics suggest`: read-only deterministic topic proposals;
- `topics list`: read-only discovery of configured canonical names and aliases;
- `topics update`: state-bound, transactional topic configuration and card assignment;
- `template`: learning payload template.

## Storage model

### Task note

One task note is maintained for each logical task: the same user goal, primary
deliverable and continuous debugging/acceptance chain. An initial interrupted
snapshot may be partial; later payloads update the stable task ID using an
optimistic revision. `template --task-id` reconstructs the current snapshot so
callers do not manually copy metadata or provenance. Updates replace the compact
snapshot instead of appending turn-by-turn text, while historical
`knowledge_use` retains the card revision actually read at the time. Only completed tasks attach durable cards.

Fresh templates are task-only unless the caller explicitly supplies one or more
`--card-category` values. This keeps the workflow independent of subjective task
size: quality gates are uniform, while payload shape follows the actual knowledge
disposition. Runtime defaults and task-level scope/topic/tag inheritance remove
mechanical duplication without inferring conclusions, evidence or future-use
scenarios on the Agent's behalf.

Task notes are historical provenance, not automatically current truth. Archived
duplicates remain addressable for audit but are excluded from default retrieval
and recent-task presentation.

### Knowledge card

A card expresses one durable project fact, constraint, risk, acceptance rule or decision. It belongs to one of 11 categories and includes:

- current/proposed/deprecated/superseded status;
- verified/accepted/inferred confidence;
- structured repository/path/symbol scope, single-repository path/symbol shorthand, topics and tags;
- structured evidence and rationale;
- context, alternatives, consequences and future-use scenarios for decisions;
- source task;
- fingerprint for deduplication;
- supersedes/superseded-by links.

### Human pages

`PROJECT.md` and each category `README.md` contain explicit canonical markers.
Text inside those markers remains eligible for retrieval with adjacent review
status. An empty category summary with current cards is a non-blocking doctor
warning. Summary-review markers bind both the body and explicit source selectors.
Category sources expand current cards and their dependencies; project sources
also include category summaries. Source evidence invalidation propagates to both.
`45_validity.py` supplies the shared read-only model used by brief, projected learn
and audit. No query writes review metadata, and reindex cannot clear review needs.

### Generated indexes

With `wiki.index_storage: local`, dynamic indexes are deterministic projections in
`.codestable/cache/wiki/`, excluded from Git. Wiki root/category/topic/history
pages are stable navigation. Cards and task notes remain the source of truth;
missing caches do not prevent reading or validation. Only local indexes are supported by the current format. See [storage](storage.md).

Staged and branch checks use an in-memory Git read view for configuration,
record discovery, source contents and runtime assembly. They never create a
checkout and never infer staged knowledge from the working tree. Governance
findings identify pre-existing versus introduced or changed issues.

## Retrieval

`brief` scans source records rather than trusting a possibly stale index. Explicit scopes, paths, symbols or topics select focused retrieval; `--broad` enables additional lexical exploration. It scores documents using:

- lexical overlap for English and CJK text;
- exact or prefix path scope;
- symbol scope;
- exact repository scope and configured business topic;
- tags and titles;
- category hints;
- pinned/manual summaries;
- status and source type.

Current cards, proposed cards, historical cards and task notes are
separate result groups. Superseded cards are excluded by default. A document must have a real relevance
signal such as pinned scope, path/symbol scope, title/tag/path overlap or
multiple content-token matches; category hints only affect ranking. Recent
decisions must satisfy the same relevance rule unless pinned.

Only the current Wiki is a retrieval source. Old directories are never scanned
and their presence cannot fill current coverage or close a knowledge gap.

## Conflict model

Current cards with the same normalized title but different conclusions are
reported as possible conflicts. Conflict resolution depends on what the
knowledge claims:

1. current user authority wins;
2. accepted requirements, constraints and decisions describe the intended
   state, so a mismatch may be an implementation defect;
3. verified behavioral facts describe confirmed current behavior, so a
   mismatch requires checking for regression, changed scope or stale knowledge;
4. proposed, inferred, deprecated, superseded and task-note material
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
- similarity candidates that block an unexplained synonymous card;
- optimistic in-place card updates for unchanged conclusions, retaining prior scope in `scope_history`;
- strict current-card checks for evidence, scope and multiple future-use scenarios;
- index rebuild after card/task writes.

The transaction is marked committed only after cards, task note, supersession links and indexes are durable. If a process terminates before that marker, the next `learn` detects the dead writer and restores the pre-write snapshot before planning new work.

Exact duplicate payloads remain backward compatible. Older task-notes without a
`revision` are read as revision 1 and can be updated through the new protocol.
Legacy duplicate notes are never deleted. Explicit consolidation uses the same
state-bound dry-run, lock, recovery journal and rollback model as learn. One
canonical task absorbs card links and symmetric history relations; duplicate
notes become archived audit pointers retaining source, verification and the
original-body hash. Archived records remain machine-indexed for traceability but
are excluded from default retrieval and recent-task/root-index presentation.
Fuzzy matching is advisory because paths discovered during debugging are not a
safe task identity; strong candidates instead require update-by-ID or an
explicit independent-goal reason before a new note can be applied.

## Drift boundary

`doctor` validates Wiki structure, links, indexes and transaction recovery. It
explicitly does not claim that current knowledge matches the implementation.
`drift` reuses the same Markdown record scan and adds two read-only inputs:

- repository path existence and conservative symbol text checks for current cards;
- Git working-tree, staged or `<base>...HEAD` name-status/diff information.

Single-repository path shorthand and structured repository scopes are checked.
`self` resolves to the current repository; configured aliases resolve to their
local roots. Unconfigured or unavailable repositories are explicitly
unverified, never missing. URL/external, legacy model/knowledge and generated
references remain non-blocking. Symbol checks are bounded text scans and a miss
cannot establish that knowledge is wrong. Only current cards can block the
reference check. Git deletion and rename are review signals, not automatic
semantic invalidation.

The Git check classifies Wiki/generated output, docs-only changes and
whitespace-only changes as mechanical. Other changes are semantic candidates
and require a changed completed task-note with final result, verification, at
least one representative path/scope or changed-symbol overlap, and knowledge
disposition. The task scope establishes traceability rather than duplicating the
complete Git manifest; Git-confirmed task deletions and renames are valid scope,
while current-card references still require review. Exit codes are 0 for no
finding, 1 for actionable candidates and 2 for command/input failure.
