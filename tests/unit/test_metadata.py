import pytest

from ragdb.application.metadata import build_ingestion_metadata, build_search_filters


def test_metadata_normalizes_and_deduplicates_tags() -> None:
    assert build_ingestion_metadata(
        tags=(" Python ", "python", "资料"), course=" 算法 ", author=" 张三 ", source_date="2026-09-20"
    ) == {"tags": ["python", "资料"], "course": "算法", "author": "张三", "date": "2026-09-20"}


@pytest.mark.parametrize("value", ["", "2026/09/20", "2026-02-30"])
def test_metadata_rejects_invalid_date(value: str) -> None:
    with pytest.raises(ValueError):
        build_ingestion_metadata(source_date=value)


def test_search_filters_normalize_tag_intersection_and_date_range() -> None:
    assert build_search_filters(tags=("RAG", "rag"), date_from="2026-01-01", date_to="2026-12-31") == {
        "tags": ["rag"], "date_from": "2026-01-01", "date_to": "2026-12-31"
    }


def test_search_filters_reject_reversed_dates() -> None:
    with pytest.raises(ValueError, match="开始日期"):
        build_search_filters(date_from="2026-02-01", date_to="2026-01-01")
