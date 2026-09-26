import math
from types import SimpleNamespace

import pytest

from ragdb.application.evaluation import ranking_metrics, evaluate


def test_metrics_match_hand_calculated_ranking():
    metrics = ranking_metrics(["wrong", "b", "a"], {"a": 2, "b": 1}, 3)
    assert metrics["recall"] == 1
    assert metrics["mrr"] == .5
    assert metrics["ndcg"] == pytest.approx((1 / math.log2(3) + 3 / 2) / (3 + 1 / math.log2(3)))


def test_duplicate_chunks_do_not_inflate_source_metrics():
    assert ranking_metrics(["a", "a", "a"], {"a": 1, "b": 1}, 3)["recall"] == .5
    assert ranking_metrics([], {"a": 1}, 3) == {"recall": 0, "mrr": 0, "ndcg": 0}


@pytest.mark.parametrize("relevant", [{}, {"a": 0}, {"a": -1}, {"a": float("nan")}])
def test_invalid_labels_rejected(relevant):
    with pytest.raises(ValueError):
        ranking_metrics([], relevant, 3)


def test_threshold_failure_and_per_query_evidence():
    dataset = {"queries": [{"id": "q", "query": "test", "relevant": {"expected": 1}}]}
    result = evaluate(dataset, lambda *_: [SimpleNamespace(metadata={}, source_uri="wrong")])
    assert not result["passed"]
    assert result["queries"][0]["ranked_sources"] == ["wrong"]
