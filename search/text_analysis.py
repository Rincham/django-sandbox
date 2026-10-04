"""日本語テキストの解析（形態素解析とトークン化）。

索引の作成と検索語の解析の両方で使う。
両者の処理が食い違うと検索漏れが起きるため、トークンを作る処理はこのモジュールに集約し、
検索方式に固有の処理（キーワードの選別など）はここに入れない。
"""

import re
import threading
from dataclasses import dataclass
from functools import cache
from importlib.metadata import version

from sudachipy import Dictionary, SplitMode
from sudachipy.errors import SudachiError

# トークン化の規則を変えたら上げる（辞書やライブラリの版は TOKENIZER_VERSION に自動で含まれる）
RULES_VERSION = 2

# 索引にも検索語にも含めない品詞（大分類）
EXCLUDED_POS = frozenset({'助詞', '助動詞', '補助記号', '空白'})

# Sudachi の入力の上限は、元のテキストで 49,149 バイト、内部の正規化後で 65,535 バイト。
# 正規化で長くなる文字（「㍿」→「株式会社」など）があるため、元のテキストで余裕を持って区切る。
MAX_CHUNK_BYTES = 16_000

# 文の区切りの直後で分割する（区切り文字は前の文に残す）。
# 半角のピリオドは小数点（5.2 など）と区別するため、直後が空白のときだけ文の区切りとみなす。
_SENTENCE_BOUNDARY = re.compile(r'(?<=[。．｡！？!?\n])|(?<=\.)(?=\s)')

# 文の区切りがない長い文を分けるときに、直後で切ってよい文字（語の途中で切らないため）
_SOFT_BREAKS = frozenset(' \t\u3000\n、，,､。．｡.！？!?')

# 入力が上限を超えたときの SudachiError のメッセージに含まれる文字列
_INPUT_TOO_LONG = 'Input is too long'


@dataclass(frozen=True, slots=True)
class Token:
    """形態素解析の結果の 1 語。"""

    surface: str
    """元のテキスト上の表記。"""
    normalized: str
    """正規化形（小文字化済み）。索引と検索語に使う。"""
    pos: tuple[str, ...]
    """品詞（Sudachi の 6 要素のうち、活用を除く 4 階層）。"""
    begin: int
    """元のテキスト上の開始位置（文字単位）。"""
    end: int
    """元のテキスト上の終了位置（文字単位）。"""


@dataclass(frozen=True, slots=True)
class Analysis:
    """1 つのテキストの解析結果。"""

    tokens: tuple[Token, ...]
    """分割単位 C（長い単位）のトークン。除外する品詞は含まない。"""
    subtokens: tuple[Token, ...]
    """分割単位 C のトークンのうち、分割単位 A でさらに分かれるものの A 単位のトークン。"""


@cache
def tokenizer_version() -> str:
    """解析結果の版。この値が変わったら、登録済みの文書のトークン列を作り直す。"""
    return f'sudachipy{version("sudachipy")}-core{version("sudachidict-core")}-r{RULES_VERSION}'


_dictionary_lock = threading.Lock()
_dictionary_instance: Dictionary | None = None


def _dictionary() -> Dictionary:
    # 辞書はプロセス内で 1 つだけ作り、スレッド間で共有する。
    # 起動直後に複数のスレッドが同時に呼んでも 1 つだけ作るように、ロックの中で作る。
    global _dictionary_instance
    if _dictionary_instance is None:
        with _dictionary_lock:
            if _dictionary_instance is None:
                _dictionary_instance = Dictionary(dict='core')
    return _dictionary_instance


_local = threading.local()


def _tokenizer():
    # トークナイザーは同時に使うと SudachiError になるため、スレッドごとに作る
    tokenizer = getattr(_local, 'tokenizer', None)
    if tokenizer is None:
        tokenizer = _local.tokenizer = _dictionary().tokenizer(mode=SplitMode.C)
    return tokenizer


