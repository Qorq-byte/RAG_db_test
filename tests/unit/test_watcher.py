from pathlib import Path

from ragdb.infrastructure.watcher import DebouncedPathEvents, PathEventHandler


def test_debounces_latest_event_per_path(tmp_path: Path) -> None:
    now = [0.0]
    events = DebouncedPathEvents(0.5, lambda: now[0])
    path = tmp_path / "notes.txt"
    events.add(path, "created")
    now[0] = 0.1
    events.add(path, "modified")
    now[0] = 0.59
    assert events.ready() == ()
    now[0] = 0.7
    assert events.ready() == ((path.resolve(), "modified"),)


def test_handler_maps_file_events(tmp_path: Path) -> None:
    events = DebouncedPathEvents(0, lambda: 0)
    handler = PathEventHandler(events)
    class Event:
        is_directory = False
        src_path = str(tmp_path / "note.txt")
    handler.on_created(Event())
    assert events.ready()[0][1] == "upsert"
