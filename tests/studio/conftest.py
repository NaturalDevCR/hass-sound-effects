"""Fixtures for Sound Effects Studio tests."""

from __future__ import annotations

import subprocess
import warnings
from collections.abc import Callable
from pathlib import Path

import pytest
from sound_effects_studio.config import Paths
from starlette.exceptions import StarletteDeprecationWarning

# Starlette 1.x prefers httpx2 for its TestClient and warns once, at first import, when only
# httpx is installed. Import it here with that notice silenced so the API tests run warning-free
# until httpx2 joins the dev dependency group.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", StarletteDeprecationWarning)
    import starlette.testclient  # noqa: F401


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    root = tmp_path / "root"
    p = Paths(
        data_dir=root / "data",
        www_dir=root / "homeassistant" / "www",
        import_roots={
            "config/www": root / "homeassistant" / "www",
            "media": root / "media",
            "share": root / "share",
        },
        static_dir=root / "static",
        dev_mode=False,
    )
    for directory in (p.data_dir, p.import_roots["media"], p.import_roots["share"]):
        directory.mkdir(parents=True, exist_ok=True)
    p.www_dir.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def make_tone(tmp_path: Path) -> Callable[..., Path]:
    """Generate a sine tone file with ffmpeg (lavfi)."""

    def _make(
        name: str = "tone.wav",
        seconds: float = 3.0,
        frequency: int = 440,
        volume_db: float = -20.0,
        channels: int = 2,
    ) -> Path:
        out = tmp_path / "fixtures" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        layout = "stereo" if channels == 2 else "mono"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:duration={seconds}:sample_rate=44100",
                "-af",
                f"volume={volume_db}dB,aformat=channel_layouts={layout}",
                *(["-c:a", "libmp3lame", "-q:a", "4"] if name.endswith(".mp3") else []),
                str(out),
            ],
            check=True,
        )
        return out

    return _make
