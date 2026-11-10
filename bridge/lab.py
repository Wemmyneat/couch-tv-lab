"""couch-tv-lab: custom remote buttons ("actions") and saving screenshots.

Everything here is configured in config.json under "lab" (docs: lab/LAB.md). Not part of upstream
couch-tv.

Buttons. Each button runs a list of steps, one after another, through the bridge's own API (so the
same checks and the same TV apply as when the phone presses a key):

    {"id": "work", "label": "Work mode", "icon": "monitor",
     "steps": [{"input": "HDMI 1"}, {"wait": 2}, {"volume_level": 15}]}

Step kinds: key, keys (a list), hold (a key, long press), text, launch (an app id, package or
intent:// link), input (an input name), volume ("up"/"down"/"mute"), volume_level (0-100),
sleep (minutes, 0 cancels), power ("on"/"off"/"toggle"), screenshot (true), wait (seconds, at most 10).

Screenshots go to every target in lab.screenshots.targets:
    server   a folder on this computer (lab.screenshots.dir, default bridge/data/screenshots)
    nas      a folder on a mounted NAS share (lab.screenshots.nas_dir); refused if it is not mounted
    immich   uploaded to an Immich album (lab.screenshots.immich: url, album). The API key is read
             from the IMMICH_API_KEY environment variable (.env), never from config.json, and never
             reaches the phone or the TV.
"""
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

import config

S = None  # the server module (set by server.py)
log = logging.getLogger("lab")

LAB = config.CONFIG.get("lab") if isinstance(config.CONFIG.get("lab"), dict) else {}
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,120}\.png")
KEY_RE = re.compile(r"[a-z_0-9]{1,30}")
ICONS = {"camera", "monitor", "moon", "power", "tv", "music", "film", "home", "game", "chart", "server",
         "bolt", "star", "volume", "input", "play", "pause", "settings", "link"}
MAX_STEPS, MAX_WAIT = 20, 10.0

DEFAULT_BUTTONS = [{"id": "screenshot", "label": "Screenshot", "icon": "camera", "steps": [{"screenshot": True}]}]


# ---------- buttons ----------
def _step(s):
    """One step, checked. None when it is not a step this module knows."""
    if not isinstance(s, dict) or len(s) != 1:
        return None
    (kind, v), = s.items()
    if kind in ("key", "hold") and isinstance(v, str) and KEY_RE.fullmatch(v):
        return {kind: v}
    if kind == "keys" and isinstance(v, list) and 0 < len(v) <= 20 and all(isinstance(k, str) and KEY_RE.fullmatch(k) for k in v):
        return {kind: list(v)}
    if kind == "text" and isinstance(v, str) and 0 < len(v) <= 200:
        return {kind: v}
    if kind in ("launch", "input") and isinstance(v, str) and 0 < len(v) <= 300:
        return {kind: v}
    if kind == "volume" and v in ("up", "down", "mute"):
        return {kind: v}
    if kind == "volume_level" and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100:
        return {kind: v}
    if kind == "sleep" and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 600:
        return {kind: v}
    if kind == "power" and v in ("on", "off", "toggle"):
        return {kind: v}
    if kind == "screenshot" and v is True:
        return {kind: True}
    if kind == "open" and isinstance(v, str) and ID_RE.fullmatch(v):   # a page from lab.links, opened on the TV
        return {kind: v}
    if kind == "wall" and v is True:   # DisplayOS on the TV, resuming where it left off
        return {kind: True}
    if kind == "wait" and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= MAX_WAIT:
        return {kind: float(v)}
    return None


def _buttons():
    raw = LAB.get("buttons")
    raw = raw if isinstance(raw, list) else DEFAULT_BUTTONS
    out, seen = [], set()
    for b in raw[:24]:
        if not isinstance(b, dict) or not isinstance(b.get("id"), str) or not ID_RE.fullmatch(b["id"]) or b["id"] in seen:
            continue
        steps = [_step(s) for s in (b.get("steps") or [])][:MAX_STEPS]
        if not steps or any(s is None for s in steps):
            log.warning("lab button %s skipped: a step is not one lab.py knows", b["id"])
            continue
        label = b.get("label") if isinstance(b.get("label"), str) and b["label"].strip() else b["id"]
        icon = b.get("icon") if b.get("icon") in ICONS else "bolt"
        seen.add(b["id"])
        out.append({"id": b["id"], "label": label.strip()[:24], "icon": icon, "steps": steps})
    return out


BUTTONS = _buttons()


async def _self(method, path, payload, tv_id):
    url = f"http://127.0.0.1:{S.PORT}{path}" + (f"?tv={tv_id}" if tv_id else "")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as s:
        async with s.request(method, url, json=payload) as r:
            j = await r.json(content_type=None)
            if not j.get("ok"):
                raise RuntimeError(j.get("error") or f"{path} failed")
            return j


async def run_step(step, tv_id):
    (kind, v), = step.items()
    if kind == "wait":
        await asyncio.sleep(v)
        return {"wait": v}
    if kind == "key":
        return await _self("POST", "/api/key", {"key": v}, tv_id)
    if kind == "hold":
        return await _self("POST", "/api/key", {"key": v, "hold": True}, tv_id)
    if kind == "keys":
        for k in v:
            await _self("POST", "/api/key", {"key": k}, tv_id)
            await asyncio.sleep(0.35)
        return {"keys": v}
    if kind == "text":
        return await _self("POST", "/api/text", {"text": v}, tv_id)
    if kind == "launch":
        return await _self("POST", "/api/launch", {"app": v}, tv_id)
    if kind == "input":
        return await _self("POST", "/api/input", {"name": v}, tv_id)
    if kind == "volume":
        return await _self("POST", "/api/volume", {"action": v}, tv_id)
    if kind == "volume_level":
        return await _self("POST", "/api/volume", {"level": v}, tv_id)
    if kind == "sleep":
        return await _self("POST", "/api/sleep", {"minutes": v}, tv_id)
    if kind == "power":
        return await _self("POST", "/api/power", {"state": v}, tv_id)
    if kind == "screenshot":
        return await save_screenshot(tv_id)
    if kind == "open":
        return await open_on_tv(v, tv_id)
    if kind == "wall":
        return await show_wall(tv_id)
    raise RuntimeError(f"unknown step {kind}")


