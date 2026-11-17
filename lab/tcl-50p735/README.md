# Reference TV: TCL 50P735

Owner's unit, read over network ADB on 2026-11-09 with [tv-recon.sh](tv-recon.sh), which only reads.
Raw output stays local (git-ignored, `out-*/`).

## Identity and firmware
| | |
|---|---|
| Marketing model | TCL 50P735 (50", 4K, "Smart TV Pro") |
| Product / device | `G03_4K_GB` / `BeyondTV4` (**GB region firmware**) |
| Build fingerprint | `TCL/G03_4K_GB/BeyondTV4:11/RP1A.200622.001/AR09:user/release-keys` |
| TCL build | `AR09` (incremental) |
| Android | 11 (SDK 30), Google TV (`launcherx`) |
| Security patch | 2024-03-05 |
| Kernel | 4.14.198+, built Wed 8 May 2024 |
| Root / debuggable | No (`ro.secure=1`, `ro.debuggable=0`) |
| Profiles | Owner (user 0) plus an unused second profile (user 10) |

Firmware policy: only ever take GB firmware for `G03_4K_GB`. The OTA updater (`com.tcl.versionUpdateApp`) is
disabled by choice. TCL ships Android upgrades through that same updater, so to check: re-enable it, open it,
then disable it again.

## Hardware
| | |
|---|---|
| SoC | Realtek RTD288O, 4× Cortex-A55, running 32-bit (`armeabi-v7a`) |
| RAM | 2 GB total, ~460–520 MB available at idle |
| Storage | `/data` 10 GB (5.7 GB free); `/system` 1.9 GB (94% full, never touch) |
| UI resolution | 1920×1080 @ 60 Hz, 320 dpi (the panel is 4K; the UI draws at 1080p) |
| HDR | HDR10, HLG, Dolby Vision listed (types 1–4) |
| Inputs | 4× HDMI, tuner, AV; eARC service present |
| Network | Wi-Fi 2.4 GHz in use (300 Mbps link, strong signal); no Ethernet in use |
| WebView | `com.google.android.webview` **156**: modern, so SSE, WebSockets, CSS grid and backdrop-filter all work |

## What it means for building on it
- **RAM is the constraint.** Keep pages light, avoid heavy blur, and don't keep many apps running in the background.
- **Design for 1080p**, not 4K.
- **APKs must be 32-bit compatible** (pure Kotlin/Java is fine; native libs need `armeabi-v7a`).
- WebView is current, so a modern web UI is fine.

## Apps (before debloat)
141 packages: 129 system, 12 user-installed, 2 already disabled (Stan, Rakuten). User-installed apps: Apple TV,
Disney+, YouTube Kids, TV Browser, MX Player, FM Radio, Note Reminder, WeTV, myTV SUPER, Youku, Nova, VLC.

## Debloat (Phase 1, applied 2026-11-09)
[debloat.txt](debloat.txt): 34 packages, `pm disable-user --user 0`, never uninstalled.
[debloat.sh](debloat.sh) `plan | apply | undo`, with a guard list of packages it will never touch.

Verified after reboot over ADB: boots to the Google TV home in about 30 s, no crash-buffer entries; the tuner,
TV input, Chromecast (`mediashell`) and Google Assistant (`katniss`) are running; 36 packages disabled.

Findings:
- `com.tcl.guard` is a **persistent** system app (`flags=PERSISTENT`), so Android starts it even when disabled.
  Disabling it has no effect on this firmware. It's kept in the list because it's harmless.
- `tcl_system_server` is a native service (pid owned by `system`), separate from the `com.tcl.system.server` package.
- Idle free RAM went from 492 MB before to 461–518 MB after, depending on when it's read. There's no clear gain yet;
  re-measure at steady state. The bigger win is no promo rows, telemetry or auto-installs.

Manual checks remaining: [CHECKLIST.md](CHECKLIST.md).

## Owner's own app changes (after Phase 1, 2026-11-09)
Done by hand on the TV, not by `debloat.sh`. Checked over ADB on 2026-11-09 (135 packages now, was 141):
- Uninstalled: Disney+, MX Player, Nova, WeTV (`com.tencent.qqlivei18n`), myTV SUPER, Youku.
- Disabled: Prime Video (`com.amazon.amazonvideo.livingroom`), plus Stan and Rakuten (already disabled at purchase).
- Media apps kept: **Apple TV, Netflix (system app), YouTube (system app)**. **VLC** is reserved for local media (the SSD).
- Other user apps still installed: YouTube Kids, TV Browser, FM Radio, Note Reminder.

This shapes the couch-tv home config later: those three apps first in the row, VLC next.
