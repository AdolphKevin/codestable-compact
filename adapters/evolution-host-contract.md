# Profile-aware Meta evaluation host contract

A host adapter connects portable CodeStable Skills to a concrete model/runtime, project workspace and external evaluator. It must preserve three isolated planes:

```text
normal delivery
passive observation
explicit offline Meta maintenance
```

## 1. Runtime Profile identity

Every run should declare the most precise observable profile available:

```json
{
  "profile_id": "<host>/<model>/<adapter-version>",
  "host": {"name": "claude-code|cursor|codex|chatgpt|other", "version": "..."},
  "model": {"declared_id": "...", "revision_or_epoch": "..."},
  "adapter": {"id": "...", "version": "..."},
  "tools": {"shell": true, "filesystem": true, "network": false},
  "context": {"compaction": "host-managed", "limit": "unknown-or-value"},
  "budget": {"max_turns": 40, "timeout_seconds": 1800}
}
```

The adapter may not pretend unknown model revisions or decoding settings are fixed. Record unknowns explicitly. Feedback/evaluation from incompatible profile IDs must not be pooled without an explicit higher-level analysis.

## 2. Normal invocation wrapper

For `/cs` or a direct lifecycle skill:

1. initialize or restore the software work item;
2. select route/lane/stage;
3. start exactly one passive observation with exact profile and active Harness identity;
4. pass the `run_id` through nested lifecycle skills;
5. append compact metadata events only;
6. run the normal project verifier;
7. finish the observation at completion, Gate, cancellation or external blockage;
8. return the software result without importing Meta tools.

Recorder failure is non-blocking when configured best-effort.

## 3. Observation event support

Preferred Level-A event coverage:

```text
route_selected
stage_started / stage_finished
policy_applied
context_loaded / knowledge_read / knowledge_written
gate_evaluated with result/reason
checkpoint_paused
human_intervention
token_usage aggregate
tool_failed / tool_retried
verification_finished
run_finished
```

Adapters with weaker APIs may omit unavailable fields, but must not fabricate them. Missing token or checkpoint data remains unknown, not zero.

Never log raw prompt, full response, source/diff, credential/environment value, private fixture, evaluator key or task-level private trace.

## 4. Normal-context isolation

Normal worker context may access only current project model/knowledge/work/code and active bounded Harness rules. It must not retrieve:

```text
observations
feedback/meta campaigns
evolution cases
evaluation protocol/results
Harness version history
rejected variants
private evaluator assets
```

It may execute deterministic observation writes without injecting file contents into model context.

## 5. Feedback mode

Only an explicit `/cs feedback ...` request may inspect a named finished observation and invoke `cs_feedback.py`. The adapter should present compressed metadata and evidence hashes, not raw transcript.

A feedback item is classified before fixture or campaign work. When converting to a fixture, the Agent receives only the minimum project context needed to construct a reproducible, sanitized case.

## 6. Meta entry boundary

Enter Meta mode only through explicit `/cs meta ...` or compatibility `/cs evolve ...`. A timer or cron may invoke `trigger-scan`, but:

- default is preview;
- `--apply` may only create campaigns;
- cron has no proposal, evaluator signer, owner approval or promotion authority.

Normal run failure, flag count or completion must not directly continue into proposal/evaluation.

## 7. Agent proposal workspace

The adapter gives the proposing Agent:

```text
selected feedback summaries
registered public fixtures
policy registry entry
committed hypothesis workspace
exact baseline Harness surface
bounded overlay directory
```

It must not give writable access to protected tools, evaluator protocol, private held-out, signer, registry/version history or other campaign results that would leak private evaluation.

The Agent writes hypothesis/variant/proposal/overlay. Optimizer scripts must not generate prompt/policy text.

## 8. Public fixture runner capability levels

### Level A — Fully replayable

The adapter can start a model task, select workspace/skills, capture events, enforce budget, repeat runs and return structured outcomes. Host-dependent fixtures can become `[measured]` when repetitions and scorer validity requirements pass.

### Level B — Artifact replayable

The adapter can obtain final code, `.codestable` delta and verifier result, but not a full event trace. It can measure artifact/task outcomes; unavailable routing/Gate/token metrics remain `[underpowered]` or `[soft]`.

### Level C — Observed manual

The host cannot be automatically replayed. Production observations can discover incidents and create fixtures, but cannot alone support automatic promotion. Human review evidence is `[soft]` unless paired with an external measured evaluator.

The adapter must declare its level per metric rather than one global capability flag.

## 9. Validity pre-pass support

Before trusted evaluation, the adapter or evaluator must confirm:

- fixture onboarding/context is mounted;
- required and subject-matter refs exist;
- oracle tolerates valid behavioral variants;
- scorer calibration set is available;
- stochastic tasks use at least five independent repeats;
- judge profile is isolated from tested profile when a judge is used;
- hypothesis and candidate locks remain unchanged.

A missing requirement produces `[underpowered]` or `blocked`, never an inferred pass.

## 10. Trusted evaluator runner

The evaluator is a separate authority and must:

1. receive the immutable challenge generated after validity pass;
2. run baseline and candidate in fresh equivalent workspaces;
3. lock exact Runtime Profile, adapter/tool set, budget, timeout and fixtures;
4. own held-in, private held-out and safety assignments;
5. keep private tasks and evaluator implementation outside candidate mounts;
6. execute required repetitions;
7. emit aggregate approved metrics only, with evidence labels;
8. sign the aggregate payload using an evaluator-only key;
9. expose no key to worker, proposer or candidate.

The project imports results only through `cs_eval.py import`.

## 11. Judge isolation

When an LLM Judge is unavoidable:

- use a distinct declared judge profile;
- do not expose candidate identity if blind scoring is possible;
- calibrate with positive, negative and equivalent-behavior examples;
- keep Judge output `[soft]` unless protocol explicitly validates it as measured;
- never let Judge prose override deterministic safety/verification failures.

## 12. Owner checkpoint

After trusted decision and measured quality gates, the adapter reads required authority from the policy registry.

Owner checkpoint is mandatory for:

```text
workflow routing
Gate thresholds
lifecycle transitions
artifact schema
runtime/tool behavior
```

Agent checkpoint is permitted only for policy/change types explicitly marked `agent_after_evidence`, and only after all required evidence is measured.

The adapter presents exact surface diff/hash, fixtures, profile scope, target/held-out/safety results, costs, risks and rollback target.

## 13. Rollback

Rollback restores a verified immutable Harness version and records actor/reason. It does not automatically run a new proposal or evaluator. Future normal runs simply use the restored active version and continue passive observation.

## 14. Capability declaration

A recommended declaration is metric-specific:

```json
{
  "runtime_profile_id": "...",
  "observation": {
    "stage_events": "measured",
    "gate_events": "measured",
    "token_usage": "underpowered",
    "human_interventions": "soft"
  },
  "evaluation": {
    "isolated_candidate_workspace": true,
    "fresh_baseline_workspace": true,
    "repeatable_model_runs": true,
    "private_holdout": true,
    "evaluator_only_signing_key": true,
    "signed_aggregate_import": true
  },
  "promotion": {
    "policy_scoped_owner_checkpoint": true,
    "immutable_rollback": true
  }
}
```

When isolation, repeatability or signing is unavailable, report the affected metrics as underpowered and do not treat local self-reported results as trusted promotion evidence.