def _tv_id(request, data=None):
    t = request.query.get("tv") or (data or {}).get("tv")
    return t if isinstance(t, str) and t in S.TVS else S._current.get()


async def h_buttons(request):
    return S.ok(buttons=[{k: b[k] for k in ("id", "label", "icon")} for b in BUTTONS])


async def h_action(request):
    data = await S.body(request)
    bid = request.match_info.get("id") or data.get("id")
    b = next((x for x in BUTTONS if x["id"] == bid), None)
    if not b:
        raise S.ApiError(404, f"no button {bid!r} in lab.buttons")
    tv_id = _tv_id(request, data)
    done = []
    for step in b["steps"]:
        try:
            r = await run_step(step, tv_id)
        except Exception as e:
            log.info("button %s stopped at %s: %s", bid, step, e)
            S.record_action(request, "lab_action", {"id": bid}, False)
            return web.json_response({"ok": False, "error": str(e), "id": bid, "done": done, "failed": step}, status=502)
        done.append({"step": step, "result": {k: v for k, v in (r or {}).items() if k in ("saved", "errors", "note", "name")}})
    S.record_action(request, "lab_action", {"id": bid}, True)
    last = done[-1]["result"] if done else {}
    return S.ok(id=bid, label=b["label"], done=len(done), **last)


# ---------- screenshots ----------
SHOTS = LAB.get("screenshots") if isinstance(LAB.get("screenshots"), dict) else {}
TARGETS = [t for t in (SHOTS.get("targets") or ["server"]) if t in ("server", "nas", "immich")] or ["server"]
SHOT_DIR = SHOTS.get("dir") if isinstance(SHOTS.get("dir"), str) and SHOTS["dir"].startswith("/") else os.path.join(config.DATA, "screenshots")
NAS_DIR = SHOTS.get("nas_dir") if isinstance(SHOTS.get("nas_dir"), str) and SHOTS["nas_dir"].startswith("/") else None
IMMICH = SHOTS.get("immich") if isinstance(SHOTS.get("immich"), dict) else {}
IMMICH_URL = (IMMICH.get("url") or "http://127.0.0.1:2283").rstrip("/")
IMMICH_ALBUM = (IMMICH.get("album") or "TV screenshots")[:80]
BLANK_BYTES = 30_000   # a 1080p PNG this small is a black frame: Netflix and others block screenshots
_album_id = None


def _write(folder, name, png):
    day = os.path.join(folder, name[-21:-11])  # ...-YYYY-MM-DD-HHMMSS.png -> YYYY-MM-DD
    os.makedirs(day, exist_ok=True)
    path = os.path.join(day, name)
    with open(path, "wb") as f:
        f.write(png)
    return path


