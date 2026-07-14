# Explicit Meta Harness maintenance

Load this reference only for `/cs feedback ...`, `/cs meta ...`, or the `/cs evolve ...` compatibility alias. Normal software delivery excludes observations, feedback, Meta campaigns, evaluation data, rejected variants and Harness version history from context.

## Operating model

```text
normal delivery
  → compact passive trace
  → optional production feedback triage
  → optional regression fixture
  → repeated matching signals or explicit selection
  → offline Meta campaign
  → diagnosis
  → committed hypothesis
  → Agent-authored proposal
  → validity pre-pass
  → external signed evaluation
  → deterministic decision
  → measured quality gates
  → policy-scoped checkpoint
  → promote / rollback
```

Hard rules:

1. **No fixture coverage, no evolution.**
2. A normal run never imports or calls `cs_meta.py`.
3. Scripts measure, lock and record; they do not invent prompt/policy changes.
4. Negative verdicts and claimed gains require a passing validity pre-pass.
5. Stochastic evidence uses at least five repeats and every metric is labelled `measured`, `soft`, or `underpowered`.
6. Private held-out fixtures, evaluator implementation and signing key stay outside candidate/worker access.
7. Approval authority is derived from the policy registry, never selected by the proposer.
8. Rejected variants and results remain indexed; accepted versions carry bidirectional evidence provenance.

## Policy admission

Run:

```bash
python3 .codestable/tools/cs_policy.py audit
```

`meta/policy-registry.json` maps each first-class policy to:

- its editable Harness surface;
- allowed change types;
- required routing/contract/e2e/regression fixture layers;
- exact fixtures;
- Agent or owner checkpoint authority.

A policy outside the whitelist, a missing fixture, or a missing required layer blocks proposal registration.

## Production feedback

A finished observation is explicitly classified with `cs_feedback.py triage`. Valid causes include Harness policy, evaluation defect, runtime-profile variance, project knowledge, product code, environment and insufficient evidence.

A confirmed Harness incident should be converted into an Agent-authored fixture with production provenance through `cs_feedback.py fixture-register`. One incident may be frozen as a regression fixture without starting a campaign.

## Campaign trigger

```bash
python3 .codestable/tools/cs_meta.py trigger-scan
```

The scan groups unassigned Harness feedback by exact signal, policy, runtime profile and baseline Harness identity. It is dry-run by default. `--apply` may only open a bounded campaign after the configured support threshold; it cannot diagnose, propose, evaluate, accept or promote.

## Proposal protocol

The Agent writes and commits a hypothesis before seeing candidate evaluation results. It then writes a variant document, proposal JSON and minimal overlay. `cs_meta.py proposal-register` validates authorship, provenance, policy coverage, change type, fixture set, protected paths and budget.

Direct low-level `cs_evolve.py candidate-add` is intentionally rejected for new candidates.

## Validity pre-pass

Before evaluation, `cs_meta.py validity-prepass` verifies:

- fixture onboarding and subject-matter context are complete;
- required references exist;
- oracle tolerance is structured rather than exact-phrase brittle;
- scorer calibration evidence exists;
- stochastic `k>=5`;
- judge and tested runtime profiles are isolated;
- hypothesis, proposal and overlay are unchanged.

`underpowered` or `soft` evidence cannot satisfy a measured promotion Gate.

## Trusted evaluation

`cs_meta.py evaluation-challenge` freezes baseline/candidate content, proposal, policy/fixture evidence, validity result, runtime profile, adapter, budget, protocol and nonce. The external evaluator runs equivalent fresh sandboxes on held-in, private held-out and safety splits, then returns only signed aggregate results. `cs_eval.py import` rejects tampering, replay, raw traces, baseline/candidate drift, protocol mismatch and missing required metrics.

## Acceptance, authority and rollback

After `cs_meta.py decide`, record all configured quality gates (`policy_audit`, `validity_prepass`, `regression`, `package`) as measured. `acceptance-check` derives required authority from the policy registry:

- prompt copy and evaluated playbook changes may permit Agent approval;
- workflow routing, risk/completion policy, artifact schema and runtime tools require owner approval.

Promotion snapshots the baseline and candidate version, links every evidence artifact and writes lineage. Rollback restores a verified immutable snapshot and records actor/reason; it does not automatically open a new campaign.
