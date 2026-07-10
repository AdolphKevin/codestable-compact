# Optional command aliases

Aliases belong to a host adapter and must invoke canonical `cs` behavior rather than copy workflow logic.

| Alias | Mapping |
|---|---|
| `/cs-auto <request>` | invoke `cs` with auto route-and-run |
| `/cs-run <request>` | same as `/cs-auto` |
| `/cs-route <request>` | invoke `cs route <request>` |
| `/cs-onboard` | invoke `cs init` |
| `/cs-evolve ...` | compatibility alias for `cs meta ...` |

The canonical default already makes `/cs` auto-run. `/cs meta` is the canonical explicit Harness maintenance entry; adapters should not expose a second implementation for `/cs-evolve`.
