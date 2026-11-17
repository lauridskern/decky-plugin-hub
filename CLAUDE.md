@AGENTS.md

# Claude notes

The project brief is in `AGENTS.md`, imported above. Short version:

- Build: `npm run build` · typecheck: `npm run typecheck` · backend:
  `python3 -m compileall -q backend main.py` · tests:
  `python3 -m unittest discover -s tests`.
- UI: `cd tools/preview && npm install` (once), then `npm run shots` and look
  at `panel.png` and `modal.png`.
- Installing is Decky's job (`src/decky.ts`); never extract into
  `~/homebrew/plugins` from this backend.
- Release: commit, `git tag -a vX.Y.Z && git push origin vX.Y.Z`, wait for
  Actions, then `python3 tools/verify_package.py <downloaded zip>` must print
  PASS. Asset name, `plugin.json.name` and the folder are coupled (§6).
