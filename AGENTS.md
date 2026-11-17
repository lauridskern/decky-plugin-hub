# AGENTS.md

Everything an agent needs to work on this repository: what it is, how to run
it, how it is tested, and how it is published.

GitHub: `lauridskern/decky-plugin-hub` · local folder: `decky-plugin-hub` ·
plugin name: `Plugin-Hub` · current line: **v0.1.x**

---

## 1. What this project is

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin: an
unofficial plugin manager for Decky plugins published as GitHub releases. You
paste a GitHub link in the Quick Access menu; the hub finds the newest
release, downloads its zip, checks it is a built Decky plugin, and asks Decky
to install it. It keeps track of which repository each plugin came from and
shows when a newer release is out.

The hub never installs by itself. Decky Loader does, through the same
backend route its store and "Install from URL" use, so the user always gets
Decky's own confirmation and Decky's hash check, permissions and reload.

## 2. Repository layout

```
main.py                 Decky entry point; the RPC surface the panel calls
plugin.json             Decky manifest (name MUST stay "Plugin-Hub"; no root flag)
package.json / rollup   frontend build (src -> dist/index.js)
backend/
  hub.py                the service: installed list, checks, resolve, links
  github.py             link parsing, releases API, ETag cache, rate limits
  package.py            release zips: ordering, download, inspection, pruning
  installed.py          reads ~/homebrew/plugins/*/plugin.json + package.json
  versions.py           tag vs version comparison, Decky InstallType
  settings.py           settings + links + install records (one JSON file)
  sendlink.py           "Send from your phone": one-page form on the local network
  certs.py              TLS roots (bundled cacert.pem; never unverified)
  cacert.pem            Mozilla CA bundle (SteamOS's is outdated)
src/
  index.tsx             definePlugin; toast on the backend's update event
  api.ts                callables and types
  decky.ts              Decky's installer via window.DeckyBackend
  format.ts             status lines, relative times
  components/Panel.tsx  the Quick Access panel
  components/PluginModal.tsx  one plugin: link, update/reinstall, unlink, uninstall
  components/SendFromPhone.tsx  the phone page's address + QR code (qrcode-generator)
tests/test_hub.py       offline backend tests
tests/test_sendlink.py  the phone page against a real local socket
tools/
  verify_package.py     validates a release zip against Decky's installer
  preview/              Chromium harness for the panel (mock @decky/ui, @decky/api)
```

## 3. Build and test

```bash
npm install                 # once
npm run build               # rollup: src/ -> dist/index.js
npm run typecheck           # tsc --noEmit
python3 -m compileall -q backend main.py
python3 -m unittest discover -s tests      # offline, < 1 s

cd tools/preview
npm install && npx playwright install chromium   # once
npm run shots               # panel.png, modal.png; clicks install + update
```

Expected: unit tests all OK; `npm run shots` prints two
`utilities/install_plugin` calls (install from a link, update one) with a
`file://` artifact and a 64-character hash, and `console errors: 0`. Open the
PNGs and look at them; the preview's QAM styling is an approximation, judge
layout and wording, not pixels.

A live check of the resolver (needs network, uses ~3 GitHub requests per
link, writes only into a temp folder):

```bash
python3 - <<'PY'
import asyncio, os, sys, tempfile
sys.path.insert(0, ".")
from backend.hub import Hub
t = tempfile.mkdtemp(); os.makedirs(f"{t}/plugins")
hub = Hub(f"{t}/s", f"{t}/d", f"{t}/plugins")
r = asyncio.run(hub.resolve("lauridskern/decky-rom-store"))
print(r["ok"], r.get("name"), r.get("tag"), r.get("error"))
PY
```

## 4. How an install goes

1. Panel: `resolve(link)` (backend). `parse_link` accepts repo, release,
   tag and asset links in any common shape.
2. `GitHub.release()` gets `/releases/latest` (or the newest non-draft of
   `/releases` with pre-releases on, or the tag in the link). A 404 is told
   apart: repository missing/private vs. no releases.
3. `package.order_assets()` ranks the `.zip` assets: the file in the link,
   then one named like the installed plugin, then like the repository; ties
   go to the most downloaded file. Source/debug zips go last. Up to 4 are
   downloaded until one passes `inspect_zip()`: exactly one
   `<folder>/plugin.json`, a name, `dist/index.js`, no path escaping the
   folder. If the repository is already installed under some name, only a
   zip with that name is accepted (updates that copy, never a second one).
