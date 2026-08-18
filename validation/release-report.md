# CodeStable Compact release validation

- Result: **PASS**
- Version: `1.1.0`
- Generated: `2026-08-18T12:20:03+08:00`

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
  "Ran 65 tests in 9.302s",
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
  "tool_version": "1.1.0",
  "scope": "structure-only",
  "current_knowledge_validated": false,
  "current_references_checked": false,
  "next_check": "run drift to compare current references and Git changes",
  "errors": [],
  "warnings": [],
  "entry_check": {
    "current_entry": ".codestable/wiki/INDEX.md",
    "files_checked": [],
    "findings": [],
    "modified": false
  },
  "stats": {
    "cards": 0,
    "current_cards": 0,
    "proposed_cards": 0,
    "task_notes": 0,
    "active_task_notes": 0,
    "archived_task_notes": 0,
    "categories": 11
  }
}
```

### fresh_install_hash — PASS

```json
{
  "ok": true,
  "root": "/private/var/folders/0j/2l0zwgv16gsfwmlb7kjbgn8r0000gn/T/tmpt3zyvt91/fresh",
  "mode": "knowledge_wiki",
  "version": "1.1.0",
  "created": [
    ".codestable/VERSION",
    ".codestable/config.json",
    ".codestable/manifest.json",
    ".codestable/tools/cs_knowledge.py",
    ".codestable/wiki/HISTORY.md",
    ".codestable/wiki/INDEX.md",
    ".codestable/wiki/PROJECT.md",
    ".codestable/wiki/README.md",
    ".codestable/wiki/TOPICS.md",
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
  "project_data_preserved": true,
  "layout": {
    "current": {
      "entry": ".codestable/wiki/INDEX.md",
      "runtime": ".codestable/tools/cs_knowledge.py",
      "schema_version": 2
    },
    "audited_history": {
      "entry": ".codestable/wiki/HISTORY.md",
      "task_notes": ".codestable/wiki/task-notes"
    },
    "preserved_not_for_normal_reads": [
      {
        "path": ".codestable/model",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/knowledge",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/work",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/observations",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/feedback",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/evals",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/evolution",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/meta",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      },
      {
        "path": ".codestable/harness",
        "normal_task_read": false,
        "reason": "retained for migration, recovery, compatibility, or project ownership"
      }
    ]
  },
  "agents_guidance": {
    "modified": false,
    "current_entry": ".codestable/wiki/INDEX.md",
    "files_checked": [],
    "findings": []
  },
  "knowledge_migration": {
    "required": false,
    "status": "not_required",
    "legacy_roots": [
      ".codestable/model",
      ".codestable/knowledge"
    ],
    "pages": [],
    "automatic_promotion": false,
    "automatic_removal": false
  }
}
```

### fresh_install_doctor — PASS

```json
{
  "ok": true,
  "tool_version": "1.1.0",
  "scope": "structure-only",
  "current_knowledge_validated": false,
  "current_references_checked": false,
  "next_check": "run drift to compare current references and Git changes",
  "errors": [],
  "warnings": [],
  "entry_check": {
    "current_entry": ".codestable/wiki/INDEX.md",
    "files_checked": [],
    "findings": [],
    "modified": false
  },
  "stats": {
    "cards": 0,
    "current_cards": 0,
    "proposed_cards": 0,
    "task_notes": 0,
    "active_task_notes": 0,
    "archived_task_notes": 0,
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
    "task_id": "T-20260818-122002-7acd3ca2",
    "task_revision": 1,
    "updated_existing_task": false,
    "task_note": ".codestable/wiki/task-notes/2026/2026-08-18-验证订单库存知识闭环-7acd3ca2.md",
    "created_cards": [
      {
        "id": "K-20260818-122002-01-540deeee",
        "path": ".codestable/wiki/transaction-boundaries/k-20260818-122002-01-540deeee-订单与库存共享本地事务.md",
        "category": "transaction-boundaries",
        "title": "订单与库存共享本地事务"
      },
      {
        "id": "K-20260818-122002-02-c71b8785",
        "path": ".codestable/wiki/acceptance/k-20260818-122002-02-c71b8785-库存不足回滚验收.md",
        "category": "acceptance",
        "title": "库存不足回滚验收"
      },
      {
        "id": "K-20260818-122002-03-319b7db3",
        "path": ".codestable/wiki/decisions/k-20260818-122002-03-319b7db3-同库时采用本地事务.md",
        "category": "decisions",
        "title": "同库时采用本地事务"
      }
    ],
    "updated_cards": [],
    "reused_cards": [],
    "superseded_cards": [],
    "task_candidates": [],
    "card_candidates": [],
    "requires_new_task_reason": false,
    "requires_new_card_reason": false,
    "apply_allowed": true,
    "plan_token": null,
    "reference_check": {
      "blocking": false,
      "review_required": true,
      "findings": [
        {
          "record_type": "task",
          "title": "验证订单库存知识闭环",
          "issue_type": "path-missing",
          "repository": "self",
          "value": "src/orders/service.py",
          "certainty": "confirmed"
        },
        {
          "record_type": "planned-card",
          "title": "订单与库存共享本地事务",
          "issue_type": "path-missing",
          "repository": "self",
          "value": "src/orders/service.py",
          "certainty": "confirmed"
        },
        {
          "record_type": "planned-card",
          "title": "库存不足回滚验收",
          "issue_type": "path-missing",
          "repository": "self",
          "value": "src/orders/service.py",
          "certainty": "confirmed"
        },
        {
          "record_type": "planned-card",
          "title": "同库时采用本地事务",
          "issue_type": "path-missing",
          "repository": "self",
          "value": "src/orders/service.py",
          "certainty": "confirmed"
        }
      ],
      "unverified": [
        {
          "record_type": "task",
          "title": "验证订单库存知识闭环",
          "issue_type": "symbol-check-unavailable",
          "repository": "self",
          "value": "OrderService.create",
          "certainty": "unverified",
          "method": "bounded-text-scan"
        },
        {
          "record_type": "planned-card",
          "title": "订单与库存共享本地事务",
          "issue_type": "symbol-check-unavailable",
          "repository": "self",
          "value": "OrderService.create",
          "certainty": "unverified",
          "method": "bounded-text-scan"
        },
        {
          "record_type": "planned-card",
          "title": "库存不足回滚验收",
          "issue_type": "symbol-check-unavailable",
          "repository": "self",
          "value": "OrderService.create",
          "certainty": "unverified",
          "method": "bounded-text-scan"
        },
        {
          "record_type": "planned-card",
          "title": "同库时采用本地事务",
          "issue_type": "symbol-check-unavailable",
          "repository": "self",
          "value": "OrderService.create",
          "certainty": "unverified",
          "method": "bounded-text-scan"
        }
      ],
      "verified": [],
      "historical_cards_skipped": []
    },
    "index": {
      "entries": 4,
      "changed": [
        ".codestable/wiki/index.jsonl",
        ".codestable/wiki/INDEX.md",
        ".codestable/wiki/TOPICS.md",
        ".codestable/wiki/transaction-boundaries/INDEX.md",
        ".codestable/wiki/acceptance/INDEX.md",
        ".codestable/wiki/decisions/INDEX.md"
      ],
      "dry_run": false
    }
  },
  "doctor": {
    "ok": true,
    "tool_version": "1.1.0",
    "scope": "structure-only",
    "current_knowledge_validated": false,
    "current_references_checked": false,
    "next_check": "run drift to compare current references and Git changes",
    "errors": [],
    "warnings": [
      {
        "code": "wiki.category.summary.empty",
        "detail": ".codestable/wiki/transaction-boundaries/README.md has current cards but no maintained summary; use TOPICS.md for navigation or add a concise summary"
      },
      {
        "code": "wiki.category.summary.empty",
        "detail": ".codestable/wiki/acceptance/README.md has current cards but no maintained summary; use TOPICS.md for navigation or add a concise summary"
      },
      {
        "code": "wiki.category.summary.empty",
        "detail": ".codestable/wiki/decisions/README.md has current cards but no maintained summary; use TOPICS.md for navigation or add a concise summary"
      }
    ],
    "entry_check": {
      "current_entry": ".codestable/wiki/INDEX.md",
      "files_checked": [],
      "findings": [],
      "modified": false
    },
    "stats": {
      "cards": 3,
      "current_cards": 3,
      "proposed_cards": 0,
      "task_notes": 1,
      "active_task_notes": 1,
      "archived_task_notes": 0,
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
  "task_id": "T-20260818-122002-7acd3ca2",
  "task_revision": 1,
  "task_note": ".codestable/wiki/task-notes/2026/2026-08-18-验证订单库存知识闭环-7acd3ca2.md",
  "created_cards": [],
  "reused_cards": [
    "K-20260818-122002-01-540deeee",
    "K-20260818-122002-02-c71b8785",
    "K-20260818-122002-03-319b7db3"
  ],
  "superseded_cards": [],
  "task_candidates": [],
  "card_candidates": [],
  "index": {
    "entries": 4,
    "changed": [],
    "dry_run": false
  },
  "plan_token": null,
  "reference_check": {
    "blocking": false,
    "review_required": true,
    "findings": [
      {
        "record_type": "task",
        "title": "验证订单库存知识闭环",
        "issue_type": "path-missing",
        "repository": "self",
        "value": "src/orders/service.py",
        "certainty": "confirmed"
      },
      {
        "record_type": "planned-card",
        "title": "订单与库存共享本地事务",
        "issue_type": "path-missing",
        "repository": "self",
        "value": "src/orders/service.py",
        "certainty": "confirmed"
      },
      {
        "record_type": "planned-card",
        "title": "库存不足回滚验收",
        "issue_type": "path-missing",
        "repository": "self",
        "value": "src/orders/service.py",
        "certainty": "confirmed"
      },
      {
        "record_type": "planned-card",
        "title": "同库时采用本地事务",
        "issue_type": "path-missing",
        "repository": "self",
        "value": "src/orders/service.py",
        "certainty": "confirmed"
      }
    ],
    "unverified": [
      {
        "record_type": "task",
        "title": "验证订单库存知识闭环",
        "issue_type": "symbol-check-unavailable",
        "repository": "self",
        "value": "OrderService.create",
        "certainty": "unverified",
        "method": "bounded-text-scan"
      },
      {
        "record_type": "planned-card",
        "title": "订单与库存共享本地事务",
        "issue_type": "symbol-check-unavailable",
        "repository": "self",
        "value": "OrderService.create",
        "certainty": "unverified",
        "method": "bounded-text-scan"
      },
      {
        "record_type": "planned-card",
        "title": "库存不足回滚验收",
        "issue_type": "symbol-check-unavailable",
        "repository": "self",
        "value": "OrderService.create",
        "certainty": "unverified",
        "method": "bounded-text-scan"
      },
      {
        "record_type": "planned-card",
        "title": "同库时采用本地事务",
        "issue_type": "symbol-check-unavailable",
        "repository": "self",
        "value": "OrderService.create",
        "certainty": "unverified",
        "method": "bounded-text-scan"
      }
    ],
    "verified": [],
    "historical_cards_skipped": []
  }
}
```

### legacy_upgrade_preservation — PASS

```json
{
  "upgrade": {
    "ok": true,
    "root": "/private/var/folders/0j/2l0zwgv16gsfwmlb7kjbgn8r0000gn/T/tmpm_uloj_i/existing",
    "mode": "knowledge_wiki",
    "version": "1.1.0",
    "created": [
      ".codestable/VERSION",
      ".codestable/manifest.json",
      ".codestable/tools/cs_knowledge.py",
      ".codestable/wiki/HISTORY.md",
      ".codestable/wiki/INDEX.md",
      ".codestable/wiki/PROJECT.md",
      ".codestable/wiki/README.md",
      ".codestable/wiki/TOPICS.md",
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
    "backup": "/private/var/folders/0j/2l0zwgv16gsfwmlb7kjbgn8r0000gn/T/tmpm_uloj_i/existing/.codestable/backups/20260818-122003",
    "backed_up": [
      ".codestable/config.json",
      ".codestable/knowledge/notes/pitfall.md",
      ".codestable/model/domain.md",
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
    "project_data_preserved": true,
    "layout": {
      "current": {
        "entry": ".codestable/wiki/INDEX.md",
        "runtime": ".codestable/tools/cs_knowledge.py",
        "schema_version": 2
      },
      "audited_history": {
        "entry": ".codestable/wiki/HISTORY.md",
        "task_notes": ".codestable/wiki/task-notes"
      },
      "preserved_not_for_normal_reads": [
        {
          "path": ".codestable/model",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/knowledge",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/work",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/observations",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/feedback",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/evals",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/evolution",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/meta",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        },
        {
          "path": ".codestable/harness",
          "normal_task_read": false,
          "reason": "retained for migration, recovery, compatibility, or project ownership"
        }
      ]
    },
    "agents_guidance": {
      "modified": false,
      "current_entry": ".codestable/wiki/INDEX.md",
      "files_checked": [],
      "findings": []
    },
    "knowledge_migration": {
      "required": true,
      "status": "pending_page_audit",
      "legacy_roots": [
        ".codestable/model",
        ".codestable/knowledge"
      ],
      "pages": [
        {
          "path": ".codestable/model/domain.md",
          "sha256": "805ddad38a0ae6e1b412df6b8f4bead202209179eb4d98b3c1405cccfa514813",
          "bytes": 13,
          "backup_path": ".codestable/model/domain.md"
        },
        {
          "path": ".codestable/knowledge/notes/pitfall.md",
          "sha256": "473a307f07760dacf0a16eda3451e091a23631ca47aa5d6a234f1ffcf962e259",
          "bytes": 16,
          "backup_path": ".codestable/knowledge/notes/pitfall.md"
        }
      ],
      "automatic_promotion": false,
      "automatic_removal": false
    }
  },
  "data_preserved": true,
  "retired": true,
  "backup_complete": true,
  "knowledge_migration_inventory": true,
  "legacy_brief_sources": [
    ".codestable/knowledge/notes/pitfall.md",
    ".codestable/model/domain.md"
  ],
  "doctor": {
    "ok": true,
    "tool_version": "1.1.0",
    "scope": "structure-only",
    "current_knowledge_validated": false,
    "current_references_checked": false,
    "next_check": "run drift to compare current references and Git changes",
    "errors": [],
    "warnings": [],
    "entry_check": {
      "current_entry": ".codestable/wiki/INDEX.md",
      "files_checked": [],
      "findings": [],
      "modified": false
    },
    "stats": {
      "cards": 0,
      "current_cards": 0,
      "proposed_cards": 0,
      "task_notes": 0,
      "active_task_notes": 0,
      "archived_task_notes": 0,
      "categories": 11
    }
  }
}
```
