"""Browse confined, named virtual roots without exposing host filesystem paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import InvalidError, NotFoundError
from .media import SUPPORTED_EXTENSIONS


class ImportBrowser:
    def __init__(self, roots: dict[str, Path]) -> None:
        self._roots = dict(roots)

    def resolve(self, virtual_path: str) -> Path:
        if "\\" in virtual_path or "\x00" in virtual_path:
            raise InvalidError("Invalid import path.")
        parts = virtual_path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise InvalidError("Import path is outside the allowed roots.")
        for name, root in self._roots.items():
            if virtual_path != name and not virtual_path.startswith(name + "/"):
                continue
            relative = virtual_path[len(name) :].lstrip("/")
            try:
                resolved_root = root.resolve()
                try:
                    target = (resolved_root / relative).resolve(strict=True)
                except FileNotFoundError:
                    target = (resolved_root / relative).resolve()
            except (OSError, ValueError, RuntimeError) as exc:
                raise InvalidError("Invalid import path.") from exc
            if not target.is_relative_to(resolved_root):
                raise InvalidError("Import path is outside the allowed roots.")
            return target
        raise InvalidError("Import path is outside the allowed roots.")

    def browse(self, virtual_path: str) -> dict[str, Any]:
        roots = list(self._roots)
        if not virtual_path:
            entries = [
                {"name": name, "path": name, "kind": "dir", "size": 0, "supported": False}
                for name in roots
            ]
            return {"path": "", "parent": None, "roots": roots, "entries": entries}
        directory = self.resolve(virtual_path)
        if not directory.exists():
            raise NotFoundError("Import directory does not exist.")
        if not directory.is_dir():
            raise InvalidError("Import path must be a directory.")
        entries: list[dict[str, Any]] = []
        for child in directory.iterdir():
            child_virtual = f"{virtual_path}/{child.name}"
            try:
                target = self.resolve(child_virtual)
            except InvalidError:
                continue
            if not target.is_dir() and not target.is_file():
                continue
            is_dir = target.is_dir()
            entries.append(
                {
                    "name": child.name,
                    "path": child_virtual,
                    "kind": "dir" if is_dir else "file",
                    "size": 0 if is_dir else target.stat().st_size,
                    "supported": not is_dir and child.suffix.lower() in SUPPORTED_EXTENSIONS,
                }
            )
        entries.sort(key=lambda entry: (entry["kind"] != "dir", entry["name"].casefold()))
        parent = "" if virtual_path in roots else virtual_path.rpartition("/")[0]
        return {"path": virtual_path, "parent": parent, "roots": roots, "entries": entries}