async def _immich_upload(name, png, when):
    global _album_id
    key = os.environ.get("IMMICH_API_KEY")
    if not key:
        raise RuntimeError("IMMICH_API_KEY is not set in .env")
    h = {"x-api-key": key, "Accept": "application/json"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
        form = aiohttp.FormData()
        stamp = when.isoformat()
        for k, v in (("deviceAssetId", name), ("deviceId", "couch-tv-lab"), ("fileCreatedAt", stamp), ("fileModifiedAt", stamp)):
            form.add_field(k, v)
        form.add_field("assetData", png, filename=name, content_type="image/png")
        async with s.post(f"{IMMICH_URL}/api/assets", data=form, headers=h) as r:
            j = await r.json(content_type=None)
            if r.status >= 300 or "id" not in j:
                log.info("Immich upload refused: %s %s", r.status, str(j)[:200])
                raise RuntimeError(f"Immich refused the upload ({r.status})")
            asset = j["id"]
        if not _album_id:
            async with s.get(f"{IMMICH_URL}/api/albums", headers=h) as r:
                albums = await r.json(content_type=None)
            _album_id = next((a["id"] for a in albums if isinstance(a, dict) and a.get("albumName") == IMMICH_ALBUM), None)
            if not _album_id:
                async with s.post(f"{IMMICH_URL}/api/albums", json={"albumName": IMMICH_ALBUM}, headers=h) as r:
                    _album_id = (await r.json(content_type=None)).get("id")
        if _album_id:
            async with s.put(f"{IMMICH_URL}/api/albums/{_album_id}/assets", json={"ids": [asset]}, headers=h) as r:
                if r.status >= 300:
                    raise RuntimeError(f"uploaded, but adding to the album failed ({r.status})")
    return asset


async def save_screenshot(tv_id=None):
    tv_id = tv_id or S._current.get()
    tok = S._current.set(tv_id)
    try:
        png = await S.tv.screenshot()
        app = ((S.now_payload().get("app") or {}).get("name") or "tv")
    finally:
        S._current.reset(tok)
    when = datetime.now(S.HOME_TZ)   # the home's time zone, not the server's (wemserver runs on UTC)
    app = re.sub(r"[^A-Za-z0-9]+", "-", app).strip("-")[:30] or "tv"
    name = f"{tv_id}-{app}-{when:%Y-%m-%d-%H%M%S}.png"
    saved, errors = [], []
    for t in TARGETS:
        try:
            if t == "server":
                _write(SHOT_DIR, name, png)
                saved.append("server")
            elif t == "nas":
                if not NAS_DIR or not os.path.isdir(NAS_DIR):
                    raise RuntimeError("the NAS folder is not mounted")
                await asyncio.to_thread(_write, NAS_DIR, name, png)
                saved.append("nas")
            elif t == "immich":
                await _immich_upload(name, png, when)
                saved.append("immich")
        except Exception as e:
            log.info("screenshot to %s failed: %s", t, e)
            # only messages this module wrote itself go to the phone; anything else stays in the log
            errors.append({"target": t, "error": str(e)[:120] if isinstance(e, RuntimeError) else "failed (see the bridge log)"})
    note = "looks blank: this app blocks screenshots" if len(png) < BLANK_BYTES else None
    return {"ok": bool(saved), "name": name, "saved": saved, "errors": errors, "note": note}


async def h_shot_save(request):
    data = await S.body(request)
    r = await save_screenshot(_tv_id(request, data))
    S.record_action(request, "screenshot_save", {}, r["ok"])
    if not r["ok"]:
        return web.json_response({"ok": False, "error": "not saved anywhere", **r}, status=502)
    return S.ok(**{k: v for k, v in r.items() if k != "ok"})


async def h_shot_list(request):
    out = []
    if os.path.isdir(SHOT_DIR):
        for day in sorted(os.listdir(SHOT_DIR), reverse=True)[:14]:
            d = os.path.join(SHOT_DIR, day)
            if os.path.isdir(d):
                out += [n for n in sorted(os.listdir(d), reverse=True) if NAME_RE.fullmatch(n)]
            if len(out) >= 60:
                break
    return S.ok(shots=[{"name": n, "url": f"/api/screenshots/{n}"} for n in out[:60]], targets=TARGETS)


async def h_shot_file(request):
    name = request.match_info["name"]
    if not NAME_RE.fullmatch(name):
        raise S.ApiError(400, "bad name")
    path = os.path.join(SHOT_DIR, name[-21:-11], name)
    if not os.path.isfile(path):
        raise S.ApiError(404, "no such screenshot")
    return web.FileResponse(path, headers={"Cache-Control": "no-store"})   # private captures: never cached


# ---------- widgets: homelab data on the TV and the phone ----------
# lab.sources names JSON endpoints (with an optional token read from .env); "prometheus" is built in.
# lab.pages lists pages of widgets. The page with id "home" is the Lab row on the TV home.
# The bridge fetches and shapes everything; the TV and the phone only get finished values.
SOURCES = {}
for _n, _s in (LAB.get("sources") or {}).items():
    if isinstance(_s, dict) and isinstance(_s.get("url"), str) and re.match(r"https?://", _s["url"]) and ID_RE.fullmatch(_n):
        SOURCES[_n] = {"url": _s["url"], "auth_env": _s.get("auth_env") if isinstance(_s.get("auth_env"), str) else None,
                       "ttl": max(10, min(int(_s.get("ttl") or 60), 3600))}
PROM_URL = (LAB.get("prometheus") or "http://127.0.0.1:9090").rstrip("/")
TYPES = ("stat", "list", "status", "text")
_cache = {}   # key -> (expires, value)


def _pages():
    out = []
    for p in (LAB.get("pages") or [])[:12]:
        if not isinstance(p, dict) or not isinstance(p.get("id"), str) or not ID_RE.fullmatch(p["id"]):
            continue
        ws = []
        for i, w in enumerate((p.get("widgets") or [])[:16]):
            if not isinstance(w, dict) or w.get("type") not in TYPES:
                continue
            src = w.get("source")
            if src != "prometheus" and src not in SOURCES:
                log.warning("lab widget %s/%d skipped: unknown source %r", p["id"], i, src)
                continue
            ws.append(dict(w, id=f"{p['id']}-{i}"))
        out.append({"id": p["id"], "title": str(p.get("title") or p["id"])[:30], "widgets": ws})
    return out


PAGES = _pages()


def _dig(v, path):
    """'study.tracks.0.title' -> the value at that path, or None."""
    for part in [x for x in str(path or "").split(".") if x]:
        if isinstance(v, list) and part.isdigit() and int(part) < len(v):
            v = v[int(part)]
        elif isinstance(v, dict):
            v = v.get(part)
        else:
            return None
    return v


def _fmt(v, fmt, decimals, unit):
    if v is None:
        return "–"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)[:60]
    if fmt == "bytes":
        for u in ("B", "KB", "MB", "GB", "TB"):
            if abs(x) < 1024 or u == "TB":
                return f"{x:.{1 if u != 'B' else 0}f} {u}"
            x /= 1024
    if fmt == "duration":
        d, h, m = int(x // 86400), int(x % 86400 // 3600), int(x % 3600 // 60)
        return f"{d}d {h}h" if d else f"{h}h {m}m"
    if fmt == "percent":
        return f"{x:.{decimals}f}%"
    s = f"{x:.{decimals}f}" if decimals else f"{x:.0f}"
    return f"{s} {unit}".strip() if unit else s


async def _get_json(url, headers, ttl):
    hit = _cache.get(url)
    if hit and hit[0] > time.time():
        return hit[1]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
        async with s.get(url, headers=headers) as r:
            if r.status >= 300:
                raise RuntimeError(f"{r.status} from the source")
            j = await r.json(content_type=None)
    _cache[url] = (time.time() + ttl, j)
    return j


async def _source(name):
    src = SOURCES[name]
    h = {}
    if src["auth_env"]:
        tok = os.environ.get(src["auth_env"])
        if not tok:
            raise RuntimeError(f"{src['auth_env']} is not set in .env")
        h["Authorization"] = f"Bearer {tok}"
    return await _get_json(src["url"], h, src["ttl"])


async def _prom(query, ttl):
    from urllib.parse import urlencode
    j = await _get_json(f"{PROM_URL}/api/v1/query?{urlencode({'query': query})}", {}, ttl)
    if j.get("status") != "success":
        raise RuntimeError(j.get("error") or "query failed")
    return j["data"]["result"]


async def render_widget(w):
    out = {"id": w["id"], "type": w["type"], "title": str(w.get("title") or "")[:40], "ok": True}
    fmt, dec, unit = w.get("format"), int(w.get("decimals") or 0), str(w.get("unit") or "")[:8]
    limit = max(1, min(int(w.get("max") or 5), 12))
    try:
        if w["source"] == "prometheus":
            res = await _prom(str(w.get("query") or ""), int(w.get("ttl") or 30))
            if w["type"] == "stat":
                if w.get("value_label"):   # a label as the value, e.g. network_type="5G(NSA)"
                    out["value"] = str(res[0]["metric"].get(w["value_label"], "–"))[:24] if res else "–"
                else:
                    v = res[0]["value"][1] if res else None
                    out["value"] = _fmt(v, fmt, dec, unit)
                if w.get("sub_query"):   # a second, smaller line from another query
                    sub = await _prom(str(w["sub_query"]), int(w.get("ttl") or 30))
                    out["sub"] = _fmt(sub[0]["value"][1] if sub else None, w.get("sub_format"),
                                      int(w.get("sub_decimals") or 0), str(w.get("sub_unit") or "")[:8])
            else:
                lab_key = w.get("label") or "instance"
                out["items"] = [{"title": str(r["metric"].get(lab_key, "?"))[:40],
                                 "sub": _fmt(r["value"][1], fmt, dec, unit),
                                 "ok": (float(r["value"][1]) > 0) if w["type"] == "status" else None}
                                for r in res[:limit]]
        else:
            data = await _source(w["source"])
            v = _dig(data, w.get("path"))
            if w["type"] == "stat":
                out["value"] = _fmt(v, fmt, dec, unit)
            elif w["type"] == "text":
                out["value"] = str(_dig(v, w.get("text")) if w.get("text") else v or "")[:280]
                if w.get("sub"):
                    out["sub"] = str(_dig(v, w["sub"]) or "")[:80]
            else:
                items = v if isinstance(v, list) else []
                t, sub, okp = w.get("item_title") or "title", w.get("item_sub"), w.get("item_ok")
                out["items"] = [{"title": str(_dig(it, t) or "")[:60], "sub": str(_dig(it, sub) or "")[:60] if sub else "",
                                 "ok": bool(_dig(it, okp)) if okp else None} for it in items[:limit]]
                out["more"] = max(0, len(items) - limit)
                if not items and w.get("empty"):
                    out["empty"] = str(w["empty"])[:60]
    except Exception as e:
        log.info("lab widget %s failed: %s", w["id"], e)
        out.update(ok=False, error=str(e)[:120] if isinstance(e, RuntimeError) else "source unavailable")
    return out


# ---------- the TV's widget grid ----------
# lab.widgets is the catalog: widget definitions (as in lab.pages) plus "id" and "sizes" ([[1,1],[2,1]]).
# Each TV keeps its own layout in data/widgets.<tv>.json: [{"id","x","y","w","h"}] on a GRID_COLS x
# GRID_ROWS grid. Widgets never stretch to fill space; empty cells stay empty.
GRID_COLS, GRID_ROWS = 2, 4
CATALOG = {}
for _w in (LAB.get("widgets") or [])[:40]:
    if not isinstance(_w, dict) or not isinstance(_w.get("id"), str) or not ID_RE.fullmatch(_w["id"]) or _w["id"] in CATALOG:
        continue
    if _w.get("type") not in TYPES or (_w.get("source") != "prometheus" and _w.get("source") not in SOURCES):
        log.warning("lab widget %s skipped: unknown type or source", _w.get("id"))
        continue
    _sizes = [s for s in (_w.get("sizes") or [[1, 1]]) if isinstance(s, list) and len(s) == 2
              and all(isinstance(n, int) and not isinstance(n, bool) for n in s) and 1 <= s[0] <= GRID_COLS and 1 <= s[1] <= GRID_ROWS]
    CATALOG[_w["id"]] = dict(_w, sizes=_sizes or [[1, 1]])


def _layout_file(tv_id):
    return os.path.join(config.DATA, f"widgets.{tv_id}.json")


def _valid_layout(items):
    """Only catalog widgets, once each, in an allowed size, inside the grid, not overlapping."""
    out, taken = [], set()
    for it in (items if isinstance(items, list) else [])[:GRID_COLS * GRID_ROWS]:
        if not isinstance(it, dict) or it.get("id") not in CATALOG or any(o["id"] == it["id"] for o in out):
            continue
        try:
            x, y, w, h = (int(it.get(k, d)) for k, d in (("x", 0), ("y", 0), ("w", 1), ("h", 1)))
        except (TypeError, ValueError):
            continue
        if [w, h] not in CATALOG[it["id"]]["sizes"] or x < 0 or y < 0 or x + w > GRID_COLS or y + h > GRID_ROWS:
            continue
        cells = {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}
        if cells & taken:
            continue
        taken |= cells
        out.append({"id": it["id"], "x": x, "y": y, "w": w, "h": h})
    return out


def _default_layout():
    """lab.default_layout if given, else the catalog in order, each at its first size, first free spot."""
    if isinstance(LAB.get("default_layout"), list):
        return _valid_layout(LAB["default_layout"])
    placed = []
    for wid, w in CATALOG.items():
        cw, ch = w["sizes"][0]
        for y in range(GRID_ROWS):
            spot = next((x for x in range(GRID_COLS - cw + 1)
                         if _valid_layout(placed + [{"id": wid, "x": x, "y": y, "w": cw, "h": ch}]) != _valid_layout(placed)), None)
            if spot is not None:
                placed = _valid_layout(placed + [{"id": wid, "x": spot, "y": y, "w": cw, "h": ch}])
                break
    return placed


def load_layout(tv_id):
    try:
        with open(_layout_file(tv_id)) as f:
            return _valid_layout(json.load(f))
    except (OSError, ValueError):
        return _default_layout()


async def h_widgets(request):
    return S.ok(cols=GRID_COLS, rows=GRID_ROWS, widgets=[
        {"id": w["id"], "title": str(w.get("title") or w["id"])[:40], "type": w["type"], "sizes": w["sizes"],
         "note": str(w.get("note") or "")[:60]} for w in CATALOG.values()])


async def h_layout_get(request):
    tv_id = _tv_id(request)
    items = load_layout(tv_id)
    rendered = await asyncio.gather(*(render_widget(dict(CATALOG[i["id"]], id=i["id"])) for i in items))
    for i, r in zip(items, rendered):
        i["widget"] = r
    return S.ok(tv=tv_id, cols=GRID_COLS, rows=GRID_ROWS, items=items, at=S.now_iso())


async def h_layout_post(request):
    data = await S.body(request)
    tv_id = _tv_id(request, data)
    items = _valid_layout(data.get("items"))
    if len(items) != len(data.get("items") or []):
        raise S.ApiError(400, "layout refused: unknown widget, size not allowed, outside the grid or overlapping")
    os.makedirs(config.DATA, exist_ok=True)
    tmp = _layout_file(tv_id) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f)
    os.replace(tmp, _layout_file(tv_id))
    S.record_action(request, "lab_layout", {"items": len(items)}, True)
    return S.ok(tv=tv_id, items=items)


