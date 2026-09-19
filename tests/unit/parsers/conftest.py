from pathlib import Path
from uuid import uuid4

import pytest

from ragdb.domain.enums import SourceType
from ragdb.domain.models import Source


@pytest.fixture
def make_source():
    def factory(path: Path, source_type: SourceType, title: str = "测试资料") -> Source:
        return Source(
            collection_id=uuid4(),
            source_type=source_type,
            title=title,
            uri=str(path),
            content_hash="0" * 64,
        )

    return factory
