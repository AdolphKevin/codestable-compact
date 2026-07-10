# Feature recovery

Use only when state and repository evidence disagree or active files are damaged.

1. Preserve the current files; do not overwrite evidence.
2. Inspect `state.json`, the headings of `work.md`, Git status/diff and relevant tests.
3. Infer the latest stage whose exit criteria are demonstrably satisfied.
4. Repair missing schema fields with the runtime tool or a minimal edit.
5. Record the reconciliation in `work.md` under changes/decisions.
6. Clear invalid context receipts by starting a new session key; do not trust old session receipts.
7. Continue from the first unproven exit criterion.

Historical feature directories are not a default recovery source. Search archive only when the active work explicitly originated there or regression evidence requires it.
