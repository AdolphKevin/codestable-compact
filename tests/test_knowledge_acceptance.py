from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support import bootstrap_module, knowledge_module, tree_digest


TOPIC = "shipment-flow"
SELF_SCOPE = {"repository": "self", "path": "shipment/service.py", "symbol": "create_shipment"}


def durable_item(category: str, title: str, knowledge: str, **overrides: object) -> dict:
    item: dict[str, object] = {
        "category": category,
        "title": title,
        "knowledge": knowledge,
        "future_use": [
            {
                "change": "替换消息发布适配器",
                "actor": "履约服务维护者",
                "constraint": "事务 outbox 与领域层隔离约束",
            },
            {
                "change": "调整 dispatcher 或履约事务",
                "actor": "事件投递维护者",
                "constraint": "至少一次发布、原子提交与消费幂等约束",
            },
        ],
        "scopes": [SELF_SCOPE],
        "topics": [TOPIC],
        "confidence": "verified",
        "evidence": [
            {
                "kind": "test",
                "artifact": "tests.test_shipment.ShipmentTests",
                "result": "匿名履约集成测试通过",
                "supports": "事务 outbox 和幂等边界可由公开测试验证",
            }
        ],
    }
    item.update(overrides)
    return item


def decision_item(title: str, knowledge: str, **overrides: object) -> dict:
    return durable_item(
        "decisions",
        title,
        knowledge,
        context="数据库提交成功但直接发布失败会让业务记录与事件不一致。",
        rationale="同一数据库事务可验证地防止业务记录存在但事件永久丢失。",
        alternatives=["数据库提交后直接发布消息", "引入分布式两阶段提交"],
        consequences=["dispatcher 可以重试", "消费者必须按 event_id 幂等", "允许重复投递但不允许丢失事件"],
        **overrides,
    )


def task_payload(title: str, **overrides: object) -> dict:
    task: dict[str, object] = {
        "title": title,
        "kind": "task",
        "status": "completed",
        "request": "演进合成履约服务的消息发布架构。",
        "summary": "在合成代码和测试中验证事务 outbox 边界。",
        "result": "发布适配器可替换，事务与幂等约束保持不变。",
        "scopes": [SELF_SCOPE],
        "topics": [TOPIC],
        "tags": ["synthetic-shipment"],
        "verification": ["python3 -m unittest discover -s tests -v"],
        "knowledge_summary": "复用 D-0007；只记录真正可复用的新约束。",
        "source": {"fixture": "synthetic-shipment"},
        "knowledge_use": [],
    }
    task.update(overrides)
    return task


class KnowledgeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap = bootstrap_module()
        cls.tool = knowledge_module()

    def make_repository(self, temporary: str) -> tuple[Path, Path, dict]:
        base = Path(temporary)
        root = base / "synthetic-shipment-service"
        related = base / "synthetic-shared-contracts"
        root.mkdir()
        related.mkdir()
        self.bootstrap.install(root)

        source = root / "shipment" / "service.py"
        source.parent.mkdir(parents=True)
        source.write_text(
            "class MemoryStore:\n"
            "    def __init__(self):\n"
            "        self.shipments = []\n"
            "        self.outbox = []\n\n"
            "def create_shipment(store, shipment_id):\n"
            "    event_id = f'shipment-{shipment_id}'\n"
            "    store.shipments.append(shipment_id)\n"
            "    store.outbox.append({'event_id': event_id, 'kind': 'ShipmentCreated'})\n"
            "    return event_id\n",
            encoding="utf-8",
        )
        test_file = root / "tests" / "test_shipment.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "import unittest\n"
            "from shipment.service import MemoryStore, create_shipment\n\n"
            "class ShipmentTests(unittest.TestCase):\n"
            "    def test_shipment_and_outbox_are_recorded_together(self):\n"
            "        store = MemoryStore()\n"
            "        event_id = create_shipment(store, 's-1')\n"
            "        self.assertEqual(store.shipments, ['s-1'])\n"
            "        self.assertEqual(store.outbox[0]['event_id'], event_id)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n",
            encoding="utf-8",
        )
        contract = related / "events" / "shipment.py"
        contract.parent.mkdir(parents=True)
        contract.write_text("class ShipmentCreated:\n    pass\n", encoding="utf-8")
        (root / "AGENTS.md").write_text(
            "Read .codestable/model/INDEX.md before development.\n",
            encoding="utf-8",
        )

        config_path = root / ".codestable" / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["wiki"]["repositories"] = {"shared-contracts": {"root": "../synthetic-shared-contracts"}}
        config["wiki"]["topics"] = {
            TOPIC: {
                "label": "履约事件流",
                "summary": "组织发货事务、事件发布与消费幂等的当前知识。",
            }
        }
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        config = self.tool.load_config(root)
        self.tool.rebuild_indexes(root, config)
        return root, related, config

    def seed_d0007(self, root: Path, config: dict) -> tuple[str, str]:
        old = self.tool.learn(
            root,
            config,
            {
                "task": task_payload("记录 D-0006 直接发布方案"),
                "items": [
                    decision_item(
                        "D-0006 提交后直接发布",
                        "发货任务提交后由业务层直接调用具体消息客户端。",
                    )
                ],
            },
        )
        old_id = old["created_cards"][0]["id"]
        d0007_scopes = [
            SELF_SCOPE,
            {"repository": "shared-contracts", "path": "events/shipment.py", "symbol": "ShipmentCreated"},
            {"repository": "future-messaging", "path": "events/shipment.py", "symbol": "ShipmentCreated"},
        ]
        current = self.tool.learn(
            root,
            config,
            {
                "task": task_payload("采用 D-0007 事务 outbox 决策"),
                "items": [
                    decision_item(
                        "D-0007 发货事件事务 outbox",
                        "发货任务与待发布事件必须在同一数据库事务中持久化；提交后由独立 dispatcher 至少一次发布，消费者按 event_id 幂等，领域层不依赖具体消息客户端。",
                        scopes=d0007_scopes,
                        supersedes=[old_id],
                        supersession_reason="原方案允许数据库成功而消息发布失败，不能保持业务事件不丢失。",
                    ),
                    durable_item(
                        "transaction-boundaries",
                        "发货任务与 outbox 的提交点",
                        "发货任务和 outbox 记录共享同一事务提交点，消息发送不在该事务内执行。",
                    ),
                    durable_item(
                        "acceptance",
                        "发货事件原子性与幂等验收",
                        "发布失败后 dispatcher 可重试；重复投递相同 event_id 不产生重复业务效果。",
                        scopes=[
                            {"repository": "self", "path": "tests/test_shipment.py", "symbol": "ShipmentTests"}
                        ],
                    ),
                ],
            },
        )
        current_id = next(item["id"] for item in current["created_cards"] if item["title"].startswith("D-0007"))
        self.tool.learn(
            root,
            config,
            {
                "task": task_payload(
                    "取消一次临时消息客户端实验",
                    status="cancelled",
                    result="临时实验被取消，只保留可追溯任务记录。",
                    knowledge_summary="没有形成长期结论。",
                ),
                "items": [],
            },
        )
        return old_id, current_id

    def test_rebuild_reports_stale_agent_entry_without_modifying_project_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fresh = self.bootstrap.install(root)
            self.assertEqual(fresh["layout"]["current"]["entry"], ".codestable/wiki/INDEX.md")
            agents = root / "AGENTS.md"
            original = "Read .codestable/model/INDEX.md and .codestable/wiki/INDEX.md.\n"
            agents.write_text(original)
            plan = self.bootstrap.install(root, rebuild=True, dry_run=True)
            result = self.bootstrap.install(root, rebuild=True, plan_token=plan["plan_token"])
            self.assertEqual(agents.read_text(), original)
            codes = {item["code"] for item in result["agents_guidance"]["findings"]}
            self.assertTrue({"agents.entry.missing", "agents.entry.retired", "agents.entry.conflict"} <= codes)
            self.assertFalse(result["agents_guidance"]["modified"])
            config = self.tool.load_config(root)
            self.assertNotIn("legacy_read_roots", config["wiki"])
            before = tree_digest(root)
            checked = self.tool.doctor(root, config)
            self.assertEqual({item["code"] for item in checked["entry_check"]["findings"]}, codes)
            self.assertEqual(before, tree_digest(root))

    def test_old_runtime_format_requires_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root)
            config_path = root / ".codestable" / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["schema_version"] = 1
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(self.tool.KnowledgeError, "bootstrap.py --rebuild"):
                self.tool.load_config(root)

    def test_task_only_repository_remains_searchable_without_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            task = task_payload(
                "记录一次性合成夹具整理",
                result="只整理合成夹具，不形成长期知识。",
                knowledge_summary="没有未来消费者，因此只写任务记录。",
            )
            learned = self.tool.learn(root, config, {"task": task, "items": []})

            brief = self.tool.selected_brief_payload(
                root, config, "合成夹具整理", [], [], None, False, [TOPIC]
            )

            self.assertIn(learned["task_id"], {item["id"] for item in brief["related_tasks"]})
            self.assertEqual(brief["knowledge"], [])

    def test_d0007_indexes_topics_history_and_brief(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            old_id, current_id = self.seed_d0007(root, config)
            category = self.tool.index_root(root, config) / "decisions" / "INDEX.md"
            category.write_text(
                f"# old mixed index\n\n- current {current_id}\n- superseded {old_id}\n",
                encoding="utf-8",
            )
            repair = self.tool.rebuild_indexes(root, config)
            self.assertIn(".codestable/cache/wiki/decisions/INDEX.md", repair["changed"])

            category_text = category.read_text(encoding="utf-8")
            history_text = (self.tool.index_root(root, config) / "HISTORY.md").read_text(encoding="utf-8")
            topics_text = (self.tool.index_root(root, config) / "TOPICS.md").read_text(encoding="utf-8")
            root_text = (self.tool.index_root(root, config) / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("D-0007 发货事件事务 outbox", category_text)
            self.assertNotIn("D-0006 提交后直接发布", category_text)
            self.assertIn("D-0006 提交后直接发布", history_text)
            self.assertIn(current_id, history_text)
            self.assertIn("取消一次临时消息客户端实验", history_text)
            self.assertIn("D-0007 发货事件事务 outbox", topics_text)
            self.assertIn("发货任务与 outbox 的提交点", topics_text)
            self.assertNotIn("发货任务与待发布事件必须在同一数据库事务中持久化", topics_text)
            self.assertIn("唯一当前入口", root_text)
            self.assertIn("业务主题", root_text)
            self.assertIn("历史索引", root_text)
            self.assertIn("最近完成任务", root_text)
            self.assertIn("未完成任务", root_text)

            queries = [
                self.tool.selected_brief_payload(root, config, "更换消息系统", [], [], None, False, [TOPIC]),
                self.tool.selected_brief_payload(root, config, "修改发布实现", ["shipment/service.py"], [], None, False),
                self.tool.selected_brief_payload(root, config, "检查创建发货", [], ["create_shipment"], None, False),
            ]
            for brief in queries:
                identifiers = {item["id"] for item in brief["knowledge"]}
                self.assertIn(current_id, identifiers)
                self.assertNotIn(old_id, identifiers)
            historical = self.tool.selected_brief_payload(
                root, config, "追踪直接发布迁移", [], [], None, True, [TOPIC]
            )
            self.assertIn(old_id, {item["id"] for item in historical["history"]})

    def test_repository_scopes_and_reference_certainty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            _, current_id = self.seed_d0007(root, config)
            missing = self.tool.learn(
                root,
                config,
                {
                    "task": task_payload("记录待复核 dispatcher 入口"),
                    "items": [
                        durable_item(
                            "architecture",
                            "dispatcher 当前入口",
                            "dispatcher 由独立模块执行批量发布。",
                            scopes=[
                                {"repository": "self", "path": "shipment/removed_dispatcher.py", "symbol": "Dispatcher"}
                            ],
                        )
                    ],
                },
            )
            missing_id = missing["created_cards"][0]["id"]

            references = self.tool.current_reference_drift(root, config)

            self.assertTrue(
                any(item["card_id"] == missing_id and item["issue_type"] == "path-missing" for item in references["findings"])
            )
            self.assertTrue(
                any(
                    item["card_id"] == current_id
                    and item["issue_type"] == "repository-unconfigured"
                    and item["repository"] == "future-messaging"
                    for item in references["unverified"]
                )
            )
            self.assertFalse(
                any(item.get("repository") == "future-messaging" and item["issue_type"] == "path-missing" for item in references["findings"])
            )
            self.assertTrue(
                any(
                    item["card_id"] == current_id
                    and item["issue_type"] == "path-verified"
                    and item["repository"] == "shared-contracts"
                    for item in references["verified"]
                )
            )

    def test_legacy_relative_paths_and_symbol_scan_are_conservative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            learned = self.tool.learn(
                root,
                config,
                {
                    "task": task_payload("记录旧格式履约路径"),
                    "items": [
                        durable_item(
                            "architecture",
                            "旧格式履约服务位置",
                            "创建发货任务的入口位于履约服务模块。",
                            paths=["shipment/service.py"],
                            symbols=["RenamedShipmentService"],
                            scopes=[],
                        )
                    ],
                },
            )
            card_id = learned["created_cards"][0]["id"]
            card_path = root / learned["created_cards"][0]["path"]
            metadata, body, _ = self.tool.read_markdown(card_path)
            metadata.pop("scopes", None)
            card_path.write_text(self.tool.render_front_matter(metadata, body), encoding="utf-8")
            self.tool.rebuild_indexes(root, config)

            references = self.tool.current_reference_drift(root, config)

            self.assertTrue(
                any(
                    item["card_id"] == card_id
                    and item["issue_type"] == "path-verified"
                    and item["reference_format"] == "legacy-relative"
                    for item in references["verified"]
                )
            )
            self.assertTrue(
                any(item["card_id"] == card_id and item["issue_type"] == "symbol-text-not-found" for item in references["unverified"])
            )
            self.assertFalse(any(item["card_id"] == card_id for item in references["findings"]))

    def test_doctor_reference_modes_and_empty_summary_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            self.seed_d0007(root, config)
            ordinary = self.tool.doctor(root, config)
            strict = self.tool.doctor(root, config, check_current_references=True)
            drift = self.tool.drift_payload(root, config, references_only=True)

            self.assertTrue(ordinary["ok"])
            self.assertEqual(ordinary["scope"], "structure-only")
            self.assertFalse(ordinary["current_knowledge_validated"])
            self.assertEqual(strict["scope"], "structure+current-references")
            self.assertIn("current_references", strict)
            self.assertEqual(drift["mode"], "references-only")
            self.assertTrue(any(item["code"] == "wiki.category.summary.empty" for item in ordinary["warnings"]))
            self.assertTrue(any(item["code"].startswith("agents.entry.") for item in ordinary["warnings"]))

    def test_knowledge_use_requires_traceable_impact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            _, card_id = self.seed_d0007(root, config)
            read_only = task_payload("只读取 D-0007")
            read_only["knowledge_use"] = [
                {"card_id": card_id, "card_revision": 1, "use": "reviewed", "detail": "读取了卡片。", "evidence": []}
            ]
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, {"task": read_only, "items": []}, dry_run=True)

            influenced = task_payload("替换消息系统并增加批量发送")
            influenced["knowledge_use"] = [
                {
                    "card_id": card_id,
                    "card_revision": 1,
                    "use": "changed-design",
                    "detail": "把改动限制在发布适配器和 dispatcher，保留业务事务内的 outbox 写入。",
                    "before": "任务允许在业务层直接调用新消息客户端。",
                    "after": "最终只替换发布适配器并在 dispatcher 中批量发送。",
                    "evidence": [
                        {
                            "kind": "design",
                            "artifact": "shipment/service.py#create_shipment",
                            "result": "业务入口仍只写 shipment 与 outbox。",
                            "supports": "对应 D-0007 的事务提交点和领域层依赖边界。",
                        },
                        {
                            "kind": "test",
                            "artifact": "ShipmentTests.test_shipment_and_outbox_are_recorded_together",
                            "result": "合成原子性测试通过。",
                            "supports": "验证 shipment 与 outbox 同时记录。",
                        },
                    ],
                }
            ]
            plan = self.tool.learn(root, config, {"task": influenced, "items": []}, dry_run=True)
            self.assertTrue(plan["apply_allowed"])
            applied = self.tool.learn(root, config, {"task": influenced, "items": []}, plan_token=plan["plan_token"])
            note = (root / applied["task_note"]).read_text(encoding="utf-8")
            self.assertIn("最终只替换发布适配器", note)
            self.assertIn("ShipmentTests.test_shipment_and_outbox_are_recorded_together", note)

    def test_durable_decision_reuse_orthogonal_creation_and_task_only_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            _, d0007_id = self.seed_d0007(root, config)
            duplicate = {
                "task": task_payload("重复描述 D-0007"),
                "items": [
                    decision_item(
                        "D-0007 发货事件事务 outbox",
                        "发货任务与待发布事件必须在同一数据库事务中持久化；提交后由独立 dispatcher 至少一次发布，消费者按 event_id 幂等，领域层不依赖具体消息客户端。",
                    )
                ],
            }
            duplicate_plan = self.tool.learn(root, config, duplicate, dry_run=True)
            self.assertFalse(duplicate_plan["apply_allowed"])
            self.assertEqual(duplicate_plan["card_candidates"][0]["card_id"], d0007_id)

            ordering = {
                "task": task_payload("确认 dispatcher 顺序约束"),
                "items": [
                    decision_item(
                        "D-0008 dispatcher 实体内顺序",
                        "dispatcher 必须按业务实体保持相对顺序，并由契约测试约束每批事件数的上限语义。",
                        new_card_reason="顺序与批量契约是 D-0007 未覆盖的正交长期约束。",
                    )
                ],
            }
            created = self.tool.learn(root, config, ordering)
            new_id = created["created_cards"][0]["id"]
            new_metadata, _, _ = self.tool.read_markdown(root / created["created_cards"][0]["path"])
            _, old_metadata, _ = self.tool.scan_existing_records(
                root / ".codestable" / "wiki", self.tool.configured_categories(config)
            )[0][d0007_id]
            self.assertNotEqual(new_id, d0007_id)
            self.assertEqual(new_metadata.get("supersedes", []), [])
            self.assertEqual(old_metadata["status"], "current")

            before_cards = self.tool.status_payload(root, config)["cards"]
            tuning_task = task_payload(
                "试验当前客户端批量参数",
                summary="在合成测试中试用了单次 25 条的临时参数。",
                result="参数只适用于当前客户端，不形成跨实现约束。",
                knowledge_summary="临时批量数只进入任务记录，不建立知识卡片。",
            )
            tuning = self.tool.learn(root, config, {"task": tuning_task, "items": []})
            self.assertEqual(self.tool.status_payload(root, config)["cards"], before_cards)
            self.assertIn("临时批量数", (root / tuning["task_note"]).read_text(encoding="utf-8"))

    def test_card_scope_update_preserves_scope_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            learned = self.tool.learn(
                root,
                config,
                {
                    "task": task_payload("记录 dispatcher 稳定边界"),
                    "items": [
                        durable_item(
                            "architecture",
                            "dispatcher 模块边界",
                            "dispatcher 独立于领域层并只依赖发布端口。",
                        )
                    ],
                },
            )
            card = learned["created_cards"][0]
            replacement = root / "shipment" / "dispatcher.py"
            replacement.write_text("class Dispatcher:\n    pass\n", encoding="utf-8")
            update = durable_item(
                "architecture",
                "dispatcher 模块边界",
                "dispatcher 独立于领域层并只依赖发布端口。",
                operation="update",
                card_id=card["id"],
                expected_revision=1,
                scopes=[{"repository": "self", "path": "shipment/dispatcher.py", "symbol": "Dispatcher"}],
            )
            result = self.tool.learn(root, config, {"task": task_payload("更新 dispatcher 范围"), "items": [update]})
            metadata, _, _ = self.tool.read_markdown(root / result["updated_cards"][0]["path"])
            self.assertEqual(result["created_cards"], [])
            self.assertEqual(metadata["revision"], 2)
            self.assertIn(SELF_SCOPE, metadata["scope_history"][0]["scopes"])

    def test_idempotency_state_binding_and_synthetic_output_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _, config = self.make_repository(temporary)
            payload = {
                "task": task_payload("建立合成验收基线"),
                "items": [
                    durable_item(
                        "acceptance",
                        "合成履约原子性验收",
                        "创建发货任务时 shipment 与 outbox 必须同时可见。",
                    )
                ],
            }
            before = tree_digest(root / ".codestable")
            plan = self.tool.learn(root, config, payload, dry_run=True)
            self.assertEqual(before, tree_digest(root / ".codestable"))
            applied = self.tool.learn(root, config, payload, plan_token=plan["plan_token"])
            repeated = self.tool.learn(root, config, payload)
            self.assertEqual(applied["task_id"], plan["task_id"])
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(self.tool.rebuild_indexes(root, config)["changed"], [])

            changed_source = root / "shipment" / "service.py"
            stale_plan = self.tool.learn(
                root,
                config,
                {"task": task_payload("验证并发状态绑定"), "items": []},
                dry_run=True,
            )
            changed_source.write_text(changed_source.read_text(encoding="utf-8") + "\n# synthetic change\n", encoding="utf-8")
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(
                    root,
                    config,
                    {"task": task_payload("验证并发状态绑定"), "items": []},
                    plan_token=stale_plan["plan_token"],
                )

            subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=root,
                check=True,
                text=True,
                capture_output=True,
            )
            generated = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / ".codestable" / "wiki").rglob("*.md")
            )
            self.assertNotIn("AdolphKevin", generated)
            self.assertNotIn("codestable-compact", generated)


if __name__ == "__main__":
    unittest.main()
