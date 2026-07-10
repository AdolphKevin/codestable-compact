# Design decisions

## D-001 — `/cs` defaults to auto-run

**Status:** accepted

**Context:** A route-only root forces the user to wait for an internal classification and send a second confirmation even when no engineering decision is needed.

**Decision:** `entry.mode` defaults to `auto`. Route choice is followed by immediate lifecycle execution in the same invocation. `/cs route` and `entry.mode=route` preserve diagnostic/backward-compatible behavior.

**Consequence:** The root skill must be capable of initializing, resuming and activating sibling lifecycles; route prose cannot be an exit condition in auto mode.

## D-002 — One user-visible skill per event lifecycle

**Status:** accepted

**Context:** Design, implementation, review, QA and acceptance are phases of feature delivery, not usually independent user intents.

**Decision:** Keep one skill for each dominant software event: feature, issue, refactor, roadmap and model. Internal phase references may remain modular and load on demand.

**Consequence:** Review discipline is preserved as automatic loops. Separate phase skills may exist only as optional host aliases and must not own workflow logic.

## D-003 — Explicit state, not artifact inference

**Status:** accepted

**Context:** Inferring progress by Glob-ing design/checklist/review files requires repeated scans and becomes ambiguous when files are partial or stale.

**Decision:** `state.json.stage/status` is authoritative. Git/code/test evidence can trigger reconciliation, but file presence does not define the state machine.

**Consequence:** Resume requires one small state read and avoids a directory-wide continuation check.

## D-004 — Three required active-work files

**Status:** accepted

**Context:** A document per phase duplicates background and creates synchronization work.

**Decision:** Require only `state.json`, `work.md` and `context.json`. Passing transient checks do not require separate reports.

**Consequence:** Material evidence and decisions remain auditable in one aggregate; ceremony scales with lane risk rather than number of phases.

## D-005 — Receipts are live-session scoped

**Status:** accepted

**Context:** A file hash proves bytes are unchanged, but it does not prove a fresh model session remembers previously read semantics.

**Decision:** Every plan/receipt uses a key that is stable only within the current live conversation. A cold conversation creates a new key and rereads necessary material. Persistent `work.md` holds the compact conclusions needed for recovery.

**Consequence:** Token savings are safe within long-running work sessions; cold-start correctness is not traded for an invalid memory assumption.

## D-006 — Archive retrieval is opt-in

**Status:** accepted

**Context:** Historical feature designs accumulate obsolete assumptions and can dominate noisy retrieval.

**Decision:** Normal search covers current model and curated knowledge. Active work is resumed by exact id/scope. Archive requires an explicit scope and reason.

**Consequence:** Completion must promote current truths and reusable knowledge before archival, or those facts will not appear in normal future retrieval.

## D-007 — A Gate represents authority/risk, not phase completion

**Status:** accepted

**Context:** Mandatory design-review/code-review/QA pauses make every phase transition a user coordination event.

**Decision:** Technical reviews and verification run automatically and loop on failure. Human Gates are limited to irreversible actions, public contract choices, security/data policy, material operational risk, unresolved accepted-decision conflicts or unavailable acceptance authority.

**Consequence:** More work proceeds unattended, while the points that genuinely need human ownership remain explicit and evidence-based.

## D-008 — No semantic database in the initial runtime

**Status:** accepted

**Context:** A vector database or daemon could improve fuzzy history search but adds dependencies, synchronization and another state authority.

**Decision:** Use explicit links, compact indexes, deterministic text search and archive opt-in. The Agent performs semantic judgment; the runtime performs mechanical filtering.

**Consequence:** The runtime stays inspectable and standard-library-only. More retrieval machinery requires evidence from real project scale, not anticipation.

## D-009 — Goal is an execution policy, not a separate lifecycle entity

**Status:** accepted

**Context:** A bounded outcome and autonomous implement/validate loop can apply to a feature, issue, refactor or a roadmap item; a separate goal skill duplicates those event semantics.

**Decision:** Use `execution.mode=continuous_until_gate` across all lifecycles. Route the observable event normally; use roadmap when the bounded outcome spans several independently accepted items.

**Consequence:** “Describe the outcome and leave” is the default interaction, while artifacts remain typed by the software event they represent.

## D-010 — Normal work is observable but not self-modifying

**Status:** accepted

