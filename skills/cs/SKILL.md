---
name: cs
description: CodeStable Compact 的统一开发入口。接收新功能、Bug、性能问题、重构、路线规划、模型维护、“继续”、运行记录检查或显式 Harness 维护请求；自动恢复或路由并在同一轮执行。正常工作只被动记录临时 observation，绝不自动进化。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; trusted Harness evaluation additionally requires an external isolated runner and evaluator-only signing key.
---

# `/cs` — route, run, observe

## Non-negotiable contract

**Do not stop after recommending another skill.** Routing is internal control flow. Select the lifecycle, show at most the configured summary, and immediately execute or resume it in the same invocation.

```text
Invalid: Route: cs-issue. Please invoke /cs-issue.
Valid:   → issue · standard · 开始复现暂存慢
```

Normal development has one passive side effect: append a compact temporary observation. It must not diagnose, propose, evaluate, promote, or read observation history back into the delivery context.

```text
normal /cs = delivery lifecycle + best-effort observation write
explicit /cs evolve = selected evidence + Harness maintenance
```

Read project-local shared rules only when needed:

- `.codestable/reference/lifecycle.md`
- `.codestable/reference/routing.md`
- `.codestable/reference/retrieval.md`
- `.codestable/reference/gates.md`
- `.codestable/reference/minimality.md`

Load `.codestable/reference/evolution.md` or `references/evolution.md` **only** for an explicit `/cs evolve ...` request. Never recursively scan `.codestable/`. Normal delivery must not retrieve `observations/`, `evolution/`, `evals/`, or Harness version history.

## 1. Parse explicit control commands

Recognize these before classifying prose:

| Command | Action |
|---|---|
| `/cs init` | Install/repair runtime; continue a following development request in the same turn |
| `/cs upgrade` | Refresh shipped tools/reference/protected protocol with backup; preserve model/work/observations |
| `/cs status` | List active work metadata only |
| `/cs continue [hint]` | Resume matching active work and execute its current stage |
| `/cs route <request>` | Diagnostic route-only mode |
| `/cs doctor` | Validate runtime and report actionable findings |
| `/cs archive <work>` | Archive only after promotion and completion checks |
| `/cs observe status` | Explicitly show temporary observation counts |
| `/cs observe list [signal]` | Explicitly list pending/flagged/selected observations |
| `/cs observe flag <run|current>` | Mark a named run as a possible Harness problem; do not evolve |
| `/cs observe prune` | Preview retention cleanup; apply only when explicitly requested |
| `/cs evolve status` | Show active Harness version and explicit maintenance cases |
| `/cs evolve inspect flagged` | Inspect flagged summaries only; no proposal |
| `/cs evolve select ...` | Select named finished observations into a case |
| `/cs evolve diagnose <case>` | Decide whether the case is Harness, project knowledge, product, model variance, environment, or insufficient evidence |
| `/cs evolve propose <case>` | Create bounded candidate overlays only after a Harness diagnosis |
| `/cs evolve evaluate <case/candidate>` | Invoke the external trusted evaluator and import its signed aggregate result |
| `/cs evolve promote <case/candidate>` | Pause at a human promotion Gate after a passing decision |
| `/cs evolve rollback <version>` | Restore an immutable snapshot with actor and reason |

There is no run-count threshold, automatic reflector, automatic proposal, automatic evaluator, or automatic promotion. Do not create user-visible reflector/curator/evaluator skills.

## 2. Ensure runtime without interrupting

Find the repository root. If `.codestable/config.json` is absent, run:

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <repo-root>
```

For `/cs upgrade`, add `--upgrade`. Then run:

```bash
python3 .codestable/tools/cs_context.py doctor
```

Repair deterministic runtime problems when safe. Never overwrite current model or active work.

## 3. Resume before creating

Run:

```bash
python3 .codestable/tools/cs_context.py list
```

This reads active `state.json` metadata only. Resume when the request matches an active title, slug, scope path, symbol, keyword, or the immediately preceding conversation. `state.json.stage` is authoritative; reconcile it with code/Git evidence if needed. Do not infer progress by Glob-ing old phase files.

## 4. Route a new event

Classify the dominant observable event, not proposed solution wording.

| Route | Choose when |
|---|---|
| `cs-feat` | A new externally observable capability or supported behavior is required |
| `cs-issue` | Intended behavior is wrong, regressed, failing, hanging, or too slow |
| `cs-refactor` | Behavior remains stable while structure, complexity, or dependencies improve |
| `cs-roadmap` | The outcome spans several features/systems or sequencing/contracts are not bounded |
| `cs-model` | The primary result is current vision/domain/requirement/contract/decision/knowledge |

For mixed requests, choose the first independently verifiable outcome and record secondary work. Lifecycle transitions are automatic unless they create a real human Gate.

## 5. Select lane

Use `micro` only when the change is local, reversible, has no public contract/schema/security/destructive impact, and is directly testable. Use `high-risk` for persistent migration, public compatibility, security, payment, destructive operations, cross-service rollout, material availability/cost, or no credible rollback. Otherwise use `standard`.

## 6. Create or resume the aggregate

For new work:

```bash
python3 .codestable/tools/cs_context.py new <kind> "<title>" \
  --slug <slug> --lane <lane>
