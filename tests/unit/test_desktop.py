import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ragdb.desktop.window import MainWindow, PAGES
from ragdb.desktop.workers import BackgroundTask


APPLICATION = QApplication.instance() or QApplication([])


def test_main_window_exposes_all_workbench_pages() -> None:
    window = MainWindow()

    assert window.navigation.count() == len(PAGES)
    assert window.pages.count() == len(PAGES)
    window.navigation.setCurrentRow(3)
    assert window.pages.currentIndex() == 3
    window.close()
    APPLICATION.processEvents()


def test_collection_context_invalidates_previous_generation() -> None:
    window = MainWindow()
    window.collection_context.select("one", "集合一")
    first = window.collection_context.generation
    window.collection_context.select("two", "集合二")

    assert window.collection_context.generation == first + 1
    assert window.collection_context.collection_name == "集合二"
    window.close()
    APPLICATION.processEvents()


def test_background_task_emits_result_and_context_token() -> None:
    seen = []
    task = BackgroundTask("collection-2", lambda: 42)
    task.signals.succeeded.connect(lambda token, result: seen.append((token, result)))

    task.run()
    APPLICATION.processEvents()

    assert seen == [("collection-2", 42)]
