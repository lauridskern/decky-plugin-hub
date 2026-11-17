"""Release zips: which file to take, and is it a Decky plugin at all.

Decky installs a zip by extracting it into ~/homebrew/plugins and then
looking for a folder whose plugin.json has the name it was given
(decky_loader/browser.py: find_plugin_folder). So an installable zip has
exactly one top-level folder holding plugin.json, and the name Decky is told
must be the one in that file. Reading the name from the zip, instead of from
the file name in the URL (what Decky's "Install from URL" does), is what
makes any release installable whatever its asset is called.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

MAX_ZIP_BYTES = 150 * 1024 * 1024
KEEP_SECONDS = 2 * 60 * 60   # Decky reads the file when the user confirms


class PackageError(Exception):
    def __init__(self, message: str, kind: str = "bad_zip") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class PluginPackage:
    path: str
    sha256: str
    size: int
    folder: str
    name: str
    version: Optional[str]
    author: Optional[str] = None
    description: Optional[str] = None
    root: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "file_url": "file://" + self.path,
            "sha256": self.sha256,
            "size": self.size,
            "folder": self.folder,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "root": self.root,
            "warnings": list(self.warnings),
        }


def inspect_zip(path: str) -> PluginPackage:
    """Read a downloaded zip the way Decky will; raise if Decky would fail."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError):
        raise PackageError("The release file is not a valid zip.") from None
    with zf:
        names = zf.namelist()
        for name in names:
            # Decky extracts with extractall(); refuse anything that could
            # land outside the plugins folder.
            if name.startswith("/") or "\\" in name or ".." in name.split("/"):
                raise PackageError("The zip contains paths outside its folder; not installing it.")
        top = {n.split("/", 1)[0] for n in names if n.strip("/")}
        manifests = [n for n in names if n.endswith("/plugin.json") and n.count("/") == 1]
        if not manifests:
            if "plugin.json" in names:
                raise PackageError(
                    "plugin.json sits at the top of the zip, not in a folder; Decky cannot install it.",
                    "no_plugin",
                )
            raise PackageError("This zip is not a Decky plugin (no plugin.json).", "no_plugin")
        if len(manifests) > 1:
            raise PackageError("The zip holds more than one plugin.", "no_plugin")
        folder = manifests[0].split("/", 1)[0]
        try:
            manifest = json.loads(zf.read(manifests[0]).decode("utf-8-sig"))
        except Exception:
            raise PackageError("plugin.json in the zip is not valid JSON.", "no_plugin") from None
        name = manifest.get("name") if isinstance(manifest, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise PackageError("plugin.json in the zip has no name.", "no_plugin")
        version = None
        package_json = f"{folder}/package.json"
        if package_json in names:
            try:
                data = json.loads(zf.read(package_json).decode("utf-8-sig"))
                if isinstance(data, dict) and isinstance(data.get("version"), str):
                    version = data["version"]
            except Exception:
                pass
        warnings: List[str] = []
        if len(top) > 1:
            warnings.append("The zip has files next to the plugin folder; Decky ignores them.")
        if f"{folder}/dist/index.js" not in names:
            raise PackageError("The zip has no dist/index.js, so it was never built; Decky cannot load it.", "no_plugin")
        flags = manifest.get("flags") or []
        root = isinstance(flags, list) and "root" in flags
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return PluginPackage(
        path=os.path.abspath(path),
        sha256=digest.hexdigest(),
        size=os.path.getsize(path),
        folder=folder,
        name=name.strip(),
        version=version,
        author=manifest.get("author") if isinstance(manifest.get("author"), str) else None,
        description=(manifest.get("publish") or {}).get("description") if isinstance(manifest.get("publish"), dict) else None,
        root=root,
        warnings=warnings,
    )


def _key(text: str) -> str:
    text = re.sub(r"\.zip$", "", text.lower())
    text = re.sub(r"[^a-z0-9]+", "", text)
    for noise in ("decky", "plugin"):
        text = text.replace(noise, "")
    return text


def order_assets(assets: List[Dict[str, Any]], repo: str, want_name: Optional[str] = None,
                 want_asset: Optional[str] = None) -> List[Dict[str, Any]]:
    """Release zips, the likeliest plugin first.

    A file named in the link wins, then a file named after the installed
    plugin, then one named after the repository; ties go to the most
    downloaded file, then the release's own order. Source archives and debug
    builds go last.
    """
    if want_asset:
        named = [a for a in assets if a.get("name") == want_asset]
        if named:
            return named
    repo_key = _key(repo.split("/")[-1])
    want_key = _key(want_name or "")

    def rank(item):
        index, asset = item
        key = _key(str(asset.get("name", "")))
        score = 0
        stem = re.sub(r"\.zip$", "", str(asset.get("name", "")), flags=re.IGNORECASE).lower()
        if want_name and stem == want_name.lower():
            score -= 8
        if want_key and key == want_key:
            score -= 4
        if repo_key and key == repo_key:
            score -= 2
        lowered = str(asset.get("name", "")).lower()
        if any(word in lowered for word in ("source", "src", "debug", "symbols")):
            score += 5
        # Between equally good names, the file people actually download.
        downloads = asset.get("download_count") or 0
        return (score, -int(downloads), index)

    return [asset for _, asset in sorted(enumerate(assets), key=rank)]


def download(open_stream: Callable[[str], Any], url: str, folder: str,
             expected_size: Optional[int] = None) -> str:
    """Stream a release file into `folder`; returns its path."""
    if expected_size and expected_size > MAX_ZIP_BYTES:
        raise PackageError("The release file is too large to be a Decky plugin.", "too_large")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"{uuid.uuid4().hex}.zip")
    written = 0
    try:
        with open_stream(url) as res, open(target, "wb") as out:
            while True:
                chunk = res.read(1 << 16)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_ZIP_BYTES:
                    raise PackageError("The release file is too large to be a Decky plugin.", "too_large")
                out.write(chunk)
    except BaseException:
        try:
            os.remove(target)
        except OSError:
            pass
        raise
    return target


def prune(folder: str, keep: Optional[List[str]] = None, max_age: int = KEEP_SECONDS) -> int:
    """Delete downloaded zips older than `max_age` (not those in `keep`)."""
    removed = 0
    keep_set = {os.path.abspath(p) for p in (keep or [])}
    now = time.time()
    try:
        entries = os.listdir(folder)
    except OSError:
        return 0
    for entry in entries:
        path = os.path.abspath(os.path.join(folder, entry))
        if path in keep_set or not entry.endswith((".zip", ".part")):
            continue
        try:
            if now - os.path.getmtime(path) > max_age:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed
