"""Chunk assembly, limits, safe filenames and stale upload cleanup."""

from __future__ import annotations

import os
import time
from datetime import timedelta

import pytest
from sound_effects_studio.errors import InvalidError, NotFoundError
from sound_effects_studio.uploads import CHUNK_SIZE, UploadStore

pytestmark = pytest.mark.studio


def test_out_of_order_chunks_and_retry(paths, tmp_path):
    store = UploadStore(paths, lambda: 3 * CHUNK_SIZE)
    data = b"a" * CHUNK_SIZE + b"b" * CHUNK_SIZE + b"end"
    upload = store.create("tone.WAV", len(data))
    assert store.write_chunk(upload, 2, data[2 * CHUNK_SIZE :]) == 3
    assert store.write_chunk(upload, 0, data[:CHUNK_SIZE]) == CHUNK_SIZE + 3
    assert store.write_chunk(upload, 0, data[:CHUNK_SIZE]) == CHUNK_SIZE + 3
    with pytest.raises(InvalidError):
        store.finish(upload, tmp_path / "dest")
    assert store.write_chunk(upload, 1, data[CHUNK_SIZE : 2 * CHUNK_SIZE]) == len(data)
    output = store.finish(upload, tmp_path / "dest")
    assert output.name == "tone.wav" and output.read_bytes() == data
    assert not list(paths.uploads_dir.iterdir())
    with pytest.raises(NotFoundError):
        store.write_chunk(upload, 0, b"x")


@pytest.mark.parametrize("filename", ["bad.exe", "no-extension"])
def test_unsupported(paths, filename):
    with pytest.raises(InvalidError):
        UploadStore(paths, lambda: 10).create(filename, 1)


def test_limits_and_received_ranges(paths, tmp_path):
    limit = [CHUNK_SIZE + 2]
    store = UploadStore(paths, lambda: limit[0])
    for size in (0, -1, limit[0] + 1):
        with pytest.raises(InvalidError):
            store.create("tone.wav", size)
    upload = store.create("tone.wav", limit[0])
    for index, data in [(0, b"x" * (CHUNK_SIZE + 1)), (1, b"xxx"), (2, b"x"), (-1, b"x")]:
        with pytest.raises(InvalidError):
            store.write_chunk(upload, index, data)
    assert store.write_chunk(upload, 0, b"x" * CHUNK_SIZE) == CHUNK_SIZE
    assert store.write_chunk(upload, 0, b"x") == 1
    assert store.write_chunk(upload, 1, b"xx") == 3
    with pytest.raises(InvalidError):
        store.finish(upload, tmp_path / "dest")
    limit[0] = 1
    with pytest.raises(InvalidError):
        store.create("tone.wav", 2)
    with pytest.raises(NotFoundError):
        store.finish("unknown", tmp_path)


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("..\\folder\\door  bell\x00.WAV", "door bell.wav"),
        ("../../.WAV", "sound.wav"),
        ("x" * 200 + ".MP3", "x" * 116 + ".mp3"),
    ],
)
def test_safe_filename(paths, tmp_path, filename, expected):
    store = UploadStore(paths, lambda: 10)
    upload = store.create(filename, 1)
    store.write_chunk(upload, 0, b"x")
    assert store.finish(upload, tmp_path / "dest").name == expected


def test_purge_stale_including_orphaned_parts(paths):
    store = UploadStore(paths, lambda: 10)
    stale = store.create("old.wav", 1)
    old_part = next(paths.uploads_dir.iterdir())
    old = time.time() - 7 * 3600
    os.utime(old_part, (old, old))
    fresh = store.create("new.wav", 1)
    orphan = paths.uploads_dir / "orphan.part"
    orphan.write_bytes(b"x")
    os.utime(orphan, (old, old))
    store.purge_stale(timedelta(hours=6))
    with pytest.raises(NotFoundError):
        store.write_chunk(stale, 0, b"x")
    assert store.write_chunk(fresh, 0, b"x") == 1
    assert not orphan.exists()


@pytest.mark.parametrize(
    "extension", [".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".mp4", ".mov"]
)
def test_all_supported_extensions(paths, extension):
    store = UploadStore(paths, lambda: 1)
    assert store.create("sound" + extension.upper(), 1)
