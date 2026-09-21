import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ragdb.application.ingestion import IGNORED_DIRECTORIES
from ragdb.domain.errors import WebCrawlError
from ragdb.infrastructure.github.filters import is_importable_file, normalize_github_url


@dataclass(frozen=True)
class RepositoryFile:
    path: Path
    relative_path: str
    repository_url: str


class PublicGitHubImporter:
    def __init__(self, cache_root: Path, maximum: int = 10 * 1024 * 1024) -> None:
        self.cache_root, self.maximum = cache_root.resolve(), maximum

    def clone_and_list(self, url: str) -> tuple[Path, tuple[RepositoryFile, ...]]:
        repository_url = normalize_github_url(url)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        root = (self.cache_root / uuid4().hex).resolve()
        try:
            subprocess.run(["git", "clone", "--depth", "1", repository_url, str(root)], check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            shutil.rmtree(root, ignore_errors=True)
            raise WebCrawlError(repository_url, "浅克隆公开仓库失败") from exc
        files = []
        for path in root.rglob("*"):
            if any(part in IGNORED_DIRECTORIES or part.startswith(".") for part in path.relative_to(root).parts):
                continue
            if is_importable_file(path, self.maximum):
                files.append(RepositoryFile(path, path.relative_to(root).as_posix(), repository_url))
        return root, tuple(sorted(files, key=lambda item: item.relative_path))
