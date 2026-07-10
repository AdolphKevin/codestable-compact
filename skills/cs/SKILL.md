---
name: cs
description: CodeStable Compact 的统一开发与显式 Meta 维护入口。接收功能、缺陷、性能、重构、路线、模型维护、继续执行、反馈分诊或离线 Harness 优化请求；普通开发自动路由并连续执行，只被动记录临时轨迹。
license: MIT
compatibility: Requires a writable project repository. Bundled deterministic helpers require Python 3.10+; profile-aware trusted Harness evaluation additionally requires a host adapter, isolated runner, private held-out fixtures and evaluator-only signing key.
---

# `/cs` — route, run, observe

## Non-negotiable contract

**Do not stop after recommending another skill.** Routing is internal control flow. Select the lifecycle, show at most the configured compact summary, and immediately execute or resume it in the same invocation.

```text
Invalid: Route: cs-issue. Please invoke /cs-issue.
Valid:   → issue · standard · 开始复现暂存慢
```

Normal development has one passive side effect: append a compact temporary observation. It must not diagnose, propose, evaluate, promote, or read observation history back into delivery context.

```text
normal /cs = delivery lifecycle + best-effort observation write
explicit /cs meta = selected production evidence + offline Harness maintenance
```

Read project-local shared rules only when needed:

- `.codestable/reference/lifecycle.md`
- `.codestable/reference/routing.md`
- `.codestable/reference/retrieval.md`
- `.codestable/reference/gates.md`
- `.codestable/reference/minimality.md`

Never recursively scan `.codestable/`. Normal delivery must not retrieve `observations/`, `meta/`, `evolution/`, `evals/`, or Harness version history.

## 1. Parse explicit delivery controls

Recognize these before classifying prose:

| Command | Action |
|---|---|
| `/cs init` | Install or repair runtime; continue any following development request in the same turn |
| `/cs upgrade` | Refresh shipped tools, references and protected protocols with backup; preserve project model, work and observations |
| `/cs status` | List active work metadata only |
| `/cs continue [hint]` | Resume matching active work and execute its current stage |
| `/cs route <request>` | Diagnostic route-only mode |
| `/cs doctor` | Validate runtime and report actionable findings |
| `/cs archive <work>` | Archive only after promotion and completion checks |
| `/cs observe status` | Explicitly show temporary observation counts |
| `/cs observe list [signal]` | Explicitly list pending, flagged or selected observations |
| `/cs observe flag <run|current>` | Mark a named run as a possible Harness problem; do not start Meta work |
| `/cs observe prune` | Preview retention cleanup; apply only when explicitly requested |
| `/cs feedback ...` | Explicitly triage a finished production observation or register its regression fixture |
| `/cs meta ...` | Enter the offline Meta control plane described after the explicit boundary |
| `/cs evolve ...` | Compatibility alias for `/cs meta ...`; do not maintain a second protocol |

## 2. Ensure runtime without interrupting

Find the repository root. If `.codestable/config.json` is absent, run:

```bash
python3 <this-skill-directory>/scripts/bootstrap.py --root <repo-root>
```

For `/cs upgrade`, add `--upgrade`. Then run:

```bash
python3 .codestable/tools/cs_context.py doctor
```

Repair deterministic runtime problems when safe. Never overwrite current project model, knowledge, active work, project-authored fixtures, feedback or observations.

## 3. Resume before creating

Run:

```bash
python3 .codestable/tools/cs_context.py list
```

This reads active `state.json` metadata only. Resume when the request matches an active title, slug, scope path, symbol, keyword, or the immediately preceding conversation. `state.json.stage` is authoritative; reconcile it with code and Git evidence when needed. Do not infer progress by Glob-ing old phase files.

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

Read only `always` and `read`. Reuse `reuse` only because the file is unchanged and remains present in this live conversation. Record reads with `receipt`; link discovered current model/knowledge once rather than rediscovering the tree.

## 7. Start one passive observation

After work id, route, lane and start stage are known, call best-effort:

```bash
python3 .codestable/tools/cs_observe.py start \
  --work <work-id> --task <short-task-id> \
  --kind <kind> --lane <lane> --entry cs --route <route> \
  --model-profile <exact-host-model-profile> --adapter <host-adapter> \
  --start-stage <stage>
```

Keep the returned `run_id` in this invocation and pass it to the lifecycle skill. A direct lifecycle-skill invocation starts its own observation only when no parent `run_id` was supplied.

Recorder rules:

- best-effort failure never blocks normal delivery;
- append compact metadata for stages, policy activation, context/knowledge reads, knowledge writes, Gate outcome/reason, checkpoints, human interventions, token usage when exposed, tool failure/retry, and task verification;
- never record raw prompts, model replies, source contents, diffs, secrets, credentials, private held-out tasks, or task-level evaluator traces;
- never read old observations during normal delivery;
- a signal may move a run to `flagged`, but it never starts Meta work.

Example events:

```bash
python3 .codestable/tools/cs_observe.py event \
  --run <run-id> --type gate_evaluated \
  --json '{"gate":"security_boundary","result":"passed","reason_code":"no_privilege_change"}'

python3 .codestable/tools/cs_observe.py event \
  --run <run-id> --type human_intervention \
  --json '{"kind":"scope_correction","count":1}'
```

