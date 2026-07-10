# Issue: intake, reproduction and analysis

## Intake

Capture without repeating known context:

- intended behavior;
- observed behavior, timing and environment;
- impact and frequency;
- first known good/bad version when available;
- user-provided evidence;
- acceptance: what would prove the issue fixed.

Do not demand a formal report from the user. Turn the available prose into the first section of `work.md`, then inspect evidence.

## Reproduce

Prefer the smallest deterministic reproduction:

1. identify the entry point and observable signal;
2. inspect existing tests, logs, metrics and recent relevant changes;
3. reproduce locally or construct a characterization test;
4. for performance, define the operation, data size, warm/cold state, repetitions and metric;
5. record baseline and environment enough to compare later.

Do not modify production behavior merely to obtain a reproduction if a test/harness/log can reveal it. If reproduction needs unavailable access, exhaust repository and local evidence before making it a Gate.

## Analyze root cause

Trace from symptom to cause:

```text
input/event → entry point → decisions/state → external/persistent boundary → observed output
```

Test hypotheses with evidence. Distinguish:

- trigger: condition that exposes the issue;
- cause: incorrect invariant/logic/state/contract;
- amplifier: factor that makes impact worse;
- symptom: final observed failure.

For performance, profile or instrument the dominant path before optimizing. Avoid replacing a system because one operation is slow until measurements show the structural cause.

Record:

- confirmed root cause;
- affected and unaffected scope;
- why the proposed patch addresses the cause;
- regression and compatibility risks;
- alternatives only when materially different.

## Internal analysis review

Challenge the explanation:

- Does it predict the observed symptom and boundary cases?
- Can the reproduction distinguish this cause from competing hypotheses?
- Is there a smaller existing fix path?
- Is the issue caused by an invalid current contract/requirement?
- Does the risk require lane escalation or human authority?

Revise automatically on technical findings. Advance to `fix` when the cause and verification strategy are credible.
