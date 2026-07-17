# CodeStable Compact release validation

- Result: **PASS**
- Version: `1.0.0`
- Generated: `2026-07-17T19:27:33+08:00`

| Check | Result |
|---|---|
| `unit_regression_suite` | PASS |
| `single_public_skill` | PASS |
| `retired_skills_absent` | PASS |
| `retired_tools_absent_from_assets` | PASS |
| `canonical_assets_doctor` | PASS |
| `fresh_install_hash` | PASS |
| `fresh_install_doctor` | PASS |
| `read_and_dry_run_zero_writes` | PASS |
| `knowledge_round_trip` | PASS |
| `learning_idempotency` | PASS |
| `legacy_upgrade_preservation` | PASS |

## Details

### unit_regression_suite — PASS

```json
[
  "Ran 23 tests in 2.165s",
  "",
  "OK"
]
```

### single_public_skill — PASS

```json
{
  "skills": [
    "cs"
  ]
}
```

### retired_skills_absent — PASS

```json
{
  "present": []
}
```

### retired_tools_absent_from_assets — PASS

```json
{
  "present": []
}
```

### canonical_assets_doctor — PASS

```json
{
  "ok": true,
  "tool_version": "1.0.0",
  "errors": [],
  "warnings": [],
  "stats": {
    "cards": 0,
    "current_cards": 0,
    "task_notes": 0,
    "categories": 11
  }
}
```

### fresh_install_hash — PASS

```json
{
  "ok": true,
  "root": "/private/var/folders/0j/2l0zwgv16gsfwmlb7kjbgn8r0000gn/T/tmpbimljgll/fresh",
  "mode": "knowledge_wiki",
  "version": "1.0.0",
  "created": [
    ".codestable/VERSION",
    ".codestable/config.json",
    ".codestable/manifest.json",
    ".codestable/tools/cs_knowledge.py",
    ".codestable/wiki/INDEX.md",
    ".codestable/wiki/PROJECT.md",
    ".codestable/wiki/README.md",
    ".codestable/wiki/acceptance/INDEX.md",
    ".codestable/wiki/acceptance/README.md",
    ".codestable/wiki/architecture/INDEX.md",
    ".codestable/wiki/architecture/README.md",
    ".codestable/wiki/compatibility/INDEX.md",
    ".codestable/wiki/compatibility/README.md",
    ".codestable/wiki/data-model/INDEX.md",
    ".codestable/wiki/data-model/README.md",
    ".codestable/wiki/decisions/INDEX.md",
    ".codestable/wiki/decisions/README.md",
    ".codestable/wiki/error-handling/INDEX.md",
    ".codestable/wiki/error-handling/README.md",
    ".codestable/wiki/index.jsonl",
    ".codestable/wiki/interfaces/INDEX.md",
    ".codestable/wiki/interfaces/README.md",
    ".codestable/wiki/learning.schema.json",
    ".codestable/wiki/performance-risks/INDEX.md",
    ".codestable/wiki/performance-risks/README.md",
    ".codestable/wiki/requirements/INDEX.md",
    ".codestable/wiki/requirements/README.md",
    ".codestable/wiki/security-boundaries/INDEX.md",
    ".codestable/wiki/security-boundaries/README.md",
    ".codestable/wiki/task-notes/.gitkeep",
    ".codestable/wiki/transaction-boundaries/INDEX.md",
    ".codestable/wiki/transaction-boundaries/README.md"
  ],
  "updated": [],
  "preserved": [],
  "retired": [],
  "backup": null,
  "backed_up": [],
  "tool_hash_matches_asset": true,
  "project_data_preserved": true
}
```

### fresh_install_doctor — PASS

```json
{
  "ok": true,
  "tool_version": "1.0.0",
  "errors": [],
  "warnings": [],
  "stats": {
    "cards": 0,
    "current_cards": 0,
    "task_notes": 0,
    "categories": 11
  }
}
```

### read_and_dry_run_zero_writes — PASS

```json
{
  "digest_equal": true,
  "git_clean": true
}
```

### knowledge_round_trip — PASS

```json
{
  "learn": {
    "ok": true,
    "idempotent": false,
    "dry_run": false,
    "task_id": "T-20260717-192733-441b0e76",
    "task_note": ".codestable/wiki/task-notes/2026/2026-07-17-验证订单库存知识闭环-441b0e76.md",
    "created_cards": [
      {
        "id": "K-20260717-192733-01-fecbdf94",
        "path": ".codestable/wiki/transaction-boundaries/k-20260717-192733-01-fecbdf94-订单与库存共享本地事务.md",
        "category": "transaction-boundaries",
        "title": "订单与库存共享本地事务"
      },
      {
        "id": "K-20260717-192733-02-5d4ab981",
        "path": ".codestable/wiki/acceptance/k-20260717-192733-02-5d4ab981-库存不足回滚验收.md",
        "category": "acceptance",
        "title": "库存不足回滚验收"
      },
      {
        "id": "K-20260717-192733-03-cdf60d8c",
        "path": ".codestable/wiki/decisions/k-20260717-192733-03-cdf60d8c-同库时采用本地事务.md",
        "category": "decisions",
        "title": "同库时采用本地事务"
      }
    ],
    "reused_cards": [],
    "superseded_cards": [],
    "plan_token": null,
    "index": {
      "entries": 4,
      "changed": [
        ".codestable/wiki/index.jsonl",
        ".codestable/wiki/INDEX.md",
        ".codestable/wiki/transaction-boundaries/INDEX.md",
        ".codestable/wiki/acceptance/INDEX.md",
        ".codestable/wiki/decisions/INDEX.md"
      ],
      "dry_run": false
    }
  },
  "doctor": {
    "ok": true,
    "tool_version": "1.0.0",
    "errors": [],
    "warnings": [],
    "stats": {
      "cards": 3,
      "current_cards": 3,
      "task_notes": 1,
      "categories": 11
    }
  },
  "matched_titles": [
    "同库时采用本地事务",
    "库存不足回滚验收",
    "订单与库存共享本地事务"
  ]
}
```