## 8. Retrieve applicable active playbook items

Query only a few already-promoted rules matching current kind, stage and scope keywords:

```bash
python3 .codestable/tools/cs_harness.py playbook-query \
  --kind <kind> --stage <stage> --keyword <keyword> --limit 5
```

This reads active Harness state, not observation, feedback or Meta history. Failure is non-blocking. Never turn a task reflection directly into a playbook update.

## 9. Execute, do not hand off

Activate or follow `cs-feat`, `cs-issue`, `cs-refactor`, `cs-roadmap`, or `cs-model` in the same invocation. Pass work id, lane, stage, session key and observation `run_id`. Continue through internal review/repair loops. Pause only under the Gate policy.

## 10. Gate policy

Design review, code review, QA and route choice are automatic checks, not user pauses. Pause only for irreversible/destructive action, genuine public-contract choice, security policy, unapproved persistent migration, material cost/availability, unresolved accepted-decision conflict, unavailable acceptance access, explicit user approval, or a policy-scoped Harness owner checkpoint.

A Gate response contains evidence, the concrete decision, recommendation, alternatives and consequences.

## 11. Finish the observation without Meta work

At completion, Gate, cancellation or external blockage, finish the current invocation's observation. Use the normal task verifier result; do not run a Harness campaign.

```bash
python3 .codestable/tools/cs_observe.py end \
  --run <run-id> --status completed --end-stage accept \
  --validation-status passed --verifier-id <task-verifier> \
  --command "<command>" --exit-code 0 \
  --metrics-json '{"tool_calls":12,"context_bytes":42000,"input_tokens":18000,"output_tokens":4200,"human_interventions":0}'
```

When a concrete Harness problem was observed, add a stable signal such as `routing.user_corrected`, `tool.repeat_failure`, `gate.false_positive`, or `verification.false_pass`. This only stores the run under `flagged/`.

## 12. Complete the software lifecycle

A lifecycle completes only after observable task verification, internal review, durable-information promotion and state closure:

```bash
python3 .codestable/tools/cs_context.py set \
  --work <id> --validation-result passed --status done
python3 .codestable/tools/cs_context.py archive \
  --work <id> --summary "<evidence-based summary>"
```

Do not search archive, observations or Meta data during normal completion. Closing a software task never directly mutates Harness policy.

## Explicit Meta boundary

Load `references/meta-loop.md` and `.codestable/reference/evolution.md` only for `/cs feedback ...`, `/cs meta ...`, or the `/cs evolve ...` compatibility alias.

```text
production observation
→ feedback triage
→ regression fixture
→ repeated matching signal or explicit selection
→ campaign
→ diagnosis
→ committed hypothesis
→ agent-authored proposal
→ validity pre-pass
→ trusted evaluation
→ deterministic decision
→ quality gates
→ policy-scoped checkpoint
→ promote or rollback
```

**No fixture coverage, no evolution.** A fixture must cover the named first-class policy and all of its required routing/contract/e2e/regression layers before a proposal is admitted.

### Feedback controls

```text
/cs feedback triage <run>
/cs feedback fixture <feedback-id> <fixture-file>
/cs feedback queue
```

Use `cs_feedback.py` to classify a finished production observation as `harness_policy`, `evaluation_defect`, `model_profile_variance`, `project_knowledge`, `product_code`, `environment`, or `insufficient_evidence`. Convert a confirmed Harness incident into a regression fixture before optimization. One signal may be stored without opening a campaign.

### Meta controls

```text
/cs meta status
/cs meta policy-audit
/cs meta trigger-scan [--apply]
/cs meta campaign-new ...
/cs meta diagnose ...
/cs meta hypothesis-freeze ...
/cs meta proposal-register ...
/cs meta validity-prepass ...
/cs meta evaluation-challenge ...
/cs meta decide ...
/cs meta quality-gate ...
/cs meta acceptance-check ...
/cs meta promote ...
/cs meta rollback ...
```

The canonical deterministic entry is `.codestable/tools/cs_meta.py`. `trigger-scan` is a dry-run by default; `--apply` may only open bounded campaigns after enough matching signals. It must never diagnose, write a proposal, run evaluation, accept, or promote.

Creative work belongs to the Agent: it writes the hypothesis, variant document and minimal overlay according to protocol. Scripts only validate, lock, measure, label, record, compare and enforce authority. A proposal must state target metric, first-class policy, allowed change type, exact fixture set, expected effect and regression risks.

A negative verdict or claimed improvement is invalid until the validity pre-pass verifies fixture context completeness, oracle tolerance, scorer calibration, stochastic `k>=5`, judge/profile isolation and committed provenance. Every number is labelled `[measured]`, `[soft]`, or `[underpowered]`; underpowered evidence cannot support promotion.

Prompt-copy or evaluated playbook changes may use an Agent checkpoint only when the policy registry declares it and all required evidence is measured. Gate thresholds, workflow routing, lifecycle, artifact schema and runtime-tool changes require an owner checkpoint. Rejected variants and results remain indexed to prevent repeated proposals.
