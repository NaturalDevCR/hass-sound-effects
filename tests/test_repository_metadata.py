import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_versions_agree() -> None:
    manifest = json.loads((ROOT / "custom_components/sound_effects/manifest.json").read_text())
    app_config = yaml.safe_load((ROOT / "app/config.yaml").read_text())
    namespace: dict[str, str] = {}
    exec((ROOT / "app/src/sound_effects_studio/__init__.py").read_text(), namespace)
    assert manifest["version"] == app_config["version"] == namespace["__version__"]


def test_hacs_metadata() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] == "Sound Effects"
    assert hacs["content_in_root"] is False


def test_app_manifest_core_fields() -> None:
    app_config = yaml.safe_load((ROOT / "app/config.yaml").read_text())
    assert app_config["slug"] == "sound_effects_studio"
    assert app_config["ingress_port"] == 8099
    assert "homeassistant_config:rw" in app_config["map"]
    assert app_config["discovery"] == ["sound_effects"]
    assert "image" not in app_config
