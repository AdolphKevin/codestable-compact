# Host adapters

Canonical portable behavior lives under [`../skills/`](../skills/). Host-specific manifests, hooks, aliases and runner integrations belong here and must not duplicate lifecycle or Meta policy logic.

An adapter has three responsibilities:

1. expose the canonical Skills and preserve `/cs` route-and-continue;
2. provide accurate Runtime Profile and passive observation capabilities without leaking raw content;
3. when supported, execute profile-aware baseline/candidate fixtures in isolated environments and return signed aggregates.

Different hosts may expose different observability and replay levels. Adapters must label unavailable metrics as underpowered rather than fabricating equality across Claude Code, Cursor, Codex, ChatGPT or other environments.

See [`evolution-host-contract.md`](evolution-host-contract.md) for the full contract and [`aliases.md`](aliases.md) for optional command mappings.