async def h_pages(request):
    return S.ok(pages=[{"id": p["id"], "title": p["title"], "widgets": len(p["widgets"])} for p in PAGES])


async def h_page(request):
    pid = request.match_info["id"]
    p = next((x for x in PAGES if x["id"] == pid), None)
    if not p:
        raise S.ApiError(404, f"no lab page {pid!r}")
    widgets = await asyncio.gather(*(render_widget(w) for w in p["widgets"]))
    return S.ok(id=p["id"], title=p["title"], widgets=list(widgets), at=S.now_iso())


# ---------- the Lab tab: status chips, pages to open on the TV, hub actions ----------
URL_RE = re.compile(r"https?://[A-Za-z0-9.:/_%?=&#~+@,;-]{1,500}")
PKG_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")
LINKS = {}
for _id, _l in (LAB.get("links") or {}).items():
    if ID_RE.fullmatch(str(_id)) and isinstance(_l, dict) and URL_RE.fullmatch(str(_l.get("url") or "")):
        LINKS[_id] = {"label": str(_l.get("label") or _id)[:24], "url": _l["url"],
                      "app": _l["app"] if PKG_RE.fullmatch(str(_l.get("app") or "")) else "com.internet.tvbrowser"}
HOSTS = [h for h in (LAB.get("hosts") or [])[:12] if isinstance(h, dict) and ID_RE.fullmatch(str(h.get("id") or ""))
         and isinstance(h.get("host"), str) and re.fullmatch(r"[A-Za-z0-9.-]{1,100}", h["host"]) and isinstance(h.get("port"), int)]
