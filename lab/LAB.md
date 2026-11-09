# The lab layer: configuration reference

Everything here lives in the bridge's `config.json` under `"lab"` (plus `home.watch_next_block`), and in its
`.env` for secrets. Code: `bridge/lab.py`, `remote/src/Lab.jsx`, the Lab strip in `tv-home/web/app.js`.
After a config change: `systemctl restart couch-tv-bridge` on the server.

## Custom remote buttons: `lab.buttons`
Shown as the **Shortcuts** strip on the phone remote. Each button runs its steps in order through the bridge's own API.

```json
"buttons": [
  {"id": "screenshot", "label": "Screenshot", "icon": "camera", "steps": [{"screenshot": true}]},
  {"id": "work", "label": "Work mode", "icon": "monitor", "steps": [{"input": "HDMI 1"}, {"wait": 2}, {"volume_level": 15}]},
  {"id": "bed", "label": "Bedtime", "icon": "moon", "steps": [{"volume_level": 8}, {"sleep": 30}]}
]
```

| Step | Value | Does |
|---|---|---|
| `key` / `hold` | key name (`home`, `back`, `ok`, `up`, `play_pause`, `power`, `input`…) | one press / long press |
| `keys` | list of key names | presses them 0.35 s apart |
| `text` | string | types into the focused field |
| `launch` | app id (`netflix`), package, or `intent://` link | opens it |
| `input` | input name (`HDMI 1`) | switches input |
| `volume` | `up` / `down` / `mute` | |
| `volume_level` | 0–100 | |
| `sleep` | minutes (0 cancels) | sleep timer |
| `power` | `on` / `off` / `toggle` | |
| `screenshot` | `true` | saves a screenshot (below) |
| `wait` | seconds, at most 10 | |

`id`: lowercase letters, digits, `-` and `_`. Icons: camera, monitor, moon, power, tv, music, film, home, game, chart,
server, bolt, star, volume, input, play, pause, settings, link. A button with any step the bridge doesn't know is
skipped (and logged), never half-run.

**iOS Shortcuts / Siri:** each button is `POST http://<bridge>:5400/api/lab/action/<id>` (empty JSON body). Use
"Get Contents of URL" with method POST.

**Hermes / MCP:** `lab_buttons`, `lab_action(id)` and `screenshot_save` are tools on the bridge's MCP server.

## Screenshots: `lab.screenshots`
```json
"screenshots": {
  "targets": ["server", "immich", "nas"],
  "dir": "/var/lib/couchtv/screenshots",
  "nas_dir": "/mnt/nas-tv",
  "immich": {"url": "http://127.0.0.1:2283", "album": "TV screenshots"}
}
```
- `server`: `dir/YYYY-MM-DD/<tv>-<app>-<date>-<time>.png`. These show in the remote's Lab tab, under Screenshots.
- `immich`: uploads and adds to the album (created if missing). Needs `IMMICH_API_KEY=…` in `.env`. Create the key in
  Immich (Account settings → API keys) with asset upload and album permissions.
- `nas`: writes to `nas_dir`, a folder that must already be mounted on the bridge server. It's refused, not
  silently skipped, if it isn't mounted.
- Each target succeeds or fails on its own; the remote says where it saved and why a target failed. Netflix and
  other DRM apps give black frames, and the remote says so.

## Widgets: `lab.sources`, `lab.prometheus`, `lab.pages`
```json
"prometheus": "http://127.0.0.1:9090",
"sources": {"hub": {"url": "http://127.0.0.1:8790/hub/today.json", "auth_env": "DISPLAYOS_HUB_TOKEN", "ttl": 120}},
"pages": [
  {"id": "home", "title": "Lab", "widgets": [
    {"type": "stat", "title": "Due today", "source": "hub", "path": "counts.dueToday"},
    {"type": "stat", "title": "Signal", "source": "prometheus", "query": "mtn_signal_rsrp_dbm", "unit": "dBm"}]},
  {"id": "infra", "title": "Infra", "widgets": [
    {"type": "status", "title": "Scrape targets", "source": "prometheus", "query": "up", "label": "job"}]}
]
```
- **Sources:** a JSON URL. `auth_env` names an `.env` variable sent as `Authorization: Bearer …`. Tokens stay on the
  server; the TV and phone only get finished values. `ttl` is the cache time in seconds (10–3600).
- **Widget types:**
  - `stat`: one value.
  - `text`: a sentence, plus `sub`.
  - `list`: items with `item_title`, `item_sub`.
  - `status`: like `list`, with a green or red dot. From Prometheus it's red when the value is 0; from JSON, `item_ok`
    names the field.
- **JSON paths:** dot paths, numbers index lists (`study.tracks.0.title`).
- **Prometheus:** instant queries. `stat` takes the first series; `list`/`status` show one row per series, named by
  the `label` label.
- **Formatting:** `format` (`percent`, `bytes`, `duration`), `unit`, `decimals`, `max` (rows), `empty` (text when a
  list is empty).
- **Where they show:** every page is a chip on the remote's **Lab** tab. The page with id `home` is also the
  **Lab strip** on the TV's Night look, top right (stat and text widgets only). Display only, so remote navigation
  on the TV is unchanged.

## Keep watching: `home.watch_next_block`
Package names whose Android Watch Next rows are promos, not shows: `["com.tcl.browser"]` (TCL BrowseHere's
"Start Searching" cards).
