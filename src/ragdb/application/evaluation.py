"""Source-level ranked retrieval metrics and reproducible query reports."""

import hashlib
import json
import math
from pathlib import Path
import statistics
import time


def ranking_metrics(ranked: list[str], relevant: dict[str, float], k: int) -> dict:
    if k < 1 or not relevant or any(not math.isfinite(v) or v <= 0 for v in relevant.values()):
        raise ValueError("K必须为正，且每条查询必须有正数相关性标注。")
    # Multiple chunks from one source must not inflate source-level relevance.
    unique = list(dict.fromkeys(ranked))[:k]
    gains = [relevant.get(key, 0.0) for key in unique]
    ideal = sorted(relevant.values(), reverse=True)[:k]
    dcg = sum((2 ** gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(gains))
    idcg = sum((2 ** gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(ideal))
    return {"recall": sum(key in relevant for key in unique) / len(relevant),
            "mrr": next((1 / (i + 1) for i, gain in enumerate(gains) if gain > 0), 0.0),
            "ndcg": dcg / idcg}


def evaluate(dataset: dict, search, *, k=3, min_recall=0.8, min_mrr=0.75) -> dict:
    queries = dataset.get("queries", [])
    if not queries or len({item["id"] for item in queries}) != len(queries):
        raise ValueError("评估集需要非空查询和唯一查询ID。")
    results = []
    for query in queries:
        if not query["query"].strip():
            raise ValueError("查询不能为空。")
        relevant = {key: float(value) for key, value in query["relevant"].items()}
        ranking_metrics([], relevant, k)  # Validate before invoking a model.
        started = time.perf_counter()
        hits = search(query["query"], query.get("filters"))
        elapsed = (time.perf_counter() - started) * 1000
        ranked = [str(hit.metadata.get("evaluation_id", hit.source_uri)) for hit in hits]
        results.append({"id": query["id"], "query": query["query"],
            "ranked_sources": list(dict.fromkeys(ranked))[:k], "relevant": relevant,
            "latency_ms": round(elapsed, 3), **ranking_metrics(ranked, relevant, k)})
    means = {name: statistics.mean(row[name] for row in results) for name in ("recall", "mrr", "ndcg")}
    latencies = sorted(row["latency_ms"] for row in results)
    digest = hashlib.sha256(json.dumps(dataset, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"dataset": dataset.get("name", "custom"), "dataset_sha256": digest,
        "unit": "source (deduplicated in returned candidate order)", "k": k,
        "query_count": len(results), "metrics": means,
        "latency_ms": {"mean": statistics.mean(latencies), "p95": latencies[math.ceil(.95 * len(latencies)) - 1]},
        "thresholds": {"recall": min_recall, "mrr": min_mrr},
        "passed": means["recall"] >= min_recall and means["mrr"] >= min_mrr,
        "queries": results}


class OfflineEmbedding:
    """Character bigram hashing for repeatable pipeline smoke tests, not model quality."""
    provider_name = "local"
    model_name = "offline-bigram-256"

    def embed_texts(self, texts):
        result = []
        for text in texts:
            normalized = "".join(text.lower().split())
            vector = [0.] * 256
            for index in range(max(0, len(normalized) - 1)):
                digest = hashlib.sha256(normalized[index:index + 2].encode()).digest()
                vector[int.from_bytes(digest[:2], "little") % 256] += 1
            norm = math.sqrt(sum(value * value for value in vector)) or 1
            result.append([value / norm for value in vector])
        return result


def benchmark(dataset, settings, directory: Path, *, offline=False, k=3, min_recall=.8, min_mrr=.75):
    from ragdb.application.ingestion import LocalIngestionService
    from ragdb.application.search import SearchService
    from ragdb.domain.models import Collection
    from ragdb.infrastructure.chunking import StructuredChunker
    from ragdb.infrastructure.database import (SQLiteDatabase, SQLiteCollectionRepository,
        SQLiteSourceRepository, SQLiteChunkRepository, SQLiteTaskRepository, SQLiteKeywordIndex)
    from ragdb.infrastructure.embeddings import create_embedding_provider
    from ragdb.infrastructure.parsers import ParserRegistry
    from ragdb.infrastructure.vectorstore import ChromaVectorStore

    documents = dataset.get("documents", [])
    identifiers = {item["id"] for item in documents}
    if not documents or len(identifiers) != len(documents):
        raise ValueError("基准评估需要唯一的非空资料集。")
    if any(not set(item["relevant"]) <= identifiers for item in dataset["queries"]):
        raise ValueError("查询标注引用了不存在的资料。")
    provider = OfflineEmbedding() if offline else create_embedding_provider(settings.embedding)
    database = SQLiteDatabase(directory / "ragdb.sqlite3")
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name="isolated evaluation"))
    sources = SQLiteSourceRepository(database)
    keyword = SQLiteKeywordIndex(database)
    with ChromaVectorStore(directory / "chroma", operation_scoped=True) as vectors:
        ingestion = LocalIngestionService(sources, SQLiteChunkRepository(database), SQLiteTaskRepository(database),
            ParserRegistry(), StructuredChunker(settings.chunking), keyword, provider, vectors)
        for document in documents:
            ingestion.ingest_text(collection, document["text"], title=document["id"],
                                  metadata={"evaluation_id": document["id"], **document.get("metadata", {})})
        search = SearchService(provider, vectors, keyword, sources, result_top_k=max(k, settings.retrieval.result_top_k),
            vector_top_k=settings.retrieval.vector_top_k, keyword_top_k=settings.retrieval.keyword_top_k,
            rrf_k=settings.retrieval.rrf_k)
        report = evaluate(dataset, lambda query, filters: search.search(collection.id, query, filters),
                          k=k, min_recall=min_recall, min_mrr=min_mrr)
    report["embedding"] = {"provider": provider.provider_name, "model": provider.model_name}
    report["scope"] = "offline pipeline smoke test" if offline else "fixed corpus model retrieval benchmark"
    return report
