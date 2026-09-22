"""Small deterministic debounce layer used by the foreground watcher."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class DebouncedPathEvents:
    def __init__(self, delay_seconds: float, clock: Callable[[], float]) -> None:
        self.delay_seconds, self.clock = delay_seconds, clock
        self._events: dict[Path, str] = {}
        self._times: dict[Path, float] = {}

    def add(self, path: Path, event: str) -> None:
        path = path.resolve()
        self._events[path], self._times[path] = event, self.clock()

    def ready(self) -> tuple[tuple[Path, str], ...]:
        now = self.clock()
        paths = sorted((path for path, at in self._times.items() if now - at >= self.delay_seconds), key=str)
        result = tuple((path, self._events.pop(path)) for path in paths)
        for path in paths:
            self._times.pop(path)
        return result


class PathEventHandler(FileSystemEventHandler):
    """Translate Watchdog file events into deterministic debounced operations."""

    def __init__(self, events: DebouncedPathEvents) -> None:
        self.events = events

    def on_created(self, event) -> None:
        if not event.is_directory:
            self.events.add(Path(event.src_path), "upsert")

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self.events.add(Path(event.src_path), "upsert")

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            self.events.add(Path(event.src_path), "delete")


def start_observer(path: Path, events: DebouncedPathEvents) -> Observer:
    observer = Observer()
    observer.schedule(PathEventHandler(events), str(path), recursive=True)
    observer.start()
    return observer
