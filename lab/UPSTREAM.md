# Staying in sync with upstream couch-tv

couch-tv-lab is a fork of [Seagey/couch-tv](https://github.com/Seagey/couch-tv), which moves fast (432 commits in the
first week after the fork). The fork keeps its own features by following these rules.

## 1. Keep our work in our own files
Most of couch-tv-lab lives in files upstream never touches, so upstream changes can't conflict with it:

| Ours | What |
|---|---|
| `bridge/lab.py` | buttons, screenshots, widgets, Lab tab, Proxmox, hub, DisplayOS wall plan, audio output |
| `remote/src/Lab.jsx` | Lab tab, widget editor, screenshots gallery, shortcuts strip |
| `tv-home/android/.../WallActivity.kt` | the DisplayOS wall screen |
| `tv-home/web/wall/` | wall interludes |
| `lab/` | docs, journal, TV kit, deploy and sync scripts |

Where we must touch an upstream file, keep it to a **small hook** and mark it with a `couch-tv-lab:` comment, so a
conflict is easy to recognise and resolve. Currently: `server.py` (3 lines: import and routes),
`MainActivity.kt` (`TVOS.reload`), `FireWatch.kt` (TCL in the Home-key list), `app.js`/`app.css`/`index.html`
(widget grid, native reload), the remote's `App.jsx`/`Remote.jsx`/`Sheets.jsx`/`styles.css` (Remote v2),
`tv.py` (`pm list packages -e`, typed text over ADB first), `config.py` (`watch_next_block`), `build.gradle.kts` (version, `webDebug`).
`git diff upstream/main --stat` shows the full list at any time.

## 2. When upstream ships the same thing, take theirs and drop ours
Upstream will keep solving problems we solved first. Taking their version shrinks the fork. Done in the
2026-11-17 sync:
- **Home watch:** upstream catches the Home key per maker. Ours is gone; we only add TCL to their list.
- **Bridge security:** upstream's host and origin checks, JSON-only POSTs and pairing key (couch-tv#73) replaced
  our allowlists.
- **Watch Next filter:** upstream's `home.skip_watch_next` does what our `watch_next_block` did. The config has
  moved over; ours can be deleted in the next sync.

## 3. Sync on a branch, test, then merge
Every week or two, and before any release:

```sh
lab/sync-upstream.sh            # new branch sync/upstream-<date>, merge upstream/main, then stop
```

It stops after the merge, so **nothing from upstream runs before you've looked at it**, and lists any conflicts.
Resolve them (rule 2 first), and review what came in, especially dependency and script changes (the script prints
the commands). Then run the checks, which install, test and build, so they run upstream's code:

```sh
lab/sync-upstream.sh --check    # any test failure stops it (a known upstream failure is listed by name)
```

When the checks pass:
1. `lab/deploy.sh --remote`, build and install the TV app (README "Building the app"), and run the TV checklist:
   - Home from an app, and a double Home press;
   - Night look toggle, the widget grid, Keep watching;
   - the phone remote: wheel, sheet, Lab tab, Proxmox sheet, screenshot;
   - the DisplayOS wall: a dashboard, an interlude, Proxmox.
2. Open a PR `sync/upstream-<date>` → `main`, merge it.

Use **merge, not rebase**: the fork's history is public.

## 4. Send generic fixes upstream
Every fix upstream accepts is one less difference to carry. Candidates:
- TCL in the Home-key list (a 3-line change, with our 50P735 notes);
- the WebView blocks page-initiated reloads, so `restart()` needs a native reload (`TVOS.reload`);
- `pm list packages -e`, so disabled apps aren't offered;
- note for upstream: `WebView.pauseTimers()` is process-wide, so it also freezes any other WebView screen in the app.

## 5. Let CI catch breakage
Turn on GitHub Actions in the fork (Actions tab). Upstream's `build.yml` then compiles the bridge and builds the
TV apps on every PR, including sync PRs.

## Versions
Fork builds are `<upstream version>-lab.<n>` (e.g. `0.12-lab.8`). When upstream cuts a new release, the next
sync moves to `<new version>-lab.1`.
