"""Domain-specific exceptions."""

from uuid import UUID


class RagdbError(Exception):
    """Base exception for expected application failures."""


class NotFoundError(RagdbError):
    """Requested domain object does not exist."""


class ConflictError(RagdbError):
    """Requested operation conflicts with existing state."""


class StorageError(RagdbError):
    """Persistent storage could not complete an operation."""


class IndexConfigurationChangedError(ConflictError):
    def __init__(self, collection_id: UUID) -> None:
        super().__init__(f"集合索引使用的嵌入配置已变化：{collection_id}；请先运行 ragdb reindex --collection NAME")


class ParserError(RagdbError):
    """A source could not be selected for or converted by a parser."""


class UnsupportedSourceError(ParserError):
    def __init__(self, source_type: str, uri: str) -> None:
        super().__init__(f"不支持的资料类型：{source_type}（{uri}）")
        self.source_type = source_type
        self.uri = uri


class DocumentParseError(ParserError):
    def __init__(self, uri: str, reason: str) -> None:
        super().__init__(f"资料解析失败：{uri}；{reason}")
        self.uri = uri
        self.reason = reason


class WebCrawlError(RagdbError):
    """A web resource cannot safely be crawled or converted to text."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"网页抓取失败：{url}；{reason}")
        self.url = url
        self.reason = reason


class OcrRequiredError(ParserError):
    """The PDF has too little extractable text and should be retried with OCR."""

    def __init__(self, uri: str, page_numbers: tuple[int, ...]) -> None:
        pages = "、".join(str(page) for page in page_numbers)
        super().__init__(f"PDF 文本层不足，建议启用 OCR：{uri}（页码：{pages}）")
        self.uri = uri
        self.page_numbers = page_numbers


class CollectionNotFoundError(NotFoundError):
    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(f"知识集合不存在：{identifier}")
        self.identifier = identifier


class CollectionAlreadyExistsError(ConflictError):
    def __init__(self, name: str) -> None:
        super().__init__(f"知识集合已存在：{name}")
        self.name = name


class SourceNotFoundError(NotFoundError):
    def __init__(self, source_id: UUID) -> None:
        super().__init__(f"资料不存在：{source_id}")
        self.source_id = source_id


class SourceAlreadyExistsError(ConflictError):
    def __init__(self, uri: str) -> None:
        super().__init__(f"资料已存在：{uri}")
        self.uri = uri


class TaskNotFoundError(NotFoundError):
    def __init__(self, task_id: UUID) -> None:
        super().__init__(f"导入任务不存在：{task_id}")
        self.task_id = task_id
