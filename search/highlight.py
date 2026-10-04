"""検索結果のハイライト。

ts_headline は空白区切りのトークン列にしか効かないため、表示する文書だけを形態素解析し、
検索語と正規化形が一致する形態素を、元のテキスト上の位置で囲む。
結果は (文字列, 一致したか) の組の列で返し、HTML への変換はテンプレートに任せる（自動エスケープを効かせるため）。
"""

from search import text_analysis

ELLIPSIS = '…'


def highlight(text: str, terms: frozenset[str]) -> list[tuple[str, bool]]:
    """テキスト全体を、一致した部分とそれ以外に分ける。"""
    return _segments(text, _match_ranges(text, terms), 0, len(text))


def snippet(text: str, terms: frozenset[str], *, width: int = 160, before: int = 40) -> list[tuple[str, bool]]:
    """最初に一致した位置の周辺を width 文字切り出し、一致した部分とそれ以外に分ける。"""
    ranges = _match_ranges(text, terms)
    start = max(ranges[0][0] - before, 0) if ranges else 0
    end = min(start + width, len(text))
    start = max(end - width, 0)

    segments = _segments(text, ranges, start, end)
    if start > 0:
        segments.insert(0, (ELLIPSIS, False))
    if end < len(text):
        segments.append((ELLIPSIS, False))
    return segments


def _match_ranges(text, terms):
    if not text or not terms:
        return []
    analysis = text_analysis.analyze(text)
    # 複合語の一部（サブトークン）が一致した場合も、その部分だけを囲む
    ranges = sorted((t.begin, t.end) for t in analysis.tokens + analysis.subtokens if t.normalized in terms)
    merged = []
    for begin, end in ranges:
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((begin, end))
    return merged


def _segments(text, ranges, start, end):
    segments = []
    position = start
    for begin, finish in ranges:
        begin, finish = max(begin, start), min(finish, end)
        if begin >= finish:
            continue
        if position < begin:
            segments.append((text[position:begin], False))
        segments.append((text[begin:finish], True))
        position = finish
    if position < end:
        segments.append((text[position:end], False))
    return segments
