import json
import tempfile
from io import StringIO
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase

from search.evaluation.datasets import (
    DatasetAlreadyLoadedError,
    DatasetDocument,
    DatasetQuery,
    build_custom,
    build_jagovfaqs,
    load_dataset,
)
from search.management.commands.import_custom_dataset import DATASET_PATH
from search.models import Document, EvaluationQuery


class BuildJaGovFaqsTests(SimpleTestCase):
    def test_answers_become_documents_and_questions_become_queries(self):
        documents, queries = build_jagovfaqs([{'Question': '質問A', 'Answer': '回答A'}])
        self.assertEqual(documents, [DatasetDocument(source_id='0', title='', body='回答A')])
        self.assertEqual(queries, [DatasetQuery(text='質問A', relevant=('0',))])

    def test_merges_duplicate_answers_and_questions(self):
        rows = [
            {'Question': '質問A', 'Answer': '回答X'},
            {'Question': '質問B', 'Answer': '回答X'},  # 同じ回答は 1 つの文書にまとめる
            {'Question': '質問A', 'Answer': '回答Y'},  # 同じ質問は正解を複数持つ
            {'Question': '質問A', 'Answer': '回答X'},  # 完全な重複は無視する
        ]
        documents, queries = build_jagovfaqs(rows)
        self.assertEqual([d.source_id for d in documents], ['0', '2'])
        self.assertEqual(
            queries, [DatasetQuery(text='質問A', relevant=('0', '2')), DatasetQuery(text='質問B', relevant=('0',))]
        )

    def test_skips_empty_rows(self):
        rows = [{'Question': ' ', 'Answer': '回答'}, {'Question': '質問', 'Answer': None}]
        documents, queries = build_jagovfaqs(rows)
        self.assertEqual((documents, queries), ([], []))


class CustomDatasetFileTests(SimpleTestCase):
    def test_relevant_documents_exist(self):
        documents, queries = build_custom(json.loads(DATASET_PATH.read_text()))
        ids = {document.source_id for document in documents}
        self.assertEqual(len(ids), len(documents))
        for query in queries:
            with self.subTest(query=query.text):
                self.assertTrue(query.relevant)
                self.assertLessEqual(set(query.relevant), ids)


class LoadDatasetTests(TestCase):
    documents = [DatasetDocument('a', '東京都庁', '展望室の案内'), DatasetDocument('b', '', '附属病院')]
    queries = [DatasetQuery('都庁', ('a',), 'メモ'), DatasetQuery('病院', ('a', 'b'))]

    def test_creates_documents_with_tokens_and_queries(self):
        self.assertEqual(load_dataset('test', self.documents, self.queries), (2, 2))
        document = Document.objects.get(source='test', source_id='b')
        self.assertEqual(document.body_tokens, '付属 病院')
        query = EvaluationQuery.objects.get(dataset='test', text='病院')
        relevant = query.relevant_documents.order_by('source_id').values_list('source_id', flat=True)
        self.assertQuerySetEqual(relevant, ['a', 'b'])

    def test_refuses_to_load_twice_without_replace(self):
        load_dataset('test', self.documents, self.queries)
        with self.assertRaises(DatasetAlreadyLoadedError):
            load_dataset('test', self.documents, self.queries)

    def test_replace(self):
        load_dataset('test', self.documents, self.queries)
        load_dataset('test', self.documents[:1], self.queries[:1], replace=True)
        self.assertEqual(Document.objects.filter(source='test').count(), 1)
        self.assertEqual(EvaluationQuery.objects.filter(dataset='test').count(), 1)

    def test_does_not_touch_other_datasets(self):
        load_dataset('other', self.documents, self.queries)
        load_dataset('test', self.documents, self.queries)
        load_dataset('test', self.documents, self.queries, replace=True)
        self.assertEqual(Document.objects.filter(source='other').count(), 2)


class ImportCommandTests(TestCase):
    def test_import_jagovfaqs_from_file(self):
        table = pa.table(
            {
                'Question': ['質問A', '質問B'],
                'Answer': ['回答A', '回答B'],
                'copyright': ['省', '省'],
                'url': ['https://example.com', 'https://example.com'],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'data.parquet')
            pq.write_table(table, path)
            call_command('import_jagovfaqs', '--file', str(path), '--limit', '1', stdout=StringIO())
            self.assertEqual(Document.objects.filter(source='jagovfaqs').count(), 1)
            with self.assertRaisesMessage(CommandError, '--replace'):
                call_command('import_jagovfaqs', '--file', str(path), stdout=StringIO())
            call_command('import_jagovfaqs', '--file', str(path), '--replace', stdout=StringIO())
        self.assertEqual(Document.objects.filter(source='jagovfaqs').count(), 2)
        self.assertEqual(EvaluationQuery.objects.filter(dataset='jagovfaqs').count(), 2)

    def test_import_custom_dataset(self):
        call_command('import_custom_dataset', stdout=StringIO())
        self.assertEqual(Document.objects.filter(source='custom').count(), 12)
        self.assertEqual(EvaluationQuery.objects.filter(dataset='custom').count(), 16)
