# Phase 1 after-reboot checks

Before: free RAM ~480 MB (`MemAvailable 491756 kB`), 141 packages, 2 disabled.

- [ ] TV boots to the Google TV home with no loop and no setup screen
- [ ] Remote works: buttons, mic button → Google Assistant answers
- [ ] Inputs: HDMI 1–4 switch; the tuner (Live TV) opens
- [ ] YouTube, Netflix and Apple TV play; VLC opens a file from USB
- [ ] Cast from a phone to the TV (Chromecast)
- [ ] Google TV phone remote (Google Home app) connects, mic works
- [ ] Settings → Picture/Sound open; the TCL settings button on the remote works
- [ ] Wi-Fi stays connected; ADB reconnects
- [ ] `adb shell head -3 /proc/meminfo`: record MemAvailable after (expect more than before)

If anything fails: `./debloat.sh undo <tv-ip>`, reboot, then re-disable in halves to find the culprit.
Note: the TV has a second, unused profile (user 10). The list only changes the main profile (user 0).
