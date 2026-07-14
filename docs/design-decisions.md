# Design decisions

## D1 — Control completion, not reasoning order

**Decision:** The Harness does not prescribe how the Owner thinks or which action comes first. It controls goal, side effects, risk, evidence integrity and completion.

**Reason:** A strong Agent can maintain user, repository, implementation and runtime context continuously. Fixed hand-offs add artifacts without improving truth.

**Consequence:** Actions may repeat or reorder. State records what is missing, not where a workflow cursor sits.

## D2 — Evidence state is canonical

**Decision:** Active work is represented by `state.json`, `context.json`, `work.md` and hash-chained `evidence.jsonl`.

**Reason:** A completion claim needs facts, open uncertainty, actual changes and reproducible results in one inspectable model.

**Consequence:** Legacy lane/stage state is migrated, but historical “validation passed” prose is not fabricated into evidence.

## D3 — Risk can only increase

**Decision:** Initial risk may be raised by discovered scope, actual paths, side effects or open critical risks; it cannot be lowered within the task.

**Reason:** Agents often discover the true impact only after implementation begins. A static initial label would permit evidence-policy evasion.

**Consequence:** Registering a critical path can immediately replace the remaining completion requirements with L3 requirements.

## D4 — Harness executes command evidence

**Decision:** `verify` runs the real command and records exit status, timing, bounded output and artifacts.

**Reason:** An Agent statement that tests ran is not proof.

**Consequence:** `FAIL`, `BLOCKED` and `PARTIAL` remain separate and block a false `done` claim.

## D5 — External evidence is fingerprinted

**Decision:** Reviews, traces and rollback demonstrations may be artifact-backed with a producer label and file fingerprints. Command-backed requirements accept only Harness command evidence.

**Reason:** Some verification cannot run inside the local Harness, but it must still be auditable and resistant to accidental replacement.

**Consequence:** L2/L3 review rejects the Owner producer label and requires an artifact. This is declarative identity unless a Host Adapter attests it.

## D6 — Exact evidence policies are non-bypassable

**Decision:** Risk-level requirements and their allowed evidence sources are canonical Harness policy. Bootstrap/runtime repair unsafe local configuration rather than accepting arbitrary same-name PASS records.

**Reason:** Declared policy and implemented gate must have one source of truth.

**Consequence:** Projects may add tools and conventions, but cannot weaken or create invisible completion requirements through config drift.

## D7 — Proof is derived, not authored

**Decision:** `proof` is assembled from prior valid evidence and cannot replace missing prerequisites.

**Reason:** A polished summary can conceal that commands were never run or review was self-issued.

**Consequence:** Proof is useful for audit and hand-off while completion still evaluates the underlying ledger.

## D8 — Reviewer is adversarial and risk-triggered

**Decision:** Reviewer does not repeat Owner analysis. It searches for counterexamples and is mandatory only at L2/L3.

**Reason:** Role simulation adds ceremony; independent challenge adds value only where regression and hidden-scope risk justify it.

**Consequence:** L0/L1 use lightweight evidence. L2/L3 require a declared distinct producer and review artifact; cryptographic identity remains a Host Adapter responsibility.

## D9 — Durable artifacts need a consumer

**Decision:** Long-lived model, knowledge and learning artifacts are admitted only when an Agent, checker, runtime, reviewer or human decision process will consume them.

**Reason:** Process documents become stale and create retrieval noise.

**Consequence:** Ordinary analysis stays in active state/session. Repeated failures become executable fixtures, invariants, rules or checkers.

## D10 — Normal work and Meta evolution are isolated

**Decision:** Normal `/cs` can append a bounded passive observation but cannot read observations or import Meta/evaluation tools. Meta work requires an explicit command.

**Reason:** Self-optimization during delivery creates circular evidence and unpredictable behavior.

**Consequence:** Normal work can use only promoted read-only playbook rules. Policy evolution requires fixture coverage, validity, trusted evaluation, authority and rollback.
