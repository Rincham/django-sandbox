"""検索画面の検索語の解析。

利用者が入力した検索語を解釈し、SearchQuery を組み立てる。
空白で区切った語はすべて含む（AND）。"…" はフレーズ、-語 は除外、語 OR 語 はいずれかを含む。
演算子は形態素解析の前に解釈する（形態素解析は引用符や - を記号として捨ててしまうため）。
"""

import re
from dataclasses import dataclass

from django.contrib.postgres.search import SearchQuery

from search import text_analysis

# 引用符で囲んだフレーズ（先頭の - は除外）か、空白で区切られた語
_TERM = re.compile(r'([-－]?)["“”＂]([^"“”＂]*)["“”＂]|(\S+)')
_OR = 'OR'


class QueryError(Exception):
    pass


@dataclass(frozen=True)
class Term:
    text: str
    phrase: bool = False


@dataclass(frozen=True)
class ParsedQuery:
    clauses: tuple[tuple[Term, ...], ...]
    """AND で結ぶ節。各節の語は OR で結ぶ。"""
    excludes: tuple[Term, ...]


@dataclass(frozen=True)
class CompiledQuery:
    search_query: SearchQuery
    description: str
    """解釈した結果を tsquery に近い形で表した文字列（画面に表示する）。"""
    highlight_terms: frozenset[str]
    """ハイライトする語の正規化形。"""


def parse_query(text: str) -> ParsedQuery:
    clauses = []
    excludes = []
    pending_or = False
    for match in _TERM.finditer(text):
        minus, quoted, word = match.groups()
        if word == _OR:
            # 先頭の OR は無視する
            pending_or = bool(clauses)
            continue
        if quoted is not None:
            term = Term(quoted, phrase=True)
        else:
            if word[0] in '-－' and len(word) > 1:
                minus, word = '-', word[1:]
            term = Term(word.strip('"“”＂'))
        if minus:
            excludes.append(term)
        elif pending_or:
            clauses[-1] += (term,)
        else:
            clauses.append((term,))
        pending_or = False
    return ParsedQuery(clauses=tuple(clauses), excludes=tuple(excludes))


def compile_query(parsed: ParsedQuery) -> CompiledQuery:
    search_query = None
    descriptions = []
    highlight_terms = set()

    for clause in parsed.clauses:
        compiled = [c for c in (_compile_term(term) for term in clause) if c is not None]
        if not compiled:
            continue
        clause_query = compiled[0][0]
        for term_query, _, _ in compiled[1:]:
            clause_query |= term_query
        search_query = clause_query if search_query is None else search_query & clause_query
        descriptions.append(' | '.join(description for _, description, _ in compiled))
        for _, _, tokens in compiled:
            highlight_terms.update(tokens)

    if search_query is None:
        if parsed.excludes:
            raise QueryError('除外する語だけでは検索できません。含める語も入力してください。')
        raise QueryError('検索に使える語が含まれていません。')

    for term in parsed.excludes:
        compiled = _compile_term(term)
        if compiled is None:
            continue
        term_query, description, _ = compiled
        search_query &= ~term_query
        descriptions.append(f'!{description}')

    description = ' & '.join(f'({d})' if ' | ' in d and len(descriptions) > 1 else d for d in descriptions)
    return CompiledQuery(search_query=search_query, description=description, highlight_terms=frozenset(highlight_terms))


def _compile_term(term: Term):
    tokens = [token.normalized for token in text_analysis.analyze(term.text).tokens]
    if not tokens:
        return None
    search_type = 'phrase' if term.phrase else 'plain'
    query = SearchQuery(' '.join(tokens), config='simple', search_type=search_type)
    description = (' <-> ' if term.phrase else ' & ').join(tokens)
    if len(tokens) > 1:
        description = f'({description})'
    return query, description, tokens
