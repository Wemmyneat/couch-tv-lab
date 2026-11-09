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
Prime Video. What's left for media is Apple TV, Netflix and YouTube, with VLC kept for local files. Not
re-checked over ADB yet because the TV was off.