### learning_idempotency — PASS

```json
{
  "ok": true,
  "idempotent": true,
  "dry_run": false,
  "task_id": "T-20260717-192733-441b0e76",
  "task_note": ".codestable/wiki/task-notes/2026/2026-07-17-验证订单库存知识闭环-441b0e76.md",
  "created_cards": [],
  "reused_cards": [
    "K-20260717-192733-01-fecbdf94",
    "K-20260717-192733-02-5d4ab981",
    "K-20260717-192733-03-cdf60d8c"
  ],
  "superseded_cards": [],
  "index": {
    "entries": 4,
    "changed": [],
    "dry_run": false
  },
  "plan_token": null
}
```

### legacy_upgrade_preservation — PASS

```json
{
  "upgrade": {
    "ok": true,
    "root": "/private/var/folders/0j/2l0zwgv16gsfwmlb7kjbgn8r0000gn/T/tmp3kymuk3m/existing",
    "mode": "knowledge_wiki",
    "version": "1.0.0",
    "created": [
      ".codestable/VERSION",
      ".codestable/manifest.json",
      ".codestable/tools/cs_knowledge.py",
      ".codestable/wiki/INDEX.md",
      ".codestable/wiki/PROJECT.md",
      ".codestable/wiki/README.md",
      ".codestable/wiki/acceptance/INDEX.md",
      ".codestable/wiki/acceptance/README.md",
      ".codestable/wiki/architecture/INDEX.md",
      ".codestable/wiki/architecture/README.md",
      ".codestable/wiki/compatibility/INDEX.md",
      ".codestable/wiki/compatibility/README.md",
      ".codestable/wiki/data-model/INDEX.md",
      ".codestable/wiki/data-model/README.md",
      ".codestable/wiki/decisions/INDEX.md",
      ".codestable/wiki/decisions/README.md",
      ".codestable/wiki/error-handling/INDEX.md",
      ".codestable/wiki/error-handling/README.md",
      ".codestable/wiki/index.jsonl",
      ".codestable/wiki/interfaces/INDEX.md",
      ".codestable/wiki/interfaces/README.md",
      ".codestable/wiki/learning.schema.json",
      ".codestable/wiki/performance-risks/INDEX.md",
      ".codestable/wiki/performance-risks/README.md",
      ".codestable/wiki/requirements/INDEX.md",
      ".codestable/wiki/requirements/README.md",
      ".codestable/wiki/security-boundaries/INDEX.md",
      ".codestable/wiki/security-boundaries/README.md",
      ".codestable/wiki/task-notes/.gitkeep",
      ".codestable/wiki/transaction-boundaries/INDEX.md",
      ".codestable/wiki/transaction-boundaries/README.md"
    ],
    "updated": [
      ".codestable/config.json"
    ],
    "preserved": [],
    "retired": [
      ".codestable/tools/cs_context.py",
      ".codestable/tools/cs_eval.py",
      ".codestable/tools/cs_evolve.py",
      ".codestable/tools/cs_feedback.py",
      ".codestable/tools/cs_fixture.py",
      ".codestable/tools/cs_harness.py",
      ".codestable/tools/cs_meta.py",
      ".codestable/tools/cs_observe.py",
      ".codestable/tools/cs_policy.py"
    ],
    "backup": "/private/var/folders/0j/2l0zwgv16gsfwmlb7kjbgn8r0000gn/T/tmp3kymuk3m/existing/.codestable/backups/20260717-192733",
    "backed_up": [
      ".codestable/config.json",
      ".codestable/tools/cs_context.py",
      ".codestable/tools/cs_eval.py",
      ".codestable/tools/cs_evolve.py",
      ".codestable/tools/cs_feedback.py",
      ".codestable/tools/cs_fixture.py",
      ".codestable/tools/cs_harness.py",
      ".codestable/tools/cs_meta.py",
      ".codestable/tools/cs_observe.py",
      ".codestable/tools/cs_policy.py"
    ],
    "tool_hash_matches_asset": true,
    "project_data_preserved": true
  },
  "data_preserved": true,
  "retired": true,
  "backup_complete": true,
  "doctor": {
    "ok": true,
    "tool_version": "1.0.0",
    "errors": [],
    "warnings": [],
    "stats": {
      "cards": 0,
      "current_cards": 0,
      "task_notes": 0,
      "categories": 11
    }
  }
}
```
