# Examples

The examples show evidence convergence, not a required command order.

## 1. L0 documentation correction

```bash
python3 .codestable/tools/cs_context.py new model \
  'correct API name' --risk 0 --allow-path 'docs/**'
python3 .codestable/tools/cs_context.py contract \
  --work correct-api-name \
  --objective 'Use the canonical API name' \
  --acceptance 'No stale spelling remains'
python3 .codestable/tools/cs_context.py ledger-add \
  --work correct-api-name change 'Corrected two references' --path docs/api.md
python3 .codestable/tools/cs_context.py verify \
  --work correct-api-name --type diff_check -- git diff --check
python3 .codestable/tools/cs_context.py verify \
  --work correct-api-name --type format_check -- python3 scripts/check_docs.py
python3 .codestable/tools/cs_context.py complete \
  --work correct-api-name --result done
```

The task does not need a design, audit ledger or independent reviewer.

## 2. Failed verification repairs understanding

```text
objective: release a concurrency slot on cancellation
fact: slot acquisition wraps run_customer_turn
assumption: CancelledError reaches the existing cleanup handler
change: add semaphore acquisition before the turn
verify: cancellation scenario → FAIL
new fact: cancellation occurs before the inner finally is entered
proposal update: acquire and release in an outer async context
execute: move ownership boundary
verify: cancellation scenario → PASS
```

The failed result stays in `evidence.jsonl`; the later pass does not erase it. Completion uses the current required PASS evidence and open-risk state.

## 3. L2 cross-module task

```bash
python3 .codestable/tools/cs_context.py new feature \
  'cap complete AI turns' --risk 2 \
  --allow-path 'app/**' --allow-path 'tests/**'

python3 .codestable/tools/cs_context.py contract \
  --work cap-complete-ai-turns \
  --objective 'Limit simultaneous complete turns' \
  --acceptance 'Observed active turns never exceed the configured cap' \
  --acceptance 'Cancellation and exceptions release capacity' \
  --invariant 'One conversation remains serial' \
  --non-goal 'No general-purpose scheduler'

python3 .codestable/tools/cs_context.py ledger-add \
  --work cap-complete-ai-turns fact \
  'handler enters run_customer_turn after conversation lock' \
  --source app/handler.py

python3 .codestable/tools/cs_context.py proposal \
  --work cap-complete-ai-turns \
  --summary 'Own one global slot across the complete turn' \
  --rationale 'The expensive boundary is the complete turn, not only the LLM call' \
  --non-change 'Conversation locking and response quality' \
  --evidence-required 'integration cap, cancellation release, multi-conversation load'

python3 .codestable/tools/cs_context.py snapshot \
  --work cap-complete-ai-turns --type audit_ledger
python3 .codestable/tools/cs_context.py snapshot \
  --work cap-complete-ai-turns --type proposal

# Implement, then register actual changed paths.
python3 .codestable/tools/cs_context.py ledger-add \
  --work cap-complete-ai-turns change 'Added turn slot ownership' \
  --path app/turn_runtime.py
python3 .codestable/tools/cs_context.py ledger-add \
  --work cap-complete-ai-turns change 'Added integration scenarios' \
  --path tests/test_turn_slots.py

python3 .codestable/tools/cs_context.py verify \
  --work cap-complete-ai-turns --type integration_test -- \
  python3 -m unittest tests.test_turn_slots

cat > review.md <<'REVIEW'
PASS: checked cancellation ordering, exception cleanup, cross-conversation fairness,
and confirmed no old slot path remains reachable.
REVIEW
python3 .codestable/tools/cs_context.py record \
  --work cap-complete-ai-turns --type independent_review \
  --status PASS --producer reviewer-1 --artifact review.md --verdict PASS

python3 .codestable/tools/cs_context.py proof --work cap-complete-ai-turns
python3 .codestable/tools/cs_context.py check --work cap-complete-ai-turns
python3 .codestable/tools/cs_context.py complete \
  --work cap-complete-ai-turns --result done
```

## 4. Dynamic escalation

A task created as L1 registers `src/auth_policy.py`. Because this is executable authorization code, the Harness raises it to L3. Existing targeted-test evidence remains in the ledger but no longer satisfies completion; the task now needs full audit, invariant contract, live validation, rollback proof, independent review and a regression fixture.

The Owner cannot lower risk to avoid the new requirements.

## 5. Blocked live validation

```bash
python3 .codestable/tools/cs_context.py verify \
  --work rotate-payment-key --type live_validation --timeout 30 -- \
  python3 scripts/live_check.py
```

When the command cannot run because credentials or the environment are unavailable, record `BLOCKED` rather than `FAIL`. Then:

```bash
python3 .codestable/tools/cs_context.py complete \
  --work rotate-payment-key --result blocked \
  --reason 'Authorized staging credentials unavailable'
```

A blocked task is not archived as completed.

## 6. Passive observation events

Normal work may append compact events such as:

```json
{"type":"action_selected","payload":{"action":"verify"}}
{"type":"evidence_recorded","payload":{"evidence_type":"integration_test","status":"PASS"}}
{"type":"risk_escalated","payload":{"from":1,"to":3,"reason":"critical_path_signal"}}
{"type":"completion_checked","payload":{"status":"INELIGIBLE","missing_count":2}}
```

Raw prompts, model responses, source, diffs, secrets and full tool output are forbidden. Normal work never reads these observations.
