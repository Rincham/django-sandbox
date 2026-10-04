"""評価の実行。評価用クエリを 1 つずつ検索方式に渡し、結果を記録する。"""

import random

from search.evaluation.metrics import QueryRecord
from search.models import Document, EvaluationQuery
from search.strategies import keyword_and, or_rank

STRATEGIES = {
    keyword_and.NAME: keyword_and.search,
    or_rank.NAME: or_rank.search,
}


def evaluate(strategy: str, dataset: str, *, k: int = 10, sample: int | None = None, seed: int = 0):
    """データセットの評価用クエリで検索方式を評価し、QueryRecord の列を返す。

    検索の対象は、そのデータセットから取り込んだ文書に限る。
    sample を指定すると、seed で決まる同じクエリの組を抜き出して評価する（方式どうしで同じクエリを比べるため）。
    """
    search = STRATEGIES[strategy]
    documents = Document.objects.filter(source=dataset)
    queries = list(
        EvaluationQuery.objects.filter(dataset=dataset).order_by('pk').prefetch_related('relevant_documents')
    )
    if sample is not None and sample < len(queries):
        queries = sorted(random.Random(seed).sample(queries, sample), key=lambda query: query.pk)
    if not queries:
        return []

    # 1 回目の検索は辞書の読み込みなどで遅くなるので、計測から外す
    search(queries[0].text, documents, limit=k)

    records = []
    for query in queries:
        outcome = search(query.text, documents, limit=k)
        records.append(
            QueryRecord(
                query_id=query.pk,
                text=query.text,
                description=outcome.description,
                relevant_ids=frozenset(document.pk for document in query.relevant_documents.all()),
                document_ids=outcome.document_ids,
                hits=outcome.hits,
                elapsed_ms=outcome.elapsed_ms,
            )
        )
    return records
