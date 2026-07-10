# Optional command aliases

Aliases belong to a host adapter and must not duplicate lifecycle logic.

Recommended mappings:

| Alias | Mapping |
|---|---|
| `/cs-auto <request>` | invoke `cs` with `entry.mode=auto` for this call |
| `/cs-run <request>` | same as `/cs-auto` |
| `/cs-route <request>` | invoke `cs route <request>` |
| `/cs-onboard` | invoke `cs init` |

The canonical default already makes `/cs` auto-run. These aliases exist only for teams preserving an older command contract or exposing explicit modes in a host UI.
