# Roadmap: decompose, review and activate

## Decompose into outcomes

Each item should include:

| Field | Meaning |
|---|---|
| ID/title | Stable concise identity |
| Outcome | Independently observable capability/risk reduction |
| Kind | feature / issue / refactor / model |
| Acceptance | Evidence that closes the item |
| Depends on | Only real contract/data/order dependencies |
| Lane | micro / standard / high-risk |
| Contracts touched | Current contract references |
| Rollout note | Only when needed |
| Status | queued / ready / active / done / dropped |

Avoid items named only “backend”, “frontend”, “database” unless each is independently valuable. Prefer vertical slices where possible.

## Sequence

Identify:

- contract-first prerequisites;
- uncertainty-reduction work;
- critical path;
- items that can proceed independently;
- migration/rollout checkpoints;
- explicit removal/cleanup after transition.

Do not add fake dependencies to make the diagram orderly.

## Internal roadmap review

Check:

- every outcome is covered exactly once;
- no item assumes an undefined contract;
- ordering follows real dependencies;
- high-risk changes have rollback/observability;
- scope is neither one giant item nor ceremony-only fragments;
- current model/accepted decisions are respected;
- first item can start with available information.

Repair internally and repeat. Human Gate only for unresolved strategy authority.

## Promote accepted roadmap

Write one current document at `.codestable/model/roadmaps/<slug>.md` and update `model/INDEX.md`. Include outcome, boundaries, contracts, item table, sequence, risks/decisions and status. Do not copy investigation logs.

## Activate

If the original request asked for execution and at least one item is ready:

1. create the first work aggregate with the item's kind/lane;
2. link it to the roadmap and relevant model contracts;
3. update roadmap item status to active;
4. immediately invoke/resume that lifecycle in the same user invocation.

Do not stop at “next, call cs-feat.” Stop only at a real Gate or when the user explicitly requested planning only.
