import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from django.test import SimpleTestCase
from sudachipy.errors import SudachiError

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

    def test_ascii_sentences_are_not_cut_in_the_middle_of_words(self):
        sentence = 'This is an example sentence about databases. '
        text = sentence * 400  # 18,000 バイト
        analysis = analyze(text)
        self.assertEqual(normalized(analysis.tokens), normalized(analyze(sentence).tokens) * 400)
        self.assert_offsets_valid(text, analysis)

    def test_decimal_point_is_not_a_sentence_boundary(self):
        sentences = text_analysis._SENTENCE_BOUNDARY.split('Django 5.2 is out. Next')
        self.assertEqual(sentences, ['Django 5.2 is out.', ' Next'])

    def test_long_text_without_sentence_boundaries_is_cut_at_commas(self):
        text = '東京都庁、' * 3300  # 約 5 万バイト
        analysis = analyze(text)
        self.assertEqual(normalized(analysis.tokens), ['東京都庁'] * 3300)
        self.assert_offsets_valid(text, analysis)

    def test_retry_cuts_near_the_middle_at_a_soft_break(self):
        # 中央で機械的に切ると「東京都庁」の途中で切れる配置にする
        text = 'あ' * 26 + ('東京都庁' + '㍿' * 10 + '、') * 1000
        with mock.patch.object(text_analysis, 'MAX_CHUNK_BYTES', 49_000):
            analysis = analyze(text)
        self.assertEqual(normalized(analysis.tokens).count('東京都庁'), 1000)
        self.assert_offsets_valid(text, analysis)

    def test_does_not_retry_other_sudachi_errors(self):
        tokenizer = mock.Mock()
        tokenizer.tokenize.side_effect = SudachiError('unexpected')
        with mock.patch.object(text_analysis, '_tokenizer', return_value=tokenizer):
            with self.assertRaisesMessage(SudachiError, 'unexpected'):
                analyze('東京' * 100)
        self.assertEqual(tokenizer.tokenize.call_count, 1)


class CutNearMiddleTests(SimpleTestCase):
    def test_prefers_the_nearest_soft_break(self):
        self.assertEqual(text_analysis._cut_near_middle('あいう、えおかきくけこ'), 4)
        self.assertEqual(text_analysis._cut_near_middle('あいうえおか、きくけこ'), 7)

    def test_falls_back_to_the_middle(self):
        self.assertEqual(text_analysis._cut_near_middle('あいうえおかきくけこ'), 5)

    def test_ignores_a_soft_break_at_the_end(self):
        self.assertEqual(text_analysis._cut_near_middle('あいうえ。'), 2)


class ConcurrencyTests(SimpleTestCase):
    def test_dictionary_is_created_once_even_when_threads_race(self):
        created = []

        def slow_dictionary(**kwargs):
            time.sleep(0.05)
            created.append(object())
            return created[-1]

        barrier = threading.Barrier(8)

        def get_dictionary(_):
            barrier.wait()
            return text_analysis._dictionary()

        with (
            mock.patch.object(text_analysis, '_dictionary_instance', None),
            mock.patch.object(text_analysis, 'Dictionary', side_effect=slow_dictionary),
            ThreadPoolExecutor(max_workers=8) as executor,
        ):
            results = list(executor.map(get_dictionary, range(8)))
        self.assertEqual(len(created), 1)
        self.assertTrue(all(result is created[0] for result in results))

    def test_can_be_used_from_multiple_threads(self):
        texts = ['選挙管理委員会が東京都庁で会見を行った。' * 20, 'シュミレーションの附属資料を確認する。' * 20]
        expected = [analyze(text) for text in texts]
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda i: analyze(texts[i % 2]) == expected[i % 2], range(200)))
        self.assertTrue(all(results))


class TokenizerVersionTests(SimpleTestCase):
    def test_includes_library_dictionary_and_rules_versions(self):
        self.assertRegex(tokenizer_version(), r'^sudachipy[\d.]+-core[\d.]+-r\d+$')
