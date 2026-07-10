# Harness policy and version state

- `manifest.json`: editable surfaces and protected control-plane paths.
- `policies/`: small first-class policy content suitable for bounded evolution.
- `playbook.jsonl`: active evaluated execution rules, never an automatic reflection dump.
- `registry.json`: active immutable version and lineage.
- `versions/`: reversible snapshots created by the evolution engine.

The separate `meta/policy-registry.json` maps each conceptual policy to editable surface, allowed change type, exact fixture coverage and approval authority. A surface being editable is not enough: it must also be fixture-covered.

Normal delivery reads only current identity, bounded promoted playbook items and bounded interaction-copy rules through `cs_harness.py`. That reader has no mutation command and cannot access observations, feedback, campaigns, evaluations, rejected candidates or version history.

Promotion requires a passing validity pre-pass, signed trusted evaluation, measured quality/package/regression gates and the authority required by the policy/change type. Version metadata links policy, fixture, hypothesis, proposal, runtime profile, evaluation, acceptance and approval evidence in both directions.
