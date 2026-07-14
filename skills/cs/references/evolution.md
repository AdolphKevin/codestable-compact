# Compatibility reference: explicit Harness maintenance

`/cs meta ...` is the canonical CodeStable 0.5 Meta control plane. `/cs evolve ...` remains a compatibility alias only; load and follow [`meta-loop.md`](meta-loop.md) rather than maintaining another implementation.

Normal evidence-state production must not read observations, feedback, campaigns, evaluation data, rejected candidates or Harness history. The alias cannot bypass fixture coverage, validity pre-pass, trusted signed evaluation, measured quality gates, policy-scoped authority or rollback provenance.
