# Passive production observations

This directory is a temporary, project-local flight recorder for normal CodeStable runs.

- `pending/`: running or finished observations without a confirmed Harness signal.
- `flagged/`: observations carrying explicit problem signals.
- `selected/`: finished observations attached to feedback/campaign evidence.
- `index.jsonl`: append-only lifecycle metadata; never normal task context.

A schema-v3 trace can record compact metadata for:

```text
route and lane
stage start/finish
policy activation
context and knowledge reads
knowledge writes/promotions
gate pass/reject and reason code
checkpoint pauses
human interventions
token/tool/context aggregates when exposed
task verifier result
```

Normal `/cs` may append events but must never retrieve old runs into delivery context. Observation failure is best-effort and does not block software work. A signal can flag a run but cannot start a Meta campaign.

Raw prompts, complete model replies, source contents, diffs, credentials, environment values, private held-out fixtures and task-level evaluator traces are prohibited. Retention is controlled by `observability.retention` and explicit `cs_observe.py prune --apply` maintenance.
