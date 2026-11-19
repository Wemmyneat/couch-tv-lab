#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
# (bridge/lab.py is imported from sys.path below; editors confuse it with this lab/ folder)
"""couch-tv-lab: check the homelab settings (config.json "lab") without touching the TV.

    .venv/bin/python lab/check.py                   uses ./config.json and ./.env
    COUCH_CONFIG=/path/config.json .venv/bin/python lab/check.py
    .venv/bin/python lab/check.py --json            the same, as JSON (for scripts and agents)

It only reads: it fetches every widget the TV would show (lab.widgets), checks each service and network map
host, and says what is missing. It changes nothing, presses nothing on the TV, and never prints a token.
Exit code 0 when every widget answered, 1 when one failed, 2 when there is no "lab" section at all.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))
os.chdir(ROOT)

import config  # noqa: E402
import lab  # noqa: E402


def env_state(name):
    return "set" if os.environ.get(name) else "MISSING in .env"


async def main(as_json):
    if not lab.LAB:
        print(f'No "lab" section in {config.CONFIG_FILE}. Copy one from lab/config.lab.example.json.')
        return 2
    out = {"config": config.CONFIG_FILE, "widgets": [], "services": [], "netmap": [], "proxmox": [], "secrets": {}}

    # what needs a token, and whether .env has it (the value is never printed)
    for p in lab.PVE.values():
        out["secrets"][p["token_env"]] = env_state(p["token_env"])
    for src in lab.SOURCES.values():
        if src.get("auth_env"):
            out["secrets"][src["auth_env"]] = env_state(src["auth_env"])
    if "immich" in lab.TARGETS or any(w.get("kind") == "photos" for w in lab.CATALOG.values()):
        out["secrets"]["IMMICH_API_KEY"] = env_state("IMMICH_API_KEY")
    skipped = [str(p.get("id")) for p in (lab.LAB.get("proxmox") or []) if isinstance(p, dict) and p.get("id") not in lab.PVE]
    if skipped:
        out["proxmox"].append({"skipped": skipped, "why": "id, host, node, token_env or fingerprint is not valid"})

    # every widget in the catalog, fetched the way the TV gets it
    for wid, w in lab.CATALOG.items():
        try:
            r = await asyncio.wait_for(lab.render_widget(w), 12)
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        row = {"id": wid, "ok": bool(r.get("ok")), "error": r.get("error")}
        if r.get("ok"):
            row["got"] = {k: v for k, v in r.items() if k not in ("id", "type", "title", "ok", "items", "nodes")}
            if "nodes" in r:
                row["got"]["nodes"] = [{k: n.get(k) for k in ("id", "label", "online", "ok") if k in n} for n in r["nodes"]]
        out["widgets"].append(row)

    ups = await asyncio.gather(*(lab._probe(s["host"], s["port"]) for s in lab.SERVICES))
    out["services"] = [{"id": s["id"], "host": f'{s["host"]}:{s["port"]}', "up": u} for s, u in zip(lab.SERVICES, ups)]
    ups = await asyncio.gather(*(lab._probe(n["host"], n["port"]) for n in lab.NETMAP))
    out["netmap"] = [{"id": n["id"], "host": f'{n["host"]}:{n["port"]}', "up": u} for n, u in zip(lab.NETMAP, ups)]
    out["internet_source"] = lab.INTERNET["source"]
    out["adguard"] = await lab.adguard_state()

    if as_json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(f"settings: {out['config']}")
        print(f"internet: source {out['internet_source']}" + (f", AdGuard {out['adguard']}" if out["adguard"] else ", no AdGuard set"))
        for k, v in out["secrets"].items():
            print(f"  .env {k}: {v}")
        for p in out["proxmox"]:
            print(f"  proxmox skipped {', '.join(p['skipped'])}: {p['why']}")
        print("widgets:")
        for w in out["widgets"]:
            print(f"  {'ok ' if w['ok'] else 'BAD'} {w['id']}" + ("" if w["ok"] else f"  {w['error']}"))
            off = [n.get("label") or n.get("id") for n in (w.get("got") or {}).get("nodes", []) if n.get("online") is False]
            if off:
                print(f"      not answering: {', '.join(off)} (check the host, the token and the fingerprint)")
        down = [s for s in out["services"] if not s["up"]]
        print(f"services: {len(out['services']) - len(down)}/{len(out['services'])} answering"
              + "".join(f"\n  down {s['id']} ({s['host']})" for s in down))
        down = [n for n in out["netmap"] if not n["up"]]
        print(f"network map: {len(out['netmap']) - len(down)}/{len(out['netmap'])} answering"
              + "".join(f"\n  down {n['id']} ({n['host']})" for n in down))
    return 0 if all(w["ok"] for w in out["widgets"]) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--json" in sys.argv)))
