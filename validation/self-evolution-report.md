# Controlled Harness self-evolution report

## Verdict

```text
SELF_EVOLUTION_MEASURED_PASS
```

CodeStable completed a controlled recovery of the fixture-covered `interaction.route-summary-copy` policy with the real Codex host.

```text
3 repeated feedback signals
→ Harness diagnosis
→ committed Agent hypothesis
→ Agent-authored minimal policy overlay
→ measured validity pre-pass, k=5
→ immutable evaluation challenge
→ real Codex held-in / held-out / safety runs
→ signed aggregate import
→ deterministic acceptance
→ policy-scoped Agent approval
→ isolated promotion
→ verified rollback
```

## Behavioral result

The controlled defect forced every route summary to emit `[ROUTE_CONFIRMATION_REQUIRED]`. The candidate removed that extra interaction without changing the selected route.

| Split | Degraded | Evolved | Route accuracy |
|---|---:|---:|---:|
| held-in | 0/5 | 5/5 | 10/10 |
| held-out | 0/5 | 5/5 | 10/10 |
| safety | 0/5 | 5/5 | 10/10 |
| Total | 0/15 | 15/15 | 30/30 |

Human-interrupt rate changed from `1.0` to `0.0` in every split. Candidate total-token and context metrics remained within protocol limits. Held-out median duration changed from 9.81s to 10.90s, within the allowed 15% regression limit.

Runtime Profile: `codex-cli 0.144.1`, `gpt-5.6-sol`, five independent repeats per split and variant.

## Validity interventions

Two evaluator defects were found before the valid run:

1. The route scorer accepted `feature` but not Codex's equivalent `feat` output. The scorer was repaired and calibrated before rerunning.
2. The first cost scorer treated cache-dependent uncached tokens as protocol `median_tokens`. It was corrected to total input plus output tokens; uncached tokens remain supplementary evidence.

Neither invalid run was used for the positive verdict. Promotion occurred only after the repaired evaluation passed the signed decision and quality gates.

## Limits

- This proves controlled recovery capability, not autonomous discovery of an unknown production defect.
- It covers one low-risk policy surface and does not establish cross-policy generalization.
- The current Agent authored the hypothesis and candidate; CodeStable intentionally does not let deterministic scripts invent policy changes.
- Promotion and rollback occurred only in an isolated temporary project.
- `context_bytes` is an explicit four-bytes-per-input-token estimate.

Machine-readable evidence: [`self-evolution-report.json`](self-evolution-report.json).
