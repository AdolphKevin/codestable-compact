---
name: cs
description: CodeStable Compact 的统一软件生产控制平面入口。它将功能、缺陷、重构、路线与模型维护请求路由给同一 Owner 闭环，按风险约束副作用、收集真实证据并由 Harness 决定完成资格；显式 Meta 请求才进入离线 Harness 学习。
license: MIT
compatibility: Requires a writable Git worktree. Bundled deterministic helpers require Python 3.10+; trusted Harness evaluation additionally requires an isolated host adapter, private held-out fixtures and an evaluator-only signing key.
---

# `/cs` — autonomous delivery, controlled completion

CodeStable Compact is a control plane, not a software-development checklist.

```text
path chosen by Owner Agent
boundaries and completion owned by Harness
contradiction owned by independent Reviewer
```

**Routing is internal control flow. Do not stop after recommending another skill.** Select `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap` or `cs-model`, show at most one compact route line, then execute/resume it in the same invocation.

```text
Invalid: Route: cs-issue. Please invoke /cs-issue.
Valid:   → issue · L1 · missing: reproduction fact
```

Core split:

```text
normal /cs = owner execution + Harness evidence gate + best-effort observation write
explicit /cs meta = selected production evidence + offline Harness maintenance
```

Never recursively scan `.codestable/`. Normal work may read only current task state, linked current model/knowledge and scoped repository evidence. It must not retrieve observations, Meta campaigns, evaluator data, rejected variants or Harness version history.

## 1. Parse explicit controls

| Request | Behavior |
|---|---|
| `/cs init` | Install/repair runtime; continue any following delivery request |
| `/cs upgrade` | Refresh shipped tools/references with backup; preserve project data |
| `/cs status` | Show active task control state only |
| `/cs continue [hint]` | Resume the matching task from missing facts/evidence |
| `/cs route <request>` | Route-only diagnostic; do not execute |
| `/cs doctor` | Check schema, evidence integrity and policy boundaries |
| `/cs archive <work>` | Archive only a Harness-completed or cancelled task |
| `/cs observe ...` | Explicitly inspect/flag/prune passive observations |
| `/cs feedback ...` | Explicitly triage a finished observation or register a fixture |
| `/cs meta ...` | Enter the explicit offline Meta boundary below |
| `/cs evolve ...` | Compatibility alias for `/cs meta ...`; no second protocol |

A user request such as “只分析原因”“先给方案，不改代码” is a task-side-effect constraint for this invocation. Set `--no-writes` or a narrow allowed path, establish the requested facts/proposal, and report `PARTIAL` when the full software acceptance is intentionally not attempted. Do not invent an ordered workflow stage.

## 2. Ensure the project runtime

Find repository root. When `.codestable/config.json` is absent:

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <repo-root>
```

For upgrade add `--upgrade`. Then:

```bash
python3 .codestable/tools/cs_context.py doctor
```

Repair deterministic runtime problems when safe. Never overwrite project-authored model, knowledge, active tasks, observations, feedback or fixtures.

## 3. Resume before creating

```bash
python3 .codestable/tools/cs_context.py list
```

Match title, slug, linked paths/symbols/keywords and live conversation. Resume from `completion.missing`, open assumptions/risks/blockers and the actual repository—not from phase files. `current_action` is only a control hint.

## 4. Route by observable outcome

| Kind / skill | Dominant outcome |
|---|---|
| `feature` / `cs-feat` | New observable capability or supported behavior |
| `issue` / `cs-issue` | Intended behavior is wrong, regressed, failing, hanging or slow |
| `refactor` / `cs-refactor` | Behavior remains stable while structure/dependencies improve |
| `roadmap` / `cs-roadmap` | Several outcomes or cross-system contracts must be bounded |
| `model` / `cs-model` | Current vision/domain/requirement/contract/decision/knowledge |

Use the first independently verifiable outcome. Record secondary work instead of creating a traditional department hand-off.

## 5. Assign initial risk, then allow escalation

- **L0 Trivial** — text/format/local naming/no behavior change; `diff_check + format_check`.
- **L1 Local** — bounded function/module behavior; `scope_inspect + targeted_test + lightweight_review`.
- **L2 Cross-module** — schemas, prompts, state, concurrency, persistence boundary or multi-component flow; `audit_ledger + proposal + integration_test + independent_review + proof`.
- **L3 Critical** — security, permissions, finance, deletion, core state machine, large architecture or live-LLM decision boundary; `full_audit + invariant_contract + live_validation + rollback_proof + independent_review + regression_fixture`.

Risk may only increase during an active task. Registered paths and side-effect categories can raise it automatically, replacing the evidence policy immediately.

## 6. Create the task contract and side-effect boundary

```bash
python3 .codestable/tools/cs_context.py new <kind> "<title>" \
  --slug <slug> --risk <0|1|2|3> --owner <owner-id> \
  --allow-path 'src/**' --allow-path 'tests/**'
