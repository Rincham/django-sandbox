from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.test import SimpleTestCase

from search import text_analysis
from search.text_analysis import analyze, join_tokens, tokenizer_version


def normalized(tokens):
    return [token.normalized for token in tokens]


class AnalyzeTests(SimpleTestCase):
    def test_excludes_particles_auxiliaries_and_symbols(self):
        analysis = analyze('東京タワーに行った。')
        self.assertEqual(normalized(analysis.tokens), ['東京', 'タワー', '行く'])

    def test_uses_normalized_form(self):
        analysis = analyze('シュミレーションの附属資料')
        self.assertEqual(normalized(analysis.tokens), ['シミュレーション', '付属', '資料'])

    def test_normalizes_width_and_case(self):
        analysis = analyze('ＰｏｓｔｇｒｅＳＱＬとｶﾞｲﾄﾞ、ＡＢＣ')
        self.assertEqual(normalized(analysis.tokens), ['postgresql', 'ガイド', 'abc'])

    def test_offsets_point_to_original_text(self):
        text = 'ＰｏｓｔｇｒｅＳＱＬで㍿のｶﾞｲﾄﾞを東京都庁に送る'
        analysis = analyze(text)
        for token in analysis.tokens + analysis.subtokens:
            self.assertEqual(text[token.begin : token.end], token.surface)

    def test_keeps_part_of_speech(self):
        (token,) = analyze('東京').tokens
        self.assertEqual(token.pos[:2], ('名詞', '固有名詞'))

    def test_subtokens_for_compound_words(self):
        analysis = analyze('東京都庁と全文')
        self.assertEqual(normalized(analysis.tokens), ['東京都庁', '全文'])
        self.assertEqual(normalized(analysis.subtokens), ['東京', '都庁'])

    def test_empty_text(self):
        for text in ['', None]:
            with self.subTest(text=text):
                analysis = analyze(text)
                self.assertEqual(analysis.tokens, ())
                self.assertEqual(analysis.subtokens, ())

    def test_join_tokens(self):
        self.assertEqual(join_tokens(analyze('東京タワーに行く').tokens), '東京 タワー 行く')


class LongTextTests(SimpleTestCase):
    def assert_offsets_valid(self, text, analysis):
        for token in analysis.tokens:
            self.assertEqual(text[token.begin : token.end], token.surface)

    def test_text_longer_than_sudachi_limit(self):
        sentence = '選挙管理委員会が会見を行った。'
        text = sentence * 3000  # 約 13 万バイト（Sudachi の上限は 49,149 バイト）
        analysis = analyze(text)
        self.assertEqual(len(analysis.tokens), len(analyze(sentence).tokens) * 3000)
        self.assert_offsets_valid(text, analysis)

    def test_long_text_without_sentence_boundaries(self):
        text = '東京' * 30000
        analysis = analyze(text)
        self.assertTrue(analysis.tokens)
        self.assert_offsets_valid(text, analysis)

    def test_retries_when_normalized_text_exceeds_limit(self):
        # 「㍿」は正規化で「株式会社」（3 バイト → 12 バイト）になり、内部の上限（65,535 バイト）を超える
        text = '㍿' * 16000
        with mock.patch.object(text_analysis, 'MAX_CHUNK_BYTES', 49_000):
            analysis = analyze(text)
        self.assertEqual(normalized(analysis.tokens), ['株式会社'] * 16000)
        self.assert_offsets_valid(text, analysis)


class ConcurrencyTests(SimpleTestCase):
    def test_can_be_used_from_multiple_threads(self):
        texts = ['選挙管理委員会が東京都庁で会見を行った。' * 20, 'シュミレーションの附属資料を確認する。' * 20]
        expected = [analyze(text) for text in texts]
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda i: analyze(texts[i % 2]) == expected[i % 2], range(200)))
        self.assertTrue(all(results))


class TokenizerVersionTests(SimpleTestCase):
    def test_includes_library_dictionary_and_rules_versions(self):
        self.assertRegex(tokenizer_version(), r'^sudachipy[\d.]+-core[\d.]+-r\d+$')