def analyze(text: str) -> Analysis:
    """テキストを形態素解析し、索引と検索語に使うトークンを返す。"""
    tokens = []
    subtokens = []
    # 先頭の塊から順に取り出すため、逆順に積む
    pending = list(_chunks(text or ''))[::-1]
    while pending:
        offset, chunk = pending.pop()
        try:
            morphemes = _tokenizer().tokenize(chunk)
        except SudachiError as e:
            # 正規化で長くなる文字が多く、内部の上限を超えた場合に限り、2 つに分けて解析し直す
            if _INPUT_TOO_LONG not in str(e) or len(chunk) <= 1:
                raise
            cut = _cut_near_middle(chunk)
            pending += [(offset + cut, chunk[cut:]), (offset, chunk[:cut])]
            continue
        for morpheme in morphemes:
            token = _to_token(morpheme, offset)
            if token is None:
                continue
            tokens.append(token)
            # 分割されない語には空のリストが返る。
            # 既定値は False（API リファレンスどおり。型定義 .pyi の True は誤り）だが、意図を明示する。
            # なお SudachiPy 0.7.0 では、分割されない語に add_single=True を指定するとパニックする。
            parts = morpheme.split(SplitMode.A, add_single=False)
            if parts:
                subtokens.extend(t for t in (_to_token(part, offset) for part in parts) if t is not None)
    return Analysis(tokens=tuple(tokens), subtokens=tuple(subtokens))


def join_tokens(tokens) -> str:
    """トークンの正規化形を空白でつなぎ、DB に保存するトークン列にする。"""
    return ' '.join(token.normalized for token in tokens)


def _to_token(morpheme, offset: int) -> Token | None:
    pos = tuple(morpheme.part_of_speech()[:4])
    if pos[0] in EXCLUDED_POS:
        return None
    # 正規化形に空白が含まれると、DB 側で別々の語彙素に分かれてしまうので取り除く
    normalized = ''.join(morpheme.normalized_form().lower().split())
    if not normalized:
        return None
    return Token(
        surface=morpheme.surface(),
        normalized=normalized,
        pos=pos,
        begin=offset + morpheme.begin(),
        end=offset + morpheme.end(),
    )


def _chunks(text: str):
    """テキストを、文の区切りで MAX_CHUNK_BYTES 以下の塊に分け、(開始位置, 塊) を返す。"""
    if len(text.encode()) <= MAX_CHUNK_BYTES:
        if text:
            yield 0, text
        return

    start = 0
    buffer = ''
    buffer_bytes = 0
    for sentence in _SENTENCE_BOUNDARY.split(text):
        size = len(sentence.encode())
        if buffer and buffer_bytes + size > MAX_CHUNK_BYTES:
            yield start, buffer
            start += len(buffer)
            buffer, buffer_bytes = '', 0
        if size > MAX_CHUNK_BYTES:
            # 区切りのない長い文は、なるべく空白や読点の直後で分ける
            for piece in _split_by_bytes(sentence):
                yield start, piece
                start += len(piece)
            continue
        buffer += sentence
        buffer_bytes += size
    if buffer:
        yield start, buffer


def _split_by_bytes(text: str):
    """区切りのない長い文を MAX_CHUNK_BYTES 以下の塊に分ける。空白や読点があればその直後で切る。"""
    while len(text.encode()) > MAX_CHUNK_BYTES:
        limit = _prefix_length_within_bytes(text, MAX_CHUNK_BYTES)
        cut = _last_soft_break(text, 0, limit) or limit
        yield text[:cut]
        text = text[cut:]
    if text:
        yield text


def _cut_near_middle(chunk: str) -> int:
    """chunk を 2 つに分ける位置。中央に最も近い区切りの直後を選び、なければ中央で切る。"""
    middle = len(chunk) // 2
    candidates = [
        position
        for position in (_last_soft_break(chunk, 0, middle), _first_soft_break(chunk, middle, len(chunk)))
        if position is not None and 0 < position < len(chunk)
    ]
    return min(candidates, key=lambda position: abs(position - middle), default=middle)


def _prefix_length_within_bytes(text: str, max_bytes: int) -> int:
    """UTF-8 で max_bytes 以下に収まる、先頭からの文字数。"""
    size = 0
    for index, char in enumerate(text):
        size += len(char.encode())
        if size > max_bytes:
            return index
    return len(text)


def _last_soft_break(text: str, start: int, end: int) -> int | None:
    """text[start:end] にある最後の区切り文字の直後の位置。"""
    for position in range(end, start, -1):
        if text[position - 1] in _SOFT_BREAKS:
            return position
    return None


def _first_soft_break(text: str, start: int, end: int) -> int | None:
    """text[start:end] にある最初の区切り文字の直後の位置。"""
    for position in range(start + 1, end + 1):
        if text[position - 1] in _SOFT_BREAKS:
            return position
    return None