```

For read-only work use `--no-writes`.

Set only what is known:

```bash
python3 .codestable/tools/cs_context.py contract --work <id> \
  --objective '<observable objective>' \
  --constraint '<constraint>' \
  --non-goal '<excluded result>' \
  --invariant '<must remain true>' \
  --acceptance '<observable success condition>'

python3 .codestable/tools/cs_context.py boundary --work <id> \
  --allow-path 'src/**' --forbid-path 'secrets/**' \
  --category <category> --authorization '<required authority>'
```

The Harness rejects registered changes outside the write boundary. L3 requires rollback capability.

## 7. Use repeatable control actions

The Owner may call these in any order and repeat them:

```text
Inspect  establish facts and unknowns
Propose  describe a bounded, falsifiable change
Execute  make the smallest coherent change inside the boundary
Verify   obtain risk-appropriate real evidence
Learn    admit a reusable fixture/rule/invariant/checker when justified
```

Set the current hint when useful:

```bash
python3 .codestable/tools/cs_context.py action --work <id> --name inspect
```

Add ledger entries as evidence changes understanding:

```bash
python3 .codestable/tools/cs_context.py ledger-add --work <id> fact '<confirmed fact>' --source repo
python3 .codestable/tools/cs_context.py ledger-add --work <id> assumption '<hypothesis>'
python3 .codestable/tools/cs_context.py ledger-add --work <id> risk '<risk>' \
  --severity high --blocking --mitigation '<mitigation>'
python3 .codestable/tools/cs_context.py ledger-add --work <id> blocker '<external blocker>'
```

Resolve assumptions/risks/blockers only with an explicit resolution and evidence IDs when available.

## 8. Retrieve only action-relevant context

Use one stable session key only within the live conversation:

```bash
python3 .codestable/tools/cs_context.py plan \
  --work <id> --action <inspect|propose|execute|verify|learn> \
  --session <live-session-key>
```

Read `always` and `read`; reuse `reuse` only because the exact bytes remain in this conversation. Record reads:

```bash
python3 .codestable/tools/cs_context.py receipt --work <id> \
  --session <live-session-key> --action <action> --reason <reason> <path>...
```

Link only current model/knowledge and scope paths that truly constrain the task. Archive retrieval always requires a reason.

## 9. Start one passive observation

After task, route, risk and initial action are known, call best-effort:

```bash
python3 .codestable/tools/cs_observe.py start \
  --work <work-id> --task <short-task-id> \
  --kind <kind> --risk-level <0|1|2|3> --entry cs --route <route> \
  --model-profile <exact-host-profile> --adapter <host-adapter> \
  --start-action <action>
```

The recorder may store compact metadata such as:

```bash
python3 .codestable/tools/cs_observe.py event --run <run-id> \
  --type action_selected --json '{"action":"verify"}'

python3 .codestable/tools/cs_observe.py event --run <run-id> \
  --type evidence_recorded --json '{"evidence_type":"integration_test","status":"PASS"}'

python3 .codestable/tools/cs_observe.py event --run <run-id> \
  --type risk_escalated --json '{"from_level":1,"to_level":2}'
```

Never record prompts, model replies, source/diffs, secrets, raw tool output, private holdouts or task-level evaluator traces. Recorder failure never blocks delivery; a signal may flag a run but cannot start Meta work.

## 10. Query only promoted, bounded playbook rules

```bash
python3 .codestable/tools/cs_harness.py playbook-query \
  --kind <kind> --action <action> --risk-level <0|1|2|3> \
  --keyword <scope-keyword> --limit 5
```

This read-only tool cannot access observations or evolution state. A task reflection never writes directly to the playbook.

## 11. Inspect and propose only as deeply as risk requires

Record confirmed facts, explicit assumptions, open risks and unknowns. Do not generate a repository tour.

For L2/L3, record a falsifiable proposal:

```bash
python3 .codestable/tools/cs_context.py proposal --work <id> \
  --summary '<change>' --rationale '<why>' \
  --non-change '<intentionally unchanged>' \
  --evidence-required <evidence-type>