4. The backend records a **pending** install (`settings.json` → `pending`)
   and returns `file_url`, the name from `plugin.json`, the tag, the sha256
   and Decky's `InstallType` (0 install, 1 reinstall, 2 update, 3 downgrade).
5. Frontend (`src/decky.ts`): `DeckyBackend.call("utilities/install_plugin",
   file_url, name, tag, sha256, install_type)`. Decky shows its modal; on OK
   it reads the file, checks the hash, uninstalls the old copy, extracts,
   chowns and loads. A `file://` artifact also skips Decky's store
   install-count POST. **Update all** uses `utilities/install_plugins`
   (one modal for all), the hub itself last.
6. Next time the list is read, a pending install whose `plugin.json` is newer
   than the request becomes an **installed record** (tag, repo, mtime). A
   record whose `plugin.json` mtime changed later (installed by something
   else) is dropped and the plugin's `package.json` version is used again.
   Downloaded zips are pruned after 2 hours (Decky needs them until the user
   confirms).

### Getting a link onto the Deck

Game Mode's on-screen keyboard has no paste key and no Ctrl key, so a long
link has to be typed (the short `owner/repo` form helps), and the Steam
client refuses `navigator.clipboard.readText()` to plugins (tried on a Deck
in v0.1.1, so there is no Paste button). The way around it:

- **Send from your phone** (`backend/sendlink.py`, `SendFromPhone.tsx`):
  only while the user turned it on, a `ThreadingHTTPServer` on `0.0.0.0`
  (port 8787-8796, else any) serves one page at `/<6-char code>`; any other
  path is 404, bodies over 4 KB are refused, and it stops itself 15 minutes
  after the last start or link. A posted link goes through `Hub.resolve()`
  on the plugin's loop (`receive_link`); on success the backend emits
  `plugin_hub_link` with the result, and `index.tsx` (loaded even with the
  panel closed) calls Decky's `install_plugin`, so **Decky's dialog on the
  Deck still has to be confirmed with A**. The phone page shows the outcome.
  Keep those limits: never let the page install without the Deck's dialog,
  never serve without the code, never leave it running by default.

### Plugin logs in Game Mode

Decky writes each plugin's log to `~/homebrew/logs/<folder>/` (one file per
start); without the hub, reading one needs Desktop Mode or SSH.
`backend/logs.py` reads the newest `*.log` of an installed plugin (folders
come from the installed list, never from a name the caller sends), last 300
lines / 256 KB. Shown in a plugin's dialog (**View log**, `LogModal.tsx`)
and on the phone page (`/<code>/logs`, `/<code>/logs/<folder>` as plain
text, same code and lifetime as the rest of the page, read-only).

## 5. Updates

- Repository per plugin: a link (`manual`, `install`, `self`) else
  auto-detection from `package.json` `repository`/`homepage`/`bugs` or
  `plugin.json` `repository`/`homepage` (`auto`). The template's, the
  loader's and the plugin database's repositories are never taken.
  Unlinking an auto-detected plugin puts it on `ignored`.
- Installed version = the recorded tag, else `package.json` version.
  `versions.is_update()` compares numerically (`v1.9` < `1.10`, beta <
  release); tags that are not numbers count as an update when they differ.
- Checks: `check_updates(false)` on every panel open, which only asks GitHub
  if the last full check is over an hour old; a background task asks every
  6 hours (`auto_check`). A rate limit stops the check, keeps the old answers
  and shows when the limit resets; the check is retried next time.
- New updates (by `name@tag`, remembered in `releases.json`) are announced
  once with the `plugin_hub_updates` event; `index.tsx` toasts it.
- Requests carry `If-None-Match`; a 304 reuses the cached body
  (`github_cache.json`, capped at 300 URLs). Unauthenticated 304s still count
  against GitHub's limit; with a token they do not.

## 6. Releasing

Releases are built by GitHub Actions from a tag (`.github/workflows/release.yml`):
build, stamp `package.json` with the tag, copy the tree into
`package/decky-plugin-hub/`, zip it as `Plugin-Hub.zip`, run
`tools/verify_package.py` on it, attach it.

