# Low-level candidate and version state

This directory stores selected cases, candidate overlays, trusted evaluation decisions and immutable Harness version operations. The canonical orchestration entry is `/cs meta ...` through `cs_meta.py`; `cs_evolve.py` remains the deterministic low-level candidate/version engine.

A valid change follows:

```text
classified production feedback + registered fixture
→ first-class policy admission
→ committed hypothesis
→ Agent-authored proposal
→ validity pre-pass
→ signed external evaluation
→ measured quality gates
→ policy-scoped approval
→ immutable promotion or rollback
```

Normal development never reads this directory. Direct candidate creation is rejected; new candidates must arrive through the Meta proposal protocol. Rejected variants remain as evidence to avoid repeated proposals.
