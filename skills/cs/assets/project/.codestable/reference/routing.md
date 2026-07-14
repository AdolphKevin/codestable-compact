# Routing and continuation

## Resume before creating

Read active task metadata first. When title, slug, linked scope or current conversation identifies an existing task, resume it from missing facts, open risks and missing evidence. Do not create a duplicate because its current action differs from the user's wording.

When the user only says “continue”:

- one active task: continue it;
- several: match recent context, title, scope and keywords;
- ask only when equally plausible choices would materially change the write/side-effect boundary.

## Route by observable outcome

- new observable capability → `feature` / `cs-feat`;
- wrong, regressed, failing, hanging or slow behavior → `issue` / `cs-issue`;
- structural improvement with preserved behavior → `refactor` / `cs-refactor`;
- several bounded outcomes or unresolved cross-system contracts → `roadmap` / `cs-roadmap`;
- current vision/domain/requirement/contract/decision/knowledge → `model` / `cs-model`.

The proposed solution does not choose the route. “Rewrite the cache to fix timeouts” begins as an issue until evidence establishes the mechanism.

## Risk is independent of route

Classify initial risk as L0–L3 from change surface, side effects, compatibility, persistence, security, rollback and validation access. Route describes the outcome; risk selects the control policy. Risk may be raised after inspection or registered changes.

## Compact output

```text
→ <kind> · L<risk> · missing: <next evidence or boundary>
```

Then continue. `/cs route` is the explicit route-only exception.
