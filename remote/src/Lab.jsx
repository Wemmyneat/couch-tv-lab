// couch-tv-lab: the custom buttons strip (lab.buttons in config.json, bridge/lab.py).
// One tap runs the button's steps on the bridge: keys, apps, inputs, volume, sleep, power, screenshot.
import { useEffect, useState } from 'react';
import { api, getTvId } from './api.js';
import * as Ic from './icons.jsx';
import { tick } from './haptics.js';
import { Sheet } from './Sheets.jsx';

const ICON = {
  camera: Ic.Camera, monitor: Ic.Screen, moon: Ic.Moon, power: Ic.Power, tv: Ic.Screen, music: Ic.Music,
  film: Ic.Film, home: Ic.Home, game: Ic.Game, chart: Ic.Chart, server: Ic.Server, bolt: Ic.Bolt, star: Ic.Star,
  volume: Ic.Speaker, input: Ic.Input, play: Ic.Play, pause: Ic.Pause, settings: Ic.Gear, link: Ic.Link,
};

const NAMES = { server: 'server', nas: 'NAS', immich: 'Immich' };

// What to tell the person after a button ran. Screenshots say where they went.
export function labResult(r) {
  if (r.saved) {
    const where = r.saved.map((s) => NAMES[s] || s).join(', ');
    const failed = (r.errors || []).map((e) => `${NAMES[e.target] || e.target}: ${e.error}`).join('; ');
    return { text: `Screenshot saved to ${where}${r.note ? ` (${r.note})` : ''}${failed ? `. Not saved to ${failed}` : ''}`, kind: failed || r.note ? 'warn' : 'info' };
  }
  return { text: `${r.label || 'Done'}`, kind: 'info' };
}

export function LabButtons({ reach, onResult, onError }) {
  const [buttons, setButtons] = useState(null);
  const [busy, setBusy] = useState(null);
  useEffect(() => { api.labButtons().then((d) => setButtons(d.buttons || [])).catch(() => setButtons([])); }, [reach]);
  if (!buttons || !buttons.length) return null;
  const run = (b) => {
    if (busy) return;
    tick();
    setBusy(b.id);
    api.labAction(b.id).then(onResult, onError).finally(() => setBusy(null));
  };
  return (
    <div className="lab-buttons" role="group" aria-label="Shortcuts">
      {buttons.map((b) => {
        const I = ICON[b.icon] || Ic.Bolt;
        return (
          <button key={b.id} className={`lab-btn glass ${busy === b.id ? 'busy' : ''}`} onClick={() => run(b)} aria-busy={busy === b.id}>
            <I size={20} /><span>{b.label}</span>
          </button>
        );
      })}
    </div>
  );
}

// One widget card: a big value, a short text, or a list (with a green or red dot for status lists).
function Widget({ w }) {
  return (
    <div className={`lab-card glass ${w.type} ${w.ok ? '' : 'bad'}`}>
      <small>{w.title}</small>
      {!w.ok && <p className="lab-err">{w.error}</p>}
      {w.ok && (w.type === 'stat' || w.type === 'text') && <b className={w.type === 'stat' ? 'lab-value' : 'lab-text'}>{w.value}</b>}
      {w.ok && w.sub && <p className="lab-sub">{w.sub}</p>}
      {w.ok && w.items && (w.items.length ? (
        <ul>{w.items.map((it, i) => (
          <li key={i}>{it.ok !== null && it.ok !== undefined && <i className={`dot ${it.ok ? 'up' : 'down'}`} />}<span>{it.title}</span>{it.sub && <em>{it.sub}</em>}</li>
        ))}{w.more > 0 && <li className="lab-more">+{w.more} more</li>}</ul>
      ) : <p className="lab-sub">{w.empty || 'Nothing here'}</p>)}
    </div>
  );
}

