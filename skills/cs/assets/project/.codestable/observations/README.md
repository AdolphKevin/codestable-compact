# Passive observations

This directory is a temporary, project-local flight recorder for normal CodeStable runs.

- `pending/`: completed or running observations without a known Harness problem.
- `flagged/`: observations carrying explicit problem signals.
- `selected/`: finished observations explicitly attached to an evolution case.
- `index.jsonl`: append-only lifecycle metadata; it is not normal task context.

Normal `/cs` work may append compact metadata here, but must never retrieve these records into the model context. The recorder does not diagnose, propose, evaluate, or modify the Harness. Retention is controlled by `observability.retention`; use `cs_observe.py prune --apply` explicitly or from maintenance automation.

Raw prompts, model responses, source contents, diffs, credentials, private held-out tasks, and task-level evaluator traces are prohibited.
