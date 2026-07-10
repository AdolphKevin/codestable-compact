# Compatibility reference: explicit Harness maintenance

`/cs meta ...` is the canonical CodeStable 0.4 Meta control plane. `/cs evolve ...` remains a compatibility alias only; load and follow [`meta-loop.md`](meta-loop.md) rather than maintaining a second workflow.

Normal delivery must not read observations, feedback, Meta campaigns, evaluation data, rejected candidates, or Harness version history. The compatibility alias cannot bypass policy fixture coverage, validity pre-pass, trusted signed evaluation, measured quality gates, policy-scoped approval, or rollback provenance.
