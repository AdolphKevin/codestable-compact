# Migration to CodeStable Compact 0.5

## 1. Public command surface

Keep these six public skills:

```text
cs
cs-feat
cs-issue
cs-refactor
cs-roadmap
cs-model
```

Remove public skills that represent internal phases or roles. Existing aliases may route to the matching outcome skill, but must not copy behavior.

## 2. From workflow state to evidence state

Old active state may contain fields such as `lane`, `stage`, stage history or a closed validation result. The 0.5 runtime migrates it to:

```text
goal / proposal / risk / side_effects / ledger / blockers / evidence / completion
```

Migration maps the historical cursor only to a best-effort current action/risk hint. It does **not** convert old prose or a prior “passed” field into command evidence. Re-run verification before claiming completion.

## 3. Active files

Every active task now needs:

```text
state.json
work.md
context.json
evidence.jsonl
```

Run:

```bash
python3 .codestable/tools/cs_context.py doctor
```

The runtime creates missing safe files, migrates supported state and reports broken evidence integrity or unrecoverable task data.

## 4. Replace stage commands

Conceptual mapping:

| Previous concept | 0.5 equivalent |
|---|---|
| start/finish stage | optional `action --name ...` observation |
| lane | `risk.level` L0–L3 |
| checklist complete | `check` missing evidence/open risk result |
| validation summary | Harness `verify` command evidence |
| review phase | risk-triggered `independent_review` artifact |
| final proof prose | machine `proof` generated from ledger |
| close task | `complete --result done` Harness gate |

Actions are not required in the old sequence.

## 5. Declare task contracts and boundaries

For migrated active work, add at least objective, acceptance and a write boundary. L2/L3 also need invariants and a ready proposal. Register actual changed paths so risk reflects reality.

Do not use broad `**` write permission merely to make migration easy. Preserve external authorization and rollback requirements explicitly.

## 6. Rebuild evidence honestly

Use `snapshot` for state-derived scope/audit/proposal/invariant evidence, `verify` for commands, and `record` for fingerprinted external artifacts. The declared reviewer producer must differ from the Owner; trusted identity requires Host Adapter attestation.

Keep failures and blockers. Do not delete failed evidence to make the ledger look clean; repair and append a later result.

## 7. Configuration upgrade

Bootstrap preserves unknown project preferences but restores non-bypassable boundaries:

```bash
python3 skills/cs/scripts/bootstrap.py /path/to/project --upgrade
```

It enforces evidence-state artifacts, exact L0–L3 requirements, passive write-only observations, explicit-only Meta, signed evaluation, private holdout location and policy-scoped promotion authority. Unsafe prior runtime files are backed up before replacement.

## 8. Observation migration

Use `scripts/migrate_alpha_observations.py` for old observation files. The current schema records risk/action/evidence/completion metadata instead of lane/stage metadata. Migration is dry-run first and strips raw or unsupported content.

## 9. Meta policy rename

The former lifecycle transition policy is now `control.evidence-convergence`, covered by evidence-repair and core-runtime fixtures. Update proposals or campaign references that used the old policy id.

## 10. Release checks

```bash
python3 scripts/validate_skills.py
python3 scripts/validate_control_plane.py
python3 scripts/validate_meta_effect.py
python3 -m unittest discover -s tests -v
```

Treat missing host adapters or private holdout access as `underpowered`, not as measured improvement.
