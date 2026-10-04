import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from search.evaluation.datasets import DatasetAlreadyLoadedError, build_custom, load_dataset

DATASET_NAME = 'custom'
DATASET_PATH = Path(__file__).resolve().parents[2] / 'evaluation' / 'custom_dataset.json'


class Command(BaseCommand):
    help = '独自クエリ集（search/evaluation/custom_dataset.json）を評価データとして取り込む'

    def add_arguments(self, parser):
        parser.add_argument('--replace', action='store_true', help='登録済みの場合、削除してから取り込み直す')

    def handle(self, *args, replace, **options):
        documents, queries = build_custom(json.loads(DATASET_PATH.read_text()))
        try:
            document_count, query_count = load_dataset(DATASET_NAME, documents, queries, replace=replace)
        except DatasetAlreadyLoadedError as e:
            raise CommandError(f'{e}。取り込み直す場合は --replace を指定してください') from e
        self.stdout.write(self.style.SUCCESS(f'文書 {document_count} 件とクエリ {query_count} 件を登録しました'))
