# Action-aware retrieval protocol

## Read order

0. facts already present in the live conversation;
1. exact active work `state.json`;
2. only the `work.md` sections relevant to the selected control action or missing evidence;
3. changed, non-empty `attention.md` when it has a current cross-task reminder;
4. changed model/knowledge documents explicitly linked by the task;
5. scoped code, tests, configuration, runtime output and contracts needed to establish facts or evidence;
6. a few targeted `search --scope current` results;
7. archive index only with an explicit historical reason; use `--deep` only after a candidate is identified.

The Harness may recommend an action from missing state, but the Owner decides the actual inspection/edit/test order.

## Prohibited defaults

- recursively scanning `.codestable/`;
- loading every ADR, requirement, knowledge note or archived task;
- treating old work prose as current system truth;
- rereading an unchanged file already present in the same live conversation;
- normal delivery reading `observations/`, `meta/`, `evolution/`, `evals/` or Harness versions;
- using action labels as proof that analysis, implementation or verification happened.

## Establish links once

When inspection finds a current requirement, contract, decision or reusable note that constrains the task, add its relative path to `state.json.links`. Link code paths/symbols/keywords into scope. Subsequent actions recover from those links instead of rediscovering the tree.

## Receipt

```bash
python3 .codestable/tools/cs_context.py receipt --work <id> \
  --session <live-conversation-key> --action <inspect|propose|execute|verify|learn> \
  --reason <reason> <path>...
```

A receipt means that exact file bytes were read in this live conversation. It is neither durable memory nor verification evidence.
