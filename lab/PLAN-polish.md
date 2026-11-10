# Polish pass before M4 (2026-11-09)

From the owner's review of the remote on an iPhone. Mockups: the "couch-tv-lab remote redesign" canvas.

## 1. Night look keeps switching to Classic: root cause found
Checked on the TV through WebView remote debugging (fork build with `-PwebDebug=true`):
- Every stored value says `night` (`TVOS.kept`, `localStorage`, bridge settings, config). A reload started by
  the **debugger** draws Night and stays Night (watched for 20 s, 5 scenes).
- A reload started by the **page** (`location.replace` or `location.reload`) is **blocked** by the app's
  WebView (`shouldOverrideUrlLoading` returns `true` for every navigation). So the Look button saves the new
  look but never redraws. The TV keeps whatever it last drew until the app restarts.

**Fix:** a native `TVOS.reload()` in `MainActivity` (it calls `webView.reload()` on the UI thread). `restart()`
uses it when present and falls back to `location.reload()`. Also let same-origin main-frame navigations through
`shouldOverrideUrlLoading`. Needs a TV app build (0.12-lab.3). Report upstream: it affects couch-tv itself.

## 2. Remote tab: one-hand layout (artboard 1)
- **Thumb zone first.** Status and now-playing on top (read, rarely tapped); the touch pad, nav row and
  shortcuts in the lower two-thirds.
- **Touch pad**: swipe to move with a haptic tick per step; tap to select; long-press for the menu.
  Smaller (360 px) and lower than today.
- **Volume wheel** beside the pad: drag to scroll, one haptic tick per volume step, ridges that move under the
  finger, +/− at the ends. iOS Safari's only haptic is the hidden-switch trick already in `haptics.js`. It ticks
  on a tap or drag *end*, not continuously, so the wheel batches: a short haptic at each 2-step detent.
  (Continuous haptics would need a native iOS app. A later option: a tiny SwiftUI app or App Clip.)
- **Nav row**: Back, Home, Play/Pause, Mute as one 4-column row of 56 px buttons.
- **Shortcuts row**: the three most-used custom buttons, plus "↑", which opens a **bottom sheet** with every
  button, Text input, Picture mode and the TV picker.
- The top bar shows the TV name with a live status dot instead of the bare "Home" label.

## 3. Lab tab: actions first, tiny status (artboards 2, 3)
- **Safe area:** content starts at `env(safe-area-inset-top)`. Today the page chips slide under the Dynamic
  Island. The same fix applies to every tab.
- **Status chips** (one line each, tap for detail): router, hub sources n/7, pve1, pve2, inverter.
- **On the TV:** Screenshot, Show DisplayOS (opens a DisplayOS page full-screen on the TV), Show Grafana
  (a kiosk panel), Ambient now.
- **Homelab:** pve1 and pve2 open a **bottom sheet** (CPU, RAM, disk, guests, and "Show on TV"). Read-only: no
  restart or shutdown from a TV remote. Hub actions (add task, log habit, memo) go through the hub's
  `/hub/actions`, which the bridge proxies with its server-side token. Power is the powerOS card.
- The big stat pages move off the phone: you see server stats elsewhere. The phone keeps actions and
  one-glance status; the TV keeps the ambient numbers.
- Data needed: **node_exporter** on pve1 and pve2 (Prometheus `node_*` for CPU, RAM, disk) and the Proxmox API
  with a **read-only PVE token** (`PVEAuditor` role) for guests and their states.

## 4. Screenshots: lazy and paged (artboard 4)
- `GET /api/screenshots?before=<name>&limit=20` paged by date. "Load 20 more", plus auto-load on scroll near
  the end.
- The bridge makes a **thumbnail** (about 20 KB JPEG, 480 px) next to each PNG, using Pillow from wheels.
  `<img loading="lazy">` with a fixed 16:9 box so nothing jumps.
- Tap opens full size, with Share (iOS share sheet) and Delete (server copy; the Immich copy stays).

## 5. Watch tab
Keep as is (the owner likes it), with one fix: it lists **Stan, Prime Video and Google TV**, which are disabled or
uninstalled. The bridge reads `pm list packages`, which includes disabled apps. Use `pm list packages -e`.

## 6. The TV and the server, seamlessly
Already: the bridge reconnects by itself after standby (seen today), and the TV keeps a saved copy of the home
for when the server is down.
- **Fixed addresses:** DHCP reservations on the router for the TV (`.160`) and wemserver (`.10`). Then nothing
  breaks on a lease change.
