# TCL 50P735 → homelab display: inventory and plan

Recon run 2026-11-09 over network ADB, read-only. Specs: [tcl-50p735/README.md](tcl-50p735/README.md). Raw output (local only): `tcl-50p735/out-*/`.

## What the TV actually is

| | Value | What it means |
|---|---|---|
| Variant | `G03_4K_GB` / device `BeyondTV4` | UK/GB firmware. Only ever take GB firmware. |
| Build | `TCL/G03_4K_GB/BeyondTV4:11/RP1A.200622.001/AR09` | Android 11 (SDK 30), patch 2024-03-05 |
| SoC | Realtek RTD288O, 4× Cortex-A55 | Running **32-bit** (`armeabi-v7a`): any APK must ship 32-bit or be pure Java/Kotlin |
| RAM | **2 GB total, ~480 MB free** | The real limit. Light pages, few background apps |
| Storage | `/data` 10 GB, 5.7 GB free; `/system` 94% full | Plenty for apps. Never touch `/system` |
| UI resolution | **1920×1080 @ 60 Hz** (panel is 4K, UI is 1080p) | Design dashboards for 1080p, not 4K |
| HDR | HDR10, HLG, Dolby Vision listed | Video only, not relevant to dashboards |
| WebView | Chrome WebView **156** | Modern: CSS grid, backdrop-filter, SSE and WebSockets all work |
| Home | `com.google.android.apps.tv.launcherx` (Google TV) | Keep it installed and enabled as a fallback |
| Network | Wi-Fi 2.4 GHz, RSSI −40, 300 Mbps | Fine. Give it a DHCP reservation |
| Inputs | 4× HDMI plus tuner and AV | HDMI 1–4 visible to apps |
| Root | No (`ro.secure=1`, `ro.debuggable=0`) | Everything goes through ADB, nothing needs root |
| Apps | 141 total: 129 system, 12 user, 2 already disabled | |

**Biggest memory users** that could be turned off: `com.tcl.bi` (telemetry, 18 MB), `com.tcl.smartalexa` (16 MB),
`com.tcl.overseasappshow` (promo, 11 MB), `com.tcl.MultiScreenInteraction_TV` (18 MB), `com.tcl.messagebox` (13 MB),
`com.tcl.guard` (20 MB). Google's `dreamx` (Ambient, 78 MB) and `katniss` (Assistant, 77 MB together) are the largest,
but turning them off costs you voice search and the screensaver.

**Fit with couch-tv:** v0.12 (released 8 Nov) has `minSdk 25` and is Kotlin plus WebView, so it runs on Android 11
on 32-bit ARM. It is past the 0.10 boot-loop bug.

## Decision: fork couch-tv, add a homelab layer

couch-tv already provides: a replacement home screen, a phone remote, a bridge server (Python) with REST and **MCP**,
and Home Assistant cards. What's missing for us is the homelab/workspace side. So:

```
 TV (couch-tv home, WebView)  ◄──LAN──►  bridge on the homelab server  
   rows: apps | keep watching                 ├─ couch-tv bridge (remote, MCP, TV control)
   NEW: Life · Infra · Agents · Dev · Ambient └─ NEW "lab" plugin: read-only, server-side tokens
                                                   ├─ displayos-hub :8790/hub/today.json
                                                   ├─ Prometheus :9090 / Grafana :3030 (kiosk panels)
                                                   ├─ Hermes :9119 (agents, approvals; read-only)
                                                   └─ AdGuard, Proxmox (read-only role)
 iPhone: couch-tv phone remote PWA + Shortcuts → bridge
 Hermes: MCP tools → "show /infra", "sleep TV"
```

Rules: the TV never holds a privileged token. The bridge fetches everything server-side and gives the TV
pre-shaped JSON. No write endpoints from the TV.

## Phases (each one is reversible; approve each before it starts)

**Phase 1: Debloat. DONE 2026-11-09.** Back up the package list (done). Build a disable list from our real
inventory, cross-checked against CleanYourTV's `tcl-50p735` list. Use `pm disable-user` only, never uninstall.
Keep enabled: `launcherx`, `setupwraith`, `tungsten`, `tvinput`, `tcl.tv`, `system.server`, GMS, Play Store,
`mediashell` (Chromecast), WebView. One undo script. Reboot and check HDMI, YouTube, Netflix and casting.

**Phase 2: couch-tv option A (TV home only).** Install the v0.12 release APK, set it as home with its own `apply.sh`,
reboot test. Google home stays installed as the fallback.

**Phase 3: bridge on wemserver.** Run the couch-tv bridge as a systemd service (option B): phone remote, "put on X",
MCP. Pair the TV once.

**Phase 4: the lab layer (the actual new work, and the public repo).** Fork couch-tv and add:
- `bridge/lab/`: a provider plugin system (displayos-hub, Prometheus, Grafana, Hermes, AdGuard, Proxmox,
  any JSON URL). YAML config, read-only credentials, response caching, SSE push for alerts.
- TV home: new rows and pages (Life, Infra, Agents, Dev) and an Ambient page with the night schedule.
  Remote-navigable, sized for 1080p, light on RAM.
- **Lab Ambient screensaver**: a `DreamService` in the on-TV app that renders the bridge's `/ambient` page
  (clock, agenda, key stats, dimmed at night) in a WebView. Google's own Ambient mode can't show custom
  content, so we replace it: `settings put secure screensaver_components <our dream>`. Undo restores `dreamx`.
- Alert toasts over whatever is playing (node down, backup failed, Hermes needs approval), with quiet hours.
- MCP tools for Hermes: `tv_show_page`, `tv_notify`, `tv_sleep`.

**Phase 5: publish.** Public repo (a fork with upstream credit, or a separate "lab plugin" repo if upstream
would take the plugin hooks). Docs on the TCL path, example configs and a demo video. Content: a build log
for each phase.

## Decisions (2026-11-09)
1. **Voice:** keep Google Assistant (`com.google.android.katniss`, `com.google.android.tv.assistant`), because the
   Google TV phone remote's mic needs it. Turn off Alexa (`com.tcl.smartalexa`) and TCL's own assistant (`com.tcl.assistant`).
   couch-tv's phone remote uses the phone keyboard's dictation for "put on X".
2. **Firmware updates off:** disable `com.tcl.versionUpdateApp`. TCL ships Android upgrades through the same
   updater, so to check for one later: re-enable it, look, then disable it again. Play Store and Google Play system updates stay on.
3. **Repo:** your own repo created as a GitHub fork of Seagey/couch-tv, renamed (e.g. `couch-tv-lab`). This keeps the
   "forked from" link, the MIT license and the upstream copyright. The README credits upstream and lists what you changed.
4. **Widgets:** couch-tv has fixed cards only (Now playing, Home Assistant, doorbell), not a general widget system.
   Phase 4 adds one: `widgets:` in YAML → bridge provider → a card type on the TV (stat, list, sparkline, Grafana image, iframe).
