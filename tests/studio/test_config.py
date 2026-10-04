import json
from pathlib import Path

import pytest

from sound_effects_studio.config import Paths, load_options

pytestmark = pytest.mark.studio


def test_derived_directories(paths: Paths) -> None:
    assert paths.publish_dir == paths.www_dir / "sound-effects"
    assert paths.originals_dir == paths.data_dir / "originals"
    assert paths.previews_dir == paths.data_dir / "previews"
    assert paths.uploads_dir == paths.data_dir / "uploads"
    assert paths.database_path == paths.data_dir / "studio.db"


def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SOUND_EFFECTS_DATA", "SOUND_EFFECTS_WWW", "SOUND_EFFECTS_DEV"):
        monkeypatch.delenv(name, raising=False)
    paths = Paths.from_env()
    assert paths.data_dir == Path("/data")
    assert paths.www_dir == Path("/homeassistant/www")
    assert paths.import_roots == {
        "config/www": Path("/homeassistant/www"),
        "media": Path("/media"),
        "share": Path("/share"),
    }
    assert paths.static_dir.parts[-3:] == ("sound_effects_studio", "static", "ui")
    assert paths.dev_mode is False


def test_from_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOUND_EFFECTS_DATA", str(tmp_path / "d"))
    monkeypatch.setenv("SOUND_EFFECTS_WWW", str(tmp_path / "w"))
    monkeypatch.setenv("SOUND_EFFECTS_DEV", "1")
    paths = Paths.from_env()
    assert paths.data_dir == tmp_path / "d"
    assert paths.www_dir == tmp_path / "w"
    assert paths.import_roots["config/www"] == tmp_path / "w"
    assert paths.dev_mode is True


def test_load_options(tmp_path: Path) -> None:
    options = tmp_path / "options.json"
    assert load_options(options) == {}
    options.write_text("not json", encoding="utf-8")
    assert load_options(options) == {}
    options.write_text("[1, 2]", encoding="utf-8")
    assert load_options(options) == {}
    options.write_text(json.dumps({"log_level": "debug"}), encoding="utf-8")
    assert load_options(options) == {"log_level": "debug"}
