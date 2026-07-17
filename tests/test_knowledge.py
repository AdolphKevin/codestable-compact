from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from support import ASSET_TOOL, base_task, bootstrap_module, knowledge_module, tree_digest, write_payload


CATEGORY_ITEMS = {
    "requirements": ("订单创建要求", "订单创建只在库存可用时成功。"),
    "architecture": ("订单服务职责", "订单服务协调订单持久化与库存预留。"),
    "interfaces": ("库存不足接口语义", "库存不足时接口返回稳定的领域错误码。"),
    "data-model": ("订单状态约束", "新订单只允许从 pending 状态进入 confirmed。"),
    "error-handling": ("库存不足异常", "库存不足属于可预期领域异常，不进行内部重试。"),
    "transaction-boundaries": ("订单库存事务", "订单写入与库存预留在同一本地事务内提交。"),
    "compatibility": ("错误码兼容", "既有库存不足错误码必须保持兼容。"),
    "performance-risks": ("库存锁竞争", "批量创建订单会增加库存行锁竞争。"),
    "security-boundaries": ("订单租户边界", "订单创建只能访问当前租户的库存。"),
    "acceptance": ("库存不足验收", "库存不足时订单数和库存数均保持不变。"),
    "decisions": ("采用本地事务", "订单与库存同库期间采用本地事务而不是异步补偿。"),
}


class KnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bootstrap = bootstrap_module()
        cls.tool = knowledge_module()

    def new_root(self, temporary: str) -> tuple[Path, dict]:
        root = Path(temporary)
        self.bootstrap.install(root, upgrade=False)
        return root, self.tool.load_config(root)

    def all_category_payload(self, title: str = "订单库存一致性修复") -> dict:
        task = base_task(title)
        items = []
        for category, (item_title, knowledge) in CATEGORY_ITEMS.items():
            item = {
                "category": category,
                "title": item_title,
                "knowledge": knowledge,
                "confidence": "verified",
                "evidence": ["tests.test_orders passes"],
                "status": "current",
            }
            if category == "decisions":
                item["rationale"] = "当前部署在同一数据库，单事务是更小且可验证的边界。"
                item["implications"] = ["拆库前重新评估"]
            items.append(item)
        return {"task": task, "items": items}

    def brief(self, root: Path, config: dict, task: str, paths=(), symbols=(), include_superseded=False) -> dict:
        return self.tool.selected_brief_payload(root, config, task, list(paths), list(symbols), None, include_superseded)

    def test_read_commands_and_learning_dry_run_do_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            before = tree_digest(root / ".codestable")
            self.brief(root, config, "修复订单事务", ["src/orders/service.py"])
            self.tool.status_payload(root, config)
            self.tool.doctor(root, config)
            self.tool.rebuild_indexes(root, config, dry_run=True)
            plan = self.tool.learn(root, config, self.all_category_payload(), dry_run=True)
            after = tree_digest(root / ".codestable")
            self.assertEqual(before, after)
            self.assertEqual(plan["index"]["entries"], 12)
            self.assertIn(".codestable/wiki/index.jsonl", plan["index"]["changed"])
            self.assertIn(".codestable/wiki/architecture/INDEX.md", plan["index"]["changed"])

    def test_learn_creates_all_categories_task_note_and_searchable_brief(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            result = self.tool.learn(root, config, self.all_category_payload())
            self.assertFalse(result["idempotent"])
            self.assertEqual(len(result["created_cards"]), 11)
            self.assertTrue((root / result["task_note"]).is_file())
            for created in result["created_cards"]:
                self.assertTrue((root / created["path"]).is_file())
                index = root / ".codestable" / "wiki" / created["category"] / "INDEX.md"
                self.assertIn(created["title"], index.read_text(encoding="utf-8"))
            entries = (root / ".codestable" / "wiki" / "index.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(entries), 12)
            doctor = self.tool.doctor(root, config)
            self.assertTrue(doctor["ok"], doctor)
            brief = self.brief(
                root,
                config,
                "调整订单创建接口的库存事务和兼容错误码",
                ["src/orders/service.py"],
                ["OrderService.create"],
            )
            titles = {item["title"] for item in brief["knowledge"]}
            self.assertIn("订单库存事务", titles)
            self.assertIn("错误码兼容", titles)
            self.assertIn("采用本地事务", titles)
            self.assertTrue(brief["related_tasks"])
            self.assertTrue(brief["read_only"])

    def test_duplicate_payload_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = self.all_category_payload()
            first = self.tool.learn(root, config, payload)
            before = tree_digest(root / ".codestable" / "wiki")
            second = self.tool.learn(root, config, payload)
            after = tree_digest(root / ".codestable" / "wiki")
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(before, after)
            self.assertEqual(second["task_id"], first["task_id"])

    def test_duplicate_items_create_one_card_and_one_task_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            item = {
                "category": "architecture",
                "title": "订单模块边界",
                "knowledge": "订单模块通过库存服务协调库存预留。",
            }
            result = self.tool.learn(root, config, {"task": base_task(), "items": [item, dict(item)]})
            self.assertEqual(len(result["created_cards"]), 1)
            self.assertEqual(result["reused_cards"], [])
            _, tasks = self.tool.scan_existing_records(
                self.tool.wiki_root(root, config), self.tool.configured_categories(config)
            )
            self.assertEqual(tasks[result["task_id"]][1]["card_ids"], [result["created_cards"][0]["id"]])

    def test_supersession_hides_stale_card_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            first_payload = {
                "task": base_task("初始事务决策"),
                "items": [
                    {
                        "category": "transaction-boundaries",
                        "title": "订单提交边界",
                        "knowledge": "订单写入先提交，再异步预留库存。",
                        "confidence": "accepted",
                    }
                ],
            }
            first = self.tool.learn(root, config, first_payload)
            old_id = first["created_cards"][0]["id"]

            second_task = base_task("修正事务决策")
            second_task["summary"] = "确认订单和库存必须原子提交。"
            second_task["result"] = "旧异步边界被新本地事务边界取代。"
            second_payload = {
                "task": second_task,
                "items": [
                    {
                        "category": "transaction-boundaries",
                        "title": "订单提交边界",
                        "knowledge": "订单写入与库存预留在同一本地事务内提交。",
                        "rationale": "防止部分成功。",
                        "confidence": "verified",
                        "evidence": ["rollback test passes"],
                        "supersedes": [old_id],
                    }
                ],
            }
            second = self.tool.learn(root, config, second_payload)
            new_id = second["created_cards"][0]["id"]
            old_path = next((root / ".codestable" / "wiki" / "transaction-boundaries").glob(f"{old_id.lower()}-*.md"))
            old_text = old_path.read_text(encoding="utf-8")
            self.assertIn('status: "superseded"', old_text)
            self.assertIn(new_id, old_text)

            normal_ids = {item["id"] for item in self.brief(root, config, "订单库存事务")["knowledge"]}
            self.assertIn(new_id, normal_ids)
            self.assertNotIn(old_id, normal_ids)
            history_ids = {item["id"] for item in self.brief(root, config, "订单库存事务", include_superseded=True)["knowledge"]}
            self.assertIn(old_id, history_ids)
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_failed_supersession_rolls_back_and_retry_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            first = self.tool.learn(
                root,
                config,
                {
                    "task": base_task("旧架构边界"),
                    "items": [
                        {
                            "category": "architecture",
                            "title": "订单边界",
                            "knowledge": "订单模块直接修改库存记录。",
                        }
                    ],
                },
            )
            old_id = first["created_cards"][0]["id"]
            payload = {
                "task": base_task("修正架构边界"),
                "items": [
                    {
                        "category": "architecture",
                        "title": "订单边界",
                        "knowledge": "订单模块只能通过库存服务预留库存。",
                        "supersedes": [old_id],
                    }
                ],
            }
            before = tree_digest(root / ".codestable")
            original = self.tool.update_card_supersession

            def fail_supersession(*args, **kwargs):
                raise OSError("injected supersession failure")

            self.tool.update_card_supersession = fail_supersession
            try:
                with self.assertRaises(OSError):
                    self.tool.learn(root, config, payload)
            finally:
                self.tool.update_card_supersession = original

            self.assertEqual(before, tree_digest(root / ".codestable"))
            retry = self.tool.learn(root, config, payload)
            self.assertFalse(retry["idempotent"])
            cards, _ = self.tool.scan_existing_records(
                self.tool.wiki_root(root, config), self.tool.configured_categories(config)
            )
            self.assertEqual(cards[old_id][1]["status"], "superseded")
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_each_write_failure_rolls_back_before_retry(self) -> None:
        for fail_at in range(1, 9):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as temporary:
                root, config = self.new_root(temporary)
                first = self.tool.learn(
                    root,
                    config,
                    {
                        "task": base_task("旧事务知识"),
                        "items": [
                            {
                                "category": "transaction-boundaries",
                                "title": "订单事务",
                                "knowledge": "订单先提交再预留库存。",
                            }
                        ],
                    },
                )
                old_id = first["created_cards"][0]["id"]
                payload = {
                    "task": base_task("新事务知识"),
                    "items": [
                        {
                            "category": "transaction-boundaries",
                            "title": "订单事务",
                            "knowledge": "订单与库存预留在同一事务中提交。",
                            "supersedes": [old_id],
                        },
                        {
                            "category": "acceptance",
                            "title": "订单回滚验收",
                            "knowledge": "库存不足时订单和库存都保持不变。",
                        },
                    ],
                }
                before = tree_digest(root / ".codestable")
                original = self.tool.atomic_write_text
                calls = 0

                def fail_once(path, content):
                    nonlocal calls
                    if ".transactions" not in Path(path).parts:
                        calls += 1
                        if calls == fail_at:
                            raise OSError(f"injected write failure {fail_at}")
                    return original(path, content)

                self.tool.atomic_write_text = fail_once
                try:
                    with self.assertRaises(OSError):
                        self.tool.learn(root, config, payload)
                finally:
                    self.tool.atomic_write_text = original
                self.assertEqual(before, tree_digest(root / ".codestable"))

                retry = self.tool.learn(root, config, payload)
                self.assertFalse(retry["idempotent"])
                self.assertTrue(self.tool.doctor(root, config)["ok"])
                third = self.tool.learn(root, config, payload)
                self.assertTrue(third["idempotent"])

    def test_hard_crash_is_recovered_on_next_learn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            first = self.tool.learn(
                root,
                config,
                {
                    "task": base_task("旧事务知识"),
                    "items": [
                        {
                            "category": "transaction-boundaries",
                            "title": "订单事务",
                            "knowledge": "订单先提交再预留库存。",
                        }
                    ],
                },
            )
            old_id = first["created_cards"][0]["id"]
            payload = {
                "task": base_task("崩溃恢复事务知识"),
                "items": [
                    {
                        "category": "transaction-boundaries",
                        "title": "订单事务",
                        "knowledge": "订单与库存预留在同一事务中提交。",
                        "supersedes": [old_id],
                    },
                    {
                        "category": "acceptance",
                        "title": "订单回滚验收",
                        "knowledge": "库存不足时订单和库存都保持不变。",
                    },
                ],
            }
            payload_path = write_payload(root, payload, "crash-learning.json")
            script = r'''
import importlib.util, json, os, sys
from pathlib import Path
tool_path, root_value, payload_value = sys.argv[1:]
spec = importlib.util.spec_from_file_location("crash_knowledge", tool_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
root = Path(root_value).resolve()
config = module.load_config(root)
payload = json.loads(Path(payload_value).read_text(encoding="utf-8"))
original = module.atomic_write_text
calls = 0
def crash_on_third_product_write(path, content):
    global calls
    if ".transactions" not in Path(path).parts:
        calls += 1
        if calls == 3:
            os._exit(99)
    return original(path, content)
module.atomic_write_text = crash_on_third_product_write
module.learn(root, config, payload)
'''
            crashed = subprocess.run(
                [sys.executable, "-c", script, str(ASSET_TOOL), str(root), str(payload_path)],
                check=False,
            )
            self.assertEqual(crashed.returncode, 99)
            self.assertTrue((root / ".codestable" / "wiki" / ".write.lock").is_file())

            recovered = self.tool.learn(root, config, payload)
            self.assertFalse(recovered["idempotent"])
            self.assertFalse((root / ".codestable" / "wiki" / ".write.lock").exists())
            self.assertFalse((root / ".codestable" / "wiki" / ".transactions").exists())
            self.assertTrue(self.tool.doctor(root, config)["ok"])
            third = self.tool.learn(root, config, payload)
            self.assertTrue(third["idempotent"])

    def test_failed_rollback_journal_is_recovered_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            first = self.tool.learn(
                root,
                config,
                {
                    "task": base_task("旧架构知识"),
                    "items": [
                        {
                            "category": "architecture",
                            "title": "订单边界",
                            "knowledge": "订单模块直接修改库存。",
                        }
                    ],
                },
            )
            old_id = first["created_cards"][0]["id"]
            payload = {
                "task": base_task("恢复架构知识"),
                "items": [
                    {
                        "category": "architecture",
                        "title": "订单边界",
                        "knowledge": "订单模块通过库存服务预留库存。",
                        "supersedes": [old_id],
                    },
                    {
                        "category": "acceptance",
                        "title": "边界验收",
                        "knowledge": "订单模块不直接写库存表。",
                    },
                ],
            }
            original = self.tool.atomic_write_text
            product_calls = 0

            def fail_product_writes(path, content):
                nonlocal product_calls
                if ".transactions" not in Path(path).parts:
                    product_calls += 1
                    if product_calls >= 2:
                        raise OSError("persistent product I/O failure")
                return original(path, content)

            self.tool.atomic_write_text = fail_product_writes
            try:
                with self.assertRaises(self.tool.KnowledgeError):
                    self.tool.learn(root, config, payload)
            finally:
                self.tool.atomic_write_text = original

            pending = root / ".codestable" / "wiki" / ".transactions"
            self.assertTrue(pending.is_dir())
            self.assertFalse(self.tool.doctor(root, config)["ok"])

            recovered = self.tool.learn(root, config, payload)
            self.assertFalse(recovered["idempotent"])
            self.assertFalse(pending.exists())
            self.assertTrue(self.tool.doctor(root, config)["ok"])
            third = self.tool.learn(root, config, payload)
            self.assertTrue(third["idempotent"])

    def test_plan_token_applies_exact_dry_run_identifiers_across_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = self.all_category_payload()
            dry_run = self.tool.learn(root, config, payload, dry_run=True)
            time.sleep(1.05)
            applied = self.tool.learn(root, config, payload, plan_token=dry_run["plan_token"])
            self.assertEqual(applied["task_id"], dry_run["task_id"])
            self.assertEqual(
                [item["id"] for item in applied["created_cards"]],
                [item["id"] for item in dry_run["created_cards"]],
            )
            self.assertEqual(
                [item["path"] for item in applied["created_cards"]],
                [item["path"] for item in dry_run["created_cards"]],
            )
            before_retry = tree_digest(root / ".codestable")
            repeated = self.tool.learn(root, config, payload, plan_token=dry_run["plan_token"])
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(before_retry, tree_digest(root / ".codestable"))
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_symlink_project_root_supports_all_public_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            real = base / "real"
            alias = base / "alias"
            real.mkdir()
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")
            self.bootstrap.install(real, upgrade=False)
            config = self.tool.load_config(alias)
            before = tree_digest(real / ".codestable")
            self.brief(alias, config, "订单事务", ["src/orders/service.py"])
            self.tool.status_payload(alias, config)
            self.tool.doctor(alias, config)
            self.tool.rebuild_indexes(alias, config, dry_run=True)
            plan = self.tool.learn(alias, config, self.all_category_payload(), dry_run=True)
            self.assertTrue(plan["index"]["changed"])
            self.assertEqual(before, tree_digest(real / ".codestable"))
            applied = self.tool.learn(alias, config, self.all_category_payload())
            self.assertEqual(len(applied["created_cards"]), 11)
            self.assertTrue(self.tool.doctor(alias, config)["ok"])

    def test_idempotent_dry_run_reports_stale_index_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = self.all_category_payload()
            self.tool.learn(root, config, payload)
            index = root / ".codestable" / "wiki" / "INDEX.md"
            index.write_text("stale\n", encoding="utf-8")
            before = tree_digest(root / ".codestable")
            plan = self.tool.learn(root, config, payload, dry_run=True)
            self.assertTrue(plan["idempotent"])
            self.assertIn(".codestable/wiki/INDEX.md", plan["index"]["changed"])
            self.assertEqual(before, tree_digest(root / ".codestable"))
            applied = self.tool.learn(root, config, payload)
            self.assertTrue(applied["idempotent"])
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_legacy_model_and_knowledge_are_read_only_search_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            decision = root / ".codestable" / "model" / "decisions" / "001-orders.md"
            decision.parent.mkdir(parents=True)
            decision.write_text("# Order transaction ADR\n\n订单和库存同库时使用本地事务。\n", encoding="utf-8")
            note = root / ".codestable" / "knowledge" / "notes" / "inventory.md"
            note.parent.mkdir(parents=True)
            note.write_text("# Inventory pitfall\n\n库存不足不能在事务提交后才报告。\n", encoding="utf-8")
            before = tree_digest(root / ".codestable")
            brief = self.brief(root, config, "订单库存本地事务")
            after = tree_digest(root / ".codestable")
            self.assertEqual(before, after)
            sources = {item["source"] for item in brief["knowledge"]}
            self.assertIn(".codestable/model/decisions/001-orders.md", sources)
            self.assertIn(".codestable/knowledge/notes/inventory.md", sources)

    def test_manual_project_overview_is_always_included(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            project = root / ".codestable" / "wiki" / "PROJECT.md"
            project.write_text(
                "# Project\n\n<!-- codestable:canonical:start -->\n订单域是项目的核心边界。\n<!-- codestable:canonical:end -->\n",
                encoding="utf-8",
            )
            brief = self.brief(root, config, "修改通知文案")
            self.assertEqual(brief["project_overview"][0]["excerpt"], "订单域是项目的核心边界。")

    def test_task_note_is_written_even_without_durable_cards(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = {"task": base_task("仅更新一次性测试数据"), "items": []}
            result = self.tool.learn(root, config, payload)
            self.assertEqual(result["created_cards"], [])
            self.assertTrue((root / result["task_note"]).is_file())
            status = self.tool.status_payload(root, config)
            self.assertEqual(status["cards"], 0)
            self.assertEqual(status["task_notes"], 1)
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_secret_like_payload_is_rejected_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = {
                "task": base_task("错误的秘密记录"),
                "items": [
                    {
                        "category": "security-boundaries",
                        "title": "不要记录秘密",
                        "knowledge": "真实密钥是 sk-abcdefghijklmnopqrstuvwxyz123456",
                    }
                ],
            }
            before = tree_digest(root / ".codestable")
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, payload)
            self.assertEqual(before, tree_digest(root / ".codestable"))

    def test_doctor_detects_stale_index_and_reindex_repairs_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = {"task": base_task(), "items": [{"category": "architecture", "title": "订单边界", "knowledge": "订单服务拥有创建编排。"}]}
            result = self.tool.learn(root, config, payload)
            card = root / result["created_cards"][0]["path"]
            card.write_text(card.read_text(encoding="utf-8") + "\n人工补充。\n", encoding="utf-8")
            doctor = self.tool.doctor(root, config)
            self.assertFalse(doctor["ok"])
            self.assertTrue(any(error["code"] == "index.stale" for error in doctor["errors"]))
            before = tree_digest(root / ".codestable")
            dry = self.tool.rebuild_indexes(root, config, dry_run=True)
            self.assertTrue(dry["changed"])
            self.assertEqual(before, tree_digest(root / ".codestable"))
            self.tool.rebuild_indexes(root, config)
            self.assertTrue(self.tool.doctor(root, config)["ok"])


if __name__ == "__main__":
    unittest.main()
