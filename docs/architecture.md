# CodeStable Compact 0.5 architecture

## 1. Purpose

CodeStable Compact is a software-production control plane. It does not encode a universal SDLC sequence. It lets an Owner Agent explore and implement autonomously while the Harness enforces evidence provenance and Git-visible task boundaries and owns completion.

```text
Intent → Task Contract → Owner Agent → Tool Plane
                         ↕
                  Evidence State
                         ↓
                Completion Policy
                         ↓
              Independent Challenge
                         ↓
           Accept / Repair / Rollback
                         ↓
              Durable Learning
```

## 2. Responsibility boundaries

### Owner

Understands the goal, inspects the real system, forms hypotheses, chooses implementation order, executes changes, responds to feedback and explains evidence. Owner does not grant completion.

### Harness

Owns deterministic state, Git-visible write comparison, authorization, monotonic risk, command execution records, artifact fingerprints, evidence integrity, required evidence and completion verdicts.

### Reviewer

Attempts to disprove the Owner's completion claim. It checks missed scope, hidden side effects, request drift, invalid tests, residual dual implementations and unsupported proof. L2/L3 review needs a declared non-Owner producer and artifact; trusted identity requires Host Adapter attestation.

## 3. Evidence state

`state.json` is the current control state, not a workflow cursor. Its important domains are:

- `goal`: objective, acceptance, constraints, non-goals and invariants;
- `proposal`: bounded change hypothesis when policy requires it;
- `risk`: current level, reasons and escalation history;
- `side_effects`: allowed/forbidden paths, task-start Git baseline, external categories, authorization and rollback;
- `ledger`: facts, assumptions, risks and actual changes;
- `blockers`: conditions preventing further work or completion;
- `evidence`: summary and chain position;
- `completion`: current eligibility/verdict and missing conditions.

`evidence.jsonl` is append-only and hash chained. Evidence entries include producer, type, status, summary, command result or artifact fingerprints, sequence, previous hash and current hash. Tampering invalidates the chain and blocks completion.

## 4. Repeated control actions

`inspect`, `propose`, `execute`, `verify` and `learn` are labels for the current control intent. They improve context retrieval and observation but do not impose order. For example:

```text
inspect → execute → verify(FAIL) → inspect → propose → execute → verify(PASS)
```

A trivial edit may use only execute/verify. A critical change may alternate all five actions many times.

## 5. Risk engine

Risk starts from the contract and may rise when the Harness observes actual changed paths or declared side effects. It never falls during a task.

- source-code changes establish at least L1;
- several changed paths or top-level modules establish at least L2;
- executable authorization, security, payment, migration, schema, deletion, rollback or core-state surfaces establish L3;
- explicit side effects and discovered risks can raise the level further.

Each level selects an exact evidence policy. Runtime and bootstrap repair unsafe local configuration back to the canonical non-bypassable requirements.

## 6. Verification plane

Harness-backed command verification records:

```text
command
cwd
started/finished time
duration
exit code
bounded stdout/stderr
artifact fingerprints
PASS / FAIL / BLOCKED / PARTIAL
```

`PASS` is produced by a successful command, Harness state snapshot/derived proof, or a fingerprinted external artifact. Completion accepts it only when that source is permitted for the required evidence type. The distinction among assertion failure, unavailable environment and incomplete evidence remains visible.

State-backed snapshots derive audit, proposal, invariant or scope evidence from current state. They cannot be replaced with a free-form Owner assertion. `proof` is machine generated from already recorded evidence and does not create missing prerequisite evidence.

## 7. Completion gate

A `done` request is eligible only when all applicable conditions hold:

- objective and acceptance exist;
- L2/L3 invariants and proposal exist;
- every Git-visible change since the task baseline is registered and inside the write scope;
- required facts exist;
- no blocking assumption, high/critical open risk or blocker remains;
- every risk-required evidence type has at least one source-valid `PASS`;
- independent review has a declared non-Owner producer and artifact;
- evidence chain integrity is valid;
- L3 rollback boundary is declared and proven.

`COMPLETED`, `BLOCKED`, `PARTIAL` and `CANCELLED` are terminal task verdicts. Reloading state preserves them. Archive additionally requires current integrity and eligibility, so later tampering cannot be hidden by moving the task.

## 8. Context plane

Normal reads are scoped to `.codestable/model`, `.codestable/knowledge` and active work. `plan` produces action-specific candidates and `receipt` records file hashes for one session. Archive requires an explicit search reason.

Observations, feedback, evaluation, evolution candidates, Meta campaigns and Harness history are excluded from normal context. A read-only `cs_harness.py` exposes only promoted playbook entries filtered by action, risk and keywords.

## 9. Meta plane

The Meta loop is explicit and isolated:

```text
observe → select → classify → propose Harness change
→ replay fixture-covered policy → validity pre-pass
→ external signed evaluation → accept or reject
→ promote with policy authority or rollback
```

Candidates can modify only manifest-declared surfaces. Private holdout inputs and evaluator keys remain outside candidate/worker workspaces. Underpowered evidence cannot support promotion.