// The Lab tab, actions first (lab/PLAN-polish.md): a line of status chips, things to do on the TV, homelab
// tiles that open a sheet, then the TV widgets editor and the screenshots. Stats live on the TV and in
// Grafana; the phone is for doing things.
function Shots() {
  const [shots, setShots] = useState(null);
  useEffect(() => { api.screenshots().then((d) => setShots(d.shots || [])).catch(() => setShots([])); }, []);
  return (
    <div className="lab-shots">{(shots || []).map((s) => (
      <a key={s.name} href={s.url} target="_blank" rel="noreferrer"><img src={s.url} alt={s.name} loading="lazy" /><small>{s.name.replace(/^[^-]+-[^-]+-/, '').replace(/\.png$/, '')}</small></a>
    ))}{shots && !shots.length && <p className="lab-sub">No screenshots yet.</p>}</div>
  );
}

function HubSheet({ open, onClose, onSaid }) {
  const [d, setD] = useState(null);
  const load = () => api.labHub().then(setD).catch((e) => onSaid?.(e.message, 'err'));
  useEffect(() => { if (open) load(); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = (type, id, done) => { tick(); api.labHubAction(type, id, done).then(() => { onSaid?.(type === 'complete-task' ? 'Task done' : 'Habit logged'); load(); }).catch((e) => onSaid?.(e.message, 'err')); };
  return (
    <Sheet open={open} onClose={onClose} title="Today">
      <div className="hub-sheet">
        <h3 className="lab-h">Tasks</h3>
        {d?.tasks?.length ? <ul className="wcat">{d.tasks.map((t) => (
          <li key={t.id}><div><b>{t.title}</b><small>{t.overdue ? 'overdue' : t.due ? 'due today' : ''}</small></div>
            <button className="wadd" aria-label={`Complete ${t.title}`} onClick={() => act('complete-task', t.id)}>✓</button></li>
        ))}</ul> : <p className="lab-sub">{d ? 'Nothing due.' : 'Loading…'}</p>}
        <h3 className="lab-h">Habits</h3>
        {d?.habits?.length ? <ul className="wcat">{d.habits.map((h) => (
          <li key={h.id}><div><b>{h.title}</b><small>{h.done ? 'done today' : 'not yet'}</small></div>
            <button className={`wadd ${h.done ? 'on' : ''}`} aria-pressed={h.done} aria-label={`${h.done ? 'Undo' : 'Log'} ${h.title}`} onClick={() => act('check-habit', h.id, !h.done)}>{h.done ? '✓' : '+'}</button></li>
        ))}</ul> : <p className="lab-sub">{d ? 'No habits today.' : ''}</p>}
      </div>
    </Sheet>
  );
}

function Bar({ label, used, total, unit = 'GB' }) {
  const pct = total ? Math.min(100, Math.round((used / total) * 100)) : 0;
  return (
    <div className="pbar"><div className="pbar-row"><span>{label}</span><span>{used} / {total} {unit}</span></div>
      <div className="pbar-track"><div className={`pbar-fill ${pct >= 85 ? 'hot' : ''}`} style={{ width: `${pct}%` }} /></div></div>
  );
}

// A Proxmox host: read-only stats from its API (bridge/lab.py, PVEAuditor token). Restart and shutdown
// stay in Proxmox, never on a TV remote. "Show on TV" opens the host's ProxMenux dashboard when one is set up.
function HostSheet({ chip, links, onClose, onSaid }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    setD(null);
    if (!chip) return undefined;
    if (!chip.pve) { setD({ online: chip.state === 'ok', plain: true }); return undefined; }
    let live = true;
    const load = () => api.labHost(chip.id).then((r) => live && setD(r)).catch((e) => live && setD({ online: false, error: e.message }));
    load();
    const t = setInterval(load, 15000);
    return () => { live = false; clearInterval(t); };
  }, [chip]);
  const link = (links || []).find((l) => l.id === `proxmenux${(chip?.id || '').replace(/\D/g, '')}`);
  return (
    <Sheet open={Boolean(chip)} onClose={onClose} title={chip?.id ? (d?.node || chip.label.split(' · ')[0]) : ''}>
      <div className="hub-sheet">
        {!d && <p className="lab-sub">Loading…</p>}
        {d && <p className="lab-sub"><i className={`dot ${d.online ? 'up' : 'down'}`} /> {d.online ? (d.plain ? 'Reachable from the bridge' : `Online · up ${d.uptime_h} h · ${d.cores} cores · load ${d.load ?? '–'}`) : (d.error || 'Not answering')}</p>}
        {d?.online && !d.plain && (<>
          <Bar label="CPU" used={d.cpu} total={100} unit="%" />
          <Bar label="Memory" used={d.mem_gb} total={d.memtotal_gb} />
          <Bar label="Root disk" used={d.root_gb} total={d.roottotal_gb} />
          <h3 className="lab-h">Guests</h3>
          {d.guests?.length ? <ul className="wcat">{d.guests.map((g) => (
            <li key={`${g.kind}${g.id}`}><i className={`dot ${g.status === 'running' ? 'up' : 'down'}`} /><div><b>{g.kind.toUpperCase()} {g.id} {g.name}</b><small>{g.status} · {g.cpu}% CPU · {g.mem_gb}/{g.maxmem_gb} GB</small></div></li>
          ))}</ul> : <p className="lab-sub">No guests.</p>}
          <h3 className="lab-h">Storage</h3>
          {(d.storage || []).map((x) => <Bar key={x.name} label={x.name} used={x.used_gb} total={x.total_gb} />)}
        </>)}
        {link && <button className="lab-tile glass small" onClick={() => { tick(); api.labOpen(link.id).then((r) => onSaid?.(r.note || 'Opened on the TV'), (e) => onSaid?.(e.message, 'err')); }}><span>Show {link.label} on TV</span><small>full dashboard</small></button>}
        <p className="lab-sub">Read-only. Restart and shutdown stay in Proxmox.</p>
      </div>
    </Sheet>
  );
}

