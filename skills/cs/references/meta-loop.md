# CodeStable Meta loop protocol

Load this reference only for an explicit `/cs feedback ...`, `/cs meta ...`, or `/cs evolve ...` compatibility request. Normal delivery must not retrieve this file or any `.codestable/meta/`, `.codestable/observations/`, `.codestable/evolution/`, `.codestable/evals/`, or Harness version-history content.

## Invariants

```text
Always observable, selectively evolvable.
No fixture coverage, no evolution.
Creative proposal by Agent; measurement and locking by deterministic tools.
No negative verdict before validity pre-pass.
No online production A/B; evaluate offline on fixtures and private held-out.
```

A normal run may write a compact trace and finish. It never imports `cs_meta.py`, diagnoses a signal, creates a proposal, runs a Harness evaluation, or changes the active Harness.

## 1. Observe and triage

Inspect only named finished observations:

```bash
python3 .codestable/tools/cs_observe.py show --run <run-id>
python3 .codestable/tools/cs_feedback.py triage \
  --run <run-id> \
  --classification <classification> \
  --signal <stable-signal> \
  --summary "<evidence-grounded summary>" \
  --policy <policy-id> \
  --actor <actor>
```

Classifications are:

- `harness_policy`
- `evaluation_defect`
- `model_profile_variance`
- `project_knowledge`
- `product_code`
- `environment`
- `insufficient_evidence`

Do not turn every incident into a Harness change. Evaluation defects repair the fixture/scorer; project knowledge updates the project knowledge plane; product defects update software; runtime-profile differences remain profile-scoped evidence.

## 2. Convert production incidents into fixtures

An Agent writes a structured fixture with production provenance, context requirements, tolerant oracle, calibrated scorer and policy mapping. Register it deterministically:

```bash
python3 .codestable/tools/cs_feedback.py fixture-register \
  --feedback <feedback-id> \
  --file <agent-authored-fixture.json> \
  --actor <actor>
```

The policy audit is the admission control:

```bash
python3 .codestable/tools/cs_policy.py audit
```

A whitelisted policy must map to an editable surface, allowed change types, an authority rule, fixture IDs and every required fixture layer. Missing coverage blocks proposal registration.

## 3. Accumulate signals, do not chase one point

Preview groups by exact signal, policy, runtime profile and baseline Harness identity:

```bash
python3 .codestable/tools/cs_meta.py trigger-scan
```

Apply only when deliberately requested:

```bash
python3 .codestable/tools/cs_meta.py trigger-scan --apply
```

The default threshold is configured in `meta.trigger.minimum_matching_signals`. Applying a scan may only create bounded campaigns. It may not diagnose, propose, evaluate, accept or promote.

A maintainer may also open a campaign explicitly from classified feedback:

```bash
python3 .codestable/tools/cs_meta.py campaign-new \
  --title "<title>" \
  --feedback <feedback-id> \
  --signal <signal> \
  --policy <policy-id> \
  --runtime-profile <exact-profile> \
  --budget <budget-id>
```

## 4. Diagnose before proposing

```bash
python3 .codestable/tools/cs_meta.py diagnose \
  --campaign <campaign-id> \
  --classification harness \
  --summary "<why this is a Harness policy defect>" \
  --mechanism <mechanism-id> \
  --surface <surface-id> \
  --confidence <0..1>
```

Only a Harness diagnosis mapped to the campaign policy/surface can proceed. Stop when evidence points to the product, project knowledge, environment, model-profile variance, evaluation defect, or insufficient evidence.

## 5. Freeze a committed hypothesis

The Agent writes a hypothesis document before seeing candidate evaluation results. It should state:

- production evidence and failure mechanism;
- target metric and evidence label;
- policy/change type and fixture set;
- expected improvement;
- explicit regression risks and falsification conditions;
- runtime-profile scope.

Commit it, then freeze it:

```bash
python3 .codestable/tools/cs_meta.py hypothesis-freeze \
  --campaign <campaign-id> \
  --file <hypothesis.md> \
  --actor <agent-or-maintainer> \
  --commit <git-commit>
```

