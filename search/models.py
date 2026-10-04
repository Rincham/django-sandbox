from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models

from search import text_analysis

# トークン列を作り直す元になるフィールド
SOURCE_FIELDS = ('title', 'body')
# SOURCE_FIELDS から作るフィールド
TOKEN_FIELDS = ('title_tokens', 'body_tokens', 'subtokens', 'tokenizer_version')


class Document(models.Model):
    title = models.CharField('タイトル', max_length=200, blank=True)
    body = models.TextField('本文')

    # テキスト解析モジュールが作る空白区切りのトークン列（save() で更新する）
    title_tokens = models.TextField('タイトルのトークン列', blank=True, editable=False)
    body_tokens = models.TextField('本文のトークン列', blank=True, editable=False)
    subtokens = models.TextField('サブトークン列', blank=True, editable=False)
    tokenizer_version = models.CharField('解析の版', max_length=50, blank=True, editable=False)

    # トークン列と食い違わないように、DB 側の生成列として計算する
    search_vector = models.GeneratedField(
        expression=(
            SearchVector('title_tokens', config='simple', weight='A')
            + SearchVector('body_tokens', config='simple', weight='B')
            + SearchVector('subtokens', config='simple', weight='C')
        ),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    # 評価データから取り込んだ文書の出典（データセット名と、データセット内の識別子）
    source = models.CharField('出典', max_length=50, blank=True)
    source_id = models.CharField('出典内の識別子', max_length=100, blank=True)

    created_at = models.DateTimeField('作成日時', auto_now_add=True)
    updated_at = models.DateTimeField('更新日時', auto_now=True)

    class Meta:
        verbose_name = '文書'
        verbose_name_plural = '文書'
        indexes = [
            GinIndex(fields=['search_vector'], name='search_document_vector_gin'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'source_id'],
                condition=~models.Q(source=''),
                name='search_document_unique_source_id',
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None or set(update_fields) & set(SOURCE_FIELDS):
            self.update_tokens()
            if update_fields is not None:
                kwargs['update_fields'] = {*update_fields, *TOKEN_FIELDS}
        super().save(*args, **kwargs)

    def update_tokens(self):
        """タイトルと本文を解析し、トークン列を更新する（保存はしない）。"""
        title = text_analysis.analyze(self.title)
        body = text_analysis.analyze(self.body)
        self.title_tokens = text_analysis.join_tokens(title.tokens)
        self.body_tokens = text_analysis.join_tokens(body.tokens)
        self.subtokens = text_analysis.join_tokens(title.subtokens + body.subtokens)
        self.tokenizer_version = text_analysis.tokenizer_version()


class EvaluationQuery(models.Model):
    """評価用のクエリと、その正解の文書。"""

    dataset = models.CharField('データセット', max_length=50)
    text = models.TextField('クエリ')
    note = models.TextField('メモ', blank=True)
    relevant_documents = models.ManyToManyField(Document, related_name='evaluation_queries', verbose_name='正解の文書')

    class Meta:
        verbose_name = '評価用クエリ'
        verbose_name_plural = '評価用クエリ'
        constraints = [
            models.UniqueConstraint(fields=['dataset', 'text'], name='search_evaluationquery_unique_text'),
        ]

    def __str__(self):
        return f'[{self.dataset}] {self.text}'
