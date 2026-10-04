"""Filesystem layout and add-on options."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

DEFAULT_DATA_DIR = "/data"
DEFAULT_WWW_DIR = "/homeassistant/www"
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Paths:
    """Where the Studio keeps its data, publishes files and reads imports from."""

    data_dir: Path
    www_dir: Path
    import_roots: dict[str, Path]
    static_dir: Path
    dev_mode: bool

    @property
    def publish_dir(self) -> Path:
        return self.www_dir / "sound-effects"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def previews_dir(self) -> Path:
        return self.data_dir / "previews"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.db"

    @classmethod
    def from_env(cls) -> Paths:
        """Build the paths from the container defaults and the SOUND_EFFECTS_* overrides."""
        www_dir = Path(os.environ.get("SOUND_EFFECTS_WWW", DEFAULT_WWW_DIR))
        return cls(
            data_dir=Path(os.environ.get("SOUND_EFFECTS_DATA", DEFAULT_DATA_DIR)),
            www_dir=www_dir,
            import_roots={
                "config/www": www_dir,
                "media": Path("/media"),
                "share": Path("/share"),
            },
            static_dir=Path(__file__).resolve().parent / "static" / "ui",
            dev_mode=os.environ.get("SOUND_EFFECTS_DEV", "").strip().lower() in _TRUTHY,
        )


def load_options(path: Path) -> dict[str, object]:
    """Read the Supervisor options file; a missing or malformed file yields no options."""
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    options: dict[str, object] = {}
    if isinstance(loaded, dict):
        for key, value in cast("dict[object, object]", loaded).items():
            options[str(key)] = value
    return options
