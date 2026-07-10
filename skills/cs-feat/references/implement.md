# Feature: implementation and internal code review

## Prepare

Read only the `plan` output for this live session. Confirm the working tree and relevant tests. Do not reread all design inputs when their digest is unchanged and the content is already in the live conversation.

For a multi-step plan, implement the smallest independently verifiable slice first. Keep `work.md` checkboxes current; do not create a separate checklist file.

## Implement

For each step:

1. follow the existing call/data path;
2. make the smallest coherent diff;
3. avoid unrelated formatting or cleanup;
4. use existing project conventions and dependencies;
5. add or update a test that demonstrates the acceptance boundary;
6. run the narrowest useful check before continuing.

When evidence invalidates the design, return to `design`, update the decision and continue. Do not force code to match an obsolete plan.

## Internal code review

Review the actual diff, not the intention:

- correctness and missing branches;
- state/concurrency/error handling;
- public and persistent compatibility;
- security and data exposure;
- regression risk;
- unnecessary abstraction, dependency or files;
- tests that can pass without proving the behavior;
- stale docs/model caused by the change.

Repair blocking findings immediately and re-review. Record only material findings and repairs in `work.md`; do not create a review report for a clean pass.

## Exit

Advance to `verify` when:

- implementation matches the current design and acceptance;
- narrow checks pass;
- internal diff review has no blocking finding;
- the working tree contains no unexplained unrelated change.
