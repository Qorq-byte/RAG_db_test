import pytest

from ragdb.application.metadata import build_ingestion_metadata


def test_metadata_normalizes_and_deduplicates_tags() -> None:
    assert build_ingestion_metadata(
        tags=(" Python ", "python", "资料"), course=" 算法 ", author=" 张三 ", source_date="2026-09-20"
    ) == {"tags": ["python", "资料"], "course": "算法", "author": "张三", "date": "2026-09-20"}


@pytest.mark.parametrize("value", ["", "2026/09/20", "2026-02-30"])
def test_metadata_rejects_invalid_date(value: str) -> None:
    with pytest.raises(ValueError):
        build_ingestion_metadata(source_date=value)
