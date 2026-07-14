# Inspect and propose a feature change

Use this guide only while current facts, boundaries or the mechanism of change are unclear. `inspect` and `propose` may alternate; neither is a mandatory hand-off.

## Establish facts

Start at the user-visible entry point and follow the real call, data and state path. Record only concise ledger entries:

- facts that are directly supported by code, tests, runtime output or accepted contracts;
- assumptions that still need a discriminating check;
- risks, including hidden writes, compatibility surfaces and failure paths;
- unknowns that materially affect scope or verification.

A fact should name its source. Do not turn a plausible reading into a fact, and do not create a long audit document when a bounded snapshot proves the surface.

## Bound the task

Set the objective, acceptance, non-goals and invariants. Declare allowed and forbidden paths plus any external write, authorization or rollback constraint. Link only current artifacts that constrain this invocation.

Let the Harness raise risk when inspection reveals multiple modules, persistent contracts, concurrency, authorization, money, deletion or core state transitions. Never lower risk to retain a cheaper evidence policy.

## Form a falsifiable proposal

L0/L1 work may execute directly when the mechanism is obvious. L2/L3 need a proposal that states:

- what behavior and mechanism will change;
- why the change is the smallest coherent one;
- what remains intentionally unchanged;
- which evidence would reject the proposal;
- rollback or compatibility handling when required.

The proposal is live state. Revise it when evidence invalidates an assumption; do not preserve a stale design merely because implementation began.
