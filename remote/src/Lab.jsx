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
export function LabPage({ reach, active }) {
  const [pages, setPages] = useState(null);
  const [cur, setCur] = useState(null);
  const [page, setPage] = useState(null);
  const [err, setErr] = useState(null);
  const [shots, setShots] = useState(null);
  useEffect(() => { api.labPages().then((d) => { setPages(d.pages || []); setCur((c) => c || d.pages?.[0]?.id || null); }).catch((e) => setErr(e.message)); }, [reach]);
  useEffect(() => {
    if (!active || !cur) return undefined;
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
        <button className={`chip glass ${cur === '_shots' ? 'on' : ''}`} onClick={() => { tick(); setCur('_shots'); }}>Screenshots</button>
      </div>
      {cur === '_shots' ? (
        <div className="lab-shots">{(shots || []).map((s) => (
          <a key={s.name} href={s.url} target="_blank" rel="noreferrer"><img src={s.url} alt={s.name} loading="lazy" /><small>{s.name.replace(/^[^-]+-[^-]+-/, '').replace(/\.png$/, '')}</small></a>
        ))}{shots && !shots.length && <p className="lab-sub">No screenshots yet. Tap Screenshot on the Remote tab.</p>}</div>
      ) : (
        <div className="lab-grid">{page?.id === cur && page.widgets.map((w) => <Widget key={w.id} w={w} />)}</div>
      )}
    </div>
  );
}
