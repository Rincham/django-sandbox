from django.test import SimpleTestCase

from search.highlight import ELLIPSIS, highlight, snippet


def marked(segments):
    return [part for part, matched in segments if matched]


class HighlightTests(SimpleTestCase):
    def test_marks_normalized_matches_in_original_text(self):
        segments = highlight('大学の附属病院', frozenset({'付属'}))
        self.assertEqual(segments, [('大学の', False), ('附属', True), ('病院', False)])

    def test_marks_subtokens(self):
        self.assertEqual(marked(highlight('東京都庁の展望室', frozenset({'都庁'}))), ['都庁'])

    def test_merges_adjacent_and_overlapping_matches(self):
        self.assertEqual(marked(highlight('東京都庁', frozenset({'東京', '都庁', '東京都庁'}))), ['東京都庁'])

    def test_no_terms(self):
        self.assertEqual(highlight('東京', frozenset()), [('東京', False)])

    def test_empty_text(self):
        self.assertEqual(highlight('', frozenset({'東京'})), [])


class SnippetTests(SimpleTestCase):
    def test_short_text_is_not_cut(self):
        self.assertEqual(''.join(part for part, _ in snippet('東京の展望室', frozenset({'東京'}))), '東京の展望室')

    def test_cuts_around_first_match(self):
        text = 'あ' * 100 + '東京' + 'い' * 100
        segments = snippet(text, frozenset({'東京'}), width=50, before=10)
        self.assertEqual(segments[0], (ELLIPSIS, False))
        self.assertEqual(segments[-1], (ELLIPSIS, False))
        self.assertEqual(marked(segments), ['東京'])
        self.assertEqual(sum(len(part) for part, _ in segments[1:-1]), 50)

    def test_starts_from_beginning_without_match(self):
        segments = snippet('い' * 100, frozenset({'東京'}), width=50)
        self.assertEqual(segments, [('い' * 50, False), (ELLIPSIS, False)])
