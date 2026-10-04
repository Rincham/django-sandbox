from django.test import SimpleTestCase

from search.query import ParsedQuery, QueryError, Term, compile_query, parse_query


class ParseQueryTests(SimpleTestCase):
    def test_words_are_and(self):
        expected = ParsedQuery(clauses=((Term('東京'),), (Term('タワー'),)), excludes=())
        self.assertEqual(parse_query('東京　タワー'), expected)

    def test_phrase(self):
        parsed = parse_query('"東京タワー" 夜景')
        self.assertEqual(parsed.clauses, ((Term('東京タワー', phrase=True),), (Term('夜景'),)))

    def test_exclude(self):
        parsed = parse_query('東京 -大阪 -"京都 府庁" －名古屋')
        self.assertEqual(parsed.clauses, ((Term('東京'),),))
        self.assertEqual(parsed.excludes, (Term('大阪'), Term('京都 府庁', phrase=True), Term('名古屋')))

    def test_or(self):
        parsed = parse_query('東京 OR 大阪 タワー')
        self.assertEqual(parsed.clauses, ((Term('東京'), Term('大阪')), (Term('タワー'),)))

    def test_leading_or_and_lowercase_or(self):
        self.assertEqual(parse_query('OR 東京 or').clauses, ((Term('東京'),), (Term('or'),)))

    def test_unclosed_quote_is_a_word(self):
        self.assertEqual(parse_query('"東京').clauses, ((Term('東京'),),))


class CompileQueryTests(SimpleTestCase):
    def test_description(self):
        compiled = compile_query(parse_query('東京タワー OR 都庁 "附属 病院" -大阪'))
        self.assertEqual(compiled.description, '((東京 & タワー) | 都庁) & (付属 <-> 病院) & !大阪')

    def test_highlight_terms_exclude_excluded_words(self):
        compiled = compile_query(parse_query('東京 -大阪'))
        self.assertEqual(compiled.highlight_terms, frozenset({'東京'}))

    def test_terms_without_tokens_are_ignored(self):
        self.assertEqual(compile_query(parse_query('東京 の')).description, '東京')

    def test_exclude_only(self):
        with self.assertRaisesMessage(QueryError, '除外する語だけ'):
            compile_query(parse_query('-大阪'))

    def test_no_usable_terms(self):
        with self.assertRaisesMessage(QueryError, '検索に使える語'):
            compile_query(parse_query('の 、'))
