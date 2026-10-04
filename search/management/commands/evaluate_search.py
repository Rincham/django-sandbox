import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from search.evaluation.metrics import summarize
from search.evaluation.runner import STRATEGIES, evaluate
from search.models import EvaluationQuery


class Command(BaseCommand):
    help = '評価用クエリで検索方式を評価し、指標を表示する'

    def add_arguments(self, parser):
        parser.add_argument('--strategy', required=True, choices=sorted(STRATEGIES), help='評価する検索方式')
        parser.add_argument('--dataset', required=True, help='評価に使うデータセット（jagovfaqs、custom など）')
        parser.add_argument('-k', type=int, default=10, help='上位何件までを評価するか')
        parser.add_argument('--sample', type=int, help='評価するクエリの数（指定しなければすべて）')
        parser.add_argument('--seed', type=int, default=0, help='クエリを抜き出すときの乱数の種')
        parser.add_argument('--output', type=Path, help='クエリごとの結果を JSON Lines で書き出すファイル')
        parser.add_argument('--details', action='store_true', help='クエリごとの結果を表示する')

    def handle(self, *args, strategy, dataset, k, sample, seed, output, details, **options):
        if not EvaluationQuery.objects.filter(dataset=dataset).exists():
            raise CommandError(f'データセット {dataset} の評価用クエリがありません')

        records = evaluate(strategy, dataset, k=k, sample=sample, seed=seed)
        notes = dict(EvaluationQuery.objects.filter(pk__in=[r.query_id for r in records]).values_list('pk', 'note'))

        if details:
            for record in records:
                rank = record.first_relevant_rank(k)
                mark = '○' if rank else '×'
                self.stdout.write(
                    f'{mark} 順位 {rank or "-":>2} ヒット {record.hits:>6}  {record.text}\n'
                    f'      条件: {record.description or "（なし）"}'
                    + (f'\n      メモ: {notes[record.query_id]}' if notes.get(record.query_id) else '')
                )

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('w') as f:
                for record in records:
                    f.write(
                        json.dumps(
                            {
                                'query_id': record.query_id,
                                'text': record.text,
                                'description': record.description,
                                'relevant_ids': sorted(record.relevant_ids),
                                'document_ids': list(record.document_ids),
                                'first_relevant_rank': record.first_relevant_rank(k),
                                'hits': record.hits,
                                'elapsed_ms': round(record.elapsed_ms, 3),
                                'note': notes.get(record.query_id, ''),
                            },
                            ensure_ascii=False,
                        )
                        + '\n'
                    )

        summary = summarize(records, k)
        self.stdout.write(
            '\n'.join(
                [
                    f'方式: {strategy}  データセット: {dataset}  クエリ: {summary.queries} 件（seed={seed}）',
                    f'Recall@{k}: {summary.recall:.3f}  MRR@{k}: {summary.mrr:.3f}  '
                    f'0 件率: {summary.zero_hit_rate:.3f}',
                    f'ヒット件数: 中央値 {summary.hits_median:g}  '
                    f'95 パーセンタイル {summary.hits_p95}  最大 {summary.hits_max}',
                    f'応答時間（ヒットしたクエリ）: 中央値 {summary.latency_median_ms:.1f} ms  '
                    f'95 パーセンタイル {summary.latency_p95_ms:.1f} ms',
                ]
            )
        )
