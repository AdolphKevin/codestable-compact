# Feature: intake, evidence and design

## Intake

Extract from the request and current conversation without re-asking:

- desired observable outcome;
- current behavior, when relevant;
- acceptance examples and boundary cases;
- compatibility expectation;
- explicit non-goals.

Ask only for product intent or a material choice that code/model cannot reveal. Before asking, inspect the relevant entry point, tests, current contracts and accepted decisions.

Write the minimum useful content into `work.md` section 1. For `micro`, this can be three bullets.

## Evidence

Trace the actual behavior:

1. locate user/API/CLI entry point;
2. follow control and data flow to the write/read boundary;
3. inspect nearest tests and existing conventions;
4. identify the smallest owned surface;
5. establish explicit `state.scope` paths/symbols/keywords;
6. link only the model/knowledge documents that truly constrain the task.

Use `search --scope current` only with specific terms. Do not search archive unless investigating a regression or a named historical decision; archive search requires a reason.

Record evidence, not a repository tour. Avoid listing every file opened.

## Lane check

Re-evaluate lane after evidence. Escalate to high-risk for public compatibility, persistent data, security, payments, destructive operations, cross-service rollout or weak rollback. Do not keep `micro` merely to avoid documentation.

## Design

Choose the smallest mechanism that satisfies acceptance:

1. existing behavior/path reuse;
2. deletion or simplification;
3. standard library/platform facility;
4. already-installed dependency;
5. small local code;
6. new abstraction/dependency only with concrete necessity.

A standard design should state:

- behavior and boundary;
- touched components and data flow;
- contract/data implications;
- failure behavior;
- tests/observability;
- migration/rollout/rollback only when relevant.

Do not create speculative extensibility, compatibility aliases or configuration switches.

## Internal design review

Review silently against:

- Does it meet every acceptance statement?
- Does it conflict with an accepted contract/decision?
- Is there a smaller existing mechanism?
- Are state, concurrency, error and compatibility edges covered?
- Is the verification plan capable of disproving the design?
- Does the lane match risk?

Blocking technical findings: revise design and review again.

Only unresolved authority/risk choices create a human Gate. Record the Gate in state with a specific question and evidence. Otherwise advance directly to `implement`.