```

The proposal is not completion. When implementation disproves it, update the ledger/proposal and continue.

State-backed evidence is derived by Harness, not asserted by Owner:

```bash
python3 .codestable/tools/cs_context.py snapshot --work <id> --type scope_inspect
python3 .codestable/tools/cs_context.py snapshot --work <id> --type audit_ledger
python3 .codestable/tools/cs_context.py snapshot --work <id> --type full_audit
python3 .codestable/tools/cs_context.py snapshot --work <id> --type proposal
python3 .codestable/tools/cs_context.py snapshot --work <id> --type invariant_contract
```

## 12. Execute autonomously inside the boundary

The Owner chooses edit order, experiments, refactors and test-first/test-after tactics. Maintain these invariants:

- follow the real call/data path;
- keep changes coherent and acceptance-oriented;
- do not introduce speculative abstractions/dependencies/artifacts;
- register every changed path;
- remove obsolete dual paths and temporary fallbacks;
- stop before unapproved side effects;
- raise risk when impact expands.

Register changes only after files exist:

```bash
python3 .codestable/tools/cs_context.py ledger-add --work <id> change '<behavioral change>' \
  --path src/example.py --path tests/test_example.py \
  --rollback '<rollback method>'
```

## 13. Obtain real verification evidence

Harness-backed command evidence:

```bash
python3 .codestable/tools/cs_context.py verify --work <id> \
  --type targeted_test --cwd . --timeout 300 -- \
  python3 -m unittest tests.test_example -v
```

The Harness records command, cwd, exit code, duration and bounded output and maps results to `PASS`, `FAIL` or `BLOCKED`. A non-zero business assertion is `FAIL`; missing executable/timeout is `BLOCKED`. Do not merge them.

Record an existing external artifact by fingerprint:

```bash
python3 .codestable/tools/cs_context.py record --work <id> \
  --type independent_review --status PASS --producer <reviewer-id> \
  --artifact review/verdict.json --verdict PASS \
  --summary '<scope/regression/completion challenge result>'
```

For `independent_review`, the declared producer must differ from `actors.owner_id`, include `--verdict PASS` and bind an artifact. Portable local identity assurance is declarative; claim cryptographic independence only when a Host Adapter supplies trusted attestation. Reviewer focuses on omitted modules, hidden effects, weak tests, duplicate paths and unsupported completion claims.

Assemble machine proof when required:

```bash
python3 .codestable/tools/cs_context.py proof --work <id> --summary '<proof purpose>'
```

The generated proof references recorded evidence; it cannot manufacture missing prerequisites.

## 14. Let Harness decide completion

Inspect the gate:

```bash
python3 .codestable/tools/cs_context.py check --work <id>
```

`done` is allowed only when:

- objective and acceptance are explicit;
- side-effect scope is bounded;
- L2/L3 invariants/proposal are present;
- every Git-visible change since the task baseline is registered and inside the boundary;
- all risk-required evidence has a `PASS` entry from its policy-approved source;
- evidence chain integrity is valid;
- no blocking assumption, risk or blocker remains;
- independent review has a declared non-Owner producer and artifact; stronger identity claims require Host Adapter attestation.

Completion requires a Git worktree so the Harness can compare the task-start baseline, including for `--no-writes`. Archive rechecks current eligibility and evidence integrity.

```bash
python3 .codestable/tools/cs_context.py complete --work <id> --result done
python3 .codestable/tools/cs_context.py archive --work <id> --summary '<observable result and proof>'
```

Use `--result blocked|partial|cancelled --reason ...` truthfully when the invocation cannot complete. These results do not grant archive-as-done.

Finish passive observation without starting Meta:

```bash
python3 .codestable/tools/cs_observe.py end --run <run-id> \
  --status completed --end-action verify \
  --validation-status passed --verifier-id <task-verifier> \
  --command '<command>' --exit-code 0
```

## 15. Admit durable learning sparingly

A learning artifact must change a future execution path: regression fixture, invariant, route/reviewer rule, checker, scenario, policy or failure signature. A retrospective document alone is not learning.

Normal tasks may record that no durable learning is warranted. Harness/playbook changes require the explicit boundary below.

## Explicit Meta boundary

Load `.codestable/reference/evolution.md` only for `/cs feedback`, `/cs meta` or `/cs evolve`.

```text
selected production evidence
→ diagnosis
→ committed hypothesis
→ Agent-authored bounded Harness change
→ historical/public/private replay
→ independent signed evaluation
→ policy-scoped accept or rollback
```

Hard rule: **No fixture coverage, no evolution.** Normal `/cs` never imports the Meta control plane.

Use explicit commands from the evolution reference, beginning with policy audit and feedback/campaign selection. Scripts may lock, measure and record; they do not invent policy changes. Private held-out fixtures, evaluator implementation and signing key remain outside candidate access. Promotion authority comes from the policy registry and every accepted version retains rollback lineage.
