from pathlib import Path

from ui.server import UiSettings


def test_explicit_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path / "env"))
    assert UiSettings.resolve(data_root=tmp_path / "explicit").data_root == tmp_path / "explicit"


def test_env_used_without_arg(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path / "env"))
    assert UiSettings.resolve().data_root == tmp_path / "env"


def test_dev_mode_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("SCOUTMB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert UiSettings.resolve(dev_mode=True).data_root == tmp_path


def test_no_env_no_dev_uses_os_location_not_cwd(tmp_path, monkeypatch):
    """A misconfigured production launch must land in the OS data dir, never cwd."""
    monkeypatch.delenv("SCOUTMB_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    root = UiSettings.resolve(dev_mode=False).data_root
    assert root != tmp_path and "ScoutingMeritBadges" in str(root)


def test_derived_paths_hang_off_root(tmp_path):
    s = UiSettings.resolve(data_root=tmp_path)
    assert s.scouts_csv == tmp_path / "scouts.csv"
    assert s.runs_dir == tmp_path / "runs"


def test_root_independent_of_module_location(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUTMB_DATA_DIR", str(tmp_path))
    s = UiSettings.resolve()
    assert Path(__file__).parent not in s.data_root.parents
