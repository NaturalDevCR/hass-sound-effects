"""Filesystem publication and retention contracts."""

import os
import re
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sound_effects_studio.config import Paths
from sound_effects_studio.publisher import Publisher

pytestmark = pytest.mark.studio


def test_ensure_dirs(paths: Paths):
    paths.www_dir.rmdir()
    publisher = Publisher(paths)
    status = publisher.ensure_dirs()
    assert status.exists and status.created_by_app and status.served is None
    assert not publisher.ensure_dirs().created_by_app
    for directory in (
        paths.originals_dir,
        paths.previews_dir,
        paths.uploads_dir,
        paths.publish_dir / "_audition",
    ):
        assert directory.is_dir()


def test_commit_is_atomic(paths: Paths, monkeypatch):
    publisher = Publisher(paths)
    publisher.ensure_dirs()
    final = paths.publish_dir / "boo-r1.mp3"
    final.write_bytes(b"old complete file")
    tmp = publisher.temp_path("boo")
    assert re.fullmatch(r"\.tmp-boo-[a-f0-9]{8}\.mp3", tmp.name)
    assert tmp != publisher.temp_path("boo")
    tmp.write_bytes(b"new complete file")
    replace = os.replace
    calls = []

    def observe(source, destination):
        assert final.read_bytes() == b"old complete file"
        assert source == tmp and destination == final
        calls.append((source, destination))
        replace(source, destination)

    monkeypatch.setattr(os, "replace", observe)
    assert publisher.commit(tmp, "boo", 1) == "boo-r1.mp3"
    assert len(calls) == 1 and not tmp.exists()
    assert publisher.published_path("boo-r1.mp3").read_bytes() == b"new complete file"


def test_cleanup_retains_kept_and_recent_files(paths: Paths):
    publisher = Publisher(paths)
    publisher.ensure_dirs()
    names = [
        "boo-r1.mp3",
        "boo-r2.mp3",
        "boo-r3.mp3",
        "boo-r4.mp3",
        ".tmp-boo-old.mp3",
        ".tmp-boo-new.mp3",
        "other-r1.mp3",
        "boo-rx.mp3",
    ]
    for name in names:
        file = paths.publish_dir / name
        file.write_bytes(b"audio")
        if name not in {"boo-r4.mp3", ".tmp-boo-new.mp3"}:
            old = time.time() - 25 * 3600
            os.utime(file, (old, old))
    assert set(publisher.cleanup("boo", keep={2, 3})) == {"boo-r1.mp3", ".tmp-boo-old.mp3"}
    assert {p.name for p in paths.publish_dir.iterdir() if p.is_file()} == set(names) - {
        "boo-r1.mp3",
        ".tmp-boo-old.mp3",
    }


def test_audition_copy_and_cleanup(paths: Paths, tmp_path: Path):
    publisher = Publisher(paths)
    publisher.ensure_dirs()
    src = tmp_path / "source.mp3"
    src.write_bytes(b"audio")
    url = publisher.audition_copy(src, "boo")
    assert re.fullmatch(r"/local/sound-effects/_audition/boo-[a-f0-9]{8}\.mp3", url)
    file = paths.publish_dir / "_audition" / url.rsplit("/", 1)[1]
    assert file.read_bytes() == src.read_bytes()
    recent = publisher.audition_copy(src, "boo")
    old = time.time() - 601
    os.utime(file, (old, old))
    publisher.cleanup_auditions()
    assert not file.exists()
    assert (paths.publish_dir / "_audition" / recent.rsplit("/", 1)[1]).exists()


def test_storage_usage_and_remove_all(paths: Paths):
    publisher = Publisher(paths)
    publisher.ensure_dirs()
    original = paths.originals_dir / "boo"
    original.mkdir()
    (original / "source.wav").write_bytes(b"123")
    (paths.previews_dir / "boo.mp3").write_bytes(b"12")
    (paths.publish_dir / "boo-r1.mp3").write_bytes(b"1234")
    (paths.publish_dir / "other-r1.mp3").write_bytes(b"1")
    (paths.publish_dir / ".tmp-boo-old.mp3").write_bytes(b"12345")
    publisher.audition_copy(paths.publish_dir / "boo-r1.mp3", "boo")
    assert publisher.storage_usage() == {
        "originals_bytes": 3,
        "published_bytes": 5,
        "previews_bytes": 2,
    }
    publisher.remove_all("boo")
    assert not original.exists() and not (paths.previews_dir / "boo.mp3").exists()
    assert {p.name for p in paths.publish_dir.iterdir()} == {"other-r1.mp3", "_audition"}
    assert not list((paths.publish_dir / "_audition").iterdir())
    publisher.remove_all("boo")
    assert publisher.cleanup("boo", set(), timedelta(0)) == []
