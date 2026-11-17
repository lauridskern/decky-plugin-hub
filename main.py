"""Plugin Hub - Decky plugin backend.

Installs Decky plugins from their GitHub releases and tells you when a newer
release is out. The actual install is done by Decky Loader itself; this
backend finds, downloads and checks the release zip (backend/hub.py).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

try:
    import decky  # type: ignore  # Decky Loader >= 3.1
except ImportError:
    try:
        import decky_plugin as decky  # type: ignore  # Decky Loader 3.0
    except ImportError:
        decky = None  # type: ignore  # tests, packaging checks

from backend.hub import Hub  # noqa: E402


def _log(message: str) -> None:
    logger = getattr(decky, "logger", None)
    if logger is not None:
        try:
            logger.info(message)
        except Exception:
            pass


def _env(name: str, fallback: str) -> str:
    value = getattr(decky, name, None) if decky is not None else None
    return str(value) if value else fallback


HOME = _env("DECKY_USER_HOME", os.path.expanduser("~"))
DECKY_HOME = _env("DECKY_HOME", os.path.join(HOME, "homebrew"))
SETTINGS_DIR = _env("DECKY_PLUGIN_SETTINGS_DIR", os.path.join(DECKY_HOME, "settings", "decky-plugin-hub"))
RUNTIME_DIR = _env("DECKY_PLUGIN_RUNTIME_DIR", os.path.join(DECKY_HOME, "data", "decky-plugin-hub"))
PLUGINS_DIR = os.path.join(DECKY_HOME, "plugins")


class Plugin:
    """Decky >= 3.1 instantiates this class; older loaders call it on the class."""

    _instance: Optional["Plugin"] = None

    def __init__(self) -> None:
        emit = getattr(decky, "emit", None) if decky is not None else None
        self.hub = Hub(SETTINGS_DIR, RUNTIME_DIR, PLUGINS_DIR, emit=emit, log=_log)
        Plugin._instance = self

    @classmethod
    def instance(cls) -> "Plugin":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _self(cls) -> "Plugin":
        return cls.instance()

    # ------------------------------------------------------------------ lifecycle
    async def _main(self) -> None:
        plugin = self._self()
        _log(f"Plugin Hub started; plugins in {PLUGINS_DIR}; TLS roots: {plugin.hub.github.ca_source}")
        plugin.hub.start()

    async def _unload(self) -> None:
        self._self().hub.stop()

    async def _uninstall(self) -> None:
        _log("Plugin Hub uninstalled")

    # ------------------------------------------------------------------ state
    async def get_state(self) -> Dict[str, Any]:
        """Installed plugins and the last known releases; no network."""
        return self._self().hub.state()

    async def check_updates(self, force: bool = False) -> Dict[str, Any]:
        return await self._self().hub.check(bool(force))

    # ------------------------------------------------------------------ installing
    async def resolve(self, link: str) -> Dict[str, Any]:
        """Download and check the plugin a GitHub link points at."""
        return await self._self().hub.resolve(link)

    async def prepare_update(self, name: str) -> Dict[str, Any]:
        return await self._self().hub.prepare_update(name)

    async def prepare_updates(self) -> List[Dict[str, Any]]:
        return await self._self().hub.prepare_updates()

    async def cancel_install(self, name: str) -> None:
        self._self().hub.cancel(name)

    # ------------------------------------------------------------------ send from a phone
    async def start_send_link(self) -> Dict[str, Any]:
        """Serve the send-a-link page on the local network (stops by itself)."""
        import asyncio
        try:
            return self._self().hub.sendlink.start(asyncio.get_running_loop())
        except OSError as exc:
            return {"running": False, "error": str(exc)}

    async def stop_send_link(self) -> Dict[str, Any]:
        return self._self().hub.sendlink.stop()

    async def send_link_state(self) -> Dict[str, Any]:
        return self._self().hub.sendlink.state()

    # ------------------------------------------------------------------ links
    async def link_repo(self, name: str, link: str) -> Dict[str, Any]:
        return self._self().hub.link(name, link)

    async def unlink_repo(self, name: str) -> Dict[str, Any]:
        hub = self._self().hub
        hub.unlink(name)
        return hub.state()

    async def forget_plugin(self, name: str) -> Dict[str, Any]:
        """Called after Decky uninstalled a plugin."""
        hub = self._self().hub
        hub.forget(name)
        return hub.state()

    # ------------------------------------------------------------------ settings
    async def set_settings(self, changes: Dict[str, Any]) -> Dict[str, Any]:
        hub = self._self().hub
        hub.update_settings(changes or {})
        return hub.state()
