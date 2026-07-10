# Roadmap: discover, frame and contracts

## Discover current system

Inspect:

- current vision/requirements/domain relevant to the outcome;
- entry points, ownership boundaries and existing capabilities;
- current public/persistent contracts;
- accepted decisions that constrain decomposition;
- operational/security/data boundaries;
- active work that already overlaps.

Use `model/INDEX.md` as a pointer and link only relevant documents. Historical features are not architecture truth; search archive only for a named regression/decision archaeology reason.

## Frame the outcome

Write:

- observable end state;
- actors and systems affected;
- in scope / out of scope;
- non-negotiable constraints;
- success and rollout measures;
- why one bounded feature is insufficient.

Ask product questions only after repository evidence cannot determine the answer. A vague request does not justify an abstract interview before inspection.

## Define contracts and boundaries

Specify only contracts needed to make independent items coherent:

- responsibility/ownership boundaries;
- API/event/schema/auth contracts;
- dependency direction;
- migration and compatibility policy;
- observability and failure semantics;
- rollout/rollback boundaries.

Do not pre-design every internal function. Prefer existing contracts and platform primitives. Mark unknowns as discovery/spike items only when they block a contract decision and have a concrete output.

## Gate check

Technical inconsistencies loop back and are repaired. Create a human Gate for strategy only when multiple legitimate boundaries/contracts carry materially different product, security, data or operational consequences. Provide a recommendation based on evidence.
