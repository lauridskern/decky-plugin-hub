# Plugin Hub

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin
that installs other Decky plugins straight from GitHub and tells you when they
have an update. Everything happens in the Quick Access menu, in Game Mode.

- **Install from a link.** Paste `github.com/owner/repo`, `owner/repo`, or a
  release link. Plugin Hub finds the newest release, picks the zip that
  actually holds a Decky plugin, checks it, and hands it to Decky, which asks
  you to confirm and installs it.
- **Updates.** Plugins you installed this way, and plugins whose files name
  their GitHub repository, are checked against their latest release: when you
  open the panel (at most once an hour) and every 6 hours in the background.
  A new release gets a notification and an **Update** button with the first
  lines of its release notes. **Update all** puts every update into one
  Decky confirmation.
- **Link anything.** A plugin that does not name its repository can be linked
  by hand (press A on it in *Installed*). Unlinking stops the checks.
- **Keeps itself up to date** the same way.
- **No typing long links.** The Deck's keyboard can't paste, so **Send from
  your phone** shows a QR code: open it on
  your phone, paste the link there, and confirm the install on the Deck. The
  page only runs while you have it on and stops by itself after 15 minutes.

## Install

Decky → Settings → Developer → enable *Developer mode*, then
Decky → Settings → Developer → *Install Plugin from URL*:

```
https://github.com/lauridskern/decky-plugin-hub/releases/latest/download/Plugin-Hub.zip
```

## How installing works

Plugin Hub does not install anything itself. It downloads the release zip into
its own data folder, checks that it contains exactly one folder with a
`plugin.json` and a built `dist/index.js`, reads the plugin's real name, and
calls Decky's own installer (`utilities/install_plugin`) with that file, the
name and the zip's SHA-256. Decky shows its usual confirmation, verifies the
hash, extracts the plugin, sets its permissions and loads it.

Because the name comes from inside the zip, a release installs whatever its
asset is called; Decky's "Install from URL" instead needs the file name to
match the plugin's name exactly.

## GitHub limits

Without a token GitHub allows 60 API requests an hour per IP address. One
check costs one request per linked plugin, and answers are cached with ETags.
If you track many plugins, add a token under Settings (a fine-grained token
with no permissions is enough; it only raises the limit). The token stays in
the plugin's settings file and is never shown again.

## Requirements of a plugin release

- A GitHub release (not just a tag) with a `.zip` asset.
- The zip holds one top-level folder with `plugin.json` and `dist/index.js`,
  i.e. a built plugin, the same thing Decky's store ships.

Source-only repositories and releases without a zip are listed as such and
cannot be installed.

## Development

See [AGENTS.md](AGENTS.md).

```bash
npm install && npm run build
python3 -m unittest discover -s tests
cd tools/preview && npm install && npm run shots
```

MIT licensed. Not affiliated with Decky Loader or GitHub.
