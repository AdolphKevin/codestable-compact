# Host adapters

The canonical, portable behavior is under `../skills/`.

Host-specific plugin manifests, command aliases, hooks or marketplace metadata belong here. They must not contain workflow logic; adapters should only expose the canonical skills to a particular host. This prevents behavior drift between Claude Code, Codex, other Agent Skills loaders, and plain `AGENTS.md` environments.

No host manifest is committed in this initial version because those schemas change independently of the lifecycle design. Add an adapter only after validating it against the target host's current official specification.

Passive observations and explicit Harness maintenance require additional execution boundaries. See [`evolution-host-contract.md`](evolution-host-contract.md) for the normal invocation wrapper, selected-case workflow, isolated candidate runner, signed evaluator boundary and human promotion Gate.

