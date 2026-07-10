# Inspiration review

This document records which ideas were retained, adapted or deliberately rejected. It is a design trace, not a claim of source-code reuse.

## CodeStable

Repository: https://github.com/liuzhengdongfortest/CodeStable

### Retained

- Software lifecycle entities are the center: requirement, decision, roadmap, feature, issue, refactor and knowledge.
- Durable state lives in a readable project-local `.codestable/` tree.
- Human engineering ownership remains explicit.
- Requirements, contracts and architectural decisions can outlive one implementation.
- Feature/issue/refactor paths retain design, review and verification discipline.

### Changed

- The root entry routes **and executes** by default instead of stopping at a recommendation.
- Internal phases are no longer separate user-visible skills.
- File presence no longer serves as the primary progress detector; `state.json.stage` is authoritative.
- Repeated full `.codestable/` startup scans are replaced by explicit links and session-scoped receipts.
- Historical feature directories are archive evidence, not default design input.
- Passing review/QA stages do not each create a separate report file.

### Why

A lifecycle remains valuable even when its phases are hidden from the command surface. Collapsing command boundaries removes user coordination cost without removing engineering checks.

## Trellis

Repository: https://github.com/mindfold-ai/Trellis

### Retained/adapted

- Task-centered state and repository-resident work artifacts.
- Resume from task status and artifact state instead of requiring the user to remember the next command.
- Compact indexes as pointers; load only applicable details.
- Stage/phase-specific instructions rather than one large always-loaded procedure.
- Verification as an explicit lifecycle phase.
- Promotion of durable findings from completed work into current project standards/knowledge.

### Changed

- CodeStable Compact uses one cross-kind work envelope (`state.json`, `work.md`, `context.json`) instead of a broader workspace/journal topology.
- Context reuse is explicitly scoped to one live conversation key; a cold session does not trust an old receipt as memory.
- The durable destination is split into current model and reusable knowledge, while process history is excluded from normal retrieval.

### Why

Task state and selective loading solve the same startup problem as a large skill tree, but with less user-visible surface. The live-session restriction prevents an unsafe optimization: unchanged bytes do not imply a new model session remembers their meaning.

## ponytail

Repository: https://github.com/DietrichGebert/ponytail

### Retained/adapted

- Inspect the actual flow before editing.
- Prefer existing behavior and patterns, then standard library/platform facilities, then installed dependencies, then minimal new code.
- Fix root causes rather than symptoms.
- Do not add abstractions, dependencies or compatibility layers for hypothetical future needs.
- Prefer deletion and consolidation when they solve the problem.
- Keep canonical skills portable and put host-specific adapters elsewhere.

### Changed

- Minimality is embedded as a cross-cutting engineering constraint inside each lifecycle rather than a separate always-on persona.
- Review does not only report complexity; each lifecycle repairs blocking findings and reruns verification automatically.

### Why

Minimality is most effective when it participates in design, implementation and review exit criteria. It should constrain the lifecycle, not compete with it as another command the user must remember.

## Original synthesis

The combined architecture is not a union of all mechanisms. It deliberately chooses:

```text
software lifecycle model (CodeStable)
+ resumable task state and selective loading (Trellis)
+ minimum-mechanism constraint (ponytail)
− command-per-phase
− global history scans
− mandatory report-per-gate
− agent-orchestration machinery
```

The result is one daily entry, five event lifecycles, three active-work files and an opt-in historical archive.

## Self-Harness, AHE and ACE

Papers:

- Self-Harness: https://arxiv.org/abs/2606.09498
- Agentic Harness Engineering: https://arxiv.org/abs/2604.25850
- Agentic Context Engineering: https://arxiv.org/abs/2510.04618

### Retained/adapted

- Harness changes are explicit objects with a predicted behavior change and exact file-level surface.
- Baseline and candidate are compared under locked model, adapter, evaluator, budget and task splits.
- Held-in evidence targets an observed weakness; evaluator-only held-out and safety protect general behavior.
- Context lessons use incremental structured playbook deltas rather than full-prompt rewriting.
- Version lineage, evaluation evidence and rollback make improvements falsifiable and reversible.

### Changed

- Normal software delivery does not continuously run the optimizer. It writes only a passive temporary observation without extra model calls or history retrieval.
- No failure threshold, scheduler or run count creates a proposal. A maintainer must explicitly select finished observations and diagnose the problem first.
- Project knowledge, product defects, model variance and environment failures are separated from genuine Harness mechanisms.
- Evaluation results must cross an external signed aggregate boundary; direct candidate/worker self-report is not trusted.
- Every Harness promotion, including low-risk routing or playbook changes, requires a human Gate.
- The evaluator, signing key, private held-out, Gate policy, manifest, evidence and promotion machinery are protected.

### Why

CodeStable operates in real repositories where the primary job is software delivery. Continuous optimizer activity would add latency and drift to that job. The adopted pattern is therefore “always observable, selectively evolvable”: collect bounded evidence cheaply, then run a controlled Self-Harness-style loop only when a real maintenance need is explicitly chosen.

## Darwin Gödel Machine

Paper: https://arxiv.org/abs/2505.22954

### Deferred ideas

- multiple parent Harness versions;
- a population archive of viable variants;
- parent selection that balances performance and underexplored lineages;
- explicit novelty/diversity pressure;
- stepping-stone variants that may become useful later.

### Why deferred

Open-ended population search costs substantially more evaluation and increases the attack surface, lineage complexity and risk of optimizing benchmark artifacts. CodeStable first uses a single active lineage with parallel minimal candidates and a conservative non-regression gate. Population search should be added only after real evidence shows hill climbing has plateaued and the host has strong sandboxing plus evaluator capacity.