```

Create one stable live-conversation session key. Plan reads with:

```bash
python3 .codestable/tools/cs_context.py plan \
  --work <id> --stage <stage> --session <session-key>
```

Read only `always` and `read`. Reuse `reuse` only because it is unchanged and still present in this live conversation. Record reads with `receipt`; link discovered current model/knowledge once rather than rediscovering the tree.

## 7. Start one passive observation

After work id, route, lane, and start stage are known, call best-effort:

```bash
python3 .codestable/tools/cs_observe.py start \
  --work <work-id> --task <short-task-id> \
  --kind <kind> --lane <lane> --entry cs --route <route> \
  --model-profile <host-model-profile> --adapter <host-adapter> \
  --start-stage <stage>
```

Keep the returned `run_id` in this invocation and pass it to the lifecycle skill. A direct lifecycle-skill invocation starts its own observation only when no parent `run_id` was supplied.

Recorder rules:

- best-effort failure never blocks normal delivery;
- append only meaningful metadata events such as stage changes, tool failure/retry, Gate creation, user correction, and verification result;
- never record raw prompts, model replies, source contents, diffs, secrets, credentials, private held-out tasks, or task-level evaluator traces;
- never read old observations during normal delivery;
- a signal may move a run to `flagged`, but it never starts evolution.

Example event:

```bash
python3 .codestable/tools/cs_observe.py event \
  --run <run-id> --type tool_failed \
  --json '{"tool":"shell","signature":"git-status-timeout","attempt":1}'
```

## 8. Retrieve applicable active playbook items

Query only a few rules matching current kind, stage, and existing scope keywords:

```bash
python3 .codestable/tools/cs_harness.py playbook-query \
  --kind <kind> --stage <stage> --keyword <keyword> --limit 5
```

This reads active Harness state, not observation/evolution history. Failure is non-blocking. Never turn a task reflection directly into a playbook update.

## 9. Execute, do not hand off

Activate or follow `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap`, or `cs-model` in the same invocation. Pass work id, lane, stage, session key, and observation `run_id`. Continue through internal review/repair loops. Pause only under the Gate policy.

## 10. Gate policy

Design review, code review, QA, and route choice are automatic checks, not user pauses. Pause only for irreversible/destructive action, genuine public-contract choice, security policy, unapproved persistent migration, material cost/availability, unresolved accepted-decision conflict, unavailable acceptance access, explicit user approval, or **promotion of a changed Harness version**.

A Gate response contains evidence, the concrete decision, recommendation, alternatives, and consequences.

## 11. Finish the observation without evolving

At completion, Gate, cancellation, or external blockage, finish the current invocation's observation. Use the normal task verifier result; do not run a Harness benchmark.

```bash
python3 .codestable/tools/cs_observe.py end \
  --run <run-id> --status completed --end-stage accept \
  --validation-status passed --verifier-id <task-verifier> \
  --command "<command>" --exit-code 0 \
  --metrics-json '{"tool_calls":12,"context_bytes":42000}'
```

When a concrete Harness problem was observed, add a stable signal such as `routing.user_corrected`, `tool.repeat_failure`, `gate.false_positive`, or `verification.false_pass`. This only stores the run under `flagged/`.

## 12. Explicit evolution boundary

For `/cs evolve ...`, load `references/evolution.md`. Evolution may read only named/selected observations and their compressed evidence. It must use:

```text
select → diagnose → propose → trusted evaluate → decide → human Gate → promote/rollback
```

If diagnosis says project knowledge or product code, update that plane instead and close the evolution case without a Harness candidate. A candidate cannot modify protected paths. An evaluator result is usable only after `cs_eval.py import` verifies the immutable challenge and nonce, baseline version/content, candidate overlay/content/definition, protocol and runtime locks, exact splits, aggregate-only schema, and evaluator-only HMAC signature.

## 13. Completion

A lifecycle completes only after observable task verification, internal review, durable-information promotion, and state closure:

```bash
python3 .codestable/tools/cs_context.py set \
  --work <id> --validation-result passed --status done
python3 .codestable/tools/cs_context.py archive \
  --work <id> --summary "<evidence-based summary>"
```

Do not search archive or observations during normal completion. Closing a software task never directly mutates Harness rules.
