# Execute a feature change

The Owner chooses implementation order. Harness controls writes, risk and completion—not the Owner's internal reasoning path.

## Make a coherent observable slice

Change the smallest mechanism that can produce the accepted behavior. Follow existing repository conventions and public contracts. Prefer deletion or reuse over a speculative framework, switch, alias or compatibility branch.

Register every changed path. A path outside the declared boundary is not a bookkeeping issue: stop the write, expand the boundary only with authority, and allow risk/evidence requirements to escalate.

## Adapt from feedback

Use experiments, targeted tests, traces or temporary local diagnostics when they reduce uncertainty. Temporary code must not survive completion unless it has an explicit consumer and contract.

When a result contradicts the proposal:

1. record the new fact and resolve the invalid assumption;
2. update scope, risk or proposal;
3. choose the next useful action—inspect, propose, execute or verify.

Do not stack fallback behavior on an unverified mechanism. Do not leave old and new paths active unless a supported rollout contract requires both and names the removal condition.

## Preserve evidence independence

Implementation notes and Owner assertions are not verification. Keep command-backed evidence, reviewer artifacts and proof generation in the Harness evidence ledger so the completion gate can reproduce what actually occurred.
