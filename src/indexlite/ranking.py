import heapq
from collections.abc import Iterable
from math import log1p

from .models import Ranking


def bm25(tf: int, df: int, length: int, count: int, average: float, ranking: Ranking) -> float:
    if not tf or not count or not average:
        return 0.0
    idf = log1p((count - df + 0.5) / (df + 0.5))
    norm = ranking.k1 * (1 - ranking.b + ranking.b * length / average)
    return idf * tf * (ranking.k1 + 1) / (tf + norm)


def top_k(scores: Iterable[tuple[int, float]], k: int) -> list[tuple[int, float]]:
    # The root is the worst retained hit: lower score, then larger document ID.
    heap: list[tuple[float, int]] = []
    for document_id, score in scores:
        item = (score, -document_id)
        if len(heap) < k:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    return [(-negative_id, score) for score, negative_id in sorted(heap, reverse=True)]
