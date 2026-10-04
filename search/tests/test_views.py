from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from search.models import Document

URL = reverse('search:index')


class SearchViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='taro', password='test-password-123')
        cls.tocho = Document.objects.create(title='東京都庁の展望室', body='展望室には午前9時30分から入場できます。')
        cls.tower = Document.objects.create(
            title='東京タワー', body='東京の展望台です。', source='custom', source_id='t'
        )
        cls.osaka = Document.objects.create(title='大阪城', body='大阪の展望台です。')

    def setUp(self):
        self.client.force_login(self.user)

    def search(self, **params):
        return self.client.get(URL, params)

    def titles(self, response):
        return [result['document'].title for result in response.context['results']]

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(URL)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={URL}')

    def test_root_redirects_to_search(self):
        self.assertRedirects(self.client.get('/'), URL)

    def test_initial_page(self):
        response = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'search/index.html')
        self.assertNotIn('results', response.context)

    def test_search(self):
        response = self.search(q='展望台')
        self.assertEqual(response.context['hits'], 2)
        self.assertCountEqual(self.titles(response), ['東京タワー', '大阪城'])
        self.assertContains(response, '<mark>展望台</mark>', count=2)

    def test_title_matches_rank_higher(self):
        response = self.search(q='東京')
        self.assertEqual(self.titles(response)[:2], ['東京タワー', '東京都庁の展望室'])

    def test_subtoken_match_is_highlighted(self):
        response = self.search(q='都庁')
        self.assertEqual(self.titles(response), ['東京都庁の展望室'])
        self.assertContains(response, '東京<mark>都庁</mark>の展望室')

    def test_exclude(self):
        response = self.search(q='展望台 -大阪')
        self.assertEqual(self.titles(response), ['東京タワー'])

    def test_source_filter(self):
        response = self.search(q='東京', source='custom')
        self.assertEqual(self.titles(response), ['東京タワー'])

    def test_query_error(self):
        response = self.search(q='-大阪')
        self.assertContains(response, '除外する語だけでは検索できません')

    def test_pagination(self):
        Document.objects.bulk_create(
            [Document(title=f'文書{i}', body='', title_tokens='共通', tokenizer_version='x') for i in range(25)]
        )
        first = self.search(q='共通')
        self.assertEqual(first.context['hits'], 25)
        self.assertEqual(len(first.context['results']), 20)
        self.assertContains(first, '?q=%E5%85%B1%E9%80%9A&amp;page=2')
        second = self.search(q='共通', page=2)
        self.assertEqual(len(second.context['results']), 5)

    def test_page_out_of_range(self):
        self.assertEqual(self.search(q='東京', page=99).status_code, 404)
