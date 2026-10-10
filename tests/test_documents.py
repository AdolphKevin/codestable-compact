from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from support import base_task, bootstrap_module, knowledge_module, run_tool, tree_digest


class DocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = knowledge_module()
        cls.bootstrap = bootstrap_module()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'app'
        self.root.mkdir()
        self.bootstrap.install(self.root)
        self.doc = self.root / 'GLOSSARY.md'
        self.doc.write_text('# Terms\n\n## Order\nAn order belongs to exactly one tenant.\n')
        self.config = self.tool.load_config(self.root)
        self.config['wiki']['documents'] = {'terms': {'path': 'GLOSSARY.md', 'category': 'requirements',
            'title': 'Order terms', 'always': True, 'applies_to': [{'repository': 'self', 'path': 'src'}]}}
        self.save_config()

    def save_config(self):
        (self.root / '.codestable/config.json').write_text(json.dumps(self.config))

    def payload(self):
        task = base_task('Reference authoritative terms')
        task.update(paths=['GLOSSARY.md'], symbols=[], request='Register authoritative terminology',
                    knowledge_summary='Reference the original document without copying its body.')
        return {'task': task, 'items': [{'category': 'requirements', 'title': 'Order definition reference',
                'reference': {'document': 'terms', 'section': 'Order', 'sha256': self.tool.sha256_file(self.doc)}}]}

    def apply(self, payload):
        preview = self.tool.learn(self.root, self.config, payload, dry_run=True)
        self.assertTrue(preview['apply_allowed'], preview)
        return self.tool.learn(self.root, self.config, payload, plan_token=preview['plan_token'])

    def brief(self):
        return self.tool.selected_brief_payload(self.root, self.config, 'change order ownership', ['src/new.py'], [], None, False)

    def test_read_commands_and_dry_run_do_not_write(self):
        before = tree_digest(self.root)
        brief = self.brief()
        self.assertIn('exactly one tenant', brief['authoritative_documents'][0]['excerpt'])
        for args in [('documents', 'list'), ('documents', 'read', '--id', 'terms'), ('doctor',), ('reindex', '--dry-run')]:
            self.assertEqual(run_tool(self.root, *args).returncode, 0)
        self.tool.learn(self.root, self.config, self.payload(), dry_run=True)
        self.assertEqual(before, tree_digest(self.root))

    def test_live_source_update_changes_receipt_and_is_not_cached(self):
        old = self.brief()['receipt']['document_state']
        self.doc.write_text('# Terms\n## Order\nOrders can have several owners.\n')
        new = self.brief()
        self.assertNotEqual(old, new['receipt']['document_state'])
        self.assertIn('several owners', new['authoritative_documents'][0]['excerpt'])

    def test_reference_has_no_duplicate_body_and_preserves_old_history(self):
        self.config['capture']['strict_durable_cards'] = False
        payload = self.payload()
        legacy = copy.deepcopy(payload)
        legacy['items'] = [{'category': 'requirements', 'title': 'Old ownership fact',
                            'knowledge': 'Every order has one owning tenant.', 'paths': ['GLOSSARY.md']}]
        old = self.apply(legacy)['created_cards'][0]
        payload['task']['title'] = 'Consolidate original terminology'
        payload['task']['new_task_reason'] = 'Replace duplicate current knowledge with the registered source reference.'
        payload['items'][0].update(supersedes=[old['id']], supersession_reason='Original document owns this definition.')
        result = self.apply(payload)
        card = self.root / result['created_cards'][0]['path']
        self.assertNotIn('exactly one tenant', card.read_text())
        meta, body, _ = self.tool.read_markdown(self.root / old['path'])
        self.assertEqual(meta['status'], 'superseded')
        self.assertIn('Every order', body)
        brief = self.brief()
        self.assertEqual(brief['knowledge'], [])
        self.assertEqual(brief['authoritative_documents'][0]['references'][0]['id'], result['created_cards'][0]['id'])

    def test_source_change_requires_explicit_reference_review(self):
        self.apply(self.payload())
        self.doc.write_text('# Terms\n## Order\nNew accepted definition.\n')
        self.assertIn('document-changed', [r['issue_type'] for r in self.brief()['document_review_queue']])
        self.assertFalse(self.tool.doctor(self.root, self.config, check_current_references=True)['ok'])

    def test_cross_repository_source_binds_preview(self):
        external = Path(self.tmp.name) / 'contracts'
        external.mkdir()
        doc = external / 'GLOSSARY.md'
        doc.write_text(self.doc.read_text())
        self.config['wiki']['repositories'] = {'contracts': {'root': '../contracts'}}
        self.config['wiki']['documents']['terms']['repository'] = 'contracts'
        preview = self.tool.learn(self.root, self.config, self.payload(), dry_run=True)
        doc.write_text('# changed external source')
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'source missing or changed|documents changed'):
            self.tool.learn(self.root, self.config, self.payload(), plan_token=preview['plan_token'])

    def test_missing_and_symlink_escape_are_explicit(self):
        self.doc.unlink()
        self.assertEqual(self.brief()['authoritative_documents'][0]['read_status'], 'file-missing')
        outside = Path(self.tmp.name) / 'secret.md'
        outside.write_text('must not be returned')
        self.doc.symlink_to(outside)
        result = self.brief()
        self.assertNotIn('must not be returned', json.dumps(result))
        self.assertEqual(result['authoritative_documents'][0]['read_status'], 'reference-outside-repository')

    def test_copied_body_and_duplicate_reference_are_rejected(self):
        payload = self.payload()
        payload['items'][0]['knowledge'] = 'copied body'
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'must not copy'):
            self.tool.learn(self.root, self.config, payload, dry_run=True)
        result = self.apply(self.payload())
        self.assertTrue(self.tool.learn(self.root, self.config, self.payload(), dry_run=True)['idempotent'])
        duplicate = self.payload()
        duplicate['items'][0]['title'] = 'Another navigation entry to the same source'
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'duplicate document reference'):
            self.tool.learn(self.root, self.config, duplicate, dry_run=True)

    def test_ambiguous_section_and_invalid_registration_rejected(self):
        self.doc.write_text('# Order\nOne\n# Order\nTwo\n')
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'source missing or changed'):
            self.tool.learn(self.root, self.config, self.payload(), dry_run=True)
        self.config['wiki']['documents']['terms']['path'] = '../outside.md'
        with self.assertRaises(self.tool.KnowledgeError):
            self.brief()

    def test_proposed_document_cannot_create_current_reference(self):
        self.config['wiki']['documents']['terms']['status'] = 'proposed'
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'status must match'):
            self.tool.learn(self.root, self.config, self.payload(), dry_run=True)


    def test_heading_only_match_still_returns_source_content(self):
        brief = self.tool.selected_brief_payload(self.root, self.config, 'Terms glossary', [], [], None, False)
        self.assertIn('exactly one tenant', brief['authoritative_documents'][0]['excerpt'])

    def test_plain_card_cannot_copy_registered_conclusion(self):
        self.config['capture']['strict_durable_cards'] = False
        payload = self.payload()
        payload['items'] = [{'title': 'Copied ownership', 'category': 'requirements',
                             'knowledge': 'An order belongs to exactly one tenant.'}]
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'already exists in a registered source'):
            self.tool.learn(self.root, self.config, payload, dry_run=True)

    def test_external_document_binds_task_only_preview(self):
        external = Path(self.tmp.name) / 'contracts'
        external.mkdir()
        doc = external / 'GLOSSARY.md'
        doc.write_text(self.doc.read_text())
        self.config['wiki']['repositories'] = {'contracts': {'root': '../contracts'}}
        self.config['wiki']['documents']['terms']['repository'] = 'contracts'
        payload = self.payload()
        payload['items'] = []
        preview = self.tool.learn(self.root, self.config, payload, dry_run=True)
        doc.write_text('# external change')
        with self.assertRaisesRegex(self.tool.KnowledgeError, 'documents changed'):
            self.tool.learn(self.root, self.config, payload, plan_token=preview['plan_token'])

    def test_reference_rereview_keeps_id_and_prior_source_hash(self):
        payload = self.payload()
        result = self.apply(payload)
        card = result['created_cards'][0]
        old_hash = payload['items'][0]['reference']['sha256']
        self.doc.write_text(self.doc.read_text() + '\nClarified ownership.\n')
        payload['task'].update(id=result['task_id'], update_existing=True, expected_revision=1)
        payload['items'][0].update(operation='update', card_id=card['id'], expected_revision=1)
        payload['items'][0]['reference']['sha256'] = self.tool.sha256_file(self.doc)
        updated = self.apply(payload)
        self.assertEqual(updated['updated_cards'][0]['id'], card['id'])
        meta, _, _ = self.tool.read_markdown(self.root / card['path'])
        self.assertEqual(meta['reference_history'][0]['sha256'], old_hash)
        self.assertEqual(self.brief()['document_review_queue'], [])
        self.assertEqual(self.tool.knowledge_review(self.root, self.config)['cards'][card['id']]['status'], 'current')

    def test_cross_repo_explicit_scope_retrieves_its_source(self):
        external = Path(self.tmp.name) / 'contracts'
        external.mkdir()
        (external / 'GLOSSARY.md').write_text(self.doc.read_text())
        self.config['wiki']['repositories'] = {'contracts': {'root': '../contracts'}}
        self.config['wiki']['documents']['terms'].update(repository='contracts', always=False, applies_to=[])
        result = self.tool.selected_brief_payload(self.root, self.config, 'update', [], [], None, False,
                  scopes=[{'repository': 'contracts', 'path': 'GLOSSARY.md', 'symbol': ''}])
        self.assertEqual(result['authoritative_documents'][0]['source'], 'contracts:GLOSSARY.md')

    def test_composed_methods_share_task_original_and_independent_experience(self):
        """A modeling handoff followed by implementation/review uses existing CS records."""
        source = self.root / 'src/orders.py'
        source.parent.mkdir()
        source.write_text('def tenant(value):\n    if not value:\n        raise ValueError("tenant required")\n    return value\n')
        namespace = {}
        exec(compile(source.read_text(), str(source), 'exec'), namespace)
        with self.assertRaises(ValueError):
            namespace['tenant']('')

        modeling = self.payload()
        modeling['task'].update(status='in-progress', summary='Clarified the owning tenant in the glossary.',
                                result='The terminology is available for implementation; validation remains.')
        modeling['items'] = []
        first = self.apply(modeling)

        implementation = self.payload()
        implementation['task'].update(id=first['task_id'], update_existing=True, expected_revision=1,
            paths=['GLOSSARY.md', 'src/orders.py'],
            summary='Implemented and reviewed rejection of an empty tenant.',
            result='Empty tenant input raises ValueError; the registered glossary retains the definition.',
            verification=['Executed tenant("") and observed ValueError.'],
            knowledge_summary='Reference the existing definition and capture only the independent rejection behavior.')
        implementation['items'].append({
            'category': 'error-handling', 'title': 'Empty tenant input is rejected',
            'knowledge': 'The tenant input boundary raises ValueError for an empty tenant identifier.',
            'paths': ['src/orders.py'], 'confidence': 'verified',
            'evidence': [{'kind': 'test', 'artifact': 'src/orders.py',
                          'result': 'Calling tenant with an empty string raised ValueError.',
                          'supports': 'The input boundary rejects an empty identifier.'}],
            'future_use': [
                {'change': 'Add an order import entry', 'actor': 'Import maintainer',
                 'constraint': 'Reject empty tenant identifiers at the new boundary.'},
                {'change': 'Change the tenant identifier parser', 'actor': 'Identity maintainer',
                 'constraint': 'Preserve the observed rejection behavior.'}],
        })
        completed = self.apply(implementation)
        preview = self.tool.learn(self.root, self.config, implementation, dry_run=True)
        repeated = self.tool.learn(self.root, self.config, implementation, plan_token=preview['plan_token'])
        self.assertEqual(completed['task_id'], first['task_id'])
        self.assertEqual(completed['task_revision'], 2)
        self.assertTrue(repeated['idempotent'])
        self.assertEqual(len(list((self.root / '.codestable/wiki/task-notes').rglob('*.md'))), 1)
        self.assertEqual(len(completed['created_cards']), 2)
        for card in completed['created_cards']:
            self.assertNotIn('An order belongs to exactly one tenant.', (self.root / card['path']).read_text())
        before = tree_digest(self.root)
        brief = self.tool.selected_brief_payload(self.root, self.config, 'change tenant input',
                                                ['src/orders.py'], [], None, False)
        self.assertEqual(len(brief['knowledge']), 1)
        self.assertIn('Empty tenant input is rejected', json.dumps(brief))
        self.assertIn(first['task_id'], json.dumps(brief))
        self.assertIn('exactly one tenant', brief['authoritative_documents'][0]['excerpt'])
        self.assertEqual(before, tree_digest(self.root))
        self.assertFalse((self.root / '.team-workflow.json').exists())
        self.assertFalse((self.root / '.team-workflow').exists())


if __name__ == '__main__':
    unittest.main()
