from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ASSET_ROOT, BOOTSTRAP_PATH, PACKAGE_ROOT, SHARED_TOOL, bootstrap_module, knowledge_module, tree_digest


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = bootstrap_module()
        cls.knowledge = knowledge_module()

    def rebuild(self, root):
        plan = self.bootstrap.install(root, rebuild=True, dry_run=True)
        return self.bootstrap.install(root, rebuild=True, plan_token=plan['plan_token'])

    def test_distribution_contains_only_the_cs_skill(self):
        self.assertEqual(sorted(p.name for p in (PACKAGE_ROOT/'skills').iterdir() if p.is_dir()), ['cs'])

    def test_asset_manifest_is_complete(self):
        files, config = self.bootstrap.source_assets()
        self.assertEqual(config['schema_version'], 4)
        self.assertEqual(config['wiki']['index_storage'], 'local')
        self.assertEqual(len(config['wiki']['categories']), 11)
        self.assertIn('.codestable/config.json', files)
        self.assertNotIn('legacy_read_roots', config['wiki'])
        self.assertNotIn('.codestable/wiki/index.jsonl', files)

    def test_fresh_install_and_preflight_are_current_and_shared(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self.bootstrap.install(root)
            self.assertEqual(Path(result['runtime_path']), SHARED_TOOL)
            self.assertEqual(result['runtime_source'], 'skill')
            self.assertTrue(result['runtime_contract']['ok'])
            self.assertTrue({'audit', 'learn', 'topics list', 'topics suggest'} <= set(result['runtime_contract']['documented_commands']))
            self.assertFalse(result['knowledge_build']['complete'])
            self.assertTrue(result['knowledge_build']['required'])
            self.assertFalse((root/'.codestable/tools').exists())
            before = tree_digest(root)
            check = self.bootstrap.check_install(root)
            self.assertTrue(check['ok'], check)
            self.assertEqual(check['status'], 'current')
            self.assertEqual(before, tree_digest(root))

    def test_fresh_preview_never_creates_a_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'absent'
            plan = self.bootstrap.install(root, dry_run=True)
            self.assertFalse(root.exists())
            self.assertTrue(plan['created'])
            self.assertEqual(plan['removed'], [])
            self.assertEqual(self.bootstrap.check_install(root)['status'], 'not-installed')
            self.assertFalse(root.exists())

    def test_plain_install_refuses_existing_data_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cs = root/'.codestable'; cs.mkdir()
            (cs/'note.txt').write_text('old authored data')
            before = tree_digest(root)
            with self.assertRaisesRegex(ValueError, 'explicitly authorized --rebuild'):
                self.bootstrap.install(root)
            self.assertEqual(tree_digest(root), before)
            self.assertEqual(self.bootstrap.check_install(root)['status'], 'needs-rebuild')

    def test_old_schemas_are_rejected_without_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root)
            path = root/'.codestable/config.json'
            config = json.loads(path.read_text())
            for schema in (1, 2, 3):
                with self.subTest(schema=schema):
                    config['schema_version'] = schema
                    path.write_text(json.dumps(config))
                    before = tree_digest(root)
                    check = self.bootstrap.check_install(root)
                    self.assertEqual(check['status'], 'needs-rebuild')
                    self.assertEqual(check['doctor']['status'], 'not-run')
                    with self.assertRaisesRegex(self.knowledge.KnowledgeError, '--rebuild'):
                        self.knowledge.load_config(root)
                    self.assertEqual(before, tree_digest(root))

    def test_rebuild_discards_old_content_and_config_only_inside_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cs = root/'.codestable'
            for folder in ('wiki', 'model', 'knowledge', 'work', 'observations', 'evals', 'evolution', 'reference', 'backups', 'unknown'):
                path = cs/folder/'old.txt'; path.parent.mkdir(parents=True)
                path.write_text('outdated synthetic content')
            (cs/'config.json').write_text('{damaged old config')
            (root/'service.py').write_text('def run(): return 1\n')
            (root/'AGENTS.md').write_text('Project rules\n')
            before = tree_digest(root)
            plan = self.bootstrap.install(root, rebuild=True, dry_run=True)
            self.assertEqual(before, tree_digest(root))
            self.assertIn('.codestable/unknown/old.txt', plan['removed'])
            result = self.bootstrap.install(root, rebuild=True, plan_token=plan['plan_token'])
            self.assertEqual((root/'service.py').read_text(), 'def run(): return 1\n')
            self.assertEqual((root/'AGENTS.md').read_text(), 'Project rules\n')
            self.assertFalse(list(cs.rglob('old.txt')))
            self.assertFalse((cs/'backups').exists())
            self.assertEqual(json.loads((cs/'config.json').read_text()), json.loads((ASSET_ROOT/'.codestable/config.json').read_text()))
            self.assertFalse(result['knowledge_build']['complete'])
            self.assertTrue(self.bootstrap.check_install(root)['ok'])
            self.assertFalse(list(root.glob('.codestable-new-*')))

    def test_rebuild_requires_an_exact_current_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.bootstrap.install(root)
            before = tree_digest(root)
            with self.assertRaisesRegex(ValueError, 'plan token'):
                self.bootstrap.install(root, rebuild=True)
            self.assertEqual(before, tree_digest(root))
            plan = self.bootstrap.install(root, rebuild=True, dry_run=True)
            note = root/'.codestable/wiki/PROJECT.md'; note.write_text('new user edit')
            changed = tree_digest(root)
            with self.assertRaisesRegex(ValueError, 'plan token'):
                self.bootstrap.install(root, rebuild=True, plan_token=plan['plan_token'])
            self.assertEqual(changed, tree_digest(root))

    def test_rebuild_plan_is_bound_to_project_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            left, right = Path(temporary)/'left', Path(temporary)/'right'
            self.bootstrap.install(left); self.bootstrap.install(right)
            plan = self.bootstrap.install(left, rebuild=True, dry_run=True)
            before = tree_digest(right)
            with self.assertRaisesRegex(ValueError, 'plan token'):
                self.bootstrap.install(right, rebuild=True, plan_token=plan['plan_token'])
            self.assertEqual(before, tree_digest(right))

    def test_symlinked_knowledge_root_is_rejected_and_nested_link_is_only_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            outside = parent/'outside'; outside.mkdir(); (outside/'keep.txt').write_text('keep')
            root = parent/'project'; root.mkdir(); (root/'.codestable').symlink_to(outside, target_is_directory=True)
            before = tree_digest(outside)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.bootstrap.install(root, rebuild=True, dry_run=True)
            self.assertEqual(before, tree_digest(outside))
            (root/'.codestable').unlink()
            self.bootstrap.install(root)
            (root/'.codestable/external').symlink_to(outside, target_is_directory=True)
            self.rebuild(root)
            self.assertEqual(before, tree_digest(outside))
            self.assertFalse((root/'.codestable/external').exists())

    def test_preparation_failure_keeps_old_data_and_cleans_temporary_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); self.bootstrap.install(root)
            plan = self.bootstrap.install(root, rebuild=True, dry_run=True)
            before = tree_digest(root)
            with mock.patch.object(self.bootstrap, 'copy_file', side_effect=OSError('synthetic copy failure')):
                with self.assertRaisesRegex(OSError, 'synthetic'):
                    self.bootstrap.install(root, rebuild=True, plan_token=plan['plan_token'])
            self.assertEqual(before, tree_digest(root))
            self.assertFalse(list(root.glob('.codestable-new-*')))

    def test_invalid_new_layout_is_rejected_before_old_data_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); self.bootstrap.install(root)
            plan=self.bootstrap.install(root, rebuild=True, dry_run=True)
            before=tree_digest(root)
            with mock.patch.object(self.bootstrap, 'run_doctor', return_value={'ok': False}):
                with self.assertRaisesRegex(RuntimeError, 'failed validation'):
                    self.bootstrap.install(root, rebuild=True, plan_token=plan['plan_token'])
            self.assertEqual(before, tree_digest(root))

    def test_rebuild_does_not_race_an_active_knowledge_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); self.bootstrap.install(root)
            (root/'.codestable/wiki/.write.lock').write_text('synthetic active writer')
            before=tree_digest(root)
            with self.assertRaisesRegex(RuntimeError, 'writer is active'):
                self.bootstrap.install(root, rebuild=True, dry_run=True)
            self.assertEqual(before, tree_digest(root))

    def test_retired_upgrade_command_cannot_delete_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); self.bootstrap.install(root)
            before=tree_digest(root)
            result=subprocess.run([sys.executable,str(BOOTSTRAP_PATH),'--root',str(root),'--upgrade'],text=True,capture_output=True)
            self.assertEqual(result.returncode,2)
            self.assertEqual(before,tree_digest(root))

    def test_skill_command_contract_rejects_a_documented_missing_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'SKILL.md'
            path.write_text('| `$cs missing-command` | unavailable |\n')
            result=self.bootstrap.verify_runtime_command_contract(SHARED_TOOL,path)
            self.assertFalse(result['ok'])
            self.assertEqual(result['unavailable_commands'][0]['command'],'missing-command')
