# Correct and verify an issue

## Correct the causal mechanism

Implement the smallest coherent change that covers the supported root-cause hypothesis. Add a regression check at the closest observable boundary. Register changed paths and remove temporary diagnostics or superseded fallbacks before completion.

When execution rejects the hypothesis, stop expanding the patch. Record the result, update the hypothesis and inspect again.

## Re-run the original signal

The evidence set must close the original reproduction or measurement, not merely pass a nearby unit test. Add targeted coverage and relevant repository checks. Use integration, scenario, replay, stress or live evidence for multi-module, persistence, concurrency, prompt or external-service behavior.

For performance, compare equivalent samples and report distribution or variance; a single favorable run is `PARTIAL` at best.

## Challenge completion

Reviewer looks for missed paths, masking, idempotency/retry effects, state leakage, invalid regression tests, compatibility/security changes and dual implementations. L2/L3 review must be independent and artifact-backed.

Ask Harness to complete only after blocking risks and assumptions are resolved and all risk-required evidence is `PASS`. An unavailable environment is `BLOCKED`; an improvement that does not fully close acceptance is `PARTIAL`.

Promote learning only as an executable regression fixture, invariant, diagnostic checker, routing/reviewer rule or stable failure signature with a future consumer.
