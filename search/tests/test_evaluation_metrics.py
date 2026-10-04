from django.test import SimpleTestCase

from search.evaluation.metrics import QueryRecord, percentile, summarize


def record(relevant, ranked, hits=None, elapsed_ms=1.0):
    return QueryRecord(
        query_id=0,
        text='',
        description='',
        relevant_ids=frozenset(relevant),
        document_ids=tuple(ranked),
        hits=len(ranked) if hits is None else hits,
        elapsed_ms=elapsed_ms,
    )


class QueryRecordTests(SimpleTestCase):
    def test_first_relevant_rank(self):
        self.assertEqual(record({3}, [1, 2, 3]).first_relevant_rank(10), 3)
        self.assertIsNone(record({3}, [1, 2, 3]).first_relevant_rank(2))
        self.assertIsNone(record({9}, [1, 2, 3]).first_relevant_rank(10))

    def test_recall_counts_each_relevant_document(self):
        self.assertEqual(record({1, 9}, [1, 2, 3]).recall(10), 0.5)
        self.assertEqual(record({1, 3}, [1, 2, 3]).recall(2), 0.5)

    def test_reciprocal_rank(self):
        self.assertEqual(record({2}, [1, 2]).reciprocal_rank(10), 0.5)
        self.assertEqual(record({2}, []).reciprocal_rank(10), 0.0)


class SummarizeTests(SimpleTestCase):
    def test_summary(self):
        records = [
            record({1}, [1], elapsed_ms=2.0),
            record({1}, [2, 1], elapsed_ms=4.0),
            record({1}, [], hits=0, elapsed_ms=0.0),
            record({1}, [2, 3], hits=100, elapsed_ms=10.0),
        ]
        summary = summarize(records, k=10)
        self.assertEqual(summary.queries, 4)
        self.assertEqual(summary.recall, 0.5)
        self.assertEqual(summary.mrr, (1 + 0.5) / 4)
        self.assertEqual(summary.zero_hit_rate, 0.25)
        self.assertEqual(summary.hits_max, 100)
        # 応答時間は、ヒットしたクエリだけで計算する
        self.assertEqual(summary.latency_median_ms, 4.0)


class PercentileTests(SimpleTestCase):
    def test_nearest_rank(self):
        values = list(range(1, 101))
        self.assertEqual(percentile(values, 95), 95)
        self.assertEqual(percentile(values, 50), 50)
        self.assertEqual(percentile([7], 95), 7)
