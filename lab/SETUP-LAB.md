# Setting up the homelab layer

couch-tv-lab is for someone who owns a TV **and** runs a server or homelab. couch-tv gives the TV an
ad-free home and a phone remote. This fork adds the homelab on top: widgets on the TV home (internet,
Proxmox, services, a network map, AdGuard, photos), a Lab tab on the phone remote, custom remote buttons,
screenshots, and your dashboards on the TV.

Nothing here is tied to one person's network. Every machine, service, address and token comes from
your own `config.json` (the `"lab"` section) and `.env`. A section you leave out simply does not show.

**For the AI agent setting this up:** this file is your guide for the homelab part, the same way
[AGENTS.md](../AGENTS.md) is for the TV. The TV comes first: the homelab layer needs option B (the bridge on
a computer that stays on, AGENTS.md and docs/SETUP.md). Same rules as there: ask in plain words, a
question or two at a time, read the plan back, and wait for a clear yes before you change anything.

## What you need
- couch-tv option B working: the bridge running on a server at home (docs/SETUP.md steps 1 to 6).
- Whatever homelab parts you want on the TV. Each one is optional:

| On the TV | Needs | Setting |
|---|---|---|
| Internet widget | nothing (a ping score), or a Prometheus exporter for your router | `lab.internet` |
| AdGuard shield | an AdGuard Home (or Pi-hole) address; no login | `lab.adguard` |
| Homelab widget | Proxmox VE and a read-only API token per node | `lab.proxmox` |
| Services and network map | the address and port of each service and machine | `lab.services`, `lab.netmap` |
| Dashboard buttons | the URLs of your dashboards (Grafana, Homepage, ...) | `lab.links` |
| Prometheus stat widgets | Prometheus | `lab.prometheus`, `lab.pages` |
| Photos widget, screenshots to Immich | Immich and an API key | `lab.screenshots.immich`, `IMMICH_API_KEY` |
| Study, Today and Verse widgets | a JSON "hub" endpoint of your own (format below) | `lab.sources`, `lab.hub_source` |

Every setting is described in [LAB.md](LAB.md). A complete starting point is
[config.lab.example.json](config.lab.example.json): its `"lab"` object goes into `config.json` next to `"tvs"`.

## 1. The questions
Ask, and write the answers down for the plan:

1. "What runs your homelab? Proxmox, plain Docker on one box, a NAS, a Raspberry Pi?" Only Proxmox gets the
   Homelab widget (CPU, memory, LXC and VMs). The others still get services and the map.
2. "Which services do you want to see as up or down?" For each: a name, the address, the port it listens
   on, and which machine it runs on (`on`, the id of a `netmap` node). You can read most of these yourself
   from `docker ps` or the Proxmox guests, and confirm with them.
3. "How is the house connected: which router, and is there a server, NAS or Proxmox host between it and
   the services?" That gives the `netmap` tree (each node's `parent`).
4. "Do you run Prometheus? Does it scrape your router?" If it does, offer the router's numbers in the
   internet widget (`"source": "prometheus"` with their own queries, or `"mtn"` for the mtn-router
   exporter). If not, the default ping score needs nothing.
5. "Do you use AdGuard Home or Pi-hole?" Its address goes in `lab.adguard`.
6. "Which dashboards do you open the most?" They become links and buttons (`lab.links`).
7. "Do you use Immich?" For the Photos widget and screenshots kept in an album.
8. "Anything else you want on the TV?" Map it to a widget type (LAB.md, Widgets): a number from
   Prometheus or from any JSON endpoint (`stat`), a list (`list`, `status`) or a line of text (`text`).
   Say plainly what cannot be done (no restarting machines from the TV: everything is read-only).

## 2. Read the plan back
One short list: which widgets, which services and machines, which tokens they will make, and that
everything is read-only (the bridge checks ports, reads Proxmox with an auditor token and asks AdGuard's
DNS; it never restarts, stops or changes anything). Wait for a clear yes.

## 3. Tokens: they make them, they go in `.env` only
Never put a token in `config.json`, never print it back, never write it anywhere but `.env` on the server.
They paste it themselves, or give it to you only to write it there.

- **Proxmox**, per node: Datacenter, Permissions, API Tokens, Add, for a user with the **PVEAuditor** role on
  `/` (read only), privilege separation on. `.env`: `PVE1_TOKEN=user@pam!couchtv=<secret>`, and
  `"token_env": "PVE1_TOKEN"` in `lab.proxmox`. The bridge pins each host's certificate instead of
  trusting any: get its fingerprint with
  `openssl s_client -connect <host>:8006 </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256`
  and put the part after `=` in `"fingerprint"`.
- **Immich**: Account settings, API keys, with `asset.upload`, `album.create`, `album.read`, `albumAsset.create`
  for screenshots and `asset.statistics` for the Photos widget. `.env`: `IMMICH_API_KEY=...`.
- **A hub source with a token**: `"auth_env": "MY_HUB_TOKEN"` on the source, and the token in `.env`.

## 4. Write the settings and check them
1. Add the `"lab"` section to `config.json` on the server (keep a backup of the old file).
2. Run the read-only check on the server. It fetches every widget the TV would show and checks each
   service and map node; it never touches the TV and never prints a token:

   ```sh
   .venv/bin/python lab/check.py
   ```

   Fix what it reports (a wrong port, a missing token, a fingerprint that does not match), and run it again
   until every widget says ok.
3. Restart the bridge (`systemctl restart couch-tv-bridge`, or `lab/deploy.sh` from your computer:
   it reads the server from `DEPLOY_HOST` or `lab/.deploy-host`).
4. On the TV: the widgets appear at the top right of the home (Night look). On the phone: the Lab tab, and
   Lab, TV widgets to arrange them.

## Your own "hub" (Study, Today, Verse)
Any JSON endpoint works as a source (`lab.sources`). The `study` and `today` panels read this shape from
the source named by `lab.hub_source`; every field is optional:

```json
{
  "counts": { "dueToday": 3, "overdue": 1, "habitsLeft": 2, "remindersSoon": 0 },
  "study":  { "streak": 5, "tracks": [ { "title": "Spanish", "lessonTitle": "Past tense",
                                          "emoji": "", "day": 12, "totalDays": 30 } ] },
  "verses": [ { "text": "…", "reference": "…" } ]
}
```

A small script, a Home Assistant template or an n8n flow can serve it. For anything else, a plain `stat`,
`list` or `text` widget can point at any path in any JSON source (LAB.md, Widgets).

## Taking it off
Remove the `"lab"` section and restart the bridge. The TV home and the phone remote go back to plain
couch-tv. Nothing on the TV changes.
