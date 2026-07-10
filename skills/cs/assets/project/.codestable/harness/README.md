# Harness state

- `manifest.json` declares the only editable surfaces and protected control-plane paths.
- `registry.json` points to the active immutable version and records lineage events.
- `versions/` contains reversible snapshots created by the evolution control plane.
- `playbook.jsonl` contains active, evaluated execution rules; it is not an automatic dump of task reflections.

Every promotion requires a trusted evaluation and an explicit human Gate, including low-risk surfaces.

Normal delivery reads only the active identity and a bounded set of promoted playbook rules through `cs_harness.py`. That reader cannot access observations, evolution cases, evaluator state, rejected candidates, or version snapshots, and has no mutation command.
