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
                raise RuntimeError(f"Immich upload: {r.status} {str(j)[:120]}")
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
            errors.append({"target": t, "error": str(e)[:200]})
            log.info("screenshot to %s failed: %s", t, e)
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
    return web.FileResponse(path, headers={"Cache-Control": "max-age=86400"})


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
                v = res[0]["value"][1] if res else None
                out["value"] = _fmt(v, fmt, dec, unit)
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
        out.update(ok=False, error=str(e)[:120])
    return out


async def h_pages(request):
    return S.ok(pages=[{"id": p["id"], "title": p["title"], "widgets": len(p["widgets"])} for p in PAGES])


async def h_page(request):
    pid = request.match_info["id"]
    p = next((x for x in PAGES if x["id"] == pid), None)
    if not p:
        raise S.ApiError(404, f"no lab page {pid!r}")
    widgets = await asyncio.gather(*(render_widget(w) for w in p["widgets"]))
    return S.ok(id=p["id"], title=p["title"], widgets=list(widgets), at=S.now_iso())


def routes(r):
    r.add_get("/api/lab/pages", h_pages)
    r.add_get("/api/lab/page/{id}", h_page)
    r.add_get("/api/lab/buttons", h_buttons)
    r.add_post("/api/lab/action", h_action)
    r.add_post("/api/lab/action/{id}", h_action)
    r.add_post("/api/screenshot/save", h_shot_save)
    r.add_get("/api/screenshots", h_shot_list)
    r.add_get("/api/screenshots/{name}", h_shot_file)
