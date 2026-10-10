"""Behavior of independent registrations, scoped reads, and lost-response retries."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from support import SHARED_TOOL, base_task, bootstrap_module, knowledge_module, run_tool, tree_digest


class ParallelKnowledge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tool = knowledge_module()
        bootstrap_module().install(self.root)
        self.config = self.tool.load_config(self.root)
        self.register('orders', 'src/orders')

    def register(self, identifier, scope):
        source = self.root / (identifier + '.md')
        source.write_text('# ' + identifier + '\n\nEach value has one owner.\n')
        directory = self.root / '.codestable/documents'
        directory.mkdir(exist_ok=True)
        (directory / (identifier + '.json')).write_text(json.dumps({
            'path': source.name, 'applies_to': [{'repository': 'self', 'path': scope}]}))
        return source

    def brief(self):
        return self.tool.selected_brief_payload(self.root, self.config, 'change owner', ['src/orders'], [], None, False)

    def test_unrelated_task_and_registration_preserve_receipt(self):
        before = self.brief()['receipt']
        task = base_task('Update invoices')
        task.update(paths=['src/invoices'], request='Separate invoice task')
        self.tool.learn(self.root, self.config, {'task': task, 'items': []})
        self.register('invoices', 'src/invoices')
        state = tree_digest(self.root)
        result = self.tool.check_brief_receipt(self.root, self.config, before)
        self.assertTrue(result['ok'], result)
        self.assertEqual(state, tree_digest(self.root))
        self.register('payments', 'src/orders')
        self.assertFalse(self.tool.check_brief_receipt(self.root, self.config, before)['ok'])

    def test_changed_and_missing_original_invalidates_receipt(self):
        before = self.brief()['receipt']
        (self.root / 'orders.md').write_text('# Changed order ownership\n')
        self.assertFalse(self.tool.check_brief_receipt(self.root, self.config, before)['ok'])
        (self.root / 'orders.md').unlink()
        self.assertFalse(self.tool.check_brief_receipt(self.root, self.config, before)['ok'])

    def test_successful_token_retry_has_no_write_after_other_task(self):
        value = {'task': base_task('Owner fix'), 'items': []}
        preview = self.tool.learn(self.root, self.config, value, dry_run=True)
        applied = self.tool.learn(self.root, self.config, value, plan_token=preview['plan_token'])
        other = copy.deepcopy(value)
        other['task'].update(title='Invoice printer', request='Independent invoice printer', paths=['src/invoices'], symbols=[], new_task_reason='Different user goal and implementation.')
        self.tool.learn(self.root, self.config, other)
        state = tree_digest(self.root)
        with patch.object(self.tool, "acquire_lock", side_effect=AssertionError("retry must not write")):
            retry = self.tool.learn(self.root, self.config, value, plan_token=preview['plan_token'])
        self.assertTrue(retry['idempotent'])
        self.assertEqual(retry['task_id'], applied['task_id'])
        self.assertEqual(state, tree_digest(self.root))

    def test_local_paths_never_enter_shared_configuration(self):
        external = self.root / 'outside'
        external.mkdir()
        (external / 'source.md').write_text('# Local source\n')
        (self.root / '.codestable/local.json').write_text(json.dumps({'repositories': {'contracts': str(external)}}))
        (self.root / '.codestable/documents/external.json').write_text(json.dumps({'repository': 'contracts', 'path': 'source.md'}))
        before = (self.root / '.codestable/config.json').read_bytes()
        result = json.loads(run_tool(self.root, 'documents', 'read', '--id', 'external').stdout)
        self.assertTrue(result['ok'])
        self.assertEqual(before, (self.root / '.codestable/config.json').read_bytes())
        missing = self.root / 'missing'
        p = run_tool(self.root, '--repository', 'contracts=' + str(missing), 'documents', 'read', '--id', 'external', check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_registry_reads_staged_and_committed_sources(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)
        git('init', '-q')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.invalid')
        git('config', 'commit.gpgsign', 'false')
        git('add', '.')
        git('commit', '-qm', 'baseline')
        (self.root / '.codestable/documents/orders.json').write_text('{"path":"missing.md"}')
        for revision in (':', 'HEAD'):
            with self.tool.git_read_view(self.root, revision):
                config = self.tool.load_config(self.root)
                self.assertTrue(self.tool.read_registered_document(self.root, config, 'orders')['ok'])
        git('add', '.codestable/documents/orders.json')
        with self.tool.git_read_view(self.root, ':'):
            self.assertFalse(self.tool.read_registered_document(self.root, self.tool.load_config(self.root), 'orders')['ok'])

    def test_two_processes_cannot_overwrite_the_same_task_revision(self):
        value = {'task': base_task('One logical task'), 'items': []}
        applied = self.tool.learn(self.root, self.config, value)
        commands = []
        for label in ('left', 'right'):
            update = copy.deepcopy(value)
            update['task'].update(id=applied['task_id'], update_existing=True,
                                  expected_revision=1, result=label + ' verified outcome')
            plan = self.tool.learn(self.root, self.config, update, dry_run=True)
            source = self.root / '.codestable/cache' / (label + '.json')
            source.parent.mkdir(exist_ok=True)
            source.write_text(json.dumps(update))
            commands.append([sys.executable, str(SHARED_TOOL), '--root', str(self.root), 'learn',
                             '--file', str(source), '--plan-token', plan['plan_token']])
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for command in commands]
        results = [process.communicate(timeout=15) for process in processes]
        self.assertEqual(sum(process.returncode == 0 for process in processes), 1, results)
        failed = next(json.loads(output[0]) for process, output in zip(processes, results) if process.returncode)
        self.assertRegex(failed['error'], 'changed|lock|revision')
        current = json.loads(run_tool(self.root, 'task-files', '--task-id', applied['task_id'], '--format', 'json').stdout)
        self.assertEqual(current['task_revision'], 2)
        self.assertEqual(len(list((self.root / '.codestable/wiki/task-notes').rglob('*.md'))), 1)

    def test_new_applicable_experience_invalidates_receipt(self):
        source = self.root / 'src/orders/check.py'
        source.parent.mkdir(parents=True)
        source.write_text('def valid(value):\n    return value > 0\n')
        before = self.brief()['receipt']
        value = {'task': base_task('Check order zero boundary'), 'items': [{
            'category': 'interfaces', 'title': 'Order positive boundary',
            'knowledge': 'The order validator rejects zero.', 'confidence': 'verified',
            'paths': ['src/orders/check.py'], 'symbols': ['valid'],
            'evidence': [{'kind': 'implementation', 'artifact': 'src/orders/check.py#valid',
                          'result': 'Returns value > 0', 'supports': 'Zero is rejected'}],
            'future_use': [{'change': 'Batch orders', 'actor': 'Maintainer', 'constraint': 'Reject zero'},
                           {'change': 'Replace validation', 'actor': 'Maintainer', 'constraint': 'Keep positive boundary'}]}]}
        self.tool.learn(self.root, self.config, value)
        result = self.tool.check_brief_receipt(self.root, self.config, before)
        self.assertFalse(result['ok'])
        self.assertTrue(any('interfaces/' in key for key in result['changed']))

    def test_invalid_receipt_is_a_read_only_error(self):
        before = tree_digest(self.root)
        with self.assertRaises(self.tool.KnowledgeError):
            self.tool.check_brief_receipt(self.root, self.config, {"kind": "brief-display", "query_state": {}})
        self.assertEqual(before, tree_digest(self.root))

    def test_registry_directory_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as outside:
            directory = self.root / '.codestable/documents'
            (directory / 'orders.json').unlink()
            directory.rmdir()
            directory.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(self.tool.KnowledgeError, 'inside'):
                self.brief()

    def test_retry_does_not_acknowledge_uncommitted_transaction(self):
        value = {'task': base_task('Owner fix'), 'items': []}
        # Preserve a recovery journal after all product writes, then simulate a
        # process stopping before its commit marker became durable.
        with patch.object(self.tool, 'remove_recovery_journal'):
            applied = self.tool.learn(self.root, self.config, value)
        transaction = next((self.root / '.codestable/wiki/.transactions').iterdir())
        (transaction / 'COMMITTED').unlink()
        acquire = self.tool.acquire_lock
        with patch.object(self.tool, 'acquire_lock', wraps=acquire) as locked:
            result = self.tool.learn(self.root, self.config, value)
        self.assertEqual(locked.call_count, 1)
        self.assertFalse(result['idempotent'])
        self.assertFalse((self.root / '.codestable/wiki/.transactions').exists())
        self.assertEqual(len(list((self.root / '.codestable/wiki/task-notes').rglob('*.md'))), 1)

    def test_legacy_config_rejection_has_no_writes(self):
        path = self.root / '.codestable/config.json'
        data = json.loads(path.read_text())
        data['schema_version'] = 4
        path.write_text(json.dumps(data))
        before = tree_digest(self.root)
        result = bootstrap_module().check_install(self.root)
        self.assertEqual(result['status'], 'needs-configuration')
        self.assertEqual(result['suggested_command'], [])
        self.assertEqual(before, tree_digest(self.root))
