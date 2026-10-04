from django.test import SimpleTestCase, TestCase

from search.models import Document
from search.strategies import keyword_and, or_rank


class SelectKeywordsTests(SimpleTestCase):
    def test_keeps_common_and_proper_nouns(self):
        keywords = keyword_and.select_keywords('東京都庁の展望室には何時から入場できますか。')
        self.assertEqual(keywords, ['東京都庁', '展望', '入場'])

    def test_drops_stopwords_numerals_and_single_ascii_letters(self):
        keywords = keyword_and.select_keywords('申請が必要な場合、第1条のaに該当することを確認する方法は？')
        self.assertEqual(keywords, ['申請', '条', '該当', '確認'])

    def test_removes_duplicates(self):
        self.assertEqual(keyword_and.select_keywords('年金と年金'), ['年金'])


class QueryTermsTests(SimpleTestCase):
    def test_uses_all_tokens(self):
        self.assertEqual(or_rank.query_terms('補助金の申請を行いたい'), ['補助金', '申請', '行う'])

    def test_removes_duplicates(self):
        self.assertEqual(or_rank.query_terms('年金と年金'), ['年金'])


class StrategySearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.both = Document.objects.create(title='', body='年金の受給資格を確認します。')
        cls.pension = Document.objects.create(title='', body='年金の支払日のお知らせです。')
        cls.other = Document.objects.create(title='', body='道路の工事のお知らせです。')
        cls.documents = Document.objects.all()

    def test_keyword_and_requires_all_keywords(self):
        outcome = keyword_and.search('年金の受給資格はどうやって確認しますか', self.documents)
        self.assertEqual(outcome.document_ids, (self.both.pk,))
        self.assertEqual(outcome.hits, 1)
        self.assertEqual(outcome.description, '年金 & 受給資格 & 確認')

    def test_or_rank_ranks_documents_matching_more_terms_higher(self):
        outcome = or_rank.search('年金の受給資格はどうやって確認しますか', self.documents)
        self.assertEqual(outcome.document_ids, (self.both.pk, self.pension.pk))
        self.assertEqual(outcome.hits, 2)

    def test_limit(self):
        outcome = or_rank.search('年金 お知らせ', self.documents, limit=1)
        self.assertEqual(len(outcome.document_ids), 1)
        self.assertEqual(outcome.hits, 3)

    def test_no_terms(self):
        for strategy in (keyword_and, or_rank):
            with self.subTest(strategy=strategy.NAME):
                outcome = strategy.search('の', self.documents)
                self.assertEqual((outcome.document_ids, outcome.hits, outcome.description), ((), 0, ''))

    def test_searches_only_given_documents(self):
        documents = Document.objects.exclude(pk=self.both.pk)
        for strategy in (keyword_and, or_rank):
            with self.subTest(strategy=strategy.NAME):
                self.assertNotIn(self.both.pk, strategy.search('年金 受給 資格', documents).document_ids)
