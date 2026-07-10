# Refactor: characterize and design

## Intake

Capture:

- structural problem and its evidence;
- behavior/contracts that must remain stable;
- desired engineering outcome (for example, one source of truth, remove cycle, reduce changed-file fanout);
- explicit non-goals;
- acceptance measures.

Do not accept “clean it up” as sufficient design input without inspecting the code. Convert observations into a bounded objective.

## Characterize current behavior

Trace entry points, data/state flow, side effects and tests. Add characterization tests when current tests cannot detect accidental behavior change. Where exact behavior is a bug, route/link that change as an issue or feature rather than silently preserving or changing it.

Useful evidence includes:

- duplicated decision tables;
- dependency graph/cycle;
- files changed together across recent work (only when deliberately inspected);
- unreachable/dead branches;
- unclear ownership of state;
- repeated conversions or protocol boundaries;
- measurable build/runtime cost.

Avoid generic complexity scores without a decision they inform.

## Minimality ladder

Try in order:

1. delete dead or duplicate path;
2. call an existing canonical path;
3. move responsibility to its current owner;
4. extract a local helper/type only where it reduces real duplication or ambiguity;
5. introduce a seam/interface only when multiple concrete implementations or dependency direction require it;
6. add a dependency only when existing/platform facilities cannot meet the proven need.

## Design incremental seams

A standard plan should identify:

- preserved contracts and characterization tests;
- target ownership/dependency direction;
- smallest sequence that keeps tests runnable;
- deletion point for the old path;
- rollback when a step crosses a risky boundary;
- success measure.

Do not maintain old and new paths indefinitely “for safety.” Any dual path needs a concrete rollout and removal condition.

## Internal design review

Reject or revise designs that:

- introduce more concepts than they remove;
- combine behavior change with structure change;
- require broad rewrites before any testable outcome;
- create speculative generic layers;
- leave two sources of truth without a removal plan;
- ignore public/persistent compatibility.

Advance automatically unless a remaining contract/architecture choice requires human authority.
