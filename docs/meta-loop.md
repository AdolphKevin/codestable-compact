# Meta loop

## Purpose

The Meta loop improves the production Harness, not product code. It is explicit, offline and evidence-gated:

```text
observe
→ select compatible production evidence
→ classify the failure
→ create/repair a fixture
→ commit a hypothesis
→ propose a bounded Harness overlay
→ replay public and private evidence
→ independent signed evaluation
→ accept or reject
→ promote with authority or rollback
```

Normal delivery never continues automatically into this loop.

## 1. Passive observation

A normal run can append bounded metadata about route, action selection, evidence status, risk escalation, Gate/checkpoint decisions, interventions, aggregate cost, policy/knowledge use and final completion result. It must not capture raw prompts, responses, source, diffs, secrets, private fixtures or full tool output.

Normal runs do not read observation history. Recorder failure is best-effort and cannot block product work.

## 2. Feedback classification

Only an explicit feedback or Meta request can inspect a named finished observation. Classify it as one of:

```text
harness_policy
evaluation_defect
model_profile_variance
project_knowledge
product_code
environment
insufficient_evidence
```

Only a grounded `harness_policy` signal can become a policy campaign. Product defects return to normal evidence-state work; fixture/scorer defects repair evaluation; project facts enter current model/knowledge only with a consumer.

## 3. Fixture admission

A production failure becomes reusable only through a sanitized fixture with provenance, complete context requirements, a tolerant oracle, calibrated scorer and policy mapping. Policy audit enforces:

```text
editable surface
+ allowed change type
+ fixture IDs
+ required fixture layers
+ approval authority
```

A whitelisted policy without complete fixture coverage is not evolvable.

## 4. Signal accumulation

`trigger-scan` groups exact signal, policy, runtime profile and baseline Harness identity. Preview is the default. Applying a scan may open a bounded campaign only; it cannot diagnose, write a proposal, evaluate, accept or promote.

This prevents one noisy incident or incompatible host/model behavior from changing global policy.

## 5. Committed hypothesis and Agent proposal

Before candidate results, freeze a committed hypothesis containing mechanism, target metric, fixture set, expected improvement, regression risks, falsification conditions and runtime-profile scope.

The Agent writes the variant document, proposal JSON and minimal declared overlay. Deterministic tools validate surfaces, locks, budgets, provenance and fixture coverage; they do not generate policy wording.

## 6. Validity pre-pass

No positive or negative attribution is trusted until the pre-pass confirms:

- context and required references are complete;
- oracle accepts equivalent correct behavior;
- scorer calibration exists;
- stochastic fixtures use at least five repeats;
- judge profile is isolated;
- hypothesis, candidate and fixture identities remain locked.

Evidence labels are `measured`, `soft` and `underpowered`. Missing adapter, low sample size or invalid scoring produces underpowered evidence, never a pass.

## 7. Trusted evaluation

After validity passes, freeze baseline, candidate, fixture set, runtime profile, adapter, budget and evidence identity. A separate evaluator runs fresh equivalent sandboxes, owns private held-out/safety cases and signs aggregate results with a key unavailable to worker/proposer/candidate processes.

Only signed aggregate data is imported. Private tasks, raw traces and evaluator implementation are not exposed.

## 8. Acceptance authority

Measured policy audit, validity, regression and package gates must pass. Approval authority comes from the policy registry:

- declared low-risk prompt/playbook changes may allow Agent approval after measured gates;
- routing, evidence convergence, Gate thresholds, artifact schema and runtime behavior require Owner approval.

Every promoted Harness version links policy, fixtures, hypothesis, candidate, validity result, signed evaluation, quality gates, runtime profile, approver and immutable rollback target.

## 9. Rollback and learning

Rollback restores a verified Harness snapshot and records actor/reason. It does not start a new campaign. Rejected variants remain indexed so future work does not repeat the same unsupported idea.

The Meta learning target is control quality: routing, risk classification, evidence requirements, reviewer triggering, failure detection and repeated failure signatures—not generic prose about making the Agent smarter.
