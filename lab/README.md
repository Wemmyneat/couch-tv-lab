# couch-tv-lab

**couch-tv-lab** is a fork of [Seagey/couch-tv](https://github.com/Seagey/couch-tv) (MIT). It turns a Google TV into
the display surface for a homelab and dev workspace: the same ad-free home and phone remote as couch-tv, plus
pages and widgets for your servers, monitoring, agents and day.

Everything outside this `lab/` folder is upstream couch-tv unless stated in [CHANGES.md](CHANGES.md).
Credit for the home screen, the phone remote, the bridge and the MCP server goes to Seagey and the couch-tv
contributors. The TCL debloat list builds on [CleanYourTV](https://github.com/Gathin23/cleanyourtv) (MIT).

## Who this is for
Software engineers and homelabbers who are comfortable with ADB and running a small service at home, and who
want the living-room TV to be part of their stack, not an ad billboard.

## What's here
| Path | What |
|---|---|
| [ROADMAP.md](ROADMAP.md) | The plan: phases, architecture, decisions |
| [CHANGES.md](CHANGES.md) | Every change this fork makes versus upstream |
| [journal/](journal/) | The build log, one entry per session (source material for write-ups and videos) |
| [tcl-50p735/](tcl-50p735/) | The reference TV: specs, firmware, recon script, debloat list, apply/undo, checks |

## Status
- [x] Phase 0: recon of the reference TV (TCL 50P735)
- [x] Phase 1: debloat (34 packages disabled, reboot verified over ADB; manual checks pending)
- [x] Phase 2: couch-tv as the home (option A, v0.12)
- [ ] Phase 3: bridge on the homelab server (option B)
- [ ] Phase 4: the lab layer (widgets, homelab pages, alerts, Lab Ambient screensaver, Hermes MCP tools)
- [ ] Phase 5: public release and docs
