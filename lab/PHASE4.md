# Phase 4: the lab layer

This is what makes couch-tv-lab more than a couch-tv install: the TV, the phone remote and Hermes become part of
the homelab. It's built in milestones; each one is a reviewable change on its own branch, deployed to wemserver,
and checked on the TV.

## Where code changes land, and what each needs

| Change in | Reaches the TV by | Needs |
|---|---|---|
| `bridge/` (Python) | `rsync` + `systemctl restart couch-tv-bridge` | nothing new |
| `remote/` (React phone app) | `npm run build` on the server | nothing new |
| `tv-home/web/` (the home page) | served by the bridge in option B, so a deploy is enough | nothing new |
| `tv-home/android/` (the APK: Home watch, screensaver) | build the APK, then `apply.sh` | JDK 21 + Android SDK, unpacked into `build/` (no sudo) |

Most of Phase 4 is bridge + remote + home page, so it ships without rebuilding the TV app.

## M1: reliability fixes and the screenshot button
1. **Home after casting goes to Google's home** (seen at 16:07: two Home events 0.1 s apart; the second fell inside
   the watch's 1.2 s debounce and its re-check didn't fire). Fix in `FireWatch.kt`: on the re-check, trust the last
   *Google home* event rather than the last event of any kind, and re-arm after a cast session ends. Needs an APK
   build. **Keep the Google home installed**: disabling it is what boot-looped TVs on couch-tv ≤0.10.
2. **Look switch doesn't apply on a bridge-served home until an app restart.** Reproduce, fix in `app.js`, and
   send it upstream.
3. **Promo cards in Keep watching** (BrowseHere "Start Searching", "Free Movies & TV"): a `home.watch_next_block`
   package list, filtered in the bridge and the home.
4. **Screenshot button on the phone remote.** `POST /api/screenshot/save` grabs the TV screen and writes it to the
   targets in `config.json` → `screenshots.targets`, and a "Screenshots" sheet in the remote lists recent ones.
   Targets (any combination):
   - `server`: `/var/lib/couchtv/screenshots/YYYY-MM-DD/…png` on wemserver (default)
   - `immich`: upload to an Immich album through Immich's API (an API key kept in `.env`, server side only)
   - `nas`: a folder on a mounted SMB/NFS share (mounted on wemserver, not on the TV)
   - `tv`: `/sdcard/Pictures/couch-tv/` on the TV (shows in the TV's Gallery)

   Netflix and some other apps block screenshots (black image); the bridge says so instead of saving a black file.

## M2: the remote, your way
- **Custom buttons** in `config.json` → `remote.buttons`: each one is a label, an icon and an action. Actions:
  a key or key sequence, launch an app, switch to an input (HDMI 2), a lab page on the TV, a sleep timer, or
  "screenshot". Example: "Work mode" = HDMI 1 + volume 15; "Grafana" = show the Infra page.
- **Layout and theme**: accent colour, which sections show (pad, now playing, watch, lab), button order.
- **iOS Shortcuts / Siri**: the same actions as plain `POST /api/action/<name>` URLs, so a Shortcut or the Action
  button can fire them. No mic needed, and this works instead of Google voice.

## M3: homelab widgets on the TV and the phone
- `bridge/lab/`: small providers, each with server-side credentials and caching:
  `displayos_hub` (today.json, needs its token), `prometheus` (PromQL), `grafana` (rendered panel PNG),
  `immich` (counts, recent), `hermes` (agent status/approvals; needs a read-only token), `json` (any URL).
- `lab.yaml`: pages and widgets, e.g.
  ```yaml
  pages:
    infra:
      - {type: stat, title: CPU, provider: prometheus, query: '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))*100', unit: '%'}
      - {type: grafana, dashboard: node, panel: 3}
    life:
      - {type: list, title: Today, provider: displayos_hub, path: tasks}
  ```
- TV home: a **Lab** row under Keep watching (one card per widget, light enough for 2 GB RAM), and full pages
  opened from it or from the remote. Phone: a **Lab** tab with the same widgets.
- Rule: the TV and the phone only see shaped JSON from the bridge. No token ever reaches them.

## M4: alerts and Hermes
- `POST /api/lab/notify` (and SSE to the home): a toast on the TV home; over apps it needs
  "display over other apps", which the doorbell card already uses. Severity and quiet hours in `lab.yaml`.
- Sources: Prometheus/Alertmanager webhook, Hermes approvals, anything that can POST.
- MCP tools for Hermes (stdio, run on wemserver with `BRIDGE_URL`): `lab_show_page`, `lab_notify`,
  `screenshot_save`, plus the existing `key`, `launch`, `power`, `now`.

## M5: Lab Ambient
A `DreamService` in the TV app that shows the bridge's `/tv/ambient` page (clock, today, key stats, dimmed at night).
Needs an APK build. Undo puts Google's Ambient mode back.

## Voice
You said you don't need voice. Optional, and reversible with `debloat.sh undo`:
disable Google Assistant (`com.google.android.katniss`, `com.google.android.tv.assistant`). The remote's mic
button and Google's search pop-ups stop. Casting and the Google home are unaffected. It frees about 75 MB of RAM.
