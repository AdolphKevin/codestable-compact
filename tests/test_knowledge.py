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

    def git(self, root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *arguments], cwd=root, text=True, capture_output=True, check=check)

    def commit_baseline(self, root: Path) -> None:
        self.git(root, "init", "-q")
        self.git(root, "config", "user.email", "codestable-tests@example.invalid")
        self.git(root, "config", "user.name", "CodeStable Tests")
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "baseline")

    def scoped_card_payload(
        self,
        title: str,
        path: str,
        symbol: str = "",
        supersedes: tuple[str, ...] = (),
    ) -> dict:
        task = base_task(title)
        task["paths"] = [path]
        task["symbols"] = [symbol] if symbol else []
        task["knowledge_summary"] = "新增或取代一张经验证的 current 卡。"
        return {
            "task": task,
            "items": [
                {
                    "category": "architecture",
                    "title": f"{title}边界",
                    "knowledge": f"{title}由 {path} 实现。",
                    "paths": [path],
                    "symbols": [symbol] if symbol else [],
                    "confidence": "verified",
                    "evidence": ["fixture verification passes"],
                    "supersedes": list(supersedes),
                }
            ],
        }

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
            self.tool.drift_payload(root, config, references_only=True)
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
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, payload, plan_token=dry_run["plan_token"])
            self.assertEqual(before_retry, tree_digest(root / ".codestable"))
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_plan_token_is_rejected_after_workspace_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")
            payload = self.all_category_payload()
            dry_run = self.tool.learn(root, config, payload, dry_run=True)
            source.write_text("value = 2\n", encoding="utf-8")

            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, payload, plan_token=dry_run["plan_token"])

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

    def test_legacy_model_and_knowledge_are_read_only_fallback_clues(self) -> None:
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
            self.assertEqual(brief["knowledge"], [])
            sources = {item["source"] for item in brief["legacy_clues"]}
            self.assertIn(".codestable/model/decisions/001-orders.md", sources)
            self.assertIn(".codestable/knowledge/notes/inventory.md", sources)
            self.assertEqual(brief["coverage"]["decisions"], {"available": 0, "matched": 0})
            self.assertIn("transaction-boundaries", brief["gaps"])
            markdown = self.tool.render_brief_markdown(brief)
            self.assertIn("## Legacy 线索（需核验）", markdown)
            self.assertIn("不计入知识覆盖", markdown)

    def test_current_knowledge_suppresses_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            legacy = root / ".codestable" / "knowledge" / "orders.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("# 订单事务旧结论\n\n订单先提交，再异步预留库存。\n", encoding="utf-8")
            payload = {
                "task": base_task("确认当前订单事务"),
                "items": [
                    {
                        "category": "transaction-boundaries",
                        "title": "订单库存当前事务",
                        "knowledge": "订单写入与库存预留在同一本地事务内提交。",
                        "confidence": "verified",
                        "evidence": ["rollback test passes"],
                    }
                ],
            }
            self.tool.learn(root, config, payload)

            brief = self.brief(root, config, "订单库存事务")

            self.assertIn("订单库存当前事务", {item["title"] for item in brief["knowledge"]})
            self.assertEqual(brief["legacy_clues"], [])
            self.assertEqual(brief["coverage"]["transaction-boundaries"], {"available": 1, "matched": 1})

    def test_non_current_cards_do_not_suppress_legacy_or_fill_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            legacy = root / ".codestable" / "model" / "architecture.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("# 订单架构旧线索\n\n订单架构通过库存服务协调。\n", encoding="utf-8")
            payload = {
                "task": base_task("记录订单架构候选"),
                "items": [
                    {
                        "category": "architecture",
                        "title": "订单架构提议",
                        "knowledge": "订单模块以后可能拆分为独立服务。",
                        "status": "proposed",
                    },
                    {
                        "category": "architecture",
                        "title": "订单架构弃用方案",
                        "knowledge": "订单模块曾经直接修改库存。",
                        "status": "deprecated",
                    },
                ],
            }
            self.tool.learn(root, config, payload)

            brief = self.brief(root, config, "评估订单架构")

            self.assertTrue(brief["legacy_clues"])
            self.assertEqual(brief["coverage"]["architecture"], {"available": 0, "matched": 0})
            self.assertIn("architecture", brief["gaps"])

    def test_implicit_acceptance_hint_does_not_select_unrelated_card(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            payload = {
                "task": base_task("记录库存验收"),
                "items": [
                    {
                        "category": "acceptance",
                        "title": "库存不足回滚验收",
                        "knowledge": "库存不足时订单数和库存数均保持不变。",
                        "confidence": "verified",
                        "evidence": ["rollback test passes"],
                    }
                ],
            }
            self.tool.learn(root, config, payload)

            brief = self.brief(root, config, "修改通知文案")

            self.assertEqual(brief["knowledge"], [])
            self.assertEqual(brief["coverage"]["acceptance"], {"available": 1, "matched": 0})
            self.assertIn("acceptance", brief["gaps"])

    def test_recent_decisions_require_relevance_or_pinning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            task = base_task("记录架构决策")
            task["paths"] = []
            task["symbols"] = []
            task["tags"] = []
            payload = {
                "task": task,
                "items": [
                    {
                        "category": "decisions",
                        "title": "订单模块采用本地事务",
                        "knowledge": "订单和库存同库时采用本地事务。",
                        "rationale": "这是当前最小的一致性边界。",
                        "paths": ["src/orders/service.py"],
                    },
                    {
                        "category": "decisions",
                        "title": "报表模块采用列式存储",
                        "knowledge": "离线报表使用列式存储。",
                        "rationale": "分析查询以扫描为主。",
                        "paths": ["src/reports/storage.py"],
                    },
                    {
                        "category": "decisions",
                        "title": "全局变更保留审计记录",
                        "knowledge": "所有领域的兼容性变更都保留审计记录。",
                        "rationale": "该约束适用于整个项目。",
                        "pinned": True,
                    },
                ],
            }
            self.tool.learn(root, config, payload)

            first = self.brief(root, config, "修改订单事务", ["src/orders/service.py"])
            second = self.brief(root, config, "修改订单事务", ["src/orders/service.py"])
            titles = {item["title"] for item in first["knowledge"]}

            self.assertIn("订单模块采用本地事务", titles)
            self.assertIn("全局变更保留审计记录", titles)
            self.assertNotIn("报表模块采用列式存储", titles)
            self.assertEqual(first["knowledge"][0]["title"], "订单模块采用本地事务")
            self.assertEqual(
                [item["source"] for item in first["knowledge"]],
                [item["source"] for item in second["knowledge"]],
            )

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

    def test_ten_sql_debug_iterations_update_one_task_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            task = base_task("匿名登录 SQL Schema 迁移")
            task.update(
                {
                    "status": "in-progress",
                    "deliverable": "migrations/anonymous_login.sql",
                    "summary": "开始执行迁移并收集数据库兼容错误。",
                    "result": "迁移尚未通过最终验收。",
                    "verification": [],
                }
            )
            current = self.tool.learn(root, config, {"task": task, "items": []})
            task_id = current["task_id"]

            errors = [
                "Visitor Cuser 清理依赖未覆盖",
                "bigint/text 类型不匹配",
                "分区表引用遗漏",
                "物化视图索引超限",
                "规范化邮箱重复",
                "Cuser 合并",
                "Conversation 孤儿引用",
                "删除顺序仍需调整",
                "回滚脚本兼容性失败",
                "全量迁移验收",
            ]
            for index, error in enumerate(errors, start=1):
                completed = index == len(errors)
                update = base_task("匿名登录 SQL Schema 迁移")
                update.update(
                    {
                        "id": task_id,
                        "update_existing": True,
                        "expected_revision": current["task_revision"],
                        "status": "completed" if completed else "in-progress",
                        "deliverable": "migrations/anonymous_login.sql",
                        "summary": f"聚合处理迁移调试链；最新处理：{error}。",
                        "result": "迁移 SQL 已通过最终验收。" if completed else "迁移仍在连续调试中。",
                        "verification": ["migration integration test passes"] if completed else [],
                    }
                )
                items = []
                if completed:
                    items = [
                        {
                            "category": "data-model",
                            "title": "匿名登录历史邮箱按规范化值合并",
                            "knowledge": "匿名登录迁移按 lower(trim(email)) 合并历史正式邮箱记录。",
                            "confidence": "verified",
                            "evidence": ["migration integration test passes"],
                        }
                    ]
                current = self.tool.learn(root, config, {"task": update, "items": items})

            status = self.tool.status_payload(root, config)
            self.assertEqual(status["task_notes"], 1)
            self.assertEqual(status["cards"], 1)
            self.assertEqual(current["task_id"], task_id)
            self.assertEqual(current["task_revision"], 11)
            note = (root / current["task_note"]).read_text(encoding="utf-8")
            self.assertIn("全量迁移验收", note)
            self.assertNotIn("Visitor Cuser 清理依赖未覆盖", note)
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_intermediate_replaced_solution_cannot_create_durable_card(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            task = base_task("迁移索引兼容调试")
            task.update({"status": "partial", "verification": [], "result": "候选方案尚未验收。"})
            temporary_item = {
                "category": "performance-risks",
                "title": "临时前缀索引方案",
                "knowledge": "暂时截断正文后建立索引。",
            }
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, {"task": task, "items": [temporary_item]})
            self.assertEqual(self.tool.status_payload(root, config)["task_notes"], 0)

            partial = self.tool.learn(root, config, {"task": task, "items": []})
            final_task = base_task("迁移索引兼容调试")
            final_task.update(
                {
                    "id": partial["task_id"],
                    "update_existing": True,
                    "expected_revision": partial["task_revision"],
                    "summary": "用项目查询所需的表达式索引替代临时截断方案。",
                    "result": "最终索引方案通过迁移测试。",
                    "verification": ["migration index test passes"],
                }
            )
            durable = {
                "category": "performance-risks",
                "title": "长正文表达式索引受 B-tree 行大小限制",
                "knowledge": "项目对任意长正文建立 LOWER(text) B-tree 前必须约束索引表达式或查询设计。",
                "confidence": "verified",
                "evidence": ["migration index test passes"],
            }
            completed = self.tool.learn(root, config, {"task": final_task, "items": [durable]})
            self.assertEqual(self.tool.status_payload(root, config)["task_notes"], 1)
            self.assertEqual(len(completed["created_cards"]), 1)
            self.assertNotIn("临时前缀索引方案", (root / ".codestable" / "wiki" / "index.jsonl").read_text(encoding="utf-8"))

    def test_explicit_second_goal_creates_second_task_note(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            migration = base_task("匿名登录 Schema 迁移")
            migration["deliverable"] = "migrations/anonymous_login.sql"
            first = self.tool.learn(root, config, {"task": migration, "items": []})

            cleanup = base_task("建立迁移后数据巡检作业")
            cleanup.update(
                {
                    "request": "独立新增迁移后每日数据巡检",
                    "summary": "新增独立巡检作业。",
                    "result": "巡检作业可独立运行。",
                    "deliverable": "jobs/anonymous_login_audit.py",
                    "paths": ["jobs/anonymous_login_audit.py"],
                }
            )
            second = self.tool.learn(root, config, {"task": cleanup, "items": []})

            self.assertNotEqual(first["task_id"], second["task_id"])
            self.assertEqual(self.tool.status_payload(root, config)["task_notes"], 2)

    def test_task_update_is_idempotent_and_revision_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            task = base_task("持续迁移任务")
            task.update({"status": "in-progress", "verification": [], "result": "尚未完成。"})
            first = self.tool.learn(root, config, {"task": task, "items": []})
            update = dict(task)
            update.update(
                {
                    "id": first["task_id"],
                    "update_existing": True,
                    "expected_revision": first["task_revision"],
                    "summary": "完成第二轮聚合修复。",
                }
            )
            applied = self.tool.learn(root, config, {"task": update, "items": []})
            repeated = self.tool.learn(root, config, {"task": update, "items": []})
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(repeated["task_revision"], applied["task_revision"])

            stale = dict(update)
            stale["summary"] = "基于旧 revision 的不同内容。"
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, {"task": stale, "items": []})

    def test_dry_run_suggests_updating_similar_task_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            task = base_task("匿名登录 SQL Schema 迁移")
            task.update({"deliverable": "migrations/anonymous_login.sql", "status": "partial", "verification": []})
            existing = self.tool.learn(root, config, {"task": task, "items": []})
            before = tree_digest(root / ".codestable")

            continuation = base_task("匿名登录 SQL Schema 迁移")
            continuation.update(
                {
                    "deliverable": "migrations/anonymous_login.sql",
                    "summary": "继续修复分区引用。",
                    "result": "仍在调试。",
                    "status": "in-progress",
                    "verification": [],
                }
            )
            plan = self.tool.learn(root, config, {"task": continuation, "items": []}, dry_run=True)

            self.assertEqual(before, tree_digest(root / ".codestable"))
            self.assertEqual(plan["task_candidates"][0]["task_id"], existing["task_id"])
            self.assertIn("same-title", plan["task_candidates"][0]["reasons"])
            self.assertIn("same-deliverable", plan["task_candidates"][0]["reasons"])
            self.assertEqual(plan["recommendation"], "update-existing-task")

    def test_likely_continuation_requires_update_or_explicit_new_goal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            first_task = base_task("连续租户授权调试")
            first_task.update(
                {
                    "status": "in-progress",
                    "result": "跨租户注入测试仍在调试。",
                    "verification": [],
                    "deliverable": "src/core/authorization.py",
                }
            )
            first = self.tool.learn(root, config, {"task": first_task, "items": []})
            continuation = dict(first_task)
            continuation["summary"] = "继续修复资源范围校验。"
            plan = self.tool.learn(root, config, {"task": continuation, "items": []}, dry_run=True)
            self.assertFalse(plan["apply_allowed"])
            self.assertTrue(plan["requires_new_task_reason"])
            self.assertIsNone(plan["plan_token"])
            self.assertEqual(plan["task_candidates"][0]["task_id"], first["task_id"])
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, {"task": continuation, "items": []})

            continuation["new_task_reason"] = "独立交付授权审计报表，不修改原授权实现。"
            allowed = self.tool.learn(root, config, {"task": continuation, "items": []}, dry_run=True)
            self.assertTrue(allowed["apply_allowed"])
            self.assertIsNotNone(allowed["plan_token"])

    def test_consolidate_archives_duplicate_tasks_without_losing_audit_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            canonical_task = base_task("收敛 Core Service 授权边界")
            canonical_task["deliverable"] = "src/core/authorization.py"
            canonical = self.tool.learn(root, config, {"task": canonical_task, "items": []})

            duplicate_ids = []
            linked_card = ""
            for index, title in enumerate(("排查跨租户资源注入", "验收租户资源校验"), start=1):
                task = base_task(title)
                task.update(
                    {
                        "deliverable": "src/core/authorization.py",
                        "new_task_reason": f"历史 runtime 曾把连续调试第 {index} 轮误记为独立任务。",
                        "source": {"fixture": f"sanitized-step-{index}"},
                        "verification": [f"sanitized authorization test {index} passes"],
                    }
                )
                items = []
                if index == 1:
                    items = [
                        {
                            "category": "security-boundaries",
                            "title": "Core Service 校验权威租户资源关系",
                            "knowledge": "Core Service 根据认证信息和权威关系校验租户与资源，不能无条件信任调用方业务范围。",
                            "rationale": "可信 service identity 不等于可信 business scope。",
                            "confidence": "verified",
                            "evidence": ["sanitized cross-tenant injection test passes"],
                        }
                    ]
                result = self.tool.learn(root, config, {"task": task, "items": items})
                duplicate_ids.append(result["task_id"])
                if items:
                    linked_card = result["created_cards"][0]["id"]

            payload = {
                "canonical_task_id": canonical["task_id"],
                "expected_revision": canonical["task_revision"],
                "duplicates": [{"id": identifier, "expected_revision": 1} for identifier in duplicate_ids],
                "reason": "三条记录属于同一用户目标、同一交付物和同一连续调试验收链。",
            }
            before = tree_digest(root / ".codestable")
            plan = self.tool.consolidate(root, config, payload, dry_run=True)
            self.assertEqual(before, tree_digest(root / ".codestable"))
            applied = self.tool.consolidate(root, config, payload, plan_token=plan["plan_token"])
            repeated = self.tool.consolidate(root, config, payload)
            self.assertFalse(applied["idempotent"])
            self.assertTrue(repeated["idempotent"])

            status = self.tool.status_payload(root, config)
            self.assertEqual(status["task_notes"], 3)
            self.assertEqual(status["active_task_notes"], 1)
            self.assertEqual(status["archived_task_notes"], 2)
            self.assertEqual([entry["id"] for entry in status["recent_tasks"]], [canonical["task_id"]])
            root_index = (root / ".codestable" / "wiki" / "INDEX.md").read_text(encoding="utf-8")
            self.assertIn("已折叠历史记录：2", root_index)
            self.assertNotIn("排查跨租户资源注入", root_index)

            _, tasks = self.tool.scan_existing_records(
                self.tool.wiki_root(root, config), self.tool.configured_categories(config)
            )
            canonical_metadata = tasks[canonical["task_id"]][1]
            self.assertIn(linked_card, canonical_metadata["card_ids"])
            self.assertEqual(set(canonical_metadata["consolidated_from"]), set(duplicate_ids))
            for identifier in duplicate_ids:
                metadata = tasks[identifier][1]
                body = tasks[identifier][2]
                self.assertEqual(metadata["visibility"], "archived")
                self.assertEqual(metadata["consolidated_into"], canonical["task_id"])
                self.assertIn("sanitized", body)
                self.assertIn("原正文 SHA-256", body)
            brief = self.brief(root, config, "Core Service 租户资源授权", ["src/core/authorization.py"])
            self.assertTrue(set(duplicate_ids).isdisjoint({item["id"] for item in brief["related_tasks"]}))
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_partial_upgrade_uses_one_task_note_and_retains_pending_page(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            legacy_paths = [
                ".codestable/model/decisions/trusted-edge.md",
                ".codestable/knowledge/core-scope.md",
                ".codestable/knowledge/debug-log.md",
                ".codestable/knowledge/uncertain-contract.md",
            ]
            for index, relative in enumerate(legacy_paths):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# Sanitized legacy page {index}\n", encoding="utf-8")

            def audit_page(relative, outcome, evidence):
                path = root / relative
                return {
                    "path": relative,
                    "sha256": self.tool.sha256_file(path),
                    "backup_path": f".codestable/backups/sanitized/{relative}",
                    "outcome": outcome,
                    "disposition": f"sanitized {outcome} audit",
                    "evidence": evidence,
                }

            first_pages = [
                audit_page(legacy_paths[0], "obsolete", ["current authorization integration test"]),
                audit_page(legacy_paths[1], "covered", ["current security-boundary card review"]),
            ]
            task = base_task("升级历史知识并审计租户授权边界")
            task.update(
                {
                    "kind": "knowledge-migration",
                    "status": "partial",
                    "result": "已完成部分逐页审计，升级仍未完成。",
                    "verification": [],
                    "deliverable": ".codestable/wiki",
                    "source": {"knowledge_migration": {"complete": False, "pages": first_pages}},
                }
            )
            first = self.tool.learn(root, config, {"task": task, "items": []})

            all_pages = [
                *first_pages,
                audit_page(legacy_paths[2], "migrated", ["current implementation and sanitized regression test"]),
                audit_page(legacy_paths[3], "pending", []),
            ]
            task.update(
                {
                    "id": first["task_id"],
                    "update_existing": True,
                    "expected_revision": first["task_revision"],
                    "summary": "逐页审计四页；覆盖、过时和迁移结论已处理，一页证据不足。",
                    "source": {"knowledge_migration": {"complete": False, "pages": all_pages}},
                }
            )
            item = {
                "category": "security-boundaries",
                "title": "Core Service 派生权威业务范围",
                "knowledge": "Core Service 使用认证信息和数据库权威关系校验租户与资源范围。",
                "rationale": "service identity 可信不能证明调用方业务 scope 可信。",
                "confidence": "verified",
                "evidence": ["current implementation and sanitized cross-tenant regression test"],
            }
            second = self.tool.learn(root, config, {"task": task, "items": [item]})
            self.assertEqual(first["task_id"], second["task_id"])
            self.assertEqual(self.tool.status_payload(root, config)["active_task_notes"], 1)
            self.assertEqual(self.tool.status_payload(root, config)["cards"], 1)
            self.assertTrue((root / legacy_paths[3]).is_file())
            self.assertIn('"complete": false', (root / second["task_note"]).read_text(encoding="utf-8").lower())
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_consolidate_rolls_back_write_failure_and_rejects_stale_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            canonical_task = base_task("授权链路主任务")
            canonical = self.tool.learn(root, config, {"task": canonical_task, "items": []})
            duplicate_task = base_task("授权链路补丁记录")
            duplicate = self.tool.learn(root, config, {"task": duplicate_task, "items": []})
            payload = {
                "canonical_task_id": canonical["task_id"],
                "expected_revision": 1,
                "duplicates": [{"id": duplicate["task_id"], "expected_revision": 1}],
                "reason": "脱敏 fixture 中两条记录属于同一连续验收链。",
            }
            plan = self.tool.consolidate(root, config, payload, dry_run=True)

            update = dict(canonical_task)
            update.update(
                {
                    "id": canonical["task_id"],
                    "update_existing": True,
                    "expected_revision": 1,
                    "summary": "并发更新 canonical task。",
                }
            )
            self.tool.learn(root, config, {"task": update, "items": []})
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.consolidate(root, config, payload, plan_token=plan["plan_token"])

            payload["expected_revision"] = 2
            retry_plan = self.tool.consolidate(root, config, payload, dry_run=True)
            before = tree_digest(root / ".codestable")
            original = self.tool.atomic_write_text
            product_writes = 0

            def fail_second_product_write(path, content):
                nonlocal product_writes
                if ".transactions" not in Path(path).parts:
                    product_writes += 1
                    if product_writes == 2:
                        raise OSError("injected consolidate failure")
                return original(path, content)

            self.tool.atomic_write_text = fail_second_product_write
            try:
                with self.assertRaises(OSError):
                    self.tool.consolidate(root, config, payload, plan_token=retry_plan["plan_token"])
            finally:
                self.tool.atomic_write_text = original
            self.assertEqual(before, tree_digest(root / ".codestable"))
            applied = self.tool.consolidate(root, config, payload, plan_token=retry_plan["plan_token"])
            self.assertFalse(applied["idempotent"])
            self.assertTrue(self.tool.doctor(root, config)["ok"])

    def test_knowledge_use_requires_a_concrete_effect_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            old = self.tool.learn(
                root,
                config,
                {
                    "task": base_task("记录早期内部服务信任边界"),
                    "items": [
                        {
                            "category": "decisions",
                            "title": "Edge Service 提供业务范围",
                            "knowledge": "Core Service 直接采用已认证内部调用方提供的租户与资源范围。",
                            "rationale": "早期设计把内部 service identity 与业务 scope 置于同一信任边界。",
                            "confidence": "accepted",
                        }
                    ],
                },
            )
            old_card_id = old["created_cards"][0]["id"]
            decision = self.tool.learn(
                root,
                config,
                {
                    "task": base_task("确立 Core Service 授权决策"),
                    "items": [
                        {
                            "category": "decisions",
                            "title": "Core Service 校验业务范围",
                            "knowledge": "Core Service 不无条件信任内部调用方提供的租户与资源范围。",
                            "rationale": "身份认证与业务授权是不同信任边界。",
                            "confidence": "verified",
                            "evidence": ["sanitized cross-tenant integration test"],
                            "supersedes": [old_card_id],
                        }
                    ],
                },
            )
            card_id = decision["created_cards"][0]["id"]
            visible = {item["id"] for item in self.brief(root, config, "租户资源业务范围")["knowledge"]}
            self.assertIn(card_id, visible)
            self.assertNotIn(old_card_id, visible)
            task = base_task("扩展案例附件授权")
            task["knowledge_use"] = [
                {
                    "card_id": card_id,
                    "use": "tested",
                    "detail": "据此拒绝原本准备复用调用方 resource scope 的方案，并由 Core Service 查询权威关系。",
                    "evidence": ["sanitized attachment cross-tenant test passes"],
                }
            ]
            learned = self.tool.learn(root, config, {"task": task, "items": []})
            note = (root / learned["task_note"]).read_text(encoding="utf-8")
            self.assertIn("历史知识使用证据", note)
            self.assertIn("拒绝原本准备复用", note)

            invalid = base_task("机械引用无关卡片")
            invalid["knowledge_use"] = [{"card_id": card_id, "use": "tested", "detail": "读取了卡片。"}]
            with self.assertRaises(self.tool.KnowledgeError):
                self.tool.learn(root, config, {"task": invalid, "items": []})

    def test_legacy_task_without_revision_updates_from_revision_one_and_keeps_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            first = self.tool.learn(root, config, {"task": base_task("旧任务记录"), "items": []})
            note_path = root / first["task_note"]
            metadata, body, _ = self.tool.read_markdown(note_path)
            metadata.pop("revision")
            note_path.write_text(self.tool.render_front_matter(metadata, body), encoding="utf-8")
            self.tool.rebuild_indexes(root, config)

            update = base_task("旧任务记录")
            update.update(
                {
                    "id": first["task_id"],
                    "update_existing": True,
                    "expected_revision": 1,
                    "summary": "在升级后的工具中继续原任务。",
                    "source": {"commit": "abc123"},
                }
            )
            result = self.tool.learn(root, config, {"task": update, "items": []})
            updated_metadata, _, _ = self.tool.read_markdown(root / result["task_note"])
            self.assertEqual(result["task_revision"], 2)
            self.assertEqual(updated_metadata["source"]["issue"], "ORDER-17")
            self.assertEqual(updated_metadata["source"]["commit"], "abc123")

    def test_drift_reports_current_card_path_deleted_from_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("class OrderService:\n    pass\n", encoding="utf-8")
            learned = self.tool.learn(root, config, self.scoped_card_payload("订单服务", "src/orders.py", "OrderService"))
            self.commit_baseline(root)
            source.unlink()

            drift = self.tool.drift_payload(root, config)

            finding = next(item for item in drift["findings"] if item["issue_type"] == "current-path-deleted")
            self.assertEqual(finding["card_id"], learned["created_cards"][0]["id"])
            self.assertEqual(finding["category"], "architecture")
            self.assertEqual(finding["value"], "src/orders.py")
            self.assertFalse(drift["ok"])

    def test_superseded_card_missing_path_does_not_fail_current_reference_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            old_source = root / "src" / "old_orders.py"
            new_source = root / "src" / "orders.py"
            old_source.parent.mkdir(parents=True)
            old_source.write_text("class OldOrderService:\n    pass\n", encoding="utf-8")
            new_source.write_text("class OrderService:\n    pass\n", encoding="utf-8")
            old = self.tool.learn(root, config, self.scoped_card_payload("旧订单服务", "src/old_orders.py", "OldOrderService"))
            self.tool.learn(
                root,
                config,
                self.scoped_card_payload(
                    "新订单服务",
                    "src/orders.py",
                    "OrderService",
                    (old["created_cards"][0]["id"],),
                ),
            )
            old_source.unlink()

            references = self.tool.current_reference_drift(root, config)

            self.assertEqual(references["findings"], [])
            self.assertEqual(references["checked_current_cards"], 1)

    def test_drift_reports_understandable_file_rename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            old_source = root / "src" / "orders.py"
            new_source = root / "src" / "order_service.py"
            old_source.parent.mkdir(parents=True)
            old_source.write_text("class OrderService:\n    pass\n", encoding="utf-8")
            self.tool.learn(root, config, self.scoped_card_payload("订单服务", "src/orders.py", "OrderService"))
            self.commit_baseline(root)
            old_source.rename(new_source)

            drift = self.tool.drift_payload(root, config)

            finding = next(item for item in drift["findings"] if item["issue_type"] == "path-renamed")
            self.assertEqual(finding["value"], "src/orders.py")
            self.assertEqual(finding["renamed_to"], "src/order_service.py")
            self.assertIn("renamed", finding["suggested_action"])

    def test_external_legacy_and_generated_reference_policies_are_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            task = base_task("显式路径策略")
            task["paths"] = []
            payload = {
                "task": task,
                "items": [
                    {
                        "category": "architecture",
                        "title": "外部依赖边界",
                        "knowledge": "外部依赖由独立仓库维护。",
                        "paths": [
                            "external:https://example.invalid/service",
                            ".codestable/model/domain.md",
                            "generated:.codestable/wiki/INDEX.md",
                        ],
                    }
                ],
            }
            self.tool.learn(root, config, payload)

            references = self.tool.current_reference_drift(root, config)

            self.assertEqual(references["findings"], [])
            path_policies = {item["policy"] for item in references["skipped"] if item["issue_type"] == "path-policy-skipped"}
            self.assertEqual(path_policies, {"external", "legacy", "generated"})

    def test_missing_current_symbol_is_reported_as_a_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("class DifferentService:\n    pass\n", encoding="utf-8")
            learned = self.tool.learn(root, config, self.scoped_card_payload("订单服务", "src/orders.py", "OrderService"))

            references = self.tool.current_reference_drift(root, config)

            finding = next(item for item in references["findings"] if item["issue_type"] == "missing-symbol")
            self.assertEqual(finding["card_id"], learned["created_cards"][0]["id"])
            self.assertEqual(finding["value"], "OrderService")

    def test_overlapping_current_cards_prompt_reuse_or_supersession(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("class OrderService:\n    pass\n", encoding="utf-8")
            first = self.scoped_card_payload("订单服务", "src/orders.py", "OrderService")
            self.tool.learn(root, config, first)
            second = self.scoped_card_payload("订单服务", "src/orders.py", "OrderService")
            second["task"]["title"] = "重复记录订单服务"
            second["items"][0]["knowledge"] = "订单服务的新描述仍由 src/orders.py 实现。"
            self.tool.learn(root, config, second)

            references = self.tool.current_reference_drift(root, config)

            finding = next(item for item in references["findings"] if item["issue_type"] == "overlapping-current-cards")
            self.assertEqual(finding["category"], "architecture")
            self.assertIn("reuse", finding["suggested_action"])

    def test_staged_semantic_change_without_task_note_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("def create_order():\n    return 1\n", encoding="utf-8")
            self.commit_baseline(root)
            source.write_text("def create_order():\n    return 2\n", encoding="utf-8")
            self.git(root, "add", "src/orders.py")

            drift = self.tool.drift_payload(root, config, cached=True)

            self.assertIn("missing-task-note", {item["issue_type"] for item in drift["findings"]})
            self.assertEqual(drift["exit_code"], 1)

    def test_staged_drift_rejects_unstaged_wiki_writeback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")
            self.commit_baseline(root)
            source.write_text("value = 2\n", encoding="utf-8")
            self.git(root, "add", "src/orders.py")
            task = base_task("未暂存知识回写")
            task["paths"] = ["src/orders.py"]
            task["knowledge_summary"] = "只写 task-note；没有长期知识。"
            self.tool.learn(root, config, {"task": task, "items": []})

            drift = self.tool.drift_payload(root, config, cached=True)

            self.assertIn("unstaged-wiki-changes", {item["issue_type"] for item in drift["findings"]})

    def test_docs_formatting_and_generated_index_changes_do_not_require_task_note(self) -> None:
        for case in ("docs", "formatting", "generated"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root, config = self.new_root(temporary)
                source = root / "src" / "orders.py"
                source.parent.mkdir(parents=True)
                source.write_text("value = 1\n", encoding="utf-8")
                readme = root / "README.md"
                readme.write_text("# Project\n", encoding="utf-8")
                self.commit_baseline(root)
                if case == "docs":
                    readme.write_text("# Project\n\nMore prose.\n", encoding="utf-8")
                    self.git(root, "add", "README.md")
                elif case == "formatting":
                    source.write_text("value    =    1\n", encoding="utf-8")
                    self.git(root, "add", "src/orders.py")
                else:
                    index = root / ".codestable" / "wiki" / "index.jsonl"
                    index.write_text(index.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                    self.git(root, "add", ".codestable/wiki/index.jsonl")

                drift = self.tool.drift_payload(root, config, cached=True)

                self.assertFalse(drift["summary"]["semantic_change"])
                self.assertNotIn("missing-task-note", {item["issue_type"] for item in drift["findings"]})

    def test_deleted_current_implementation_requires_supersession_but_superseded_version_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            old_source = root / "src" / "legacy_orders.py"
            old_source.parent.mkdir(parents=True)
            old_source.write_text("class LegacyOrderService:\n    pass\n", encoding="utf-8")
            old = self.tool.learn(root, config, self.scoped_card_payload("旧订单实现", "src/legacy_orders.py", "LegacyOrderService"))
            self.commit_baseline(root)
            old_source.unlink()
            before = self.tool.drift_payload(root, config)
            self.assertIn("current-path-deleted", {item["issue_type"] for item in before["findings"]})

            new_source = root / "src" / "orders.py"
            new_source.write_text("class OrderService:\n    pass\n", encoding="utf-8")
            replacement = self.scoped_card_payload(
                "订单替换实现",
                "src/orders.py",
                "OrderService",
                (old["created_cards"][0]["id"],),
            )
            replacement["task"]["paths"] = ["src/legacy_orders.py", "src/orders.py"]
            replacement["task"]["knowledge_summary"] = "新建替换实现卡，并 supersede 旧实现卡。"
            self.tool.learn(root, config, replacement)
            self.git(root, "add", "-A")

            after = self.tool.drift_payload(root, config, cached=True)

            self.assertNotIn("current-path-deleted", {item["issue_type"] for item in after["findings"]})
            self.assertNotIn("missing-task-note", {item["issue_type"] for item in after["findings"]})
            self.assertNotIn("task-scope-mismatch", {item["issue_type"] for item in after["findings"]})

    def test_task_note_scope_mismatch_and_incomplete_outcome_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")
            self.commit_baseline(root)
            source.write_text("value = 2\n", encoding="utf-8")
            task = base_task("错误范围任务")
            task.update(
                {
                    "paths": ["src/other.py"],
                    "symbols": [],
                    "result": "计划稍后完成。",
                    "verification": [],
                    "knowledge_summary": "",
                }
            )
            self.tool.learn(root, config, {"task": task, "items": []})
            self.git(root, "add", "-A")

            drift = self.tool.drift_payload(root, config, cached=True)
            issue_types = {item["issue_type"] for item in drift["findings"]}

            self.assertIn("task-scope-mismatch", issue_types)
            self.assertIn("task-final-result-missing", issue_types)
            self.assertIn("task-verification-missing", issue_types)
            self.assertIn("task-knowledge-disposition-missing", issue_types)

    def test_doctor_declares_structure_only_boundary_and_can_check_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, config = self.new_root(temporary)
            doctor = self.tool.doctor(root, config)
            checked = self.tool.doctor(root, config, check_current_references=True)

            self.assertTrue(doctor["ok"])
            self.assertEqual(doctor["scope"], "structure-only")
            self.assertFalse(doctor["current_knowledge_validated"])
            self.assertIn("drift", doctor["next_check"])
            self.assertEqual(checked["scope"], "structure+current-references")
            self.assertIn("current_references", checked)

    def test_drift_cli_json_and_exit_codes_are_stable_for_ci(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, _ = self.new_root(temporary)
            source = root / "src" / "orders.py"
            source.parent.mkdir(parents=True)
            source.write_text("value = 1\n", encoding="utf-8")
            self.commit_baseline(root)
            source.write_text("value = 2\n", encoding="utf-8")
            self.git(root, "add", "src/orders.py")

            failed = subprocess.run(
                [sys.executable, str(root / ".codestable" / "tools" / "cs_knowledge.py"), "--root", str(root), "drift", "--cached", "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(failed.stdout)
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(payload["exit_code"], 1)
            self.assertFalse(payload["ok"])

            self.git(root, "reset", "-q", "HEAD", "--", "src/orders.py")
            source.write_text("value = 1\n", encoding="utf-8")
            passed = subprocess.run(
                [sys.executable, str(root / ".codestable" / "tools" / "cs_knowledge.py"), "--root", str(root), "drift", "--cached", "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0)
            self.assertEqual(json.loads(passed.stdout)["exit_code"], 0)
            base = subprocess.run(
                [sys.executable, str(root / ".codestable" / "tools" / "cs_knowledge.py"), "--root", str(root), "drift", "--base", "HEAD", "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(base.returncode, 0)
            self.assertEqual(json.loads(base.stdout)["mode"], "base:HEAD")

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
