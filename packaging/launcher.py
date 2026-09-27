"""Frozen GUI/CLI dispatch; child reader mode must not initialize user storage."""

import multiprocessing
import json
import os
from pathlib import Path
import sys


def main():
    multiprocessing.freeze_support()
    if "--index-reader" in sys.argv:
        from ragdb.infrastructure.vectorstore.query import reader_main
        reader_main()
        return 0
    if "--self-test" in sys.argv:
        from ragdb.packaging_check import run
        return run()
    # Resolve explicitly supplied config paths before selecting the writable cwd.
    if "--config" in sys.argv:
        index = sys.argv.index("--config") + 1
        if index < len(sys.argv):
            sys.argv[index] = str(Path(sys.argv[index]).resolve())
    location = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RAGDB"
    location.mkdir(parents=True, exist_ok=True)
    config = location / "config.toml"
    if not config.exists():
        try:
            with config.open("x", encoding="utf-8") as stream:
                stream.write('[storage]\ndata_dir = ' + json.dumps(str(location / ".data")) + '\n\n[embedding]\nprovider = "ollama"\nollama_model = "embeddinggemma:latest"\n\n[chat]\nprovider = "local"\n')
        except FileExistsError:
            pass
    if "--config" not in sys.argv:
        sys.argv[1:1] = ["--config", str(config)]
    if Path(sys.executable).stem.lower().endswith("-cli"):
        from ragdb.cli import app
        app()
        return 0
    from ragdb.desktop.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
