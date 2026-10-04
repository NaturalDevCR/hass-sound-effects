"""Virtual import roots and confinement."""

from __future__ import annotations

import pytest

from sound_effects_studio.errors import InvalidError, NotFoundError
from sound_effects_studio.importer import ImportBrowser

pytestmark = pytest.mark.studio


def test_browse_roots_and_entries(paths):
    browser = ImportBrowser(paths.import_roots)
    root = browser.browse("")
    assert root["path"] == "" and root["parent"] is None
    assert root["roots"] == ["config/www", "media", "share"]
    assert [entry["path"] for entry in root["entries"]] == root["roots"]
    media = paths.import_roots["media"]
    (media / "folder").mkdir()
    (media / "tone.WAV").write_bytes(b"123")
    (media / "notes.txt").write_text("hi")
    body = browser.browse("media")
    assert body["parent"] == ""
    assert body["entries"] == [
        {"name": "folder", "path": "media/folder", "kind": "dir", "size": 0, "supported": False},
        {
            "name": "notes.txt",
            "path": "media/notes.txt",
            "kind": "file",
            "size": 2,
            "supported": False,
        },
        {
            "name": "tone.WAV",
            "path": "media/tone.WAV",
            "kind": "file",
            "size": 3,
            "supported": True,
        },
    ]
    assert browser.browse("media/folder")["parent"] == "media"
    assert browser.resolve("config/www") == paths.www_dir.resolve()
    with pytest.raises(NotFoundError):
        browser.browse("media/missing")
    with pytest.raises(InvalidError):
        browser.browse("media/tone.WAV")


@pytest.mark.parametrize(
    "path",
    [
        "media/../../etc",
        "media/../share",
        "/media",
        "unknown",
        "media\\..\\etc",
        "media/./folder",
        "media/\x00",
    ],
)
def test_reject_outside_or_malformed_paths(paths, path):
    with pytest.raises(InvalidError):
        ImportBrowser(paths.import_roots).resolve(path)


def test_symlink_escape_hidden_and_rejected(paths, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "tone.wav").write_bytes(b"x")
    media = paths.import_roots["media"]
    (media / "escape").symlink_to(outside, target_is_directory=True)
    (media / "loop").symlink_to(media / "loop")
    browser = ImportBrowser(paths.import_roots)
    for path in ("media/escape", "media/escape/tone.wav", "media/loop"):
        with pytest.raises(InvalidError):
            browser.resolve(path)
    assert browser.browse("media")["entries"] == []
