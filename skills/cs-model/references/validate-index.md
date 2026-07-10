# Model: validate and index

## Validate content

Check:

- statements are current or explicitly status-marked;
- terminology matches domain language and code-facing names where appropriate;
- requirement and contract statements are testable/observable;
- decisions do not conflict without supersession;
- links resolve;
- no secrets, private data or volatile logs were promoted;
- no implementation checklist or task diary became current truth;
- code/model drift is visible and linked to work.

Use targeted search to find exact duplicate terms or conflicting contract names. Do not recursively read all archive.

## Update indexes

For each changed current document, add/update one concise row in `model/INDEX.md` or `knowledge/INDEX.md`:

- relative path;
- one-sentence summary;
- useful tags/domain;
- for knowledge, evidence/last-validated reference.

Remove rows for deleted/superseded current files. The index should be cheap to read; do not paste headings or full requirements. Keep a top-level index under the configured line budget (default 160); shard by bounded context/domain and leave only shard pointers when it grows beyond that.

## Promotion review

When invoked from feature/issue/refactor acceptance, confirm that the promoted statement remains useful after the task id and implementation details are removed. If not, leave it in archive.

## Close or transition

If model changes require code:

1. create/link a feature, issue or refactor;
2. state the drift and acceptance;
3. continue the executable lifecycle when the user requested the outcome;
4. do not call the model edit itself “complete system behavior.”

Otherwise record validation, mark done and archive the model-edit work aggregate.
