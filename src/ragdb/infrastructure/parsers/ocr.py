"""Local Tesseract adapter for optional scanned-PDF recognition."""

from pathlib import Path
import subprocess
import tempfile

import pymupdf

from ragdb.domain.errors import DocumentParseError


class TesseractOcr:
    def __init__(self, executable_path: Path, languages: str, dpi: int) -> None:
        self.executable_path, self.languages, self.dpi = executable_path, languages, dpi

    def recognize_page(self, page: pymupdf.Page, uri: str) -> str:
        if not self.executable_path.is_file():
            raise DocumentParseError(uri, f"未找到 Tesseract：{self.executable_path}")
        scale = self.dpi / 72
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(image.name)
            completed = subprocess.run(
                [str(self.executable_path), image.name, "stdout", "-l", self.languages],
                capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
            )
        if completed.returncode:
            raise DocumentParseError(uri, f"Tesseract 识别失败：{completed.stderr.strip()}")
        return completed.stdout.strip()
