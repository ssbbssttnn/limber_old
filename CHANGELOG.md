# Limber — Build Log & App Reference

A stretching / mobility Progressive Web App (PWA). Single-file HTML/CSS/JS,
deployed via GitHub → Netlify. This document is a cut-down log of how it was
built and a reference to its current state.

---

## WHAT LIMBER IS

- A personal stretching/mobility app: build routines, run a guided timer with
  cues, track progress.
- One self-contained `index.html` (HTML + CSS + JS in one file).
- Installs to a phone home screen as a PWA. All data stored on-device
  (localStorage). No account, no server, no ads.
- Current aesthetic: **architectural / precise / technical** — JetBrains Mono +
  Archivo fonts, blueprint grid background, hairline borders, sharp corners,
  red accent (#ed3426) on deep blue-black. (This started as a design called
  "Span" and became the chosen look for Limber.)

---

## CURRENT STATE (at handoff)

- **270 stretches** across areas: neck, shoulders, back, hips, legs, core, glide
  (nerve glides). Each has muscle-group sub-tags (hamstring, quad, calf, chest,
  glute, etc.) for filtering and search.
- **16 pre-built routines** including a Mobility routine (standing hip openers,
  elephant walks, windshield wipers, cat-cow, scapular pushups, thread the
  needle, windmills) and Nerve Flossing.
- **41 curated sounds** across 4 events — Switch sides (11), Next stretch (6),
  Countdown (10), Routine complete (14). Completion sounds use unusual musical
  scales (Hirajoshi, Mixolydian, pentatonic, etc.) with resolving cadences.
- **6 themes**: Blueprint, Carbon, Concrete, Paper, Cyan, Amber (all share the
  red accent).
- Library version 4 (migration logic refreshes built-in content on update while
  preserving progress and custom stretches).

---

## FEATURES

- **Timer / "go"**: continuous auto-advance, countdown ring (scrubbable),
  play/pause, End button, resume an in-progress session from the nav. Prep time
  and switch-side pause configurable. Next-stretch thumbnail during prep.
  Skip-prep-on-first option.
- **PNF** (tense/relax technique) as a per-stretch toggle — cues "tense" and
  "relax, sink deeper" through the hold.
- **Sounds**: distinct, selectable sound per event (tap chip to preview+select).
- **Voice cues**: optional spoken cues; voice picker lists the phone's installed
  voices + speed/pitch. (More voices require installing them via phone Settings →
  Text-to-speech.)
- **Breathing pacer**: pulsing ring on long holds.
- **Library**: search, area + type filter chips (incl. chest), equipment toggle,
  custom stretch add. Tap image = enlarge; long-press row = info popup (with
  Edit inside). "+"/"−" to add/remove.
- **Routines**: build, drag-reorder, search, ⋯ menu (rename / edit stretches /
  schedule a weekday / per-routine timing overrides / duplicate / delete),
  random generator, "Today" banner for scheduled routines.
- **Progress**: streak, this-week, total sessions/minutes, 35-day calendar,
  focus-by-area breakdown, session history.
- **Settings**: menu → sub-pages (Appearance / Timing / Sounds / Voice / Data /
  Guide). Data export/import as JSON backup.

---

## PHOTO SYSTEM

- App loads stretch photos from a `photos/` folder in the repo, named by stretch
  ID (e.g. `pigeon.jpg`). Formats: jpg/jpeg/png/webp.
- `photo-filenames.txt` lists every stretch's exact filename (a personal
  reference sheet).
- **Auto-fetch (optional)**: `fetch_photos.py` + `.github/workflows/fetch-photos.yml`
  let GitHub Actions scrape matching photos from Lift Manual and commit them into
  `photos/`. Trigger from the GitHub app: Actions → "Fetch stretch photos" →
  Run workflow. (Requires Settings → Actions → Workflow permissions → Read and
  write.) Note: downloads copyrighted images for personal use.

---

## REPO FILES

- `index.html` — the entire app (only required file to run it)
- `manifest.json` — PWA metadata (name "Limber", id "limber-stretch-app")
- `sw.js` — service worker (offline caching)
- `icon-192.png`, `icon-512.png` — app icon (red arch on blue-black)
- `fetch_photos.py` — photo scraper (optional)
- `fetch-photos.yml` — GitHub Action; must live at `.github/workflows/fetch-photos.yml`
- `photo-filenames.txt` — filename reference sheet
- `photos/` — your stretch images (you create/populate this)

---

## DEPLOY

1. Put all files in a GitHub repo (the workflow yml goes at
   `.github/workflows/fetch-photos.yml`, not the root).
2. Connect the repo to Netlify → it auto-deploys on every push.
3. Open the Netlify URL on your phone → install to home screen.
4. Updating: edit/replace `index.html` in GitHub → Netlify redeploys. Your
   on-device progress is NOT wiped by updates (only clearing browser data /
   reinstalling / switching device does that — use Settings → Data → Export for
   backups).

---

## BUILD HISTORY (condensed)

1. Built the original Limber (calm/tactile aesthetic, lime accent) with the full
   stretch library, timer, routines, progress tracking, themes, PWA setup.
2. Overhauled the library to ~261 stretches from Lift Manual; added mobility
   moves; built the GitHub Actions photo-fetch system.
3. Added: end-routine button, resume-session navigation, design polish.
4. Built per-event selectable sounds, a voice picker, and PNF as a per-stretch
   toggle.
5. Added wishlist features: next-up thumbnail, skip-prep toggle, routine
   reorder, routine search, weekday scheduling, per-routine timing overrides,
   richer progress (this-week stat, focus-by-area).
6. Created two alternate visual versions as separate apps — Float (Y2K/glossy)
   and Span (architectural/technical). Span's look was chosen for Limber.
7. Renamed the Span-design app to "Limber"; added 4 stretches (scorpion, reverse
   prayer, cow face, dead hang); renamed nerve/floss → "glide"; added muscle
   sub-tags; tap-to-enlarge images; long-press info; go-button active state.
8. Fixed bugs: skip-while-running now keeps playing; bottom content cut-off
   (changed body height:100% → min-height so padding isn't clipped).
9. Expanded the sound library to ~236 candidates, built a standalone sound-
   curator tool, and trimmed to the final 41 curated sounds.

---

## NOTES / TODO IDEAS (not built)

- Smart sequencing / supersets.
- Monthly flexibility self-check.
- Recorded-clip voice cues (fallback if device voices are insufficient).
- Populate the `photos/` folder (manually or via the fetch Action).
