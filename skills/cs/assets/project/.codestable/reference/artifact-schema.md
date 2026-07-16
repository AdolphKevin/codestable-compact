# Evidence-state task schema

CodeStable Compact keeps one active aggregate per task. The aggregate is a control surface, not a phase-document bundle.

## Required files

```text
state.json       # current control state; Harness managed
work.md          # concise human/Agent working note
context.json     # live-conversation read receipts; Harness managed
evidence.jsonl   # append-only hash-chained evidence ledger; Harness managed
```

`proof.json` is generated only when a risk policy requires a proof artifact. No other task document is required by default.

## `state.json`

Required top-level fields:

- identity: `schema_version`, `id`, `kind`, `title`, `slug`, timestamps;
- ownership: `actors.owner_id`, `actors.reviewer_ids`;
- task contract: `goal.objective`, `constraints`, `non_goals`, `invariants`, `acceptance`, plus optional machine-readable `acceptance_scope`;
- current control hint: `current_action` in `inspect | propose | execute | verify | learn`;
- risk: `risk.level`, `name`, `reasons`, monotonic `escalations`;
- side effects: allowed/forbidden paths, categories, authorization, rollback requirements and task-start Git baseline;
- working ledger: confirmed facts, assumptions, risks, registered changes and blockers;
- proposal: bounded change, rationale, non-changes and requested evidence;
- evidence summary: required types, status counts, chain head and integrity state;
- completion: eligibility, missing evidence, open assumptions/risks/blockers and Harness verdict;
- links/scope: only current model, knowledge, code paths, symbols and keywords relevant to the task.

There is no authoritative workflow `stage` or `lane`. Legacy state is migrated to an action hint and risk level, but old validation text is never converted into evidence.

## `evidence.jsonl`

Every schema-v2 entry contains:

- `id`, sequence, timestamp, type and `PASS | FAIL | BLOCKED | PARTIAL`;
- producer and source;
- actual command, cwd, exit code and duration when command-backed;
- bounded stdout/stderr tails;
- fingerprints of existing artifacts;
- optional evidence `scope.coverage`;
- deterministic `bindings`;
- `previous_sha256` and `entry_sha256`.

`bindings` make a PASS applicable only to the deliverable it actually checked. They include hashes for the current source/Git snapshot, registered change set, relevant task state, proposal, invariants and acceptance contract. Independent review also binds the reviewed diff. Artifact-backed evidence binds the artifact set and is invalidated if a recorded artifact is replaced, changed or removed. Volatile Harness fields such as completion timestamps and evidence counters are excluded, so recording another evidence entry does not invalidate otherwise current proof.

Legacy schema-v1 entries remain readable and hash-chain verifiable, but they have no provenance bindings and therefore report as `stale`; an upgrade never silently treats an old PASS as current. Completion distinguishes `missing`, `stale` and `scope_mismatch`, and reports the evidence ID that must be rerun or replaced.

Acceptance scope uses `[evidence_type=]scope` tokens. For example, `live_validation=scenario:*` requires full Scenario coverage for `live_validation`; evidence recorded with `scenario:address` is focused and cannot satisfy it. A coverage wildcard may cover a concrete requirement, but a concrete subset never covers a wildcard/full-matrix requirement. Scope may be declared with `contract --acceptance-scope` or inline as `[scope:live_validation=scenario:*]` in an acceptance condition, then recorded with `verify/record --scope`.

The Harness calculates hashes and command results. Completion also checks each required evidence type against its allowed source: command evidence from `command_execution`, state evidence from `state_snapshot`, proof from `proof_assembly`, and declared external review/rollback evidence from `artifact_record`.

The Owner may explain evidence but cannot replace command-backed evidence with an artifact assertion. Local reviewer identity is a declared producer label plus artifact, not a cryptographic identity proof; trusted identity requires Host Adapter attestation.

## `work.md`

Use only sections with an active consumer:

- task contract;
- facts, assumptions and unknowns;
- risks and side effects;
- proposed change;
- changes and decisions;
- evidence and completion;
- durable learning.

Do not create design, checklist, review or acceptance documents merely to represent progress. Keep durable truth in model/knowledge only when future tasks, checkers or humans will consume it.

## `context.json`

Stores file fingerprints read in one live conversation and the action/reason for the read. A receipt avoids redundant reads; it does not prove semantic understanding and never spans conversations.
