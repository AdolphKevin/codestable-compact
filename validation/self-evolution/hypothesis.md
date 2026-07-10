# Frozen hypothesis

Repeated route confirmations are caused by the active interaction-copy policy. Replacing the mandatory confirmation marker with compact no-confirmation copy should remove the extra turn on unseen route requests without changing route selection.

Falsification conditions:

- held-out requests still emit `[ROUTE_CONFIRMATION_REQUIRED]`;
- route selection changes;
- safety requests lose their expected route;
- token, duration, or context cost materially regresses.

Scope: `interaction.route-summary-copy` on the exact Codex Runtime Profile recorded by the evaluation.
