# couch-tv-lab

**couch-tv-lab** is a fork of [Seagey/couch-tv](https://github.com/Seagey/couch-tv) (MIT). It turns a Google TV into
the display surface for a homelab and dev workspace: the same ad-free home and phone remote as couch-tv, plus
pages and widgets for your servers, monitoring, agents and day.

Everything outside this `lab/` folder is upstream couch-tv unless stated in [CHANGES.md](CHANGES.md).
Credit for the home screen, the phone remote, the bridge and the MCP server goes to Seagey and the couch-tv
contributors. The TCL debloat list builds on [CleanYourTV](https://github.com/Gathin23/cleanyourtv) (MIT).

## Who this is for
Someone who owns a TV **and** runs a server or homelab at home (Proxmox, Docker, a NAS, Prometheus, AdGuard,
Immich...), and wants the TV to be part of that setup instead of an ad billboard. Without a homelab, plain
[couch-tv](https://github.com/Seagey/couch-tv) is the better fit.

Nothing is tied to one network: your machines, services, addresses and tokens all come from your own
`config.json` and `.env`. An AI agent (Claude Code or similar) can set it up with you: the TV by
[AGENTS.md](../AGENTS.md), the homelab by [SETUP-LAB.md](SETUP-LAB.md).

## What's here
| Path | What |
|---|---|
| [SETUP-LAB.md](SETUP-LAB.md) | **Start here** for the homelab part: what you need, the questions, tokens, checking |
| [LAB.md](LAB.md) | Every `lab` setting: buttons, screenshots, widgets, services, the network map, AdGuard, DisplayOS |
| [config.lab.example.json](config.lab.example.json) | A complete `lab` section to copy into `config.json` |
| [check.py](check.py) | Read-only check of your `lab` settings: every widget, service and token, without touching the TV |
| [deploy.sh](deploy.sh) | Copy this checkout to your bridge server and restart it (`DEPLOY_HOST` or `lab/.deploy-host`) |
| [ROADMAP.md](ROADMAP.md) | The plan: phases, architecture, decisions |
| [CHANGES.md](CHANGES.md) | Every change this fork makes versus upstream |
| [journal/](journal/) | The build log of the reference setup, one entry per session |
| [tcl-50p735/](tcl-50p735/) | The reference TV (an example, not a requirement): specs, recon, debloat list, apply/undo, checks |

## Status
- [x] Phase 0: recon of the reference TV (TCL 50P735)
- [x] Phase 1: debloat (34 packages disabled, reboot verified over ADB; manual checks pending)
- [x] Phase 2: couch-tv as the home (option A, v0.12)
- [x] Phase 3: bridge on the homelab server (option B, wemserver, systemd)
- [ ] Phase 4: the lab layer (widgets, homelab pages, alerts, Lab Ambient screensaver, Hermes MCP tools)
- [ ] Phase 5: public release and docs