const STATE_DOT = { ok: 'up', down: 'down', warn: 'warn', idle: 'idle' };

export function LabPage({ reach, active, onSaid }) {
  const [st, setSt] = useState(null);
  const [view, setView] = useState('home');
  const [busy, setBusy] = useState(null);
  const [hub, setHub] = useState(false);
  const [host, setHost] = useState(null);
  useEffect(() => {
    if (!active) return undefined;
    let live = true;
    const load = () => api.labStatus().then((d) => live && setSt(d)).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => { live = false; clearInterval(t); };
  }, [active, reach]);
  const run = (key, p) => { if (busy) return; tick(); setBusy(key); p.then((r) => { const m = labResult(r); onSaid?.(r.note || m.text, m.kind); }, (e) => onSaid?.(e.message, 'err')).finally(() => setBusy(null)); };
  if (view !== 'home') {
    return (
      <div className="lab">
        <div className="lab-top"><button className="round glass small" aria-label="Back to Lab" onClick={() => { tick(); setView('home'); }}><Ic.Back size={18} /></button>
          <h1 className="lab-title">{view === 'widgets' ? 'TV widgets' : 'Screenshots'}</h1></div>
        {view === 'widgets' ? <WidgetEditor onSaid={onSaid} /> : <Shots />}
      </div>
    );
  }
  const hosts = (st?.chips || []).filter((c) => !['internet', 'hub', 'power'].includes(c.id));
  return (
    <div className="lab">
      <h1 className="lab-title">Lab</h1>
      <div className="lab-chips" role="list" aria-label="Status">
        {(st?.chips || []).map((c) => <span key={c.id} role="listitem" className="lab-chip glass"><i className={`dot ${STATE_DOT[c.state] || ''}`} />{c.label}</span>)}
      </div>
      <h3 className="lab-h">On the TV</h3>
      <div className="lab-tiles">
        <button className="lab-tile glass accent" aria-busy={busy === 'shot'} onClick={() => run('shot', api.labAction('screenshot'))}><Ic.Camera size={22} /><span>Screenshot</span></button>
        {(st?.links || []).filter((l) => !l.id.startsWith('proxmenux')).map((l) => <button key={l.id} className="lab-tile glass" aria-busy={busy === l.id} onClick={() => run(l.id, api.labOpen(l.id))}><Ic.Chart size={22} /><span>Show {l.label}</span></button>)}
      </div>
      <h3 className="lab-h">Homelab</h3>
      <div className="lab-tiles">
        {hosts.map((h) => <button key={h.id} className="lab-tile glass small" onClick={() => { tick(); setHost(h); }}><span>{h.label.split(' · ')[0]}</span><small><i className={`dot ${STATE_DOT[h.state]}`} />{h.state !== 'ok' ? 'down' : h.pve ? h.label.split(' · ').slice(1).join(' · ') : 'up'}</small></button>)}
        {st?.hub && <button className="lab-tile glass small" onClick={() => { tick(); setHub(true); }}><span>Hub actions</span><small>tasks · habits</small></button>}
      </div>
      <div className="lab-tiles">
        <button className="lab-tile glass small" onClick={() => { tick(); setView('widgets'); }}><span>TV widgets</span><small>add · arrange</small></button>
        <button className="lab-tile glass small" onClick={() => { tick(); setView('shots'); }}><span>Screenshots</span><small>server · Immich</small></button>
      </div>
      <HubSheet open={hub} onClose={() => setHub(false)} onSaid={onSaid} />
      <HostSheet chip={host} links={st?.links} onClose={() => setHost(null)} onSaid={onSaid} />
    </div>
  );
}

