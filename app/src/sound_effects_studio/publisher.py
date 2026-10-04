"""Atomic publication and retention of audio served by Home Assistant."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from .config import Paths


@dataclass
class WwwStatus:
    exists: bool
    created_by_app: bool
    served: bool | None = None


class Publisher:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def ensure_dirs(self) -> WwwStatus:
        created = not self.paths.www_dir.exists()
        for directory in (
            self.paths.www_dir,
            self.paths.publish_dir,
            self.paths.originals_dir,
            self.paths.previews_dir,
            self.paths.uploads_dir,
            self.paths.publish_dir / "_audition",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return WwwStatus(exists=True, created_by_app=created)

    def temp_path(self, sound_id: str) -> Path:
        return self.paths.publish_dir / f".tmp-{sound_id}-{secrets.token_hex(4)}.mp3"

    def commit(self, tmp: Path, sound_id: str, revision: int) -> str:
        """Expose a complete render with a single rename on the publish filesystem."""
        filename = f"{sound_id}-r{revision}.mp3"
        fd = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.published_path(filename))
        return filename

    def published_path(self, filename: str) -> Path:
        return self.paths.publish_dir / filename

    def cleanup(
        self,
        sound_id: str,
        keep: set[int],
        older_than: timedelta = timedelta(hours=24),
    ) -> list[str]:
        cutoff = time.time() - older_than.total_seconds()
        pattern = re.compile(rf"{re.escape(sound_id)}-r([0-9]+)\.mp3")
        removed: list[str] = []
        for path in _entries(self.paths.publish_dir):
            match = pattern.fullmatch(path.name)
            stale_tmp = path.name.startswith(f".tmp-{sound_id}-")
            if match is None and not stale_tmp:
                continue
            if match is not None and int(match[1]) in keep:
                continue
            with suppress(FileNotFoundError):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed.append(path.name)
        return removed

    def remove_all(self, sound_id: str) -> None:
        # Removal ignores age, including files with a future mtime.
        pattern = re.compile(rf"{re.escape(sound_id)}-r[0-9]+\.mp3")
        for path in _entries(self.paths.publish_dir):
            with suppress(FileNotFoundError):
                if path.is_file() and (
                    pattern.fullmatch(path.name) or path.name.startswith(f".tmp-{sound_id}-")
                ):
                    path.unlink()
        original = self.paths.originals_dir / sound_id
        with suppress(FileNotFoundError):
            shutil.rmtree(original)
        (self.paths.previews_dir / f"{sound_id}.mp3").unlink(missing_ok=True)
        audition_pattern = re.compile(rf"\.?{re.escape(sound_id)}-[a-f0-9]{{8}}\.mp3")
        for path in _entries(self.paths.publish_dir / "_audition"):
            with suppress(FileNotFoundError):
                if audition_pattern.fullmatch(path.name) and path.is_file():
                    path.unlink()

    def audition_copy(self, src: Path, sound_id: str) -> str:
        name = f"{sound_id}-{secrets.token_hex(4)}.mp3"
        directory = self.paths.publish_dir / "_audition"
        tmp = directory / f".{name}"
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, directory / name)
        finally:
            tmp.unlink(missing_ok=True)
        return f"/local/sound-effects/_audition/{name}"

    def cleanup_auditions(self, older_than: timedelta = timedelta(minutes=10)) -> None:
        cutoff = time.time() - older_than.total_seconds()
        for path in _entries(self.paths.publish_dir / "_audition"):
            with suppress(FileNotFoundError):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()

    def storage_usage(self) -> dict[str, int]:
        """Count originals, committed publications and previews, excluding staging copies."""
        return {
            "originals_bytes": sum(_file_size(p) for p in self.paths.originals_dir.rglob("*")),
            "published_bytes": sum(
                _file_size(p)
                for p in _entries(self.paths.publish_dir)
                if re.fullmatch(r".+-r[0-9]+\.mp3", p.name)
            ),
            "previews_bytes": sum(
                _file_size(p)
                for p in self.paths.previews_dir.glob("*.mp3")
                if not p.name.startswith(".")
            ),
        }


def _entries(directory: Path) -> list[Path]:
    try:
        return list(directory.iterdir())
    except FileNotFoundError:
        return []


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except FileNotFoundError:
        return 0
