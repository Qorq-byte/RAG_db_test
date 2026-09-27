"""Readable import status shared by collection feedback and task history."""

from ragdb.application.ingestion import DirectoryIngestionResult
from ragdb.domain.enums import TaskItemStatus


TASK_LABELS = {
    "pending": "等待处理", "running": "处理中", "completed": "已完成",
    "partial": "部分失败", "failed": "失败", "cancelled": "已取消",
}
IMPORT_LABELS = {
    "file": "文件导入", "directory": "目录导入", "text": "文本导入",
    "web": "网页导入", "repository": "GitHub 仓库导入",
}


def format_counts(counts) -> str:
    return " / ".join(f"{label} {counts.get(field, 0)}" for field, label in (
        ("succeeded", "新增"), ("updated", "更新"), ("skipped", "跳过"), ("failed", "失败"),
    ))


def import_feedback(result) -> tuple[str, str]:
    if isinstance(result, DirectoryIngestionResult):
        items = result.items
    elif isinstance(result, list):
        items = result
    else:
        items = (result,)
    counts = {
        field: sum(item.status == status for item in items)
        for field, status in (
            ("succeeded", TaskItemStatus.CREATED), ("updated", TaskItemStatus.UPDATED),
            ("skipped", TaskItemStatus.SKIPPED), ("failed", TaskItemStatus.FAILED),
        )
    }
    if not items:
        return "未发现可导入资料", "warning"
    if counts["failed"]:
        label, severity = ("导入失败", "failure") if counts["failed"] == len(items) else ("部分导入失败", "warning")
    elif counts["skipped"] == len(items):
        label, severity = "已跳过（内容未变化或超出限制）", "warning"
    else:
        label, severity = "导入完成", "success"
    return f"{label}：{format_counts(counts)}", severity
