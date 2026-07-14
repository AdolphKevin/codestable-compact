# Inspect an issue and test hypotheses

Start with an observable signal, not a preferred fix.

## Define the signal

Record intended behavior, observed behavior, environment, impact and the smallest reproduction or measurement that distinguishes the defect from normal operation. For performance, hold operation, input, warm/cold state, repetitions and metric constant.

## Trace the earliest divergence

Follow the real call/data/state path from the symptom toward the first point where actual behavior diverges from the supported contract. Record facts with sources and causal assumptions separately.

Maintain multiple hypotheses only when they are materially different and testable. For each blocking hypothesis, state a discriminating experiment, trace, test or artifact. Reject or resolve it in the ledger; do not silently abandon it.

## Bound risk and writes

Identify affected callers, retries, concurrency, persistence, schema, prompt, authorization and external side effects. Set allowed paths and non-goals. Let discovered scope raise the risk level and evidence policy.

A suspicious line, correlation or unrelated passing test is not root-cause evidence. Continue inspection until the proposed correction explains the original signal and predicts a result that verification can falsify.