**Context:** Running weakness mining, proposal and regression evaluation after every software task adds latency, token cost and Harness drift to the primary workflow.

**Decision:** Every normal Skill invocation may write one best-effort temporary observation, but no normal run may diagnose, propose, evaluate, promote or retrieve observation history.

**Consequence:** Evidence exists when a real Harness problem appears, while normal delivery keeps its original execution path and cost profile.

## D-011 — Observations are temporary flight-recorder data

**Status:** accepted

**Decision:** Store compact `meta.json`, `events.jsonl` and `outcome.json` under pending/flagged/selected states. Prohibit raw prompts, model responses, source contents, diffs, secrets, private held-out and task-level evaluator traces. Apply size and retention limits.

**Consequence:** Observation history does not become another first-order feature archive or privacy-heavy transcript corpus.

## D-012 — Evolution requires explicit evidence selection

**Status:** accepted

**Decision:** No task count, failure threshold or scheduler creates an evolution case. A maintainer explicitly selects named finished observations or a named existing signal. Cases freeze one baseline Harness version and contain compressed evidence only.

**Consequence:** Single-run noise cannot silently become a permanent rule, and unrelated history is not scanned.

## D-013 — Diagnose before proposing

**Status:** accepted

**Decision:** Classify each selected case as Harness, project knowledge, product code, model variance, environment or insufficient evidence. Only Harness classification mapped to a declared editable surface may create a candidate.

**Consequence:** Harness evolution is not used as a substitute for fixing software or curating project truth.

## D-014 — Evaluator and promotion control plane are protected

**Status:** accepted

**Decision:** Private held-out tasks, evaluator logic, signing key, split assignments, Gate policy, promotion rules, observations, evidence, manifest, registry and evolution/evaluator tools are outside the candidate edit surface.

**Consequence:** A candidate cannot redefine success, forge its own evidence, broaden its whitelist or erase lineage.

## D-015 — Harness edits are bounded overlays

**Status:** accepted

**Decision:** `harness/manifest.json` declares exact editable files and risk classes. Candidate overlays must contain exactly those declared files and freeze base/candidate SHA-256 hashes.

**Consequence:** Candidate generation is inspectable, parallelizable and reversible; broad self-rewrites and file smuggling are rejected.

## D-016 — Evaluation results are externally authenticated aggregates

**Status:** accepted

**Decision:** A challenge immutably locks baseline version/content, candidate content/definition, protocol, model profile, adapter, evaluator, budget, splits, repeats and nonce. The project accepts only aggregate results signed with an evaluator-only HMAC key; direct unsigned `eval-record` is absent.

**Consequence:** The control plane can reject tampering, replay and lock mismatch. Actual trust still requires the host to keep the key and private held-out outside candidate/worker environments.

## D-017 — Promotion is non-regressive and always human-approved

**Status:** accepted

**Decision:** Compare baseline and candidate on held-in, private held-out and safety splits with repeats. Require measurable improvement, no permitted regression, perfect configured safety and bounded resource/interaction metrics. Every passing candidate, including low risk, stops at a human promotion Gate.

**Consequence:** Plausible prose and local success cannot activate a new Harness. Human authority remains explicit for changes that affect future work.

## D-018 — Evolving memory uses evaluated incremental deltas

**Status:** accepted

**Decision:** Store Harness lessons as structured JSONL playbook items. Add, revise, merge or deactivate individual items; never rewrite the full memory after each task. Playbook deltas are ordinary candidates subject to trusted evaluation and the promotion Gate.

**Consequence:** Cross-task execution knowledge can improve without context collapse or unverified memory pollution.

## D-019 — Version lineage is immutable and rollback is explicit

**Status:** accepted

**Decision:** Snapshot all declared surfaces before and after promotion. Record parent, case, candidate, evaluation hash, actor and reason. Rollback restores a named verified snapshot and never auto-starts a replacement proposal.

**Consequence:** Every Harness change is auditable and reversible without turning rollback into another autonomous loop.

## D-020 — Single-lineage maintenance before open-ended populations

**Status:** accepted

**Decision:** Start with conservative, explicitly initiated single-lineage improvement. Population archives, novelty and automatic parent selection are deferred until benchmark evidence and isolation budgets justify them.

**Consequence:** The design remains understandable and safe while preserving a future path to broader evolutionary search.
