# Architecture

## Purpose

CodeStable is a project-local knowledge adapter for implementation Agents. It has two boundaries:

```text
read boundary  = produce relevant project context without writes
write boundary = persist a completed task note and selected durable knowledge
```

It does not orchestrate software delivery.

## Components

### `$cs` Skill

`skills/cs/SKILL.md` defines the Agent behavior:

1. bootstrap or upgrade when needed;
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
- **preserve roots** document project data boundaries that must never be deleted.

### Knowledge tool

`.codestable/tools/cs_knowledge.py` is dependency-free and supports:

- `brief`: read-only retrieval;
- `learn`: validated task note/card write;
- `doctor`: read-only schema, link and index validation;
- `status`: read-only inventory;
- `reindex`: deterministic generated-index rebuild;
- `template`: learning payload template.

## Storage model

### Task note

One task note is written for each applied learning payload. It records the request, actual processing summary, final result, verification, paths, symbols, tags, source metadata and linked cards.

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

Superseded cards are excluded by default. Recent current decisions are included even when lexical relevance is weak. Legacy `.codestable/model` and `.codestable/knowledge` Markdown remains read-only and lower authority.

## Conflict model

Current cards with the same normalized title but different conclusions are reported as possible conflicts. Resolution is explicit:

1. determine current truth from user authority, accepted knowledge and executable behavior;
2. write a new card;
3. list old card IDs in `supersedes`;
4. retain old Markdown as historical provenance.

## Write safety

`learn` validates the full payload and supersession targets before writing. Applied writes use:

- an exclusive wiki lock;
- atomic replacement for each file;
- a dry-run plan token binding payload, identifiers, timestamp and pre-write knowledge state;
- a recovery journal prepared before project knowledge is mutated;
- automatic rollback for in-process failures and abandoned-transaction recovery on the next write;
- idempotent task fingerprints;
- card fingerprints for duplicate reuse;
- index rebuild after card/task writes.

The transaction is marked committed only after cards, task note, supersession links and indexes are durable. If a process terminates before that marker, the next `learn` detects the dead writer and restores the pre-write snapshot before planning new work.
