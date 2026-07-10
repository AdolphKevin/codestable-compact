# Explicit Harness maintenance

Load this reference only for an explicit `/cs evolve ...` request. Normal development must not retrieve `.codestable/observations/`, `.codestable/evolution/`, `.codestable/evals/`, or `.codestable/harness/versions/`.

## Core invariant

```text
Always observable, selectively evolvable.
```

A normal `/cs` invocation may append a compact temporary observation. It never diagnoses, proposes, evaluates, or modifies the Harness. No signal, failure count, timer, or successful run starts this workflow automatically.

## Roles and authority

| Role | Authority |
|---|---|
| Normal worker | Execute software lifecycle; append best-effort observation metadata |
| Maintainer / `/cs evolve` | Select named evidence, diagnose, create bounded candidate overlays |
| External evaluator | Run baseline/candidate in isolated fresh environments; own private held-out and signing key |
| Deterministic tools | Enforce schemas, locks, protected paths, decisions, snapshots, Gate, rollback |
| Human | Approve or reject every Harness promotion |

The worker/proposer must never receive the evaluator signing key or private held-out tasks.

## Command surface

### Inspect without evolving

```bash
python3 .codestable/tools/cs_observe.py status
python3 .codestable/tools/cs_observe.py list --state flagged --limit 20
python3 .codestable/tools/cs_observe.py show --run <run-id>
```

These commands expose metadata and hashes, not raw Prompt/source content.

### Select an explicit case

By named runs:

```bash
python3 .codestable/tools/cs_evolve.py case-new \
  --title "repeated identical tool retry" \
  --run <run-1> --run <run-2> --case-id <case-id>
```

Or, only after the user explicitly requested it, by an existing flag signal:

```bash
python3 .codestable/tools/cs_evolve.py case-new \
  --title "routing corrections" \
  --signal routing.user_corrected --signal-limit 20
```

Selection moves finished observations to `observations/selected/` and writes a compressed `evidence.json`. It does not create a candidate.

### Diagnose first

Use repository evidence and selected observation summaries to classify the problem as one of:

- `harness`
- `project_knowledge`
- `product_code`
- `model_variance`
- `environment`
- `insufficient_evidence`

Only `harness` can proceed to a candidate, and it must map to one declared editable surface:

```bash
python3 .codestable/tools/cs_evolve.py diagnose \
  --case <case-id> --classification harness \
  --summary "same failed command was retried without strategy change" \
  --mechanism recovery.identical_retry \
  --surface lifecycle-policy --confidence 0.86
```

If the classification is not `harness`, close the case and update the appropriate software or knowledge plane. Never use Harness evolution as a substitute for fixing product code.

### Propose a bounded overlay

Create an isolated overlay directory containing exactly the declared surface files at their project-relative paths. Then register it:

```bash
python3 .codestable/tools/cs_evolve.py candidate-add \
  --case <case-id> --candidate <candidate-id> \
  --title "stop identical retry after one failure" \
  --surface lifecycle-policy \
  --overlay <overlay-directory> \
  --expected-effect "identical tool failure is retried at most once" \
  --regression-risk "may force earlier strategy analysis"
```

A candidate cannot modify config, Gates, observation/evolution tools, evaluator protocol, evidence, registry, snapshots, or private evaluator assets. Base and candidate hashes are frozen at proposal time.

Prefer several small, mechanistically different candidates over one broad rewrite, but evaluate each separately.

## Trusted evaluation

### 1. Create a challenge

```bash
python3 .codestable/tools/cs_eval.py challenge \
  --case <case-id> --candidate <candidate-id> \
  --model-profile <model-profile> --adapter <adapter> \
  --evaluator <evaluator-id> --budget <budget-id>
```

The challenge locks:

- baseline Harness version and exact active content hash;
- candidate content hash and immutable candidate-definition hash;
- protocol hash;
- model profile and adapter;
- evaluator and budget;
- required splits and repeats;
- random nonce.

### 2. Run outside the candidate workspace

The host adapter runs baseline and candidate with identical assignments, budget, tools, and fresh sandboxes on:

- `held_in`: reproduces the selected weakness;
- `held_out`: private evaluator-only non-regression tasks;
- `safety`: Gate, permissions, path isolation, and critical invariants.

The evaluator fills `result-template.json` using only aggregate pass counts and approved metrics. It must not write private task descriptions or task-level traces into the project.

### 3. Sign in the evaluator boundary

Only the evaluator/import process receives `CODESTABLE_EVALUATOR_KEY` and optional `CODESTABLE_EVALUATOR_KEY_ID`:

```bash
python3 .codestable/tools/cs_eval.py sign \
  --input <aggregate-result.json> \
  --output <signed-result.json>
```

Candidate and normal worker processes must not inherit that environment variable.

### 4. Import and verify

```bash
python3 .codestable/tools/cs_eval.py import \
  --case <case-id> --candidate <candidate-id> \
  --file <signed-result.json>
```

Import rejects unsigned/tampered results, replayed or modified challenge data, baseline content drift, candidate overlay/content/definition drift, protocol or runtime-lock mismatch, missing or extra splits, invalid pass counts, raw/private trace fields, and duplicate result import.

### 5. Decide mechanically

```bash
python3 .codestable/tools/cs_evolve.py decide \
  --case <case-id> --candidate <candidate-id>
```

Acceptance requires:

- improvement on at least one required split;
- no held-in or held-out pass-rate regression;
- perfect safety when configured;
- no configured token, duration, interruption, or context regression;
- a verified signed result that is unchanged after import.

A passing decision is still only `accepted_pending_human_gate`.

## Human promotion Gate

Present:

- selected evidence and diagnosis;
- exact changed surfaces and hashes;
- baseline/candidate results per split;
- resource/interruption metrics;
- risks and rollback target;
- recommendation and alternatives.

After explicit approval:

```bash
python3 .codestable/tools/cs_evolve.py promote \
  --case <case-id> --candidate <candidate-id> \
  --human-approved --approved-by "<actor>" \
  --reason "<why this evaluated change should become active>"
```

Every surface, including low risk, requires this Gate. Promotion verifies that the baseline is still active, the candidate definition is exactly the one evaluated, and all challenge/result/overlay hashes still match; it then snapshots the baseline, applies the overlay atomically, snapshots the new version, and records lineage.

## Rollback

```bash
python3 .codestable/tools/cs_evolve.py rollback \
  --version <version-id> --approved-by "<actor>" \
  --reason "<observed regression or policy decision>"
```

Rollback restores a verified immutable snapshot and records the event. A later investigation starts a new explicit case from named observations; rollback itself does not auto-propose a fix.

## Observation signals

Signals are stable indexes, not diagnoses. Examples:

```text
routing.user_corrected
resume.wrong_work
tool.repeat_failure
context.constraint_missed
context.overload
memory.activation_failure
memory.adherence_failure
gate.false_positive
gate.false_negative
verification.false_pass
artifact.loss
entry.extra_turn
cost.budget_exceeded
```

A single signal may be insufficient evidence. Selection and diagnosis remain explicit.

## Protected invariants

1. Normal work never reads observation/evolution history.
2. Observation write failure is non-blocking for delivery.
3. Observation data is temporary, bounded, low-sensitivity, and project-local.
4. No automatic diagnose, propose, evaluate, promote, or run-count trigger exists.
5. Only selected, finished observations may support an evolution case.
6. Candidate edits are limited to manifest-declared surfaces.
7. Private held-out and signing key stay outside candidate/worker workspaces.
8. Direct, unsigned `eval-record` is not supported.
9. Every promotion requires trusted evaluation plus a human Gate.
10. Every promoted version is immutable and reversible.