```bash
git tag -a v0.1.0 -m "Plugin Hub v0.1.0" && git push origin v0.1.0
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
curl -sSL -o /tmp/Plugin-Hub.zip \
  https://github.com/lauridskern/decky-plugin-hub/releases/download/v0.1.0/Plugin-Hub.zip
python3 tools/verify_package.py /tmp/Plugin-Hub.zip     # must print PASS
```

Coupled, as with every plugin installed from a URL: the asset is
`Plugin-Hub.zip`, `plugin.json.name` is `Plugin-Hub`, the zip has exactly one
top folder (`decky-plugin-hub/`). Decky's "Install from URL" derives the name
from the URL's last segment and fails silently on a mismatch.

Install URL for users:
`https://github.com/lauridskern/decky-plugin-hub/releases/latest/download/Plugin-Hub.zip`

## 7. On the Deck

- Logs: `~/homebrew/logs/decky-plugin-hub/`
- Settings, links, records: `~/homebrew/settings/decky-plugin-hub/plugin-hub.json`
- Downloads, release cache: `~/homebrew/data/decky-plugin-hub/`
- The backend runs as the `deck` user (no `root` flag). It only reads
  `~/homebrew/plugins`; Decky (root) writes there.


### Decky's Python has only some of the standard library

Decky Loader runs plugin backends with the Python frozen into its
PluginLoader binary (PyInstaller, Python 3.14 in v3.3.1). It contains only
the standard-library modules Decky itself pulls in. **`xml.etree` is not
there** (`xml.sax`, `xml.parsers.expat` are). One `import` of a missing
module stops the whole backend from loading, and every call from the UI then
fails. That is what Emu Hub v0.1.1 did: the page sat on "Looking at what
is installed…" and Settings stayed empty, because `configfmt.py` imported
`xml.etree` for Cemu's settings.xml.

- `tests/test_imports.py` checks every import in `main.py` and `backend/`
  against `tests/decky_modules.txt`, the module list read out of
  PluginLoader v3.3.1 (PYZ, base_library.zip, lib-dynload, bootstrap).
  It runs with the other unit tests in CI and before a release.
- After a Decky Loader update, regenerate the list: download `PluginLoader`
  from the decky-loader release, `pip install pyinstaller` in a venv, read
  the archive with `PyInstaller.archive.readers.CArchiveReader` (the PYZ and
  `base_library.zip` entries, plus the `lib-dynload/*.so` names).

## 8. Rules worth keeping

- **Decky installs, the hub never does.** No extracting into the plugins
  folder, no `root` flag, no skipping Decky's confirmation
  (`utilities/confirm_plugin_install` is not called by the hub).
- **Always pass the sha256** of the zip that was inspected, so Decky installs
  exactly that file.
- **TLS is always verified** (`certs.py` has no unverified fallback): what is
  downloaded becomes code Decky runs as root or as the user.
- **The GitHub token never leaves the backend**: `public_settings()` returns
  only whether one is set and its last four characters. Never log it.
- **No idle timers in the frontend.** Checks run in the backend; the panel
  reads state when the Quick Access menu becomes visible
  (`useQuickAccessVisible`) and when Decky reports a finished install
  (`loader/plugin_download_finish`).
- Only Decky's own components (`PanelSection`, `ButtonItem`, `Field`,
  `TextField`, `ToggleField`, `DialogButton`, `ModalRoot`, `ConfirmModal`) so
  everything takes gamepad focus and opens the on-screen keyboard.
- Only GitHub. No torrents, mirrors or other hosts; no private repositories.

## 9. Known limitations

- Not yet run on a Deck. The preview harness renders the panel with mocked
  Decky modules; what only a Deck shows: that `window.DeckyBackend` is
  reachable from a plugin on the user's Decky version, that Decky accepts a
  `file://` artifact from the hub's data folder and the hash, that the
  `loader/plugin_download_finish` listener fires, how `Field` rows with
  `onActivate` take focus in the QAM, and that the modal's `DialogButton`
  column moves with the d-pad.
- Decky's update notification badge (Decky settings) is only for its own
  store; the hub's count shows in its panel and in a toast.
- A plugin whose release zip has a different `plugin.json` name than the
  installed copy (renamed plugin) is not offered as that plugin's update.
- Releases only: tags without a release, GitHub Actions artifacts and
  source-only repositories cannot be installed.
