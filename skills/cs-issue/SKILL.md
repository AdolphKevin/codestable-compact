---
name: cs-issue
description: 在 CodeStable Compact 控制平面内修复错误、回归、异常、卡顿或性能退化。以可复现信号和根因假设驱动最小变化，并由 Harness 用真实命令证据和风险自适应 review 控制完成。
license: MIT
compatibility: Requires a CodeStable Compact project runtime. Performance work additionally needs a reproducible measurement boundary; external services may require authorized validation access.
---

# Issue outcome lens

Use when intended behavior is wrong, regressed, failing, hanging or too slow. A proposed rewrite does not make it a refactor until evidence shows that structure—not only symptom repair—is the bounded outcome.

This skill does not impose report → analyze → fix → QA phases. The Owner repeatedly narrows facts, hypotheses, changes and evidence until the original signal is closed.

Read only what is needed:

| Need | Reference |
|---|---|
| Establish symptom, reproduction, facts and competing hypotheses | `references/inspect-hypotheses.md` |
| Execute the correction, verify the original signal and challenge completion | `references/execute-verify.md` |

## Issue contract

Record:

- intended and observed behavior;
- observable reproduction or measurement signal;
- impact/boundary and known environment;
- acceptance that would distinguish fixed from merely changed;
- non-goals and protected invariants;
- allowed write/side-effect surface.

No formal user bug template is required. Convert available prose and system evidence directly into the contract.

## Inspect and hypothesize

Prefer the smallest deterministic reproduction or characterization. Trace from the observable symptom to the earliest divergence in the real call/data path. Record confirmed facts separately from causal assumptions.

Maintain competing hypotheses only while they can be discriminated. Each blocking assumption needs an experiment, trace, test or artifact capable of confirming/rejecting it. Do not treat correlation, a suspicious line or a passing unrelated test as root-cause proof.

For performance, define equivalent operation, data, warm/cold state, repetitions and metric before changing code.

## Execute the root-cause correction

Make the smallest coherent correction that covers the causal mechanism and preserves unrelated behavior. Add a regression test at the closest observable boundary. Register changed paths and allow automatic risk escalation.

When implementation evidence rejects the current cause, stop extending the patch. Update the ledger/hypothesis and inspect again. Do not layer fallbacks onto an unproven cause.

## Verify against the original signal

Evidence must include the original reproduction/measurement, targeted regression coverage and relevant project checks. For concurrency, persistence, schema, prompt or multi-module issues, use integration/scenario/stress/replay evidence as appropriate.

For performance, compare equivalent samples and report distribution/variance rather than one favorable run.

Reviewer challenges:

- cause coverage and missed paths;
- retry/idempotency/concurrency/state effects;
- error masking or observability loss;
- regression test discriminating power;
- hidden compatibility/security effects;
- temporary or dual implementations;
- completion claims that do not close the original signal.

## Complete and learn

Harness completion requires closure of blocking assumptions/risks and all risk-required PASS evidence. A blocked environment is `BLOCKED`; partial reproduction or partial fix is `PARTIAL`, not success.

Admit durable learning only when the failure mode should alter future execution: regression fixture, invariant, diagnostic checker, routing/reviewer rule or stable failure signature.
