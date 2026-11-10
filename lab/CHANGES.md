# Changes versus upstream couch-tv

Forked from Seagey/couch-tv at `8b4a6d5` (v0.12 era, 2026-11-09).

## Added
- `lab/`: project docs, build journal, and the TCL 50P735 reference-TV kit (recon, debloat, checks).
- `.gitignore`: ignores per-TV recon output and debloat backups (`lab/**/out-*/`, `lab/**/backup-*/`),
  because they contain LAN details (Wi-Fi name, MAC addresses).
- `bridge/lab.py`: custom remote buttons (`/api/lab/buttons`, `/api/lab/action/<id>`), screenshot saving to
  server, Immich or NAS (`/api/screenshot/save`, `/api/screenshots`), and homelab widgets from Prometheus and
  JSON sources (`/api/lab/pages`, `/api/lab/page/<id>`). Reference: [LAB.md](LAB.md).
- `bridge/mcp_server.py`: `lab_buttons`, `lab_action`, `screenshot_save` tools.
- `remote/`: a Shortcuts strip under the controls, and a third **Lab** tab (widget pages and recent screenshots).
- `tv-home/web/`: the Lab strip on the Night look (display only).
- `lab/deploy.sh`: copy to the bridge server and restart.

## Changed
- `FireWatch.kt`: couch-tv's own window events no longer cancel the Home watch's re-check (two Home events 0.1 s
  apart after a cast left the Google home in front).
- `app.js` `restart()`: reloads instead of a same-address `replace()`, which the TV app's WebView blocks, so a
  look change applies straight away on a bridge-served home.
- `home.watch_next_block` (bridge config + `app.js`): hide promo rows from Keep watching.
- `build.gradle.kts`: version `0.12-lab.1`, `-PwebDebug=true` turns on WebView remote debugging, update checks
  point at Wemmyneat/couch-tv-lab. Signed with the fork's own key, so it replaces upstream's app with an
  uninstall first (settings come back from the bridge).
- `remote/src/gestures.js`, `App.jsx`: the pager handles three tabs.
