# Host adapters

Canonical portable production and Meta behavior lives under [`../skills/`](../skills/). Host-specific manifests, wrappers, aliases, sandboxing, reviewer integration and evaluator runners belong here and must not duplicate control policy.

An adapter must preserve:

```text
route-and-continue
evidence-state task identity
side-effect authorization
Harness-backed result capture
normal/Meta isolation
profile-aware trusted evaluation
```

See [`evolution-host-contract.md`](evolution-host-contract.md) for the full contract and [`aliases.md`](aliases.md) for optional command mappings.
