# Architecture

## 1. Design thesis

CodeStable Compact treats the software system—not the agent—as the durable center of work.

The runtime separates information by **semantic half-life**:

| Layer | Meaning | Lifetime | Default retrieval |
|---|---|---:|---|
| `model/` | What the software is and must remain true now | Long | Yes, through a small index and explicit links |
| `knowledge/` | Reusable engineering knowledge that survived one concrete task | Long | Yes, targeted search only |
| `work/active/` | What is being changed now | Short | Yes, exact task only |
| `work/archive/` | How old work happened | Historical | No |
| Source/tests/config | Executable evidence | Current | Yes, scoped to the touched surface |

This separation avoids two common category errors:

1. treating every historical design as current truth;
2. repeatedly loading all durable documents merely because they exist.

## 2. User-facing topology

```text
                        ┌───────────┐
real request ─────────▶ │    cs     │
                        └─────┬─────┘
                  resume first│otherwise classify
        ┌──────────────┬──────┼──────┬──────────────┐
        ▼              ▼      ▼      ▼              ▼
     cs-feat        cs-issue cs-refactor cs-roadmap cs-model
        │              │      │      │              │
        └──────────────┴──────┴──────┴──────────────┘
                         continue now
```

`cs` is not a “recommendation screen.” Routing is an implementation detail and therefore cannot be a default blocking state.

The direct lifecycle skills remain available for expert use, deterministic automation and testing. The ordinary user only needs `/cs`.

## 3. Route-before-ask, evidence-before-ask

The entry follows this order:

1. Parse an explicit command (`init`, `status`, `continue`, `route`, `doctor`) if present.
2. Inspect active work metadata, not full work histories.
3. Resume an exact matching active work item when one exists.
4. Otherwise classify the dominant event type.
5. Inspect repository evidence before asking a question.
6. Start the selected lifecycle in the same invocation.

Questions are reserved for facts that repository evidence cannot provide, such as product intent, an unavailable credential, an irreversible trade-off or two materially different valid contracts.

A route decision itself is never such a fact.

## 4. Event classification

| Event type | Positive signals | Negative signals |
|---|---|---|
| `feature` | net-new observable capability, new supported behavior, new integration | existing intended behavior is merely broken |
| `issue` | defect, regression, wrong output, exception, hang, performance degradation | behavior is correct and only structure should improve |
| `refactor` | preserve behavior while changing structure, dependency direction, naming or complexity | user asks for new externally observable behavior |
| `roadmap` | several coordinated capabilities, sequencing/contract uncertainty, multi-system initiative | one bounded deliverable is already clear |
| `model` | vision, domain vocabulary, requirement, contract, ADR, durable knowledge | executable code change is the dominant outcome |

For mixed requests, choose the event that can produce the first independently verifiable outcome, record secondary work, and transition automatically when necessary. Example: a bug caused by architectural rot starts as `issue`; after reproduction and root-cause evidence, it may create a linked `refactor` work item.

## 5. Adaptive lanes

A separate fast-path skill is unnecessary. Complexity is a property of a work item, not a separate user intent.

### `micro`

All must hold:

- bounded to one local surface;
- reversible with a small diff;
- no public API or persistent schema change;
- no security, permissions, payments or destructive operation;
- acceptance can be demonstrated with an existing or small new test.

The skill still inspects evidence and verifies the result. It simply records less ceremony.

### `standard`

Used for normal bounded engineering work. It records intent, evidence, design or root cause, an implementation plan, changed files and verification.

### `high-risk`

Any of the following is enough:

- persistent data migration or destructive data operation;
- public API, protocol, event or schema compatibility;
- authentication, authorization, secrets or security boundary;
- payment, billing, quota or financial correctness;
- cross-service rollout or availability risk;
- irreversible vendor or architecture commitment;
- no credible rollback or verification path.

It requires an explicit rollback/rollout strategy and may create a human Gate.

Lane can be escalated at any time; it should be de-escalated only when evidence removes the triggering risk.

## 6. Work state machine

All executable work uses the same envelope:

```text
created → active → blocked? → active → done → archived
                 └─ cancelled ────────────────▶ archived
```

Each kind defines its own `stage` values:

```text
feature:  intake → evidence → design → implement → verify → accept
issue:    intake → reproduce → analyze → fix → verify → accept
refactor: intake → characterize → design → implement → verify → accept
roadmap:  discover → frame → contracts → decompose → review → activate
model:    inspect → edit → validate → index
```

`state.json` is authoritative for status and stage. File presence is supporting evidence, never the state machine itself. This removes the need for repeated Glob-based “where did we stop?” inference.

## 7. Minimal work aggregate

Each active work directory has exactly three required files.

### `state.json`

Machine-readable control state:

- identity, kind, lane, stage and status;
- scope paths, symbols and keywords;
- explicit links to model and knowledge documents;
- Gate status and reasons;
- verification commands and last result;
- parent/child work relations.

It is intentionally small and is always safe to read.

### `work.md`

One human-readable aggregate containing only the sections appropriate for the lane and kind. Design review, code review, QA and acceptance findings are appended to this document rather than split into one file per phase.

A passing transient review does not require prose. Only decisions, failures, exceptions, evidence and durable conclusions are recorded.

### `context.json`

A receipt map. For every previously read path it stores:

- normalized relative path;
- SHA-256 digest;
- size and modification time;
- stage and reason for reading;
- timestamp.

It never caches file content. An unchanged receipt may be reused only when its session key belongs to the same live conversation and the understanding is still present there. A cold conversation uses a new key and rereads the necessary material.

## 8. Context planner

The planner is a conservative filter, not an autonomous semantic oracle.

```bash
python3 .codestable/tools/cs_context.py plan \
  --work <id> --stage <stage> --session <live-conversation-key>
```

It returns four buckets:

- `always`: small control state;
- `read`: required and new/changed paths;
- `reuse`: already read, unchanged paths;
- `missing`: explicit links that no longer resolve.

The planner never recursively scans archive. It does not automatically open every model document. It starts from explicit links in `state.json`; when links have not yet been established, it offers only `model/INDEX.md` as a pointer.

Top-level model and knowledge indexes have a default 160-line budget. When they grow, `cs-model` shards them by bounded context/domain and leaves only pointers at the top level.

### Retrieval ladder

```text
0. Current conversation
1. Exact active work state and current-stage sections
2. attention.md, only if non-empty and changed
3. Explicitly linked model/knowledge documents, only if changed
4. Scoped source, tests, configuration and executable contracts
5. Targeted current-state knowledge search
6. Archive-index search with a written reason; deep historical-content search only after a candidate is identified
```

The skill must not descend to a lower tier merely because that tier exists.

## 9. Current truth vs. history

Historical feature documents can contain obsolete assumptions, abandoned designs and constraints that later changed. They are therefore evidence about the past, not authoritative input to a new design. Archive search first consults the lightweight metadata index; scanning archived bodies requires an explicit `--deep` request and reason.

Before archival, the accepting lifecycle performs a **promotion pass**:

| Finding | Destination |
|---|---|
| Current user-visible capability | `model/requirements/` |
| Stable interface or event shape | `model/contracts/` |
| Architectural trade-off that constrains future work | `model/decisions/` |
| Domain term | `model/domain.md` |
| Reusable pitfall, diagnostic or implementation constraint | `knowledge/notes/` |
| Task-specific discussion, rejected local alternative, transient logs | archive only |

Only promoted material appears in normal future retrieval. The full task remains available for deliberate archaeology.

## 10. Gate model

A Gate means the agent lacks authority to choose safely, not merely that a phase ended.

### Automatic internal checks

These run without stopping the user:

- design consistency and scope review;
- simplest-solution review;
- diff review for correctness, regressions and unnecessary complexity;
- test/lint/typecheck/acceptance execution;
- documentation/model promotion review.

A failing internal check loops back to the responsible stage and continues.

### Human Gate triggers

Pause only when at least one is true:

1. irreversible or destructive action;
2. public compatibility decision with multiple legitimate choices;
3. security boundary or permission policy decision;
4. persistent data migration without an already approved strategy;
5. material cost, availability or operational risk;
6. conflict with an accepted decision that cannot be resolved by implementation evidence;
7. acceptance cannot be observed with available access;
8. the user explicitly requested approval at that point.

The Gate output contains a concrete decision, evidence, recommended option, alternatives and consequences. “Approve routing to cs-issue” is invalid Gate content.

## 11. Automatic review loops

### Feature

