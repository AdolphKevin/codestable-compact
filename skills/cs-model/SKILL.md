---
name: cs-model
description: 在 CodeStable Compact 控制平面内维护当前 vision、domain、requirement、contract、decision 或可复用 knowledge。只把有明确未来消费者的真相沉淀为文档，并用代码、测试、链接和一致性检查验证。
license: MIT
compatibility: Requires a CodeStable Compact project runtime. Current repository/model access is needed to resolve truth and drift; implementation follow-up requires a writable repository.
---

# Current-model outcome lens

Use when the primary result is current shared truth or reusable knowledge rather than immediate product-code behavior. A model edit is not a substitute for changing a system whose acceptance requires executable behavior.

Read only:

- `references/inspect-edit.md` to classify evidence and make the minimal canonical edit;
- `references/validate-index.md` to challenge truth, links, consumers and follow-up work.

## Contract

State the concept to make current, its authority/evidence, intended consumer and acceptance. Bound whether this is vision, domain language, requirement, public/persistent contract, accepted decision or reusable knowledge.

Do not create a file for task-specific analysis, rejected alternatives, execution logs or generic advice. Without an Agent/checker/runtime/reviewer/human consumer, keep the note session-local or in the active task only.

## Inspect current truth

Start from the exact concept and model index, then inspect only relevant code, tests, config and accepted decisions. Separate:

- confirmed current truth;
- proposal/future intent;
- accepted decision;
- superseded history;
- reusable engineering knowledge;
- task process detail.

Expose conflicts instead of silently choosing stale prose. Authority order is explicit current product/user authority, accepted current contracts/decisions, executable supported behavior, implementation detail, then historical work prose.

## Edit minimally

Modify the canonical document and remove duplicate statements when safe. Keep requirements observable, contracts precise enough for compatibility/failure behavior and decisions limited to real future constraints.

When an edit identifies code/model drift, link or create the bounded feature/issue/refactor task and continue when the user asked for system alignment. Do not claim the model edit completed system behavior.

## Verify and complete

Check currency/status, terminology, testability, conflicts/supersession, links, sensitive data and index budget. Register the changed paths and obtain L0/L1 evidence by default; contract/security/persistent-state changes may require L2/L3 review even when only documentation changes because they alter a control surface.

Harness completion—not the presence of a document—closes the task. Promote reusable knowledge only when a future execution path will consume it.
