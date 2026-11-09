// couch-tv-lab: the custom buttons strip (lab.buttons in config.json, bridge/lab.py).
// One tap runs the button's steps on the bridge: keys, apps, inputs, volume, sleep, power, screenshot.
import { useEffect, useState } from 'react';
import { api } from './api.js';
import * as Ic from './icons.jsx';
import { tick } from './haptics.js';

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

// The Lab tab: pages from lab.pages (bridge/lab.py), refreshed every 30 s while it is showing.
export function LabPage({ reach, active, onSaid }) {
  const [pages, setPages] = useState(null);
  const [cur, setCur] = useState(null);
  const [page, setPage] = useState(null);
  const [err, setErr] = useState(null);
  const [shots, setShots] = useState(null);
  useEffect(() => { api.labPages().then((d) => { setPages(d.pages || []); setCur((c) => c || d.pages?.[0]?.id || null); }).catch((e) => setErr(e.message)); }, [reach]);
  useEffect(() => {
    if (!active || !cur || cur === '_widgets') return undefined;
    let live = true;
    const load = () => (cur === '_shots'
      ? api.screenshots().then((d) => live && setShots(d.shots || []))
      : api.labPage(cur).then((d) => { if (live) { setPage(d); setErr(null); } })).catch((e) => live && setErr(e.message));
    load();
    const t = setInterval(load, 30000);
    return () => { live = false; clearInterval(t); };
  }, [active, cur, reach]);
  if (err && !pages) return <div className="lab"><p className="lab-sub">{err}</p></div>;
  if (!pages) return <div className="lab" />;
  return (
    <div className="lab">
      <div className="chips-row chips-wrap lab-tabs">
        {pages.map((p) => <button key={p.id} className={`chip glass ${cur === p.id ? 'on' : ''}`} onClick={() => { tick(); setCur(p.id); }}>{p.title}</button>)}
        <button className={`chip glass ${cur === '_widgets' ? 'on' : ''}`} onClick={() => { tick(); setCur('_widgets'); }}>TV widgets</button>
        <button className={`chip glass ${cur === '_shots' ? 'on' : ''}`} onClick={() => { tick(); setCur('_shots'); }}>Screenshots</button>
      </div>
      {cur === '_widgets' ? <WidgetEditor onSaid={onSaid} /> : cur === '_shots' ? (
        <div className="lab-shots">{(shots || []).map((s) => (
          <a key={s.name} href={s.url} target="_blank" rel="noreferrer"><img src={s.url} alt={s.name} loading="lazy" /><small>{s.name.replace(/^[^-]+-[^-]+-/, '').replace(/\.png$/, '')}</small></a>
        ))}{shots && !shots.length && <p className="lab-sub">No screenshots yet. Tap Screenshot on the Remote tab.</p>}</div>
      ) : (
        <div className="lab-grid">{page?.id === cur && page.widgets.map((w) => <Widget key={w.id} w={w} />)}</div>
      )}
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
  useEffect(() => {
    api.labWidgets().then((d) => { setCat(d.widgets || []); setGrid({ cols: d.cols, rows: d.rows }); }).catch((e) => onSaid?.(e.message, 'err'));
    api.labLayout().then((d) => setItems((d.items || []).map(({ id, x, y, w, h }) => ({ id, x, y, w, h })))).catch((e) => onSaid?.(e.message, 'err'));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!cat || !items) return <p className="lab-sub">Loading the TV's widgets…</p>;
  const byId = Object.fromEntries(cat.map((w) => [w.id, w]));
  const save = (next) => {
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
