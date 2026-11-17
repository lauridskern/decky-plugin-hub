"""GitHub: reading links, and the releases API with an ETag cache."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .certs import ssl_context

API = "https://api.github.com"
USER_AGENT = "Plugin-Hub (Decky plugin manager)"
TIMEOUT = 20
CACHE_LIMIT = 300

_NAME = r"[A-Za-z0-9_.-]+"


class GitHubError(Exception):
    """A failure the panel can show as it is."""

    def __init__(self, message: str, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind


class RateLimited(GitHubError):
    def __init__(self, reset_at: Optional[int]) -> None:
        self.reset_at = reset_at
        when = ""
        if reset_at:
            minutes = max(1, int((reset_at - time.time() + 59) // 60))
            when = f" Try again in {minutes} min"
        super().__init__(
            "GitHub's rate limit for this Deck is used up." + (when + "," if when else "")
            + " or add a GitHub token in Settings.",
            "rate_limited",
        )


@dataclass
class RepoRef:
    owner: str
    repo: str
    tag: Optional[str] = None     # a release named in the link
    asset: Optional[str] = None   # a file named in the link

    @property
    def full(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_link(text: str) -> RepoRef:
    """Any way of writing a GitHub repository, release or release file.

    https://github.com/o/r, github.com/o/r.git, o/r, …/releases,
    …/releases/latest, …/releases/tag/v1, …/releases/download/v1/X.zip,
    git@github.com:o/r.git, …/tree/main.
    """
    raw = (text or "").strip().strip("<>\"'")
    if not raw:
        raise GitHubError("Paste a GitHub link or owner/repo.", "bad_link")
    ssh = re.match(rf"^git@github\.com:({_NAME})/({_NAME})$", raw)
    if ssh:
        return RepoRef(ssh.group(1), _strip_git(ssh.group(2)))
    short = re.match(rf"^({_NAME})/({_NAME})$", raw)
    if short and "." not in short.group(1):
        return RepoRef(short.group(1), _strip_git(short.group(2)))
    if "://" not in raw:
        raw = "https://" + raw
    url = urllib.parse.urlparse(raw)
    host = (url.hostname or "").lower()
    if host in ("www.github.com", "github.com"):
        parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
    elif host == "api.github.com":
        parts = [urllib.parse.unquote(p) for p in url.path.split("/") if p]
        if parts[:1] == ["repos"]:
            parts = parts[1:]
    else:
        raise GitHubError("That is not a GitHub link.", "bad_link")
    if len(parts) < 2 or not re.fullmatch(_NAME, parts[0]) or not re.fullmatch(_NAME, parts[1]):
        raise GitHubError("The link does not name a repository (github.com/owner/repo).", "bad_link")
    ref = RepoRef(parts[0], _strip_git(parts[1]))
    rest = parts[2:]
    if rest[:2] == ["releases", "tag"] and len(rest) >= 3:
        ref.tag = "/".join(rest[2:])
    elif rest[:3] == ["releases", "latest", "download"] and len(rest) >= 4:
        ref.asset = rest[-1]
    elif rest[:2] == ["releases", "download"] and len(rest) >= 4:
        ref.tag = "/".join(rest[2:-1])
        ref.asset = rest[-1]
    return ref


def _strip_git(name: str) -> str:
    return name[:-4] if name.lower().endswith(".git") else name


def github_repo_in(text: Any) -> Optional[str]:
    """owner/repo of the first github.com link in a string, else None."""
    if not isinstance(text, str):
        return None
    match = re.search(rf"github\.com[/:]({_NAME})/({_NAME})", text)
    if not match:
        return None
    return f"{match.group(1)}/{_strip_git(match.group(2))}"


class GitHub:
    """The releases API, with conditional requests.

    A cached answer is sent back with If-None-Match; GitHub answers 304
    without a body, and (with a token) that does not count against the rate
    limit. The cache is a small JSON file: one entry per URL asked, capped.
    """

    def __init__(self, cache_path: str, token: str = "") -> None:
        self.cache_path = cache_path
        self.token = token
        self.context, self.ca_source = ssl_context()
        self.rate: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._cache: Dict[str, Dict[str, Any]] = self._load()

    # -------------------------------------------------------------- cache
    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self) -> None:
        if len(self._cache) > CACHE_LIMIT:
            keep = sorted(self._cache.items(), key=lambda kv: kv[1].get("at", 0))[-CACHE_LIMIT:]
            self._cache = dict(keep)
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._cache, fh)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    # -------------------------------------------------------------- requests
    def headers(self, accept: str = "application/vnd.github+json") -> Dict[str, str]:
        out = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            out["Authorization"] = f"Bearer {self.token}"
        return out

    def get_json(self, path: str) -> Any:
        """GET api.github.com<path>; a 304 returns the cached body."""
        url = API + path
        with self._lock:
            cached = self._cache.get(url)
        headers = self.headers()
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT, context=self.context) as res:
                self._note_rate(res.headers)
                body = json.loads(res.read().decode("utf-8"))
                etag = res.headers.get("ETag")
                with self._lock:
                    self._cache[url] = {"etag": etag, "body": body, "at": time.time()}
                    self._save()
                return body
        except urllib.error.HTTPError as exc:
            self._note_rate(exc.headers)
            if exc.code == 304 and cached is not None:
                with self._lock:
                    cached["at"] = time.time()
                return cached.get("body")
            if exc.code in (403, 429) and self._rate_limited(exc.headers):
                raise RateLimited(_int(exc.headers.get("X-RateLimit-Reset"))) from None
            if exc.code == 401:
                raise GitHubError("GitHub did not accept the token in Settings.", "bad_token") from None
            if exc.code == 404:
                raise GitHubError("not found", "not_found") from None
            raise GitHubError(f"GitHub answered {exc.code}.", "http") from None
        except urllib.error.URLError as exc:
            raise GitHubError(f"Could not reach GitHub ({exc.reason}).", "network") from None
        except (TimeoutError, OSError) as exc:
            raise GitHubError(f"Could not reach GitHub ({exc}).", "network") from None

    def _note_rate(self, headers: Any) -> None:
        if not headers:
            return
        remaining = _int(headers.get("X-RateLimit-Remaining"))
        if remaining is not None:
            self.rate = {
                "remaining": remaining,
                "limit": _int(headers.get("X-RateLimit-Limit")),
                "reset": _int(headers.get("X-RateLimit-Reset")),
            }

    @staticmethod
    def _rate_limited(headers: Any) -> bool:
        if not headers:
            return False
        return headers.get("X-RateLimit-Remaining") == "0" or bool(headers.get("Retry-After"))

    # -------------------------------------------------------------- releases
    def release(self, ref: RepoRef, prereleases: bool = False) -> Dict[str, Any]:
        """The release to install: the one in the link, else the newest."""
        base = f"/repos/{_q(ref.owner)}/{_q(ref.repo)}"
        try:
            if ref.tag:
                return self.get_json(f"{base}/releases/tags/{_q(ref.tag)}")
            if not prereleases:
                return self.get_json(f"{base}/releases/latest")
            releases = self.get_json(f"{base}/releases?per_page=15") or []
            usable = [r for r in releases if isinstance(r, dict) and not r.get("draft")]
            if usable:
                return usable[0]
        except GitHubError as exc:
            if exc.kind != "not_found":
                raise
        # 404 on releases: either the repository has none or it is not visible.
        try:
            self.get_json(base)
        except GitHubError as exc:
            if exc.kind == "not_found":
                raise GitHubError(
                    f"{ref.full} was not found on GitHub (it may be private).", "repo_not_found"
                ) from None
            raise
        if ref.tag:
            raise GitHubError(f"{ref.full} has no release called {ref.tag}.", "no_release")
        raise GitHubError(f"{ref.full} has no releases yet.", "no_release")

    def open_asset(self, url: str):
        """A streaming response for a release file (follows the CDN redirect)."""
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
        try:
            return urllib.request.urlopen(request, timeout=60, context=self.context)
        except urllib.error.HTTPError as exc:
            raise GitHubError(f"The download answered {exc.code}.", "http") from None
        except urllib.error.URLError as exc:
            raise GitHubError(f"Could not download the file ({exc.reason}).", "network") from None


def zip_assets(release: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        a for a in (release.get("assets") or [])
        if isinstance(a, dict) and str(a.get("name", "")).lower().endswith(".zip")
    ]


def notes_excerpt(body: Optional[str], lines: int = 6, chars: int = 400) -> str:
    """The first lines of the release notes, markdown noise removed."""
    out: List[str] = []
    for line in (body or "").splitlines():
        text = line.strip()
        if not text or text.startswith("<!--"):
            continue
        text = re.sub(r"^#+\s*", "", text)
        text = re.sub(r"\*\*|__|`", "", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"^[-*]\s+", "• ", text)
        out.append(text)
        if len(out) >= lines:
            break
    joined = "\n".join(out)
    return joined if len(joined) <= chars else joined[: chars - 1].rstrip() + "…"


def _q(part: str) -> str:
    return urllib.parse.quote(part, safe="")


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
