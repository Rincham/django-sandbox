from io import StringIO

from django.contrib.postgres.search import SearchQuery
from django.core.management import call_command
from django.test import TestCase

from search.models import Document
from search.text_analysis import tokenizer_version


def search(text, search_type='plain'):
    return Document.objects.filter(search_vector=SearchQuery(text, config='simple', search_type=search_type))


class DocumentTokensTests(TestCase):
    def test_save_updates_tokens(self):
        document = Document.objects.create(title='東京都庁の附属施設', body='シュミレーションを行った。')
        self.assertEqual(document.title_tokens, '東京都庁 付属 施設')
        self.assertEqual(document.body_tokens, 'シミュレーション 行う')
        self.assertEqual(document.subtokens, '東京 都庁')
        self.assertEqual(document.tokenizer_version, tokenizer_version())

    def test_save_with_update_fields_updates_tokens(self):
        document = Document.objects.create(title='東京', body='本文')
        document.title = '大阪'
        document.save(update_fields=['title'])
        document.refresh_from_db()
        self.assertEqual(document.title_tokens, '大阪')

    def test_save_without_source_fields_keeps_tokens(self):
        document = Document.objects.create(title='東京', body='本文')
        Document.objects.filter(pk=document.pk).update(title_tokens='古い')
        document.refresh_from_db()
        document.save(update_fields=['updated_at'])
        document.refresh_from_db()
        self.assertEqual(document.title_tokens, '古い')


class SearchVectorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.document = Document.objects.create(title='東京都庁の附属施設', body='東京タワーに行った。')

    def test_matches_normalized_tokens(self):
        self.assertQuerySetEqual(search('付属'), [self.document])

    def test_matches_subtokens_of_compound_words(self):
        self.assertQuerySetEqual(search('都庁'), [self.document])

    def test_phrase_search(self):
        self.assertQuerySetEqual(search('東京 タワー', 'phrase'), [self.document])
        self.assertQuerySetEqual(search('タワー 東京', 'phrase'), [])

    def test_weights(self):
        document = Document.objects.get(pk=self.document.pk)
        vector = str(document.search_vector)
        self.assertIn("'東京都庁':1A", vector)
        self.assertIn("'東京':4B,7C", vector)
        self.assertIn("'都庁':8C", vector)


class RebuildSearchTokensTests(TestCase):
    def setUp(self):
        self.current = Document.objects.create(title='東京', body='本文')
        self.outdated = Document.objects.create(title='大阪', body='本文')
        Document.objects.filter(pk=self.outdated.pk).update(title_tokens='', tokenizer_version='old')
        Document.objects.filter(pk=self.current.pk).update(title_tokens='そのまま')

    def rebuild(self, *args):
        call_command('rebuild_search_tokens', *args, stdout=StringIO())
        self.current.refresh_from_db()
        self.outdated.refresh_from_db()

    def test_rebuilds_only_outdated_documents(self):
        self.rebuild()
        self.assertEqual(self.outdated.title_tokens, '大阪')
        self.assertEqual(self.outdated.tokenizer_version, tokenizer_version())
        self.assertEqual(self.current.title_tokens, 'そのまま')

    def test_rebuilds_all_documents(self):
        self.rebuild('--all', '--batch-size', '1')
        self.assertEqual(self.outdated.title_tokens, '大阪')
        self.assertEqual(self.current.title_tokens, '東京')
