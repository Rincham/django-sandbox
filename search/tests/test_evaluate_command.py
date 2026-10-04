import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from search.evaluation.runner import evaluate


class EvaluateSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('import_custom_dataset', stdout=StringIO())

    def run_command(self, *args):
        out = StringIO()
        call_command('evaluate_search', *args, stdout=out)
        return out.getvalue()

    def test_summary(self):
        for strategy in ('keyword_and', 'or_rank'):
            with self.subTest(strategy=strategy):
                output = self.run_command('--strategy', strategy, '--dataset', 'custom')
                self.assertIn(f'方式: {strategy}  データセット: custom  クエリ: 16 件', output)
                self.assertIn('Recall@10', output)

    def test_details_and_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'result.jsonl')
            args = ['--strategy', 'or_rank', '--dataset', 'custom', '--details', '--output', str(path)]
            output = self.run_command(*args)
            lines = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(lines), 16)
        self.assertIn('メモ: 既知の弱点', output)
        first = next(line for line in lines if line['text'] == '付属病院 面会')
        self.assertEqual(first['first_relevant_rank'], 1)

    def test_sample_is_reproducible(self):
        first = [r.query_id for r in evaluate('keyword_and', 'custom', sample=5, seed=1)]
        second = [r.query_id for r in evaluate('or_rank', 'custom', sample=5, seed=1)]
        self.assertEqual(len(first), 5)
        self.assertEqual(first, second)

    def test_unknown_dataset(self):
        with self.assertRaisesMessage(CommandError, 'データセット unknown'):
            self.run_command('--strategy', 'or_rank', '--dataset', 'unknown')
