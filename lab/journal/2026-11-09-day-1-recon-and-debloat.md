# Day 1: recon and debloat (2026-11-09)

## Starting point
A used TCL 50P735 on the home Wi-Fi, developer options on, no USB cable. Goal: make the TV part of the homelab
and workspace, with DisplayOS, Hermes, Grafana and the rest showing up on it, and release the result publicly.
Two AI plans were on the table (Hermes: Glance plus Fully Kiosk; ChatGPT: a new Next.js DisplayOS).

## Choosing a base
Searched GitHub for "couch tv". [Seagey/couch-tv](https://github.com/Seagey/couch-tv) (MIT, about 350 stars,
launched 26 Oct 2026, very active) has a native Android TV home, a phone remote PWA, and a Python bridge with REST
**and an MCP server**. The bridge is the natural place for homelab integrations, so we fork it rather than build
a second frontend.
Also looked at CleanYourTV (has a 50P735-specific debloat list) and couchlight-tvOS (another CleanYourTV fork).
Upstream warning learned early: couch-tv ≤0.10 disabled the Google home and setup apps and boot-looped some
TVs. Lesson: **never disable `launcherx` or `setupwraith`**.

## Recon
- Found the TV by scanning the LAN for port 5555, then `adb connect` and approved the prompt on the TV.
- Surprises compared with what the AI plans assumed:
  - The UI is **1080p**, not 4K.
  - WebView is **current** (v156), not "dated".
  - The OS runs **32-bit**.
  - Only **2 GB RAM**, with about 480 MB free.
- Full specs: [../tcl-50p735/README.md](../tcl-50p735/README.md).

## Decisions
1. Keep Google Assistant (the phone remote's mic needs it); drop Alexa and TCL's assistant.
2. TCL OTA updater off.
3. Publish as `couch-tv-lab`, a GitHub fork, so the upstream credit is permanent.
4. Widgets: couch-tv only has fixed cards, so building a widget system is this fork's main feature.
5. External SSD: better on the homelab server (Jellyfin) than on the TV. On the TV it's only good for local media.

## Debloat
Cross-checked CleanYourTV's 30-package list against the real inventory (all 30 present), added 4, and wrote our own
`debloat.sh` with plan/apply/undo and a guard list. Dry run, then applied (34/34 disabled), then rebooted.
It booted to the Google TV home in about 30 s with no crashes. Odd finding: `com.tcl.guard` keeps running because
it's marked persistent.

## Next
- Manual checks on the TV (remote mic, HDMI, streaming, casting).
- Phase 2: install the couch-tv v0.12 release as the home.

## Later the same day
Trimmed the streaming apps by hand: uninstalled the ones without a subscription (Disney+ among them) and disabled
Prime Video. What's left for media is Apple TV, Netflix and YouTube, with VLC kept for local files. Checked over ADB
once the TV was back on: Disney+, MX Player, Nova, WeTV, myTV SUPER and Youku uninstalled.

## Phase 2: couch-tv as the home (option A)
Downloaded the v0.12 `couch-tv-home.apk` from upstream Releases and checked its SHA-256 against the release
(`b049cb1f…`). couch-tv's `check-tv.py` said A and B are supported and ADB was open on 5555; `survey-tv.py`
found no ad trackers. Config: one person, Ikole-Ekiti weather, 12-hour clock, all five scenes, dock of 5,
quick buttons Look and Input, weekly update check.

`apply.sh` installed it, switched Google Ambient (`dreamx`) off, and turned on the Home button watch. The
TV kept `launcherx` as the Home-key default (normal on some Google TVs), so the watch brings couch-tv back after
Google's home appears. Pressing Home showed couch-tv with the Waterline scene and the weather.

Findings:
- The TV's system time zone was **GMT+08:00** (factory/region default) with automatic time zone on, so the
  clock was wrong. Fix: Settings › System › Date & time, automatic time zone off, time zone Lagos.
- Keep watching fills from Android's Watch Next list, and the browser app pushes promo cards into it
  ("Start Searching", "Free Movies & TV"). That's a candidate for a lab-side filter.
- The dock came up as YouTube, Netflix, Apple TV, BrowseHere and Gallery; VLC was behind More apps. With
  option A the order is set on the TV (hold OK, Move).
- Fixed by hand on the TV the same afternoon, checked over ADB: time zone `Africa/Lagos` (the clock matches),
  dock now YouTube, Netflix, Apple TV, VLC, Browser, and one Google account left after removing the
  previous owner's.

## Phase 3: the bridge on wemserver (option B)
wemserver (Debian 13 LXC, Python 3.13, Node 22) could reach the TV on 5555 (ADB), 6466/6467 (remote protocol)
and 8009 (Cast). Deployed to `/opt/couch-tv-lab`, running as a dedicated `couchtv` system user rather than root,
because the bridge holds an ADB key that controls the TV. Built the phone remote with npm on the server.

Paired twice from the server: the Android TV remote protocol (6-character code read off the TV) and ADB (Allow on
the TV). Then a hardened systemd unit (`NoNewPrivileges`, `ProtectSystem=strict`, write access only to the app and
its home), and `apply.sh` re-run from the Mac with `BRIDGE_URL`. `/api/health` reports the TV connected with ADB;
`/api/now` sees the home in front, the volume and the person; `/api/screenshot` works.

Findings:
- The remote protocol reports a different MAC (`38:C8:…`) from the Wi-Fi MAC. Wake-on-LAN uses the Wi-Fi one
  and is untested.
- After the switch the TV home came up in the Classic look (the TV sent `look: classic` in its Home settings).
  Classic shows apps in default order, so the dock order looked lost until the Night look was back.
- The bridge has no auth: anyone on the LAN can use the remote. Fine for a home LAN, not for anything wider.
- Follow-up: pressing Night look saved `look: night` to the bridge, but the page kept drawing Classic until
  the app was restarted (`am force-stop app.couchtv.launcher`, then start it). After that: Night look, the
  dock order back, and the bridge's quick buttons. Possible upstream bug in the in-page restart after a
  look change on a bridge-served home; worth reproducing and reporting.
- The phone remote works from the iPhone (keys, power off/on); the bridge reconnected by itself after the TV
  came back from standby.