The file must exist at the declared commit and remain byte-identical. This prevents after-the-fact hypothesis rewriting.

## 6. Agent-authored proposal

The Agent—not an optimizer script—writes:

1. a human-readable variant document;
2. a proposal JSON conforming to `meta/proposal.schema.json`;
3. a minimal overlay containing only declared surface paths.

Register it:

```bash
python3 .codestable/tools/cs_meta.py proposal-register \
  --campaign <campaign-id> \
  --proposal <proposal.json> \
  --overlay <overlay-directory>
```

Admission rejects script-authored proposals, undeclared policies, disallowed change types, missing fixture layers, protected paths, extra files, stale hypothesis provenance and budget overflow.

## 7. Validity pre-pass

Before attributing a failure or improvement to policy, run:

```bash
python3 .codestable/tools/cs_meta.py validity-prepass \
  --campaign <campaign-id> \
  --candidate <candidate-id> \
  --repeats <k>=5 \
  --judge-profile <separate-judge-profile> \
  --actor <actor>
```

It checks:

- every fixture has complete onboarding and subject-matter context;
- required references exist;
- oracle tolerance is structured rather than brittle exact wording;
- scorer is calibrated with evidence;
- stochastic fixtures use at least five repeats;
- judge profile is isolated from the tested profile;
- hypothesis and candidate provenance remain unchanged.

Results are labelled:

- `[measured]`: directly executed deterministic or sufficiently repeated evidence;
- `[soft]`: useful expert/judge evidence that is not a hard promotion Gate;
- `[underpowered]`: missing adapter, low sample count, uncalibrated scorer or incomplete context.

Only a passing measured pre-pass may create a trusted evaluation challenge.

## 8. Trusted evaluation

Freeze the exact candidate, baseline, fixture set, runtime profile, adapter, budget and Meta evidence:

```bash
python3 .codestable/tools/cs_meta.py evaluation-challenge \
  --campaign <campaign-id> \
  --candidate <candidate-id> \
  --model-profile <exact-profile> \
  --adapter <adapter-id> \
  --evaluator <evaluator-id> \
  --budget <budget-id>
```

The external evaluator runs baseline and candidate in fresh equivalent sandboxes. Private held-out and signing credentials stay outside candidate/worker access. Import only signed aggregate results through `cs_eval.py`; raw prompts, private tasks and task-level traces are forbidden.

Then decide mechanically:

```bash
python3 .codestable/tools/cs_meta.py decide \
  --campaign <campaign-id> --candidate <candidate-id>
```

## 9. Quality gates and acceptance

Record required measured gates:

```bash
python3 .codestable/tools/cs_meta.py quality-gate \
  --campaign <campaign-id> \
  --name <policy_audit|validity_prepass|regression|package> \
  --status passed --label measured \
  --actor <actor> --command "<command>" \
  --evidence <artifact> --note "<summary>"
```

Acceptance requires all configured gates, unchanged signed evaluation and the authority declared by the first-class policy registry:

```bash
python3 .codestable/tools/cs_meta.py acceptance-check \
  --campaign <campaign-id> --candidate <candidate-id>
```

- prompt copy and evaluated playbook entries may permit `agent` approval;
- workflow routing, Gate thresholds, lifecycle, artifact schema and runtime tools require `owner` approval.

Promote only after the correct checkpoint:

```bash
python3 .codestable/tools/cs_meta.py promote \
  --campaign <campaign-id> --candidate <candidate-id> \
  --approval-kind <owner|agent> \
  --approved-by <actor> \
  --reason "<evidence-based reason>"
```

Every accepted version links policy, fixtures, hypothesis, proposal, validity, signed evaluation, quality gates, runtime profile and approval. Rejected variants remain indexed.

## 10. Rollback

Use the immutable Harness snapshot through the low-level evolution tool:

```bash
python3 .codestable/tools/cs_evolve.py rollback \
  --version <version> --actor <actor> --reason "<reason>"
```

Rollback changes only the active Harness pointer/files and records provenance. It does not automatically open another campaign.
