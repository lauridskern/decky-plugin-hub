"""The plugins Decky has installed, read from ~/homebrew/plugins."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .github import github_repo_in

# Links that name a repository which is not the plugin's own: the plugin
# database (store images), the template plugins are made from, the loader.
NOT_A_PLUGIN_REPO = {
    "steamdeckhomebrew/decky-plugin-database",
    "steamdeckhomebrew/decky-plugin-template",
    "steamdeckhomebrew/decky-loader",
    "steamdeckhomebrew/decky-frontend-lib",
}


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def detect_repo(manifest: Dict[str, Any], package: Optional[Dict[str, Any]]) -> Optional[str]:
    """The plugin's own GitHub repository, from what its files say."""
    candidates: List[Any] = []
    if package:
        for key in ("repository", "homepage", "bugs"):
            value = package.get(key)
            if isinstance(value, dict):
                value = value.get("url")
            candidates.append(value)
    for key in ("repository", "homepage", "url", "source"):
        candidates.append(manifest.get(key))
    for value in candidates:
        repo = github_repo_in(value)
        if repo and repo.lower() not in NOT_A_PLUGIN_REPO:
            return repo
    return None


def list_plugins(plugins_dir: str) -> List[Dict[str, Any]]:
    """Every folder with a readable plugin.json, sorted by name."""
    out: List[Dict[str, Any]] = []
    try:
        entries = sorted(os.listdir(plugins_dir))
    except OSError:
        return out
    for folder in entries:
        base = os.path.join(plugins_dir, folder)
        manifest_path = os.path.join(base, "plugin.json")
        manifest = _read_json(manifest_path)
        if not manifest or not isinstance(manifest.get("name"), str):
            continue
        package = _read_json(os.path.join(base, "package.json"))
        version = package.get("version") if package and isinstance(package.get("version"), str) else None
        try:
            mtime = os.path.getmtime(manifest_path)
        except OSError:
            mtime = 0.0
        flags = manifest.get("flags") or []
        out.append(
            {
                "name": manifest["name"],
                "folder": folder,
                "version": version,
                "author": manifest.get("author") if isinstance(manifest.get("author"), str) else None,
                "detected_repo": detect_repo(manifest, package),
                "mtime": mtime,
                "root": isinstance(flags, list) and "root" in flags,
            }
        )
    out.sort(key=lambda p: p["name"].lower())
    return out
