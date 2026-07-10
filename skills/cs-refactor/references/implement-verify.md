# Refactor: implement, review and verify

## Implement incrementally

For each seam:

1. confirm characterization tests are green;
2. make one structural move;
3. run the narrow checks;
4. inspect the diff for behavior changes;
5. update the plan from evidence;
6. delete the obsolete path as soon as the new canonical path is proven.

Avoid unrelated formatting, renaming and dependency upgrades unless they are the actual refactor objective.

## Internal diff review

Review for:

- accidental semantic changes;
- changed ordering, retry, transaction, concurrency or error behavior;
- new dependency direction violations;
- duplicated old/new sources of truth;
- public or persistent compatibility;
- abstraction that only forwards calls or renames concepts;
- tests coupled to implementation rather than observable behavior;
- dead code and temporary scaffolding left behind.

Repair and re-review automatically.

## Verify equivalence and objective

Run:

- characterization and existing tests at observable boundaries;
- relevant lint/typecheck/build/full subsystem tests;
- contract/serialization snapshots when applicable;
- before/after structural measure tied to the objective;
- performance comparison only when performance is a stated non-functional contract.

Inspect the final diff and search for remaining duplicate symbols/paths deliberately. Do not search archive by default.

## Accept and promote

Record how behavior equivalence and structural improvement were proven. Promote an ADR or contract only when future work must obey a new current constraint. Ordinary refactor rationale and step history remain in archive.
