"""Persist one task per import action, sharing progress with nested item imports."""

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Generic, TypeVar

from ragdb.domain.enums import TaskItemStatus, TaskStatus
from ragdb.domain.errors import StorageError
from ragdb.domain.models import Collection, IngestionTask, OperationLog, utc_now
from ragdb.domain.ports import TaskRepository


T = TypeVar("T")
COUNTERS = {
    TaskItemStatus.CREATED: "succeeded",
    TaskItemStatus.UPDATED: "updated",
    TaskItemStatus.SKIPPED: "skipped",
    TaskItemStatus.FAILED: "failed",
}


@dataclass
class _ImportState:
    task: IngestionTask
    kind: str
    last_error: Exception | None = None


@dataclass(frozen=True)
class RecordedImport(Generic[T]):
    result: T
    task: IngestionTask


class ImportRecorder:
    def __init__(self, tasks: TaskRepository, logs=None) -> None:
        self.tasks = tasks
        self.logs = logs
        # Runtime services share this recorder; concurrent workers do not share a task.
        self._active: ContextVar[_ImportState | None] = ContextVar("import_task", default=None)

    def run(
        self, collection: Collection, kind: str, operation: Callable[[], T], *, item: bool = False,
    ) -> RecordedImport[T]:
        state = self._active.get()
        owner = state is None or state.task.collection_id != collection.id
        if owner:
            state = _ImportState(self.tasks.create(IngestionTask(
                collection_id=collection.id, status=TaskStatus.RUNNING,
            )), kind)
        token = self._active.set(state)
        try:
            try:
                if owner:
                    self._log(state, "import_started")
                result = operation()
                if item:
                    self._count(state, result.status)
            except Exception as error:
                # A nested item and its enclosing batch see the same exception.
                if item or state.last_error is not error:
                    self._count(state, TaskItemStatus.FAILED)
                    state.last_error = error
                raise
            finally:
                if owner:
                    task = state.task
                    status = TaskStatus.COMPLETED
                    if task.failed:
                        status = TaskStatus.PARTIAL if task.succeeded + task.updated + task.skipped else TaskStatus.FAILED
                    state.task = self.tasks.update(task.model_copy(update={
                        "status": status, "finished_at": utc_now(),
                    }))
                    self._log(state, "import_finished")
            return RecordedImport(result, state.task)
        finally:
            self._active.reset(token)

    def _count(self, state: _ImportState, status: TaskItemStatus) -> None:
        field = COUNTERS[status]
        state.task = self.tasks.update(state.task.model_copy(update={
            field: getattr(state.task, field) + 1,
        }))

    def _log(self, state: _ImportState, action: str) -> None:
        if self.logs is None:
            return
        task = state.task
        details = {
            "task_id": str(task.id), "kind": state.kind, "status": task.status.value,
            "succeeded": task.succeeded, "updated": task.updated,
            "skipped": task.skipped, "failed": task.failed,
        }
        # Exception messages can contain credentials, document text or signed URLs.
        if state.last_error is not None:
            details["error_type"] = type(state.last_error).__name__
        try:
            self.logs.record(OperationLog(collection_id=task.collection_id, action=action, details=details))
        except Exception as error:
            raise StorageError("任务状态已保存，但操作日志写入失败，请在“最近任务”查看处理结果。") from error


def recorded_item(kind: str):
    def decorate(method):
        @wraps(method)
        def wrapped(self, collection, *args, **kwargs):
            return self.import_recorder.run(
                collection, kind, lambda: method(self, collection, *args, **kwargs), item=True,
            ).result
        return wrapped
    return decorate
