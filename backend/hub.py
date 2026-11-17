"""The hub: installed plugins, their GitHub releases, and install requests.

Installing is Decky's job. The hub finds the release, downloads its zip,
checks that Decky can install it, and hands the frontend a file:// path, the
plugin's real name and the zip's sha256; the frontend passes those to
Decky's own `utilities/install_plugin`, which asks the user to confirm,
verifies the hash, extracts, sets permissions and loads the plugin.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from . import package as pkg
from .github import GitHub, GitHubError, RateLimited, RepoRef, notes_excerpt, parse_link, zip_assets
from .installed import list_plugins
from .sendlink import LinkServer
from .settings import SELF_NAME, Store
from .versions import install_type, is_update

CHECK_MAX_AGE = 60 * 60            # a panel opened within the hour reuses the last check
AUTO_CHECK_EVERY = 6 * 60 * 60     # background checks
MAX_CANDIDATES = 4                 # release zips downloaded to find the plugin
PARALLEL = 4

Emit = Callable[..., Awaitable[Any]]


class Hub:
    def __init__(self, settings_dir: str, runtime_dir: str, plugins_dir: str,
                 emit: Optional[Emit] = None, log: Callable[[str], None] = lambda _m: None) -> None:
        self.store = Store(os.path.join(settings_dir, "plugin-hub.json"))
        self.sendlink = LinkServer(self.receive_link, log=log)
        self.runtime_dir = runtime_dir
        self.downloads_dir = os.path.join(runtime_dir, "downloads")
        self.plugins_dir = plugins_dir
        self.state_path = os.path.join(runtime_dir, "releases.json")
        self.github = GitHub(os.path.join(runtime_dir, "github_cache.json"),
                             self.store.settings.get("github_token") or "")
        self.emit = emit
        self.log = log
        self.checking = False
        self.last_error: Optional[Dict[str, Any]] = None
        self._check_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        saved = self._load_state()
        self.latest: Dict[str, Dict[str, Any]] = saved.get("latest", {})
        self.checked_at: float = float(saved.get("checked_at") or 0)
        self.notified: List[str] = list(saved.get("notified") or [])

    # ------------------------------------------------------------------ state file
    def _load_state(self) -> Dict[str, Any]:
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self) -> None:
        try:
            os.makedirs(self.runtime_dir, exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"latest": self.latest, "checked_at": self.checked_at,
                           "notified": self.notified[-200:]}, fh)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    # ------------------------------------------------------------------ installed
    def _plugins(self) -> List[Dict[str, Any]]:
        plugins = list_plugins(self.plugins_dir)
        self._sync_records(plugins)
        return plugins

    def _sync_records(self, plugins: List[Dict[str, Any]]) -> None:
        """Turn confirmed installs into records; drop records that went stale."""
        data = self.store.data
        by_name = {p["name"]: p for p in plugins}
        changed = False
        now = time.time()
        for name, pending in list(data["pending"].items()):
            plugin = by_name.get(name)
            # Decky extracts the zip fresh, so plugin.json is newer than the request.
            if plugin and plugin["mtime"] >= float(pending.get("at", 0)) - 2:
                data["installed"][name] = {"tag": pending.get("tag"), "repo": pending.get("repo"),
                                           "mtime": plugin["mtime"]}
                if pending.get("repo") and data["links"].get(name, {}).get("source") != "self":
                    data["links"][name] = {"repo": pending["repo"],
                                           "source": data["links"].get(name, {}).get("source", "install")}
                del data["pending"][name]
                changed = True
            elif now - float(pending.get("at", 0)) > pkg.KEEP_SECONDS:
                del data["pending"][name]
                changed = True
        for name, record in list(data["installed"].items()):
            plugin = by_name.get(name)
            # Gone, or replaced by something else (the store, a manual copy).
            if plugin is None or abs(plugin["mtime"] - float(record.get("mtime", 0))) > 2:
                del data["installed"][name]
                changed = True
        if changed:
            self.store.save()

    def _repo_for(self, plugin: Dict[str, Any]) -> Dict[str, Optional[str]]:
        link = self.store.data["links"].get(plugin["name"])
        if link and link.get("repo"):
            return {"repo": link["repo"], "link": link.get("source") or "manual"}
        if plugin.get("detected_repo") and plugin["name"] not in self.store.data["ignored"]:
            return {"repo": plugin["detected_repo"], "link": "auto"}
        return {"repo": None, "link": None}

    def _installed_version(self, plugin: Dict[str, Any]) -> Optional[str]:
        record = self.store.data["installed"].get(plugin["name"])
        if record and record.get("tag"):
            return record["tag"]
        return plugin.get("version")

    def _view(self, plugin: Dict[str, Any]) -> Dict[str, Any]:
        repo = self._repo_for(plugin)
        version = self._installed_version(plugin)
        latest = self.latest.get((repo["repo"] or "").lower()) if repo["repo"] else None
        update = False
        status = "unlinked" if not repo["repo"] else "unchecked"
        if latest:
            if latest.get("error"):
                status = latest.get("kind") or "error"
            elif not latest.get("has_zip"):
                status = "no_zip"
            else:
                update = is_update(version, latest.get("tag"))
                status = "update" if update else "current"
        return {
            "name": plugin["name"],
            "folder": plugin["folder"],
            "version": version,
            "package_version": plugin.get("version"),
            "author": plugin.get("author"),
            "repo": repo["repo"],
            "link": repo["link"],
            "detected_repo": plugin.get("detected_repo"),
            "root": plugin.get("root", False),
            "latest": latest,
            "update": update,
            "status": status,
            "pending": plugin["name"] in self.store.data["pending"],
            "is_self": plugin["name"] == SELF_NAME,
        }

    def state(self) -> Dict[str, Any]:
        views = [self._view(p) for p in self._plugins()]
        return {
            "plugins": views,
            "updates": sum(1 for v in views if v["update"]),
            "checked_at": self.checked_at or None,
            "checking": self.checking,
            "error": self.last_error,
            "rate": self.github.rate or None,
            "settings": self.store.public_settings(),
            "plugins_dir": self.plugins_dir,
        }

    # ------------------------------------------------------------------ checking
    def _fetch_latest(self, repo: str) -> Dict[str, Any]:
        owner, name = repo.split("/", 1)
        prereleases = bool(self.store.settings.get("include_prereleases"))
        try:
            release = self.github.release(RepoRef(owner, name), prereleases=prereleases)
        except RateLimited:
            raise
        except GitHubError as exc:
            return {"error": str(exc), "kind": exc.kind, "checked": time.time()}
        return {
            "tag": release.get("tag_name"),
            "title": release.get("name") or release.get("tag_name"),
            "notes": notes_excerpt(release.get("body")),
            "url": release.get("html_url"),
            "published_at": release.get("published_at"),
            "prerelease": bool(release.get("prerelease")),
            "has_zip": bool(zip_assets(release)),
            "checked": time.time(),
        }

    async def check(self, force: bool = False) -> Dict[str, Any]:
        """Ask GitHub for the newest release of every linked plugin."""
        if not force and self.checked_at and time.time() - self.checked_at < CHECK_MAX_AGE:
            return self.state()
        async with self._check_lock:
            if not force and self.checked_at and time.time() - self.checked_at < CHECK_MAX_AGE:
                return self.state()
            self.checking = True
            try:
                plugins = self._plugins()
                repos = sorted({(self._repo_for(p)["repo"] or "").lower(): self._repo_for(p)["repo"]
                                for p in plugins if self._repo_for(p)["repo"]}.items())
                gate = asyncio.Semaphore(PARALLEL)
                self.last_error = None

                async def one(key: str, repo: str) -> None:
                    async with gate:
                        if self.last_error and self.last_error.get("kind") == "rate_limited":
                            return
                        try:
                            self.latest[key] = await asyncio.to_thread(self._fetch_latest, repo)
                        except RateLimited as exc:
                            self.last_error = {"message": str(exc), "kind": exc.kind, "reset": exc.reset_at}

                await asyncio.gather(*(one(k, r) for k, r in repos))
                if not self.last_error:
                    self.checked_at = time.time()
                self._save_state()
            finally:
                self.checking = False
        state = self.state()
        await self._notify(state)
        return state

    async def _notify(self, state: Dict[str, Any]) -> None:
        fresh = []
        for view in state["plugins"]:
            if not view["update"]:
                continue
            key = f"{view['name']}@{view['latest'].get('tag')}"
            if key not in self.notified:
                self.notified.append(key)
                fresh.append({"name": view["name"], "from": view["version"], "to": view["latest"].get("tag")})
        if fresh:
            self._save_state()
            if self.emit and self.store.settings.get("notify", True):
                try:
                    await self.emit("plugin_hub_updates", {"updates": fresh, "total": state["updates"]})
                except Exception as exc:
                    self.log(f"could not send the update notice: {exc!r}")

    def start(self) -> None:
        self._task = asyncio.get_running_loop().create_task(self._background())
        try:
            pkg.prune(self.downloads_dir)
        except Exception:
            pass

    def stop(self) -> None:
        self.sendlink.stop()
        if self._task:
            self._task.cancel()
            self._task = None

    async def _background(self) -> None:
        await asyncio.sleep(90)   # let the Deck finish booting first
        while True:
            try:
                if self.store.settings.get("auto_check", True) and time.time() - self.checked_at >= AUTO_CHECK_EVERY:
                    await self.check(force=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log(f"background update check failed: {exc!r}")
            await asyncio.sleep(30 * 60)

    # ------------------------------------------------------------------ installing
    def _resolve_sync(self, ref: RepoRef, want_name: Optional[str]) -> Dict[str, Any]:
        release = self.github.release(ref, prereleases=bool(self.store.settings.get("include_prereleases")))
        assets = zip_assets(release)
        tag = release.get("tag_name")
        if not assets:
            raise GitHubError(f"{ref.full} {tag} has no .zip file to install.", "no_zip")
        candidates = pkg.order_assets(assets, ref.repo, want_name, ref.asset)
        if ref.asset and candidates and candidates[0].get("name") != ref.asset:
            raise GitHubError(f"{ref.full} {tag} has no file called {ref.asset}.", "no_zip")
        problems: List[str] = []
        found: Optional[pkg.PluginPackage] = None
        for asset in candidates[:MAX_CANDIDATES]:
            url = asset.get("browser_download_url")
            if not url:
                continue
            path = pkg.download(self.github.open_asset, url, self.downloads_dir, asset.get("size"))
            try:
                candidate = pkg.inspect_zip(path)
            except pkg.PackageError as exc:
                problems.append(f"{asset.get('name')}: {exc}")
                os.remove(path)
                continue
            if want_name and candidate.name != want_name:
                problems.append(f"{asset.get('name')} is {candidate.name}, not {want_name}")
                os.remove(path)
                continue
            found = candidate
            break
        if found is None:
            detail = problems[0] if len(problems) == 1 else "; ".join(problems[:3])
            raise GitHubError(f"No release file of {ref.full} {tag} is an installable Decky plugin ({detail}).",
                              "no_plugin")
        return {
            "repo": ref.full,
            "tag": tag,
            "title": release.get("name") or tag,
            "notes": notes_excerpt(release.get("body")),
            "prerelease": bool(release.get("prerelease")),
            "package": found.to_dict(),
        }

    async def resolve(self, link: str, want_name: Optional[str] = None) -> Dict[str, Any]:
        """Find and download the plugin a link points at; nothing is installed yet."""
        try:
            ref = parse_link(link)
        except GitHubError as exc:
            return {"ok": False, "error": str(exc), "kind": exc.kind}
        if want_name is None:
            # Installing a repository that is already installed (perhaps under
            # the name of another asset) updates that copy, never a second one.
            for plugin in self._plugins():
                if (self._repo_for(plugin)["repo"] or "").lower() == ref.full.lower():
                    want_name = plugin["name"]
                    break
        try:
            pkg.prune(self.downloads_dir, keep=[p.get("path") for p in self.store.data["pending"].values()])
            result = await asyncio.to_thread(self._resolve_sync, ref, want_name)
        except RateLimited as exc:
            return {"ok": False, "error": str(exc), "kind": exc.kind, "reset": exc.reset_at}
        except (GitHubError, pkg.PackageError) as exc:
            return {"ok": False, "error": str(exc), "kind": getattr(exc, "kind", "error")}
        except Exception as exc:  # never let a surprise kill the panel
            self.log(f"resolve {link!r} failed: {exc!r}")
            return {"ok": False, "error": f"Something went wrong: {exc}", "kind": "error"}

        package = result["package"]
        name = package["name"]
        current = next((p for p in self._plugins() if p["name"] == name), None)
        installed = self._installed_version(current) if current else None
        # The release's tag is the version Decky shows and the hub compares.
        version = result["tag"] or package.get("version") or "unknown"
        kind = install_type(installed if current else None, version)
        self.store.data["pending"][name] = {"tag": result["tag"], "repo": result["repo"],
                                            "sha256": package["sha256"], "path": package["path"],
                                            "at": time.time()}
        link_entry = self.store.data["links"].get(name)
        if not link_entry or link_entry.get("source") not in ("manual", "self"):
            self.store.data["links"][name] = {"repo": result["repo"], "source": "install"}
        if name in self.store.data["ignored"]:
            self.store.data["ignored"].remove(name)
        self.store.save()
        # This release is now the latest known one for the repository.
        self.latest[result["repo"].lower()] = {
            "tag": result["tag"], "title": result["title"], "notes": result["notes"],
            "url": f"https://github.com/{result['repo']}/releases/tag/{result['tag']}",
            "prerelease": result["prerelease"], "has_zip": True, "checked": time.time(),
        }
        self._save_state()
        return {
            "ok": True,
            **result,
            "name": name,
            "version": version,
            "installed_version": installed,
            "install_type": kind,
        }

    async def receive_link(self, link: str) -> Dict[str, Any]:
        """A link sent from the phone page: resolve it, then let the Deck ask.

        The frontend listens for `plugin_hub_link` and shows Decky's install
        dialog with the result; nothing is installed without A on the Deck.
        """
        result = await self.resolve(link)
        if not result.get("ok"):
            return {"ok": False, "message": result.get("error") or "That link has no installable plugin."}
        if not self.emit:
            return {"ok": False, "message": "The Deck could not show the install dialog."}
        try:
            await self.emit("plugin_hub_link", result)
        except Exception as exc:
            self.log(f"could not hand the link to the panel: {exc!r}")
            return {"ok": False, "message": "The Deck could not show the install dialog."}
        word = {1: "Reinstall", 2: "Update", 3: "Downgrade"}.get(result.get("install_type") or 0, "Install")
        return {"ok": True, "name": result.get("name"), "version": result.get("version"),
                "message": f"{word} {result.get('name')} {result.get('version')}: confirm on your Deck."}

    async def prepare_update(self, name: str) -> Dict[str, Any]:
        plugin = next((p for p in self._plugins() if p["name"] == name), None)
        if plugin is None:
            return {"ok": False, "error": f"{name} is not installed.", "kind": "not_installed"}
        repo = self._repo_for(plugin)["repo"]
        if not repo:
            return {"ok": False, "error": f"{name} is not linked to a GitHub repository.", "kind": "unlinked"}
        return await self.resolve(repo, want_name=name)

    async def prepare_updates(self) -> List[Dict[str, Any]]:
        """Every available update, the hub itself last (it reloads when updated)."""
        names = [v["name"] for v in self.state()["plugins"] if v["update"]]
        names.sort(key=lambda n: n == SELF_NAME)
        return [await self.prepare_update(n) for n in names]

    def cancel(self, name: str) -> None:
        pending = self.store.data["pending"].pop(name, None)
        self.store.save()
        if pending and pending.get("path"):
            try:
                os.remove(pending["path"])
            except OSError:
                pass

    # ------------------------------------------------------------------ links
    def link(self, name: str, link: str) -> Dict[str, Any]:
        try:
            ref = parse_link(link)
        except GitHubError as exc:
            return {"ok": False, "error": str(exc)}
        self.store.link(name, ref.full)
        return {"ok": True, "repo": ref.full}

    def unlink(self, name: str) -> None:
        self.store.unlink(name)

    def forget(self, name: str) -> None:
        self.cancel(name)
        self.store.forget(name)

    def update_settings(self, changes: Dict[str, Any]) -> None:
        before_pre = self.store.settings.get("include_prereleases")
        self.store.update_settings(changes)
        self.github.token = self.store.settings.get("github_token") or ""
        if self.store.settings.get("include_prereleases") != before_pre:
            self.checked_at = 0   # the answers mean something else now
            self._save_state()

