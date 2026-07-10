# Repository guidance

This repository contains portable Agent Skills. Canonical behavior lives under `skills/`; host-specific adapters remain under `adapters/`.

When changing a workflow:

1. Preserve the invariant that `/cs` routes and continues in the same invocation.
2. Do not add a user-visible skill for an internal phase or optimizer role.
3. Keep archive retrieval opt-in and normal observation/evolution retrieval off.
4. Normal Skills may append one passive observation, but must never diagnose, propose, evaluate or promote.
5. Normal active-rule retrieval must use read-only `cs_harness.py`; never call `cs_evolve.py` from a normal lifecycle.
6. Pass one observation `run_id` through nested lifecycle skills to avoid duplicate traces.
7. Never log raw prompts, model responses, source contents, diffs, secrets or private evaluator data.
8. Evolution cases require explicitly selected finished observations and a recorded diagnosis.
9. Candidates may modify only manifest-declared surfaces; protected control-plane paths remain immutable.
10. Never expose private held-out tasks or evaluator signing keys to worker/proposer/candidate processes.
11. Do not accept direct unsigned evaluation records; use challenge plus signed aggregate import.
12. Every Harness promotion requires a passing decision, explicit human Gate, version snapshot and rollback path.
13. Prefer existing state/reference files over new artifacts and use only Python standard library unless proven necessary.
14. Run `python3 scripts/validate_skills.py` and `python3 -m unittest discover -s tests -v` before release.
