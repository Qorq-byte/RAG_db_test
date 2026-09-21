import subprocess
from pathlib import Path

import pytest

from ragdb.domain.errors import WebCrawlError
from ragdb.infrastructure.github.filters import normalize_github_url
from ragdb.infrastructure.github.importer import PublicGitHubImporter


def test_url_validation() -> None:
    assert normalize_github_url("https://github.com/openai/example.git") == "https://github.com/openai/example"
    with pytest.raises(WebCrawlError):
        normalize_github_url("https://github.com/openai/example/tree/main")


def test_clone_is_shallow_and_filters_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        root = Path(args[-1]); root.mkdir()
        (root / "keep.py").write_text("print(1)", encoding="utf-8")
        (root / "binary.py").write_bytes(b"\0")
        (root / "node_modules").mkdir()
        (root / "node_modules" / "skip.js").write_text("x", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr("ragdb.infrastructure.github.importer.subprocess.run", fake_run)
    root, files = PublicGitHubImporter(tmp_path / "cache", 100).clone_and_list("https://github.com/openai/example")
    assert calls[0][:4] == ["git", "clone", "--depth", "1"]
    assert root.parent == (tmp_path / "cache").resolve()
    assert [file.relative_path for file in files] == ["keep.py"]