```text
design → self-review
  ├─ blocking technical flaw → revise design
  ├─ human decision required → Gate
  └─ clear → implement

implement → diff review → repair until clear
          → QA/acceptance → repair until clear
          → promote → archive
```

### Issue

```text
reproduce → root cause → smallest fix
          → regression review → verify original symptom
          → promote diagnostic only when reusable → archive
```

### Refactor

```text
characterize behavior → design smallest structural move
                      → incremental diff review
                      → equivalence verification → archive
```

## 12. Minimality policy

Every lifecycle applies this ladder before adding machinery:

1. Does the requested behavior already exist?
2. Can an existing code path, pattern or helper be reused?
3. Can a standard-library or platform-native facility solve it?
4. Is an already-installed dependency sufficient?
5. Can deletion or simplification solve the root cause?
6. What is the smallest change that proves the outcome?

New abstraction, dependency, artifact or compatibility layer requires concrete evidence. “May be useful later” is not evidence.

## 13. Portability boundary

The canonical workflow is stored in `skills/`. Project-local shared behavior is copied into `.codestable/reference/`. Host manifests and aliases live under `adapters/` and contain no lifecycle logic.

This creates three stable layers:

```text
portable skills → project-local runtime/reference → optional host adapter
```

A host schema can change without changing lifecycle semantics, and one host cannot silently acquire different engineering rules from another.

## 14. Failure and recovery

- If `state.json` is corrupt, `doctor` reports it; the skill reconstructs only from `work.md` and Git evidence, then records the repair.
- If a linked file moved, the planner reports `missing`; the skill searches the current model/code for a replacement and updates the link.
- If context receipts are stale, their hash mismatch forces a reread.
- If an agent changed code without advancing state, Git evidence wins; the lifecycle reconciles state before continuing.
- If an old archived design conflicts with current model or code, current accepted model and executable behavior win unless the task is explicitly investigating a regression.
- Completed work is not archived until `validation.last_result` records a non-failing result; cancellation may archive without validation.

## 15. Two modes, two authorities

CodeStable separates normal software delivery from Harness maintenance.

```text
Normal mode (worker authority)
request → route/resume → evidence → change product → task verify → accept
                         └── best-effort passive observation write

Maintenance mode (maintainer + evaluator + human authority)
explicit select → diagnose → candidate → trusted evaluate → decide
→ human promotion Gate → version/rollback
```

Normal mode owns `model/`, `knowledge/`, `work/` and only appends to `observations/`. It may never read observation/evolution history, create a candidate, run a Harness benchmark, or modify the active Harness.

Maintenance mode may read only explicitly selected observations and compressed case evidence. The external evaluator owns private held-out tasks and its signing key. The human owns promotion authority.

## 16. Passive observation as a flight recorder

Each invocation records one temporary directory:

```text
.codestable/observations/<state>/<run-id>/
├── meta.json
├── events.jsonl
└── outcome.json
```

`meta.json` binds the run to work id, route, lane, start/end stage, active Harness version, model profile, adapter and repository commit. `events.jsonl` contains small metadata events. `outcome.json` records the normal task verifier, signals and aggregate metrics.

Recorder properties:

- best effort and non-blocking;
- no extra model call;
- no cross-run analysis;
- no raw prompt, source, diff, secret, private hold-out or task-level evaluator trace;
- bounded event count, payload size and retention;
- explicit `pending`, `flagged`, `selected` states.

A flag is only an index. It does not prove a Harness defect and cannot trigger evolution.

## 17. Context and data separation

```text
.codestable/model/                 current software truth
.codestable/knowledge/             validated reusable project knowledge
.codestable/work/                  active and archived software work
.codestable/observations/          temporary run evidence; write-only in normal mode
.codestable/harness/               active Harness, manifest, playbook, versions
.codestable/evolution/cases/       explicit maintenance cases
.codestable/evals/                 protected evaluation protocol and public fixtures
```

`cs_context.py plan` and normal search exclude observations, evolution, evals and Harness version history. Normal lifecycle code may query a bounded set of already-promoted active playbook rules only through the read-only `cs_harness.py`; that tool has no control-plane imports or mutation commands. An evolution case starts from named finished observations and writes a compressed `evidence.json`; it never recursively loads all historical runs.

## 18. Explicit selection and diagnosis

No scheduler, threshold or run count creates an evolution case. A maintainer explicitly selects run ids or a named existing signal. Selection moves those finished observations to `selected/` and freezes one baseline Harness version.

