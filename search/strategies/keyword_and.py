"""方式 K：質問文から内容語（キーワード）を選び、すべてを含む文書を探す（AND）。

利用者がキーワードを入力する検索画面を想定した方式。
"""

import time
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F

from search import text_analysis

NAME = 'keyword_and'

# キーワードとして残す品詞（大分類、中分類）。数詞や助動詞語幹の名詞は除く。
KEYWORD_POS = frozenset({('名詞', '普通名詞'), ('名詞', '固有名詞')})

# 質問文に頻出し、検索の役に立たない名詞（正規化形）。評価の結果（特に 0 件率）を見ながら調整する。
STOPWORDS = frozenset(
    {'こと', '物', '為', '時', '場合', '方法', '方', '際', '他', 'うち', '所', '必要', '具体的', '当該', '件'}
)


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


def select_keywords(text: str) -> list[str]:
    keywords = []
    for token in text_analysis.analyze(text).tokens:
        if token.pos[:2] not in KEYWORD_POS or token.normalized in STOPWORDS:
            continue
        # 「a」「b」のような英字 1 文字は、条文の項目記号などで検索の役に立たない
        if len(token.normalized) == 1 and token.normalized.isascii():
            continue
        if token.normalized not in keywords:
            keywords.append(token.normalized)
    return keywords


def search(text: str, documents, *, limit: int = 10) -> SearchOutcome:
    keywords = select_keywords(text)
    if not keywords:
        return SearchOutcome(document_ids=(), hits=0, elapsed_ms=0.0, description='')

    query = SearchQuery(' '.join(keywords), config='simple', search_type='plain')
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
        description=' & '.join(keywords),
    )
