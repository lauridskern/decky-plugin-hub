"""Settings and the hub's own records, in one small JSON file.

    settings   user choices (token, pre-releases, automatic checks)
    links      plugin name -> {"repo": "owner/repo", "source": "manual"|"install"}
    ignored    plugin names whose auto-detected repository the user unlinked
    installed  plugin name -> {"tag", "repo", "mtime"}: what the hub installed
    pending    plugin name -> {"tag", "repo", "sha256", "at"}: handed to Decky,
               not confirmed yet
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

SELF_NAME = "Plugin-Hub"
SELF_REPO = "lauridskern/decky-plugin-hub"

DEFAULTS: Dict[str, Any] = {
    "include_prereleases": False,
    "auto_check": True,
    "notify": True,
    "github_token": "",
}


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            pass
        settings = dict(DEFAULTS)
        if isinstance(data.get("settings"), dict):
            settings.update({k: v for k, v in data["settings"].items() if k in DEFAULTS})
        data["settings"] = settings
        for key in ("links", "installed", "pending"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        if not isinstance(data.get("ignored"), list):
            data["ignored"] = []
        # The hub keeps itself up to date.
        data["links"].setdefault(SELF_NAME, {"repo": SELF_REPO, "source": "self"})
        return data

    def save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self.data, fh, indent=2, sort_keys=True)
                os.replace(tmp, self.path)
            except OSError:
                pass

    # ---------------------------------------------------------------- settings
    @property
    def settings(self) -> Dict[str, Any]:
        return self.data["settings"]

    def public_settings(self) -> Dict[str, Any]:
        """Settings for the panel; the token itself never leaves the backend."""
        out = {k: v for k, v in self.settings.items() if k != "github_token"}
        token = self.settings.get("github_token") or ""
        out["has_token"] = bool(token)
        out["token_hint"] = ("…" + token[-4:]) if len(token) >= 8 else ""
        return out

    def update_settings(self, changes: Dict[str, Any]) -> None:
        with self._lock:
            for key, value in (changes or {}).items():
                if key not in DEFAULTS:
                    continue
                if isinstance(DEFAULTS[key], bool):
                    value = bool(value)
                elif isinstance(DEFAULTS[key], str):
                    value = str(value or "").strip()
                self.settings[key] = value
            self.save()

    # ---------------------------------------------------------------- links
    def link(self, name: str, repo: str, source: str = "manual") -> None:
        with self._lock:
            self.data["links"][name] = {"repo": repo, "source": source}
            if name in self.data["ignored"]:
                self.data["ignored"].remove(name)
            self.save()

    def unlink(self, name: str) -> None:
        with self._lock:
            self.data["links"].pop(name, None)
            self.data["installed"].pop(name, None)
            if name not in self.data["ignored"]:
                self.data["ignored"].append(name)
            self.save()

    def forget(self, name: str) -> None:
        """The plugin was uninstalled: drop what the hub knew about it."""
        with self._lock:
            if self.data["links"].get(name, {}).get("source") != "self":
                self.data["links"].pop(name, None)
            self.data["installed"].pop(name, None)
            self.data["pending"].pop(name, None)
            if name in self.data["ignored"]:
                self.data["ignored"].remove(name)
            self.save()
