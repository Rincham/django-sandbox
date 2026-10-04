from django.core.management.base import BaseCommand

from search.models import SOURCE_FIELDS, TOKEN_FIELDS, Document
from search.text_analysis import tokenizer_version


class Command(BaseCommand):
    help = '文書のトークン列を作り直す（既定では、解析の版が現在と異なる文書だけを対象にする）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all', action='store_true', dest='rebuild_all', help='解析の版にかかわらず、すべての文書を作り直す'
        )
        parser.add_argument('--batch-size', type=int, default=500, help='1 回の更新でまとめる文書数')

    def handle(self, *args, rebuild_all, batch_size, **options):
        documents = Document.objects.only('pk', *SOURCE_FIELDS).order_by('pk')
        if not rebuild_all:
            documents = documents.exclude(tokenizer_version=tokenizer_version())
        total = documents.count()

        done = 0
        batch = []
        for document in documents.iterator(chunk_size=batch_size):
            document.update_tokens()
            batch.append(document)
            if len(batch) >= batch_size:
                done += self._flush(batch)
                self.stdout.write(f'{done} / {total}')
        done += self._flush(batch)
        message = f'{done} 件のトークン列を作り直しました（解析の版: {tokenizer_version()}）'
        self.stdout.write(self.style.SUCCESS(message))

    def _flush(self, batch):
        # バッチごとにコミットされるので、途中で止めても続きから再開できる
        Document.objects.bulk_update(batch, TOKEN_FIELDS)
        count = len(batch)
        batch.clear()
        return count
