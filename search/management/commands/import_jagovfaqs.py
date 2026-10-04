import hashlib
import shutil
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from search.evaluation.datasets import DatasetAlreadyLoadedError, build_jagovfaqs, load_dataset

DATASET_NAME = 'jagovfaqs'
# Hugging Face が自動変換した Parquet（元データは https://huggingface.co/datasets/matsuxr/JaGovFaqs-22k 、CC BY 4.0）
SOURCE_URL = 'https://huggingface.co/api/datasets/matsuxr/JaGovFaqs-22k/parquet/default/train/0.parquet'
DEFAULT_PATH = Path(settings.BASE_DIR, 'data', 'jagovfaqs-22k.parquet')


class Command(BaseCommand):
    help = 'JaGovFaqs-22k を評価データとして取り込む（回答を文書、質問を評価用クエリにする）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file', type=Path, default=DEFAULT_PATH, help='Parquet ファイル（なければダウンロードする）'
        )
        parser.add_argument('--replace', action='store_true', help='登録済みの場合、削除してから取り込み直す')
        parser.add_argument('--limit', type=int, help='先頭から指定した行数だけ取り込む（動作確認用）')

    def handle(self, *args, file, replace, limit, **options):
        # pyarrow は dev グループの依存関係なので、本番のコードから import されないようにここで読み込む
        import pyarrow.parquet as pq

        if not file.exists():
            self._download(file)
        self.stdout.write(f'{file}（SHA-256: {_sha256(file)}）')

        rows = pq.read_table(file, columns=['Question', 'Answer']).to_pylist()
        if limit is not None:
            rows = rows[:limit]
        documents, queries = build_jagovfaqs(rows)
        self.stdout.write(f'{len(rows)} 行から、文書 {len(documents)} 件とクエリ {len(queries)} 件を作りました')

        try:
            document_count, query_count = load_dataset(DATASET_NAME, documents, queries, replace=replace)
        except DatasetAlreadyLoadedError as e:
            raise CommandError(f'{e}。取り込み直す場合は --replace を指定してください') from e
        self.stdout.write(self.style.SUCCESS(f'文書 {document_count} 件とクエリ {query_count} 件を登録しました'))

    def _download(self, path):
        self.stdout.write(f'{SOURCE_URL} からダウンロードします')
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix('.part')
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response, partial.open('wb') as out:
            shutil.copyfileobj(response, out)
        partial.rename(path)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()