- **A name, not an IP:** an AdGuard rewrite (AdGuard is already the LAN's DNS on pve1), e.g.
  `couch.home.arpa` → `.10`. The TV app, the phone remote and Shortcuts all use the name.
- **ADB stays open:** port 5555 survives reboots on this TCL (USB debugging alone opens it). The bridge's daily
  guard checks it and the Home watch.
- **Health on the Infra status:** the bridge reports TV reachable, ADB, remote paired, watch bound and the home
  version. An alert fires if any drops (M4).
- **Wake:** Wake-on-LAN over Wi-Fi is unreliable on TVs. Test CEC from an HDMI device, or the Android TV remote
  protocol's power key while the TV is in network standby ("Quick start" or "Instant power on" in TCL settings).
- **Away from home:** Tailscale on wemserver; the remote served over HTTPS on the tailnet name (also unlocks the
  remote's real mic button).

## 7. powerOS (after the Elfin-EW10A arrives)
powerOS already runs on wemserver and is read-only by design. Have it expose **Prometheus metrics**
(`poweros_battery_soc_percent`, `poweros_load_watts`, `poweros_pv_watts`, `poweros_grid_present`…). Then:
- TV strip card "Power · inverter" and a Power status chip on the phone: config only, no bridge code.
- Alerts in M4: grid lost, battery under 30%, inverter overload, exporter silent.
- Ambient (M5): the battery ring as the screensaver's main element at night.

## 8. More improvements worth doing
- **Now playing on the phone lock screen:** the Media Session API on the remote page (title, art, play/pause).
- **Scenes:** "Movie" (lights via Home Assistant later, volume 25, Netflix), "Work" (HDMI 1, Lab strip on).
- **Haptics:** a distinct haptic for "action done" vs "failed" (two ticks).
- **Undo-able screenshot:** the toast has "Delete" for 5 s.
- **Guest mode:** a PIN or a "guest network can't reach the bridge" check on the Infra page, since the bridge has
  no auth.
- **The TV app's own update channel:** cut `v0.12-lab.N` releases on the fork so Home settings › Updates works.
- **Night-time dimming:** the TV home dims the Lab strip and scenes after 23:00 (OLED-style burn-in isn't an issue
  on this VA panel, but glare is).

## Order
1. Night look fix (TV app 0.12-lab.3) and the Watch tab disabled-apps fix.
2. Safe area plus Lab tab rebuild (actions, sheets), with node_exporter and a PVE read-only token.
3. Remote tab rebuild (pad, wheel, nav row, shortcut sheet).
4. Screenshots paging and thumbnails.
5. Fixed addresses and the AdGuard name.
6. Then M4 (alerts + Hermes), with powerOS when the EW10A is in.

---

## Revision after the mockup review (owner's 11 comments, 2026-11-09)
These replace the matching points above where they differ.

**Remote tab (artboard 1, v2)**
- Top bar **as before**: the person switch (Wemmyneat | Both), the current app's name, More, Power. No TV chip.
- **Now playing as before**: artwork, the card takes the show's colour, plus a progress line.
- Touch pad keeps its **chevrons on all four sides**. While a finger is on it, the pad **expands over the volume
  wheel's space** and the wheel shrinks to a thin vertical volume bar, springing back on lift.
  **Pad speed (DPI)** becomes a setting: Settings › Remote, slow / normal / fast, i.e. points of travel per step.
- **Volume wheel stays beside the pad** (right thumb's natural vertical stroke), with a left-hand mirror setting.
  It shows the **audio output**: TV speakers, Soundbar (ARC) or Bluetooth <name>, from `dumpsys audio` over ADB
  (`speaker`, `hdmi`, `bt_a2dp`).
- Nav row is **Play/Pause, Mute, Back**, with **Back at the end** of the row (right thumb).
- **TV Home moves out of the reach zone**: a round button beside the tab bar, not a tab. It presses Home on the TV.
- The tab bar keeps the **original icons** for Remote, Watch and Lab.

**Lab tab (artboard 2)**
- The router chip shows the **active service and a signal percentage**: `5G (NSA) · 74%`. Source:
  `mtn_network_info{network_type}`, plus RSRP of the active RAT (`mtn_signal_rsrp_dbm{tech="5g"}` when
  `mtn_network_type`=5). Percent = (RSRP + 140) / 96, clamped. The same on the TV's Internet widget.
- Adds **TV widgets** (editor) and Screenshots as two entry tiles.

**TV home: widgets on a real grid (artboards 5, 6)**
- The Lab strip becomes a **widget grid**: 2 columns × 4 rows of 96 px cells, top right under the quick
  buttons. Widgets are **1×1 or 2×1** and never stretch to fill the space; empty cells stay empty (invisible).
- **Widget catalog from the server**: `lab.widgets` in the bridge config (what each widget is, its source, its
  allowed sizes). The **layout per TV** is saved on the bridge (`data/widgets.<tv>.json`):
  `[{"id","x","y","w","h"}]`.
- **Editor on the phone** (Lab › TV widgets): drag to arrange, − to remove, + to add from the catalog. The TV
  updates live (SSE). On the TV, hold OK on a widget: Move / Remove.
- Alert toasts (the owner likes them) stay top left; M4 delivers them.
- Fixes the overlap in the owner's TV photo, where the old strip ran into the quick buttons.

**New in the backlog:** pad speed setting, left-hand mirror, audio-output label, widget editor + layout API
(`GET/POST /api/lab/layout`, `GET /api/lab/widgets`).

### Revised order
1. Night look fix (TV app 0.12-lab.3) + Watch tab hides disabled apps.
2. **TV widget grid + layout API + phone widget editor** (replaces the Lab strip).
3. Lab tab: safe area, actions, router chip, pve sheets (node_exporter + read-only PVE token).
4. Remote tab v2: top bar and now-playing as before, expanding pad + wheel, nav row with Back last, TV Home by
   the tabs, pad speed, audio output.
5. Screenshots paging and thumbnails.
6. Fixed addresses and the AdGuard name; then M4 (alerts + Hermes) and powerOS when the EW10A arrives.

**Owner's follow-up (2026-11-09):** the top-bar ⋯ button goes away; ↑ (above the TV Home button) opens a native-style
**bottom sheet with exactly the current ⋯ menu's content** (TV picker, Type to TV, sleep timer, picture mode, Arrange
apps, People). New content waits. Play/Pause is the large centre button of the nav row: Mute · Play/Pause · Back.
