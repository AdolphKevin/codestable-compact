# Profile-aware host and evaluator contract

A host adapter connects portable CodeStable Skills to a concrete model/runtime, repository and external evaluator while preserving three isolated planes:

```text
normal evidence-state production
passive observation
explicit offline Meta maintenance
```

## 1. Runtime profile

Declare the most precise observable identity:

```json
{
  "profile_id": "<host>/<model>/<adapter-version>",
  "host": {"name": "codex|claude-code|cursor|chatgpt|other", "version": "..."},
  "model": {"declared_id": "...", "revision_or_epoch": "unknown-or-value"},
  "adapter": {"id": "...", "version": "..."},
  "tools": {"shell": true, "filesystem": true, "network": false},
  "context": {"compaction": "host-managed", "limit": "unknown-or-value"},
  "budget": {"max_turns": 40, "timeout_seconds": 1800}
}
```

Unknown values remain unknown. Do not pool incompatible profiles without explicit analysis.

## 2. Normal invocation

For `/cs` or a direct outcome skill, the adapter:

1. initializes or resumes one evidence-state task;
2. routes to the outcome lens and selects an initial risk/action hint;
3. starts exactly one passive observation with active Harness/profile identity;
4. passes the run id through nested skills;
5. exposes repository/tool access within declared side-effect authorization;
6. lets Harness-backed verification record actual results;
7. finishes observation at `COMPLETED`, `PARTIAL`, `BLOCKED`, `CANCELLED` or an external Gate;
8. returns the product result without importing Meta tools.

Recorder failure is non-blocking in best-effort mode.

## 3. Preferred observation support

```text
route_selected
action_selected
evidence_recorded
risk_escalated
completion_checked
policy_applied
context_loaded / knowledge_read / knowledge_written
gate_evaluated with result/reason
checkpoint_paused
human_intervention
token_usage aggregate
tool_failed / tool_retried
run_finished
```

Do not fabricate unavailable fields. Missing cost or intervention data is unknown, not zero. Never log raw prompts, full responses, source/diffs, credentials, private fixtures, signing keys or private task traces.

## 4. Normal-context isolation

Normal worker context may read current model, knowledge, active work, repository and promoted read-only Harness rules. It must not retrieve observations, feedback/campaigns, evaluation results/protocol, evolution cases, Harness version history, rejected candidates or private evaluator assets.

Observation writes may occur deterministically without injecting their file contents into model context.

## 5. Side-effect enforcement

The adapter must respect task-declared allowed/forbidden paths, external write categories, authorization and rollback requirements. A host tool that cannot technically sandbox writes must still report attempted/actual paths to the Harness and stop on an unauthorized surface. It must not silently broaden scope.

## 6. Independent reviewer

For L2/L3, provide a reviewer identity distinct from the Owner and a fingerprintable artifact. Reviewer receives the task contract, diff/behavior evidence and completion claim, but should independently challenge scope, regressions, side effects, dual paths and invalid tests.

The adapter may use a separate model profile or human reviewer. Merely changing the producer string on Owner output is invalid.

## 7. Feedback and Meta entry

Only explicit `/cs feedback ...`, `/cs meta ...` or compatibility `/cs evolve ...` may inspect named finished observations or Meta files. Scheduled `trigger-scan` defaults to preview; applying it may create bounded campaigns only and has no proposal, evaluator, approval or promotion authority.

## 8. Candidate workspace

A proposing Agent may receive selected sanitized feedback, registered public fixtures, the relevant policy entry, committed hypothesis workspace, exact baseline surface and a bounded overlay directory. It may not write protected tools/registries, access private holdout/signers or inspect competing private campaign results.

The Agent authors hypothesis/variant/proposal/overlay. Scripts only validate, lock, measure and record.

## 9. Replay capability labels

- **Level A — fully replayable:** fresh model runs, workspace selection, event capture, budget enforcement and repetitions. Supported metrics may become `measured`.
- **Level B — artifact replayable:** final artifacts and verifier results are available, but some decision events are unavailable. Unsupported metrics remain `soft` or `underpowered`.
- **Level C — observed manual:** incidents can inform fixtures, but cannot alone support automatic promotion.

Declare capability per metric, not as one global flag.

## 10. Validity and evaluator isolation

Before evaluation, ensure complete fixture context, tolerant oracle, calibrated scorer, stochastic `k>=5`, judge isolation and unchanged provenance locks. Missing requirements are underpowered or blocked.

The external evaluator must run baseline/candidate in fresh equivalent sandboxes, own private held-in/held-out/safety assignments, enforce exact profile/budget, emit aggregate approved metrics only and sign them with an evaluator-only key. Import only through `cs_eval.py`.

## 11. Approval and rollback

Read authority from the policy registry. Routing, evidence convergence, Gate thresholds, artifact schema and runtime/tool changes require Owner approval. Agent approval is allowed only for an explicitly declared low-risk change after all measured gates.

Present exact surface hash/diff, fixtures, profile scope, target/held-out/safety results, costs, risks and rollback target. Rollback restores a verified immutable version and records actor/reason; it does not start a new candidate automatically.

## 12. Capability declaration

```json
{
  "runtime_profile_id": "...",
  "observation": {
    "action_events": "measured",
    "evidence_events": "measured",
    "risk_events": "measured",
    "token_usage": "underpowered"
  },
  "production": {
    "write_sandbox": true,
    "command_exit_capture": true,
    "independent_reviewer": true
  },
  "evaluation": {
    "fresh_baseline_workspace": true,
    "isolated_candidate_workspace": true,
    "repeatable_model_runs": true,
    "private_holdout": true,
    "signed_aggregate_import": true
  },
  "promotion": {
    "policy_scoped_owner_checkpoint": true,
    "immutable_rollback": true
  }
}
```
