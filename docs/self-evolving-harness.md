# Observable and selectively evolving Harness

## Inner and outer loops

```text
Inner production loop
  goal ↔ inspect/propose/execute/verify/learn
  bounded by risk, side effects and completion evidence

Outer Harness loop
  observation → feedback → fixture → candidate
  → validity → independent evaluation → promotion/rollback
```

The loops share evidence identity but not execution authority. Normal production may write one passive observation; it cannot read Meta history or change the Harness.

## Why evolution is selective

Automatically changing policy after every run would create circular grading, profile overfitting and unstable behavior. Compact requires three admission filters:

1. the incident is classified as a Harness defect rather than product/environment/knowledge/evaluation;
2. the target policy has fixture coverage across required layers;
3. the candidate passes validity and trusted evaluation for a declared runtime profile.

## First-class policy surfaces

The registry maps stable policy IDs to editable files, allowed change types, fixture IDs, required layers and authority. Current core surfaces include routing, selective context, minimality, promoted playbook, evidence convergence, risk Gates, artifact schema, context runtime and route-summary copy.

Protected tools, evaluation protocol, private evidence, Meta registry and version history cannot be smuggled through a candidate overlay.

## Observation semantics

Compact observations capture decisions and results, not content:

```text
route
action selection
evidence type/status
risk escalation
Gate/checkpoint/intervention
aggregate cost
policy and knowledge identifiers
completion/verifier result
```

They are intentionally insufficient to reconstruct source or private user content. Normal work cannot query them.

## Profile-aware evidence

Harness behavior depends on host, model, adapter, tools, context management and budget. Evaluation identity therefore includes the exact runtime profile. Results from incompatible profiles are not pooled automatically.

Evidence applicability grows cautiously:

```text
one project + exact profile
→ several projects + same profile
→ supported profile matrix
```

## Goodhart defenses

A candidate is blocked when context is incomplete, oracle is brittle, scorer uncalibrated, repeats insufficient, judge not isolated or hypothesis rewritten after results. Deterministic safety and product verification cannot be overridden by judge prose.

Private holdout and signing keys stay outside candidate workspaces. Only signed aggregates are imported.

## Promotion and rollback

Promotion is a sequence of gates, not a single score:

```text
policy coverage
→ validity measured
→ target improvement
→ held-out/safety non-regression
→ regression/package measured
→ correct approval authority
→ immutable version and rollback proof
```

Low-risk declared copy/playbook changes may use Agent approval; control, routing, Gate, schema and runtime changes require Owner checkpoint. Every version is immutable and rollback is a first-class recorded operation.

## What the shipped tests prove

The local suite can prove isolation, fixture admission, surface protection, provenance locks, validity rules, signature/tamper/replay rejection, authority enforcement, promotion lineage and rollback integrity. It cannot prove a policy improves every real model/host without that profile's external adapter and private evaluation. Such evidence is reported as underpowered rather than inferred.