// ---------- TV widgets editor (bridge/lab.py: /api/lab/widgets, /api/lab/layout) ----------
// Tap a widget to pick it, then move it, change its size or take it off. "+" puts a widget from the
// catalog in the first free spot. Every change is saved to the bridge at once; the TV picks it up
// within 20 s. The bridge checks every layout too (inside the grid, no overlap, allowed sizes).
const cellsOf = (it) => { const c = []; for (let x = it.x; x < it.x + it.w; x++) for (let y = it.y; y < it.y + it.h; y++) c.push(`${x},${y}`); return c; };
function fits(items, cand, cols, rows) {
  if (cand.x < 0 || cand.y < 0 || cand.x + cand.w > cols || cand.y + cand.h > rows) return false;
  const taken = new Set(items.filter((i) => i.id !== cand.id).flatMap(cellsOf));
  return !cellsOf(cand).some((c) => taken.has(c));
}
function firstSpot(items, w, h, cols, rows, id) {
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) { const c = { id, x, y, w, h }; if (fits(items, c, cols, rows)) return c; }
  return null;
}

export function WidgetEditor({ onSaid }) {
  const [cat, setCat] = useState(null);
  const [grid, setGrid] = useState({ cols: 2, rows: 4 });
  const [items, setItems] = useState(null);
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadedTv, setLoadedTv] = useState(null);   // the TV this layout came from; saves go only there
  useEffect(() => {
    api.labWidgets().then((d) => { setCat(d.widgets || []); setGrid({ cols: d.cols, rows: d.rows }); }).catch((e) => onSaid?.(e.message, 'err'));
    api.labLayout().then((d) => { setLoadedTv(d.tv); return d; }).then((d) => setItems((d.items || []).map(({ id, x, y, w, h }) => ({ id, x, y, w, h })))).catch((e) => onSaid?.(e.message, 'err'));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!cat || !items) return <p className="lab-sub">Loading the TV's widgets…</p>;
  const byId = Object.fromEntries(cat.map((w) => [w.id, w]));
  const save = (next) => {
    if (loadedTv && (getTvId() || loadedTv) !== loadedTv) { onSaid?.('You switched TV. Close and reopen TV widgets.', 'err'); return; }
    const before = items; setItems(next); setBusy(true); tick();
    api.saveLabLayout(next).then(() => onSaid?.('Saved. The TV updates in a few seconds.'))
      .catch((e) => { setItems(before); onSaid?.(e.message, 'err'); }).finally(() => setBusy(false));
  };
  const cur = items.find((i) => i.id === sel);
  const move = (dx, dy) => { if (!cur) return; const c = { ...cur, x: cur.x + dx, y: cur.y + dy }; if (fits(items, c, grid.cols, grid.rows)) save(items.map((i) => (i.id === sel ? c : i))); };
  const resize = () => {
    if (!cur) return; const sizes = byId[sel]?.sizes || [[1, 1]];
    const k = sizes.findIndex(([w, h]) => w === cur.w && h === cur.h);
    for (let n = 1; n <= sizes.length; n++) {
      const [w, h] = sizes[(k + n) % sizes.length];
      const c = fits(items, { ...cur, w, h }, grid.cols, grid.rows) ? { ...cur, w, h } : firstSpot(items.filter((i) => i.id !== sel), w, h, grid.cols, grid.rows, sel);
      if (c) { save(items.map((i) => (i.id === sel ? c : i))); return; }
    }
    onSaid?.('No room for another size', 'warn');
  };
  const remove = () => { if (cur) { save(items.filter((i) => i.id !== sel)); setSel(null); } };
  const add = (w) => {
    const spot = w.sizes.map(([cw, ch]) => firstSpot(items, cw, ch, grid.cols, grid.rows, w.id)).find(Boolean);
    if (!spot) { onSaid?.('The grid is full. Take a widget off first.', 'warn'); return; }
    save([...items, spot]); setSel(w.id);
  };
  const free = cat.filter((w) => !items.some((i) => i.id === w.id));
  const empty = [];
  const taken = new Set(items.flatMap(cellsOf));
  for (let y = 0; y < grid.rows; y++) for (let x = 0; x < grid.cols; x++) if (!taken.has(`${x},${y}`)) empty.push({ x, y });
  return (
    <div className="wedit">
      <p className="lab-sub">Tap a widget, then move it, change its size or take it off. Living room · {grid.cols} × {grid.rows}</p>
      <div className="wgrid" style={{ gridTemplateColumns: `repeat(${grid.cols}, minmax(0, 1fr))`, gridTemplateRows: `repeat(${grid.rows}, 64px)` }}>
        {empty.map((e) => <div key={`e${e.x},${e.y}`} className="wcell" style={{ gridColumn: e.x + 1, gridRow: e.y + 1 }} />)}
        {items.map((i) => (
          <button key={i.id} className={`wtile glass ${sel === i.id ? 'on' : ''}`} aria-pressed={sel === i.id}
            style={{ gridColumn: `${i.x + 1} / span ${i.w}`, gridRow: `${i.y + 1} / span ${i.h}` }} onClick={() => { tick(); setSel(sel === i.id ? null : i.id); }}>
            <span>{byId[i.id]?.title || i.id}</span><small>{i.w}×{i.h}</small>
          </button>
        ))}
      </div>
      {cur && (
        <div className="wtools" role="group" aria-label={`Edit ${byId[sel]?.title}`}>
          <button className="chip glass" aria-label="Move left" disabled={busy} onClick={() => move(-1, 0)}>←</button>
          <button className="chip glass" aria-label="Move up" disabled={busy} onClick={() => move(0, -1)}>↑</button>
          <button className="chip glass" aria-label="Move down" disabled={busy} onClick={() => move(0, 1)}>↓</button>
          <button className="chip glass" aria-label="Move right" disabled={busy} onClick={() => move(1, 0)}>→</button>
          <button className="chip glass" disabled={busy || (byId[sel]?.sizes || []).length < 2} onClick={resize}>Size</button>
          <button className="chip glass wremove" disabled={busy} onClick={remove}>Remove</button>
        </div>
      )}
      <h3 className="lab-h">Add from your server</h3>
      {free.length ? (
        <ul className="wcat">{free.map((w) => (
          <li key={w.id}><div><b>{w.title}</b><small>{[w.note, w.sizes.map(([a, b]) => `${a}×${b}`).join(' or ')].filter(Boolean).join(' · ')}</small></div>
            <button className="wadd" aria-label={`Add ${w.title}`} disabled={busy} onClick={() => { tick(); add(w); }}>+</button></li>
        ))}</ul>
      ) : <p className="lab-sub">Every widget is on the TV.</p>}
    </div>
  );
}