Diagnosis then classifies the evidence as:

- Harness behavior;
- project knowledge gap;
- product code defect;
- model variance;
- environment/tool problem;
- insufficient evidence.

Only a Harness diagnosis can proceed, and it must name one declared editable surface and a falsifiable mechanism. Other diagnoses close the case without a Harness candidate.

## 19. Editable and protected surfaces

Initial editable surfaces are routing, retrieval, minimality, structured playbook, lifecycle policy, artifact schema and context tooling. Every surface carries a risk class, but **all promotions require a human Gate**, including low-risk edits.

Protected surfaces include:

- config and Gate policy;
- read-only Harness reader plus observation/evolution/evaluator tools;
- evaluation protocol and private held-out;
- observations and case evidence;
- manifest, registry and version snapshots;
- signing keys, sandbox and resource policy.

Candidates are isolated overlays containing exactly the declared surface paths. Proposal records base and candidate hashes; a candidate cannot modify its whitelist or evaluation rules.

## 20. Trusted evaluator boundary

`cs_eval.py challenge` freezes:

- baseline Harness version and exact active content hash;
- candidate content hash and immutable candidate-definition hash;
- evaluation protocol hash;
- model profile, adapter, evaluator and budget;
- exact required splits and repeats;
- a random nonce.

The host runs baseline and candidate in fresh isolated environments on `held_in`, evaluator-only `held_out`, and `safety`. The candidate and normal worker never receive private tasks or the evaluator-only HMAC key.

The project accepts only aggregate results. `cs_eval.py import` verifies the immutable challenge digest, signature, nonce, baseline content, candidate overlay and definition, protocol lock, exact split schema, score ranges, aggregate-only fields and one-result-per-challenge. Direct unsigned `eval-record` is intentionally absent.

This does not make an in-process evaluator magically trustworthy: trust depends on adapter isolation and keeping the key outside candidate/worker environments. The control plane makes that boundary auditable and rejects unauthenticated results.

## 21. Deterministic decision and human Gate

A verified result passes only when:

- at least one required split improves;
- held-in and held-out pass rates do not regress;
- safety is perfect when configured;
- token, duration, interruption and context metrics stay within protocol limits;
- the imported result remains unchanged.

Passing produces `accepted_pending_human_gate`, not an active version. The Gate presents selected evidence, diagnosis, exact diff surface, split results, resource metrics, risks, alternatives and rollback target.

Promotion rechecks that the baseline is still active, the candidate definition is byte-for-byte the one evaluated, and all challenge/result/overlay hashes match; it then snapshots the baseline, applies the overlay atomically, snapshots the new version and records actor/reason lineage.

## 22. Version lineage and rollback

```text
.codestable/harness/
├── manifest.json
├── registry.json
├── playbook.jsonl
└── versions/<version>/
```

Snapshots contain every declared editable surface plus hashes and metadata. Rollback restores a named verified snapshot and records actor and reason. A rollback or later flagged observation does not auto-propose a replacement; a new explicit case is required.

## 23. Structured playbook

`harness/playbook.jsonl` is an incremental list of active, evaluated rules with identifiers, scope, evidence and confidence. It is not a monolithic prompt and is never rewritten after each task. Playbook edits are ordinary bounded candidates subject to trusted evaluation and the human promotion Gate.

Normal lifecycles retrieve only a handful of applicable rules by kind, stage and existing scope keywords through `cs_harness.py`, never through `cs_evolve.py`. Unverified task reflection never enters durable playbook state.

## 24. Host adapter responsibility

The portable package does not embed a model API, private benchmark or container service. A conforming adapter must:

1. call the passive recorder around normal/direct Skill invocations without exposing records to model context;
2. pass one observation id through nested lifecycle skills to avoid duplicate traces;
3. run baseline and candidate in fresh worktrees/containers with identical locks;
4. keep private held-out tasks, evaluator implementation and HMAC key outside candidate/worker mounts and environments;
5. emit aggregate-only signed results;
6. invoke promotion only after an explicit human Gate;
7. enforce sandbox, time, network, secret and cleanup boundaries.

Without an isolated adapter the package still provides observation, selection, bounded candidates, versioning and deterministic guards, but it must not claim that locally self-supplied evaluation is trustworthy.
