"""評価データの取り込み。

データセットの形式の違いは各データセット用の変換関数で吸収し、DB への登録は load_dataset() に集約する。
"""

from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction

from search.models import Document, EvaluationQuery


@dataclass(frozen=True)
class DatasetDocument:
    source_id: str
    title: str
    body: str


@dataclass(frozen=True)
class DatasetQuery:
    text: str
    relevant: tuple[str, ...]
    """正解の文書の source_id。"""
    note: str = ''


class DatasetAlreadyLoadedError(Exception):
    pass


@transaction.atomic
def load_dataset(name, documents, queries, *, replace=False, batch_size=1000):
    """文書と評価用クエリを登録し、(文書数, クエリ数) を返す。

    同じ名前のデータセットが登録済みの場合、replace=True なら削除してから登録し直す。
    """
    existing_documents = Document.objects.filter(source=name)
    existing_queries = EvaluationQuery.objects.filter(dataset=name)
    if existing_documents.exists() or existing_queries.exists():
        if not replace:
            raise DatasetAlreadyLoadedError(f'データセット {name} は登録済みです')
        existing_queries.delete()
        existing_documents.delete()

    # bulk_create() は save() を通らないので、トークン列はここで作る
    new_documents = []
    for document in documents:
        instance = Document(title=document.title, body=document.body, source=name, source_id=document.source_id)
        instance.update_tokens()
        new_documents.append(instance)
    created = Document.objects.bulk_create(new_documents, batch_size=batch_size)
    document_ids = {document.source_id: document.pk for document in created}

    created_queries = EvaluationQuery.objects.bulk_create(
        [EvaluationQuery(dataset=name, text=query.text, note=query.note) for query in queries], batch_size=batch_size
    )
    relation = EvaluationQuery.relevant_documents.through
    relation.objects.bulk_create(
        [
            relation(evaluationquery_id=created_query.pk, document_id=document_ids[source_id])
            for created_query, query in zip(created_queries, queries, strict=True)
            for source_id in query.relevant
        ],
        batch_size=batch_size,
    )
    return len(created), len(created_queries)


def build_jagovfaqs(rows: Iterable[dict]):
    """JaGovFaqs-22k の行（Question、Answer）から、文書と評価用クエリを作る。

    回答を文書、質問をクエリにする。
    同じ回答は 1 つの文書にまとめ（同じ内容の文書が並んで正解の順位が下がるのを防ぐ）、
    同じ質問は 1 つのクエリにまとめて、正解の文書を複数持たせる。
    """
    document_ids = {}
    documents = []
    relevant = {}
    for index, row in enumerate(rows):
        question = (row['Question'] or '').strip()
        answer = (row['Answer'] or '').strip()
        if not question or not answer:
            continue
        source_id = document_ids.get(answer)
        if source_id is None:
            source_id = document_ids[answer] = str(index)
            documents.append(DatasetDocument(source_id=source_id, title='', body=answer))
        ids = relevant.setdefault(question, [])
        if source_id not in ids:
            ids.append(source_id)
    queries = [DatasetQuery(text=question, relevant=tuple(ids)) for question, ids in relevant.items()]
    return documents, queries


def build_custom(data: dict):
    """独自クエリ集（custom_dataset.json の内容）から、文書と評価用クエリを作る。"""
    documents = [
        DatasetDocument(source_id=document['id'], title=document['title'], body=document['body'])
        for document in data['documents']
    ]
    queries = [
        DatasetQuery(text=query['text'], relevant=tuple(query['relevant']), note=query.get('note', ''))
        for query in data['queries']
    ]
    return documents, queries
