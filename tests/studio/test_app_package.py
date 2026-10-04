"""Supervisor App packaging metadata and assets."""

from __future__ import annotations

import struct
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"


def test_dockerfile_uses_local_context_and_pinned_runtime() -> None:
    dockerfile = (APP / "Dockerfile").read_text()
    assert "ghcr.io/home-assistant/${BUILD_ARCH}-base-python:3.13-alpine3.22" in dockerfile
    assert "COPY src " in dockerfile
    assert "COPY rootfs /" in dockerfile
    assert '"fastapi==0.142.2"' in dockerfile
    assert '"starlette==1.7.0"' in dockerfile
    assert '"uvicorn[standard]==0.54.0"' in dockerfile
    assert '"httpx==0.28.1"' in dockerfile
    assert '"pydantic==2.12.2"' in dockerfile
    assert "apk add --no-cache ffmpeg" in dockerfile
    assert "--no-cache-dir" in dockerfile
    assert "ui/package.json" in dockerfile
    assert "ui/package-lock.json" in dockerfile
    assert "COPY ui/" in dockerfile
    if (APP / "ui").exists():
        assert (APP / "ui/package.json").is_file()
        assert (APP / "ui/package-lock.json").is_file()


def test_entry_script_is_tracked_executable() -> None:
    entry = APP / "rootfs/usr/bin/sound-effects-studio"
    assert entry.is_file()
    records = subprocess.check_output(
        ["git", "ls-files", "-s", "--", "app/rootfs/usr/bin/sound-effects-studio"],
        cwd=ROOT,
        text=True,
    )
    assert any(line.startswith("100755 ") for line in records.splitlines())
    assert "exec python3 -m sound_effects_studio.main" in entry.read_text()


def test_translations_define_log_level() -> None:
    for locale in ("en", "es"):
        document = yaml.safe_load((APP / "translations" / f"{locale}.yaml").read_text())
        option = document["configuration"]["log_level"]
        assert option["name"]
        assert option["description"]


def _png_dimensions(path: Path) -> tuple[int, int]:
    contents = path.read_bytes()
    assert contents[:8] == b"\x89PNG\r\n\x1a\n"
    assert contents[12:16] == b"IHDR"
    return struct.unpack(">II", contents[16:24])


def test_app_icons_are_pngs_with_supervisor_dimensions() -> None:
    assert _png_dimensions(APP / "icon.png") == (128, 128)
    assert _png_dimensions(APP / "logo.png") == (250, 100)
