#!/usr/bin/env bash
# Read-only inventory of an Android TV over network ADB.
# Changes nothing on the TV: only getprop, dumpsys, pm list, cat /proc, wm size.
# Usage: ./tv-recon.sh <tv-ip>
set -u
TV="${1:?usage: tv-recon.sh <tv-ip>}:5555"
OUT="$(dirname "$0")/out-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
A() { adb -s "$TV" shell "$@" 2>&1; }

{
echo "== identity =="
for p in ro.product.manufacturer ro.product.brand ro.product.model ro.product.name ro.product.device \
         ro.build.fingerprint ro.build.version.release ro.build.version.sdk ro.build.version.security_patch \
         ro.build.display.id ro.build.version.incremental ro.board.platform ro.hardware ro.product.cpu.abi \
         ro.product.locale persist.sys.locale ro.tcl.region ro.product.vendor.model ro.boot.hardware.sku \
         ro.sf.lcd_density ro.config.low_ram ro.debuggable ro.secure; do
  printf '%-36s %s\n' "$p" "$(A getprop "$p" | tr -d '\r')"
done
echo; echo "== kernel ==";  A uname -a
echo; echo "== cpu ==";     A "cat /proc/cpuinfo | grep -E 'Hardware|model name|Processor|CPU part' | sort | uniq -c"
echo "cores: $(A 'nproc')"
echo; echo "== memory =="; A "head -5 /proc/meminfo"
echo; echo "== storage =="; A "df -h /data /system /vendor 2>/dev/null"
echo; echo "== display =="; A wm size; A wm density
A "dumpsys display | grep -E 'mBaseDisplayInfo|supportedModes|mActiveModeId|hdrCapabilities' | head -8"
echo; echo "== network =="; A "ip -4 addr | grep -E 'inet |^[0-9]'"
A "dumpsys wifi | grep -E 'mWifiInfo|Wi-Fi is' | head -3"
echo; echo "== home / launcher =="
A cmd package resolve-activity --brief -c android.intent.category.HOME -a android.intent.action.MAIN
A "dumpsys activity activities | grep -E 'mResumedActivity|ResumedActivity' | head -3"
echo; echo "== webview =="; A "dumpsys webviewupdate | grep -E 'Current WebView|package' | head -5"
echo; echo "== hdmi / tv inputs =="; A "dumpsys tv_input | grep -E 'TvInputInfo|id=' | head -20"
echo; echo "== package counts =="
echo "all:      $(A pm list packages | wc -l)"
echo "system:   $(A pm list packages -s | wc -l)"
echo "3rdparty: $(A pm list packages -3 | wc -l)"
echo "disabled: $(A pm list packages -d | wc -l)"
echo; echo "== top memory users =="; A "dumpsys meminfo | sed -n '/Total PSS by process/,/Total PSS by OOM/p' | head -30"
} | tee "$OUT/summary.txt"

A pm list packages -f            | sort > "$OUT/packages-all.txt"
A pm list packages -3            | sort > "$OUT/packages-3rdparty.txt"
A pm list packages -d            | sort > "$OUT/packages-disabled.txt"
A getprop                                > "$OUT/getprop.txt"
echo; echo "Saved to $OUT"
