# Explicit Meta control plane

This directory contains CodeStable's offline, policy-scoped Meta loop. Normal `/cs` delivery excludes it from context and never imports `cs_meta.py`.

```text
observed production run
→ feedback triage
→ regression fixture
→ repeated matching signal or explicit campaign
→ diagnosis
→ committed hypothesis
→ Agent-authored variant
→ validity pre-pass
→ trusted evaluation
→ measured quality gates
→ policy-scoped approval
→ promotion / rollback
```

## Contents

- `policy-registry.json`: first-class policies, editable surfaces, allowed change types, fixture coverage and owner rules.
- `trace.schema.json`: compact production trace schema.
- `feedback.schema.json`: classified production feedback schema.
- `proposal.schema.json`: Agent-authored proposal contract.
- `campaign.schema.json`: campaign state and evidence contract.
- `feedback/`: classified feedback records and index.
- `campaigns/`: explicit or threshold-grouped offline campaigns.
- `hypotheses/`: frozen, committed hypotheses.
- `variants/`: proposal metadata and Agent-authored variant documents.
- `results/`: validity, quality-gate and acceptance evidence.
- `strategy-evidence.jsonl`: policy-version-to-evidence provenance.
- `trigger-state.json`: bounded scan cursor/state; it is not an autonomous optimizer.

## Hard rules

1. **No fixture coverage, no evolution.**
2. Normal runs may write observations but may not read or import this directory.
3. `trigger-scan` is dry-run by default; `--apply` may only open campaigns.
4. Scripts do not author prompt/policy variants. The Agent writes hypotheses, proposal documents and overlays.
5. A negative verdict or claimed improvement requires a passing validity pre-pass.
6. Stochastic evidence needs `k>=5`; every metric is labelled `measured`, `soft`, or `underpowered`.
7. Private held-out tasks and evaluator signing credentials remain outside the candidate workspace.
8. Approval authority comes from `policy-registry.json`; a proposer cannot choose it.
9. Rejected variants and evidence remain indexed; accepted versions link both directions to their evidence.
