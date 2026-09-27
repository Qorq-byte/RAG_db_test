import importlib.util
from pathlib import Path
import sys
import tomllib


def test_frozen_launcher_keeps_relative_cli_arguments_in_callers_directory(tmp_path, monkeypatch):
    from ragdb import cli

    spec = importlib.util.spec_from_file_location("frozen_launcher", Path(__file__).parents[2] / "packaging/launcher.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))
    monkeypatch.setattr(sys, "executable", str(tmp_path / "RAGDB-CLI.exe"))
    monkeypatch.setattr(sys, "argv", ["RAGDB-CLI.exe", "backup", "create", "relative.zip"])
    observed = []
    monkeypatch.setattr(cli, "app", lambda: observed.append((Path.cwd(), list(sys.argv))))
    assert launcher.main() == 0
    assert observed[0][0] == tmp_path
    assert observed[0][1][-1] == "relative.zip"
    config = Path(observed[0][1][2])
    assert Path(tomllib.loads(config.read_text(encoding="utf-8"))["storage"]["data_dir"]).is_absolute()