HUB = LAB.get("hub_source") if LAB.get("hub_source") in SOURCES else None


async def open_on_tv(link_id, tv_id):
    import shlex
    link = LINKS.get(link_id)
    if not link:
        raise RuntimeError(f"no link {link_id!r} in lab.links")
    tok = S._current.set(tv_id)
    try:
        # adb shell joins its arguments into one string for the TV's shell, so the URL is quoted
        await S.tv.adb("shell", "am", "start", "-a", "android.intent.action.VIEW",
                       "-d", shlex.quote(link["url"]), "-p", link["app"])
    finally:
        S._current.reset(tok)
    return {"note": f"Opened {link['label']} on the TV"}


async def _reachable(host, port):
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), 2)
        w.close()
        return True
    except Exception:
        return False


async def h_status(request):
    chips = []
    net = CATALOG.get("internet")
    if net:
        r = await render_widget(dict(net, id="internet"))
        chips.append({"id": "internet", "label": f"{r.get('value', '–')} · {r.get('sub', '')}".strip(" ·") if r["ok"] else "Router",
                      "state": "ok" if r["ok"] else "down"})
    if HUB:
        try:
            src = (await _source(HUB)).get("sources") or []
            good = sum(1 for s in src if s.get("ok"))
            chips.append({"id": "hub", "label": f"Hub {good}/{len(src)}", "state": "ok" if good == len(src) else "warn"})
        except Exception as e:
            log.info("hub status failed: %s", e)
            chips.append({"id": "hub", "label": "Hub", "state": "down"})
    pve_res = await asyncio.gather(*(asyncio.wait_for(pve_summary(p), 6) for p in PVE), return_exceptions=True)
    for pid, sm in zip(PVE, pve_res):
        if isinstance(sm, Exception):
            log.info("proxmox %s chip failed: %s", pid, sm)
            chips.append({"id": pid, "label": PVE[pid]["label"], "state": "down", "pve": True})
        else:
            chips.append({"id": pid, "label": f"{sm['label']} · {sm['cpu']}% · {sm['mem_gb']}/{sm['memtotal_gb']} GB", "state": "ok", "pve": True})
    ups = await asyncio.gather(*(_reachable(h["host"], h["port"]) for h in HOSTS))
    chips += [{"id": h["id"], "label": str(h.get("label") or h["id"])[:20], "state": "ok" if up else "down"} for h, up in zip(HOSTS, ups)]
    if LAB.get("power_pending"):
        chips.append({"id": "power", "label": str(LAB["power_pending"])[:40], "state": "idle"})
    return S.ok(chips=chips, links=[{"id": k, "label": v["label"]} for k, v in LINKS.items()], hub=bool(HUB))


