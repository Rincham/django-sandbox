"""評価指標の計算。2 つの検索方式で共有する（指標の計算が方式ごとに異なると、結果を比べられないため）。"""

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class QueryRecord:
    """1 つの評価用クエリに対する検索結果。"""

    query_id: int
    text: str
    description: str
    relevant_ids: frozenset[int]
    document_ids: tuple[int, ...]
    hits: int
    elapsed_ms: float

    def first_relevant_rank(self, k: int) -> int | None:
        """上位 k 件のうち、最初の正解の順位（1 始まり）。"""
        for rank, document_id in enumerate(self.document_ids[:k], start=1):
            if document_id in self.relevant_ids:
                return rank
        return None

    def recall(self, k: int) -> float:
        """正解の文書のうち、上位 k 件に入った割合。"""
        return len(self.relevant_ids & set(self.document_ids[:k])) / len(self.relevant_ids)

    def reciprocal_rank(self, k: int) -> float:
        rank = self.first_relevant_rank(k)
        return 0.0 if rank is None else 1 / rank


@dataclass(frozen=True)
class Summary:
    queries: int
    recall: float
    mrr: float
    zero_hit_rate: float
    hits_median: float
    hits_p95: float
    hits_max: int
    latency_median_ms: float
    latency_p95_ms: float


def summarize(records: list[QueryRecord], k: int) -> Summary:
    hits = [record.hits for record in records]
    latencies = [record.elapsed_ms for record in records if record.hits]
    return Summary(
        queries=len(records),
        recall=statistics.fmean(record.recall(k) for record in records),
        mrr=statistics.fmean(record.reciprocal_rank(k) for record in records),
        zero_hit_rate=sum(1 for h in hits if h == 0) / len(records),
        hits_median=statistics.median(hits),
        hits_p95=percentile(hits, 95),
        hits_max=max(hits),
        latency_median_ms=statistics.median(latencies) if latencies else 0.0,
        latency_p95_ms=percentile(latencies, 95) if latencies else 0.0,
    )


def percentile(values, p: float):
    """最近順位法によるパーセンタイル。"""
    ordered = sorted(values)
    return ordered[max(math.ceil(p / 100 * len(ordered)), 1) - 1]
