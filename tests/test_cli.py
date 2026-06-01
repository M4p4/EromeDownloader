from importlib.metadata import entry_points

import pytest

import dump


def test_main_is_callable():
    assert callable(dump.main)


def test_main_requires_url_or_file(monkeypatch):
    monkeypatch.setattr("sys.argv", ["eromedump"])
    with pytest.raises(SystemExit) as exc_info:
        dump.main()
    assert exc_info.value.code != 0


def test_eromedump_entry_point_registered():
    scripts = entry_points(group="console_scripts")
    matches = [ep for ep in scripts if ep.name == "eromedump"]
    if not matches:
        pytest.skip("package not installed (run `pip install -e .`)")
    assert matches[0].value == "dump:main"