async def h_hub(request):
    if not HUB:
        raise S.ApiError(404, "no lab.hub_source")
    d = await _source(HUB)
    tasks = [{"id": t["id"], "title": str(t.get("title") or "")[:80], "due": bool(t.get("dueToday")), "overdue": bool(t.get("overdue"))}
             for t in (d.get("tasks") or []) if isinstance(t, dict) and isinstance(t.get("id"), str) and not t.get("done")][:30]
    habits = [{"id": h["id"], "title": str(h.get("title") or h.get("name") or "")[:80], "done": bool(h.get("doneToday"))}
              for h in (d.get("habits") or []) if isinstance(h, dict) and isinstance(h.get("id"), str)][:30]
    return S.ok(tasks=tasks, habits=habits)


async def h_hub_action(request):
    """Only the hub's two actions, forwarded with the bridge's own token: complete a task, check a habit."""
    if not HUB:
        raise S.ApiError(404, "no lab.hub_source")
    data = await S.body(request)
    kind, iid = data.get("type"), data.get("id")
    if kind not in ("complete-task", "check-habit") or not isinstance(iid, str) or not re.fullmatch(r"[A-Za-z0-9:@._-]{1,120}", iid):
        raise S.ApiError(400, "type must be complete-task or check-habit, with an id")
    payload = {"type": kind, "id": iid}
    if kind == "check-habit":
        payload["done"] = data.get("done") is not False
    src = SOURCES[HUB]
    url = src["url"].rsplit("/hub/", 1)[0] + "/hub/actions"
    tok = os.environ.get(src["auth_env"] or "")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.post(url, json=payload, headers={"Authorization": f"Bearer {tok}"}) as r:
            if r.status >= 300:
                log.info("hub action %s refused: %s %s", kind, r.status, (await r.text())[:200])
                raise S.ApiError(502, f"the hub refused it ({r.status})")
    _cache.pop(src["url"], None)   # the next read shows the change
    S.record_action(request, "hub_action", payload, True)
    return S.ok(**payload)


# ---------- Proxmox hosts (read-only API token, pinned certificate) ----------
# lab.proxmox: [{"id","label","host","node","token_env","fingerprint"}]. The token is a PVEAuditor API token
# kept in .env ("user@realm!name=secret"); it can only read. Proxmox serves a self-signed certificate, so
# instead of trusting any certificate the bridge pins each host's SHA-256 fingerprint.
FP_RE = re.compile(r"([0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}")
PVE = {}
for _p in (LAB.get("proxmox") or [])[:8]:
    if (isinstance(_p, dict) and ID_RE.fullmatch(str(_p.get("id") or "")) and re.fullmatch(r"[A-Za-z0-9.-]{1,100}", str(_p.get("host") or ""))
            and re.fullmatch(r"[A-Za-z0-9_-]{1,60}", str(_p.get("node") or "")) and isinstance(_p.get("token_env"), str) and FP_RE.fullmatch(str(_p.get("fingerprint") or ""))):
        PVE[_p["id"]] = dict(_p, label=str(_p.get("label") or _p["id"])[:20])


class PveCertMismatch(RuntimeError):
    pass


async def _pve(p, path):
    tok = os.environ.get(p["token_env"])
    if not tok:
        raise RuntimeError("not configured")
    fp = aiohttp.Fingerprint(bytes.fromhex(p["fingerprint"].replace(":", "")))
    url = f"https://{p['host']}:8006/api2/json{path}"
    hit = _cache.get(url)
    if hit and hit[0] > time.time():
        if isinstance(hit[1], Exception):   # failures are remembered briefly too: a down host is not re-dialled per poll
            raise hit[1]
        return hit[1]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as s:
            async with s.get(url, headers={"Authorization": f"PVEAPIToken={tok}"}, ssl=fp) as r:
                if r.status >= 300:
                    raise RuntimeError(f"Proxmox answered {r.status}")
                data = (await r.json(content_type=None)).get("data")
    except aiohttp.ServerFingerprintMismatch as e:
        log.warning("proxmox %s: certificate does not match the pinned fingerprint (%s)", p["id"], e)
        err = PveCertMismatch("certificate does not match the pinned one")
        _cache[url] = (time.time() + 60, err)
        raise err
    except Exception as e:
        _cache[url] = (time.time() + 20, e if isinstance(e, RuntimeError) else RuntimeError("not answering"))
        raise
    _cache[url] = (time.time() + 30, data)
    return data


def _gb(n):
    return round((n or 0) / 2**30, 1)


