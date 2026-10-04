"""方式 R：質問文のトークンをすべて使い、いずれかを含む文書（OR）をランキングで並べる。

利用者が質問文をそのまま入力する検索を想定した方式。
"""

import time
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F

from search import text_analysis

NAME = 'or_rank'


@dataclass(frozen=True)
class SearchOutcome:
    document_ids: tuple[int, ...]
    """上位 limit 件の文書の ID（順位順）。"""
    hits: int
    """ヒットした文書の総数。"""
    elapsed_ms: float
    """上位 limit 件の取得にかかった時間（件数の取得は含まない）。"""
    description: str
    """組み立てた検索条件。"""


def query_terms(text: str) -> list[str]:
    terms = []
    for token in text_analysis.analyze(text).tokens:
        if token.normalized not in terms:
            terms.append(token.normalized)
    return terms


def search(text: str, documents, *, limit: int = 10) -> SearchOutcome:
    terms = query_terms(text)
    if not terms:
        return SearchOutcome(document_ids=(), hits=0, elapsed_ms=0.0, description='')

    query = SearchQuery(terms[0], config='simple', search_type='plain')
    for term in terms[1:]:
        query |= SearchQuery(term, config='simple', search_type='plain')
    matched = documents.filter(search_vector=query)
    started = time.perf_counter()
    document_ids = tuple(
        matched.annotate(rank=SearchRank(F('search_vector'), query))
        .order_by('-rank', 'pk')
        .values_list('pk', flat=True)[:limit]
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    return SearchOutcome(
        document_ids=document_ids,
        hits=matched.count(),
        elapsed_ms=elapsed_ms,
        description=' | '.join(terms),
    )
