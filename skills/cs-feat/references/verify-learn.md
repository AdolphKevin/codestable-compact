# Verify, challenge and learn from a feature change

Verification is selected by risk and acceptance, not by a universal checklist.

## Build discriminating evidence

Choose evidence that observes the requested behavior and could have failed before the change. Cover the primary path plus material boundary, error, compatibility and invariant behavior. Use the narrowest adequate combination of unit, integration, scenario, replay, stress, trace or live validation.

Run commands through the Harness so each record contains the command, working directory, exit code, bounded output, artifacts and status:

- `PASS`: the asserted evidence succeeded;
- `FAIL`: the assertion ran and was false;
- `BLOCKED`: required execution was unavailable or unauthorized;
- `PARTIAL`: some, but not all, of the intended evidence was obtained.

Never translate `BLOCKED` or `PARTIAL` into success.

## Independent challenge

For L2/L3, the declared reviewer producer must differ from the Owner and should try to disprove completion: missed callers, hidden side effects, invalid tests, dual implementations, regression surfaces, request drift and unsupported claims. A review record needs a real artifact. Portable producer identity is declarative unless a Host Adapter supplies trusted attestation.

## Complete

Generate machine proof from accepted evidence, then ask the Harness to evaluate eligibility. Completion is denied while required evidence, facts, invariants, bounded writes, proposal, risks, assumptions or blockers remain unresolved. Archive only after a preserved `COMPLETED` verdict.

## Admit durable learning

Create a fixture, invariant, checker, routing/reviewer rule or failure signature only when this task exposed a repeatable failure mode. Name the future consumer and add regression evidence. A retrospective document alone is not learning.