async def pve_summary(pid):
    p = PVE[pid]
    node = f"/nodes/{p['node']}"
    st, lxc, qemu, storage = await asyncio.gather(_pve(p, f"{node}/status"), _pve(p, f"{node}/lxc"), _pve(p, f"{node}/qemu"),
                                                  _pve(p, f"{node}/storage"), return_exceptions=True)
    if isinstance(st, Exception):
        raise st
    partial = [n for n, r in (("guests", lxc), ("guests", qemu), ("storage", storage)) if isinstance(r, Exception)]
    guests = []
    for kind, rows in (("ct", lxc), ("vm", qemu)):
        for g in (rows if isinstance(rows, list) else []):
            guests.append({"id": int(g.get("vmid") or 0), "kind": kind, "name": str(g.get("name") or "")[:40], "status": str(g.get("status") or ""),
                           "cpu": round(float(g.get("cpu") or 0) * 100), "mem_gb": _gb(g.get("mem")), "maxmem_gb": _gb(g.get("maxmem"))})
    disks = [{"name": str(d.get("storage"))[:30], "used_gb": _gb(d.get("used")), "total_gb": _gb(d.get("total"))}
             for d in (storage if isinstance(storage, list) else []) if d.get("active") and d.get("total")]
    return {"id": pid, "label": p["label"], "node": p["node"], "online": True,
            "cpu": round(float(st.get("cpu") or 0) * 100), "cores": (st.get("cpuinfo") or {}).get("cpus"),
            "mem_gb": _gb((st.get("memory") or {}).get("used")), "memtotal_gb": _gb((st.get("memory") or {}).get("total")),
            "root_gb": _gb((st.get("rootfs") or {}).get("used")), "roottotal_gb": _gb((st.get("rootfs") or {}).get("total")),
            "uptime_h": int((st.get("uptime") or 0) // 3600), "load": (st.get("loadavg") or [None])[0],
            "guests": sorted(guests, key=lambda g: g["id"]), "storage": disks, "partial": sorted(set(partial))}


async def h_host(request):
    pid = request.match_info["id"]
    if pid not in PVE:
        raise S.ApiError(404, "no such host")
    try:
        body = {"ok": True, **await pve_summary(pid)}
    except Exception as e:
        log.info("proxmox %s failed: %s", pid, e)
        body = {"ok": True, "id": pid, "label": PVE[pid]["label"], "online": False,
                "error": str(e) if isinstance(e, PveCertMismatch) else "not answering"}
    return web.json_response(body, headers={"Cache-Control": "no-store"})


# ---------- DisplayOS wall on the TV ----------
# The TV app's Wall screen (WallActivity) rotates the same dashboards as DisplayOS on the Mac. The bridge
# reads a copy of displayos.yaml (lab.wall.config, synced from the Mac by lab/displayos-sync.sh) and turns
# it into a plan the TV follows: slides of at most WALL_PANES dashboards side by side, an interlude after
# every N slides (clock, weather, verse), and quiet hours. Self-signed dashboards (insecureTLS) are pinned:
# the TV accepts only the certificate fingerprint the bridge reports for that host.
WALL = LAB.get("wall") if isinstance(LAB.get("wall"), dict) else {}
WALL_PANES = 2          # a 2 GB TV keeps two dashboards on screen; the interlude covers loading the next slide
_wall_cache = {"mtime": None, "plan": None}
_fp_cache = {}
TV_INTERLUDES = ("clock", "weather", "verse")


def _declared_pins():
    """Certificate pins for self-signed dashboards, declared by the operator (never learned at runtime):
    lab.wall.pins {"host:port": "AA:BB:..."} plus every lab.proxmox host's fingerprint on port 8006."""
    pins = {}
    for hp, fp in (WALL.get("pins") or {}).items():
        if re.fullmatch(r"[A-Za-z0-9.-]{1,100}:\d{1,5}", str(hp)) and FP_RE.fullmatch(str(fp)):
            pins[hp] = fp.replace(":", "").upper()
    for p in PVE.values():
        pins.setdefault(f"{p['host']}:8006", p["fingerprint"].replace(":", "").upper())
    return pins


def _wall_plan():
    import yaml
    from urllib.parse import urlsplit
    path = WALL.get("config")
    if not isinstance(path, str) or not path.startswith("/"):
        raise RuntimeError("lab.wall.config is not set")
    mtime = os.path.getmtime(path)
    if _wall_cache["mtime"] == mtime:
        return _wall_cache["plan"]
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    default = int(cfg.get("defaultDuration") or 300)
    dash, pins, declared = {}, {}, _declared_pins()
    for d in cfg.get("dashboards") or []:
        if not isinstance(d, dict) or d.get("enabled") is False or not ID_RE.fullmatch(str(d.get("id") or "")):
            continue
        url = str(d.get("url") or "")
        if not URL_RE.fullmatch(url):
            continue
        u = urlsplit(url)
        item = {"id": d["id"], "name": str(d.get("name") or d["id"])[:60], "url": url,
                "duration": int(d.get("duration") or default), "refresh": int(d.get("refresh") or 0),
                "zoom": float(d.get("zoom") or 1), "css": str(d.get("css") or "")[:4000]}
        if u.username or u.password:   # never hand credentials embedded in a URL to the TV
            continue
        if d.get("insecureTLS") and u.scheme == "https":
            hp = f"{u.hostname}:{u.port or 443}"
            if hp in declared:
                pins[hp] = declared[hp]
            else:
                log.info("wall: %s needs a pin in lab.wall.pins for its self-signed certificate; skipped", d["id"])
                continue
        dash[d["id"]] = item
    slides = []
    for s in (cfg.get("slides") or [[k] for k in dash]):
        if isinstance(s, str):
            ids, name, dur = [s], None, None
        elif isinstance(s, list):
            ids, name, dur = s, None, None
        elif isinstance(s, dict):
            show = s.get("show")
            ids, name, dur = (show if isinstance(show, list) else [show]), s.get("name"), s.get("duration")
        else:
            continue
        ids = [i for i in ids if i in dash][:WALL_PANES]
        if not ids:
            continue
        slides.append({"name": str(name or " · ".join(dash[i]["name"] for i in ids))[:60], "ids": ids,
                       "duration": int(dur or max(dash[i]["duration"] for i in ids))})
    inter = cfg.get("interludes") if isinstance(cfg.get("interludes"), dict) else {}
    items = [{"type": i["type"], "duration": int(i.get("duration") or inter.get("duration") or 30)}
             for i in (inter.get("items") or []) if isinstance(i, dict) and i.get("type") in TV_INTERLUDES]
    q = cfg.get("quietHours") if isinstance(cfg.get("quietHours"), dict) else {}
    plan = {"dashboards": dash, "slides": slides, "pins": pins,
            "interludes": {"every": int(inter.get("every") or 0), "items": items},
            "quiet": {"start": str(q.get("start") or ""), "end": str(q.get("end") or "")},
            "transition_ms": int(cfg.get("transitionMs") or 900)}
    _wall_cache.update(mtime=mtime, plan=plan)
    return plan


async def h_wall(request):
    try:
        plan = await asyncio.to_thread(_wall_plan)
    except Exception as e:
        log.info("wall plan failed: %s", e)
        raise S.ApiError(404, "DisplayOS config could not be read")
    return S.ok(**plan)


async def h_wall_interlude(request):
    """What the interlude page shows: the verse from the hub and the weather (Open-Meteo, no key)."""
    out = {"place": None, "temp": None, "code": None, "verse": None}
    wx = config.CONFIG.get("weather") if isinstance(config.CONFIG.get("weather"), dict) else {}
    if isinstance(wx.get("lat"), (int, float)) and isinstance(wx.get("lon"), (int, float)):
        try:
            j = await _get_json(f"https://api.open-meteo.com/v1/forecast?latitude={wx['lat']}&longitude={wx['lon']}"
                                "&current=temperature_2m,weather_code&timezone=auto", {}, 600)
            out.update(place=str(wx.get("place") or "")[:40], temp=(j.get("current") or {}).get("temperature_2m"),
                       code=(j.get("current") or {}).get("weather_code"))
        except Exception as e:
            log.info("wall weather failed: %s", e)
    if HUB:
        try:
            v = ((await _source(HUB)).get("verses") or [None])[0] or {}
            out["verse"] = {"text": str(v.get("text") or "")[:400], "ref": str(v.get("reference") or "")[:60]}
        except Exception as e:
            log.info("wall verse failed: %s", e)
    return S.ok(**out)


async def show_wall(tv_id):
    tok = S._current.set(tv_id)
    try:
        await S.tv.adb("shell", "am", "start", "-n", "app.couchtv.launcher/.WallActivity", "--ez", "resume", "true")
    finally:
        S._current.reset(tok)
    return {"note": "DisplayOS is on the TV"}


async def h_wall_show(request):
    data = await S.body(request)
    r = await show_wall(_tv_id(request, data))
    S.record_action(request, "wall_show", {}, True)
    return S.ok(**r)


# ---------- audio output (the remote's volume wheel says where the sound goes) ----------
AUDIO_NAMES = {"speaker": "TV speakers", "hdmi": "Soundbar (ARC)", "hdmi_arc": "Soundbar (ARC)", "hdmi_earc": "Soundbar (eARC)",
               "bt_a2dp": "Bluetooth", "usb_headset": "USB audio", "line": "Line out", "spdif": "Optical"}
_audio = {"at": 0, "out": None}


async def h_audio_out(request):
    if time.time() - _audio["at"] > 30:
        tok = S._current.set(_tv_id(request))
        try:
            raw = await S.tv.adb("shell", "dumpsys audio | grep -A14 -- '- STREAM_MUSIC:' | grep -m1 'Devices:'")
            dev = str(raw).split("Devices:", 1)[-1].strip().split()[0] if "Devices:" in str(raw) else None
            _audio.update(at=time.time(), out=AUDIO_NAMES.get(dev, dev))
        except Exception as e:
            log.info("audio output read failed: %s", e)
            _audio.update(at=time.time(), out=None)
        finally:
            S._current.reset(tok)
    return S.ok(output=_audio["out"])


async def h_open(request):
    data = await S.body(request)
    try:
        r = await open_on_tv(request.match_info["id"], _tv_id(request, data))
    except RuntimeError as e:
        raise S.ApiError(404, str(e))
    S.record_action(request, "lab_open", {"id": request.match_info["id"]}, True)
    return S.ok(**r)


def routes(r):
    r.add_get("/api/lab/status", h_status)
    r.add_post("/api/lab/open/{id}", h_open)
    r.add_get("/api/lab/host/{id}", h_host)
    r.add_get("/api/lab/wall", h_wall)
    r.add_get("/api/lab/audio-out", h_audio_out)
    r.add_get("/api/lab/wall/interlude", h_wall_interlude)
    r.add_post("/api/lab/wall/show", h_wall_show)
    r.add_get("/api/lab/hub", h_hub)
    r.add_post("/api/lab/hub/action", h_hub_action)
    r.add_get("/api/lab/widgets", h_widgets)
    r.add_get("/api/lab/layout", h_layout_get)
    r.add_post("/api/lab/layout", h_layout_post)
    r.add_get("/api/lab/pages", h_pages)
    r.add_get("/api/lab/page/{id}", h_page)
    r.add_get("/api/lab/buttons", h_buttons)
    r.add_post("/api/lab/action", h_action)
    r.add_post("/api/lab/action/{id}", h_action)
    r.add_post("/api/screenshot/save", h_shot_save)
    r.add_get("/api/screenshots", h_shot_list)
    r.add_get("/api/screenshots/{name}", h_shot_file)
