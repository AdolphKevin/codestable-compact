# Architecture

## Purpose

CodeStable is a project-local knowledge adapter for implementation Agents. It has two boundaries:

```text
read boundary  = produce relevant project context without writes
write boundary = create/update one logical task note and persist selected durable knowledge after acceptance
```

It does not orchestrate software delivery.

## Schema 3 design choices

- Keep the 11 stable categories as storage and coverage axes; add a generated
  topic link view. Moving cards into topic folders would break stable category
  coverage, while copying conclusions into topic pages would create a second
  source of truth.
- Use explicit `{repository, path, symbol}` scopes. Prefix-encoded path strings
  are ambiguous across repositories, and guessing repository identities during
  upgrade could silently corrupt old scope.
- Keep ordinary doctor structural and make complete current-reference checking
  explicit. Making every historical or external reference block all work would
  turn migration debt into an unrelated development outage.
- Require authored, artifact-linked `knowledge_use` evidence. Inferring use from
  retrieval logs, text similarity or diffs cannot distinguish “seen” from
  “changed the work” and would reintroduce telemetry-like behavior.
- Keep retained legacy data and require explicit legacy retrieval. Automatic
  deletion risks project-owned data; automatic fallback makes an obsolete entry
  look current.
- Keep one standard-library distribution file while maintaining ordered source
  sections under `skills/cs/runtime_src`. `scripts/build_runtime.py --check`
  makes the source/distribution boundary deterministic and release-testable.
- Keep `doctor` structural and add a separate read-only `audit` for current
  references, evidence/topic governance, generated artifacts, and Git writeback.
  The audit explicitly leaves business truth unevaluated.

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
facts, and record the disposition. Compatibility upgrade keeps the audited
source page as retained data; ordinary retrieval does not read legacy roots.
Bootstrap also reports current/audited/retained layout and stale or conflicting
`AGENTS.md` entries without modifying that file.

### Knowledge tool

`skills/cs/runtime_src` is the maintenance source. The deterministic build
assembles it into dependency-free `.codestable/tools/cs_knowledge.py`, which supports:

- `brief`: read-only retrieval;
- `learn`: validated task note/card write;
- `consolidate`: transactional duplicate-task archival into one canonical note;
- `doctor`: read-only schema, link and index validation;
- `status`: read-only inventory;
- `reindex`: deterministic generated-index rebuild;
- `drift`: read-only current-reference and Git/task-note candidate checks;
- `audit`: read-only structure, current-reference, governance and delivery acceptance;
- `topics suggest`: read-only deterministic topic proposals;
- `topics update`: state-bound, transactional topic configuration and card assignment;
- `template`: learning payload template.

## Storage model

### Task note

One task note is maintained for each logical task: the same user goal, primary
deliverable and continuous debugging/acceptance chain. An initial interrupted
snapshot may be partial; later payloads update the stable task ID using an
optimistic revision. Updates replace the compact snapshot instead of appending
turn-by-turn text. Only completed tasks normally attach durable cards; a partial
knowledge-migration may attach individually evidenced accepted/verified facts
while its remaining page ledger stays pending.

Task notes are historical provenance, not automatically current truth. Archived
duplicates remain addressable for audit but are excluded from default retrieval
and recent-task presentation.

### Knowledge card

A card expresses one durable project fact, constraint, risk, acceptance rule or decision. It belongs to one of 11 categories and includes:

- current/proposed/deprecated/superseded status;
- verified/accepted/inferred confidence;
- structured repository/path/symbol scope, legacy paths/symbols, topics and tags;
- structured evidence and rationale;
- context, alternatives, consequences and future-use scenarios for decisions;
- source task;
- fingerprint for deduplication;
- supersedes/superseded-by links.

### Human pages

`PROJECT.md` and each category `README.md` contain explicit canonical markers.
Text inside those markers is always eligible for retrieval and may be curated
manually. An empty category summary with current cards is a non-blocking doctor
warning. An optional summary-review marker binds the human summary to the
current card ID/revision/conclusion digest; `audit` reports missing or stale
review metadata unless a healthy explicit topic view provides that navigation.

### Generated indexes

`index.jsonl`, root `INDEX.md`, category `INDEX.md`, `TOPICS.md` and `HISTORY.md`
are deterministic projections of cards and task notes. The root is the only
current entry; category indexes show current/proposed knowledge, the topic view
cross-links current cards without copying their conclusions, and the history
view preserves deprecated/superseded chains and archived/cancelled tasks. They
can be checked or rebuilt and are not the source of truth.

## Retrieval

`brief` scans the current filesystem rather than trusting a possibly stale index. It scores documents using:

- lexical overlap for English and CJK text;
- exact or prefix path scope;
- symbol scope;
- exact repository scope and configured business topic;
- tags and titles;
- category hints;
- pinned/manual summaries;
- status and source type.

Current cards, proposed cards, historical cards, task notes and legacy pages are
separate result groups. Superseded cards are excluded by default. A document must have a real relevance
signal such as pinned scope, path/symbol scope, title/tag/path overlap or
multiple content-token matches; category hints only affect ranking. Recent
decisions must satisfy the same relevance rule unless pinned.

Legacy `.codestable/model` and `.codestable/knowledge` Markdown remains
read-only and lower authority. It is not scanned by ordinary briefs; explicit
`--include-legacy` migration/history requests return it as labeled clues.
Legacy clues never count as current coverage or close a current knowledge gap.

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

Repository-relative legacy paths and Schema 2/3 structured scopes are checked.
`self` resolves to the current repository; configured aliases resolve to their
local roots. Unconfigured or unavailable repositories are explicitly
unverified, never missing. URL/external, legacy model/knowledge and generated
references remain non-blocking. Symbol checks are bounded text scans and a miss
cannot establish that knowledge is wrong. Only current cards can block the
reference check. Git deletion and rename are review signals, not automatic
semantic invalidation.

The Git check classifies Wiki/generated output, docs-only changes and
whitespace-only changes as mechanical. Other changes are semantic candidates
and require a changed completed task-note with final result, verification,
scope coverage and knowledge disposition. Exit codes are 0 for no finding, 1
for actionable candidates and 2 for command/input failure.
