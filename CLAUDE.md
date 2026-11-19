# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read first

`AGENTS.md` holds the binding project rules (scope overrides, correctness contracts, evidence rules); follow it. `Plan.md` is the product contract — never edit or rename it. `PROJECT.md` is the running log of decisions, commands, results and blockers; append to it after each milestone. The product is **WorldForge**; the directory and original GitHub repo name are **WordForge** (GitHub now redirects to `rithish007/WorldForge`).

`docs/VISION.md` holds the forward product direction: a fully browser-based,
prompt-native robot simulation editor with model-agnostic AI, an asset and robot
library, and either bring-your-own-key or subscription billing.

- Its open decisions must be answered by the user before code depends on them.
- Until then, the MVP limits in `AGENTS.md` still govern the code.
- The live public page is https://worldforge-lab.vercel.app/. The old
  `worldforge-nine` alias is retired; don't reintroduce it.

The repo root *is* the `astra/` root from the plan: `server/`, `web/` and `site/` live here directly.

## Commands (Windows / PowerShell, from repo root)

- Full local demo (backend :8000 + `next start` :3000, logs in `artifacts/logs/`): `./scripts/start-demo.ps1` — `-Check` preflights only, `-Build` forces a frontend rebuild after editing `web/`.
- Backend alone (from `server/`): `../.venv/Scripts/python.exe -m uvicorn astra.main:app --host 127.0.0.1 --port 8000`
- Python env: `.venv/` at repo root (gitignored, Python 3.12). Call `.venv/Scripts/python.exe` directly; fresh setup is `python -m venv .venv` then `pip install -r server/requirements.txt`.
- All tests (from `server/`): `../.venv/Scripts/python.exe -m pytest -q`
- Single test: `../.venv/Scripts/python.exe -m pytest tests/test_pipeline.py::test_determinism -q`
- Keep `server/pytest.ini` options (`-p no:cacheprovider` etc.); teardown stalled in this workspace without them.
- Frontend (from `web/`): `npm ci`, `npm run dev`, `npm run build`, `npm run typecheck` (add `--incremental false` if tsbuildinfo is unwritable).
- Scene export used by the parity test: `node web/tests/export-scene.mjs examples/angled_depot.json` (needs Node with TS type stripping; imports `web/lib/geometry.ts` directly).
- Static submission site preview: `python -m http.server 4173 --bind 127.0.0.1 --directory site`
- `./scripts/sync-design.ps1` copies `site/design.css` → `web/app/design.css` and `site/interaction.js` → `web/public/`; run it after changing shared design files.

## Architecture

Three independent parts:

1. **`server/astra/`** (FastAPI + Pydantic + MuJoCo). Pipeline: `specs.py` (strict `WorldSpec`, 8 object types, `ROBOTS` with sourced Boxer / RB-THERON dimensions) → `geometry.py` (structural validation incl. SAT overlap, conservative `OccupancyGrid` inflated by the largest `collision_radius + safety_margin`, navigability report) → `planner.py` (8-connected A*, shortcutting and smoothing that are kept only if every segment re-validates, 0.25 m resampling) → `simulator.py` (MJCF compile + pure-pursuit control + collision classification, deterministic hash) → `worker.py` (subprocess entry, stdin/stdout JSON). `main.py` exposes `/api/{health,worlds,robots,schema,validate,plan,run}`; `/api/run` spawns the worker with a 25 s timeout under a single global lock (409 when busy) and writes `artifacts/runs/<uuid>/`. `ai.py` mounts `/api/ai/*`.
2. **`web/`** (Next.js + React Three Fiber). `next.config.ts` rewrites `/api/*` to `127.0.0.1:8000` — there is no public backend. `/` is the prompt-first entry (`Composer.tsx`); `/lab` is the editor (`WarehouseLab.tsx`, `WorldScene.tsx`). Results are batch telemetry replayed client-side; no WebSockets. `web/lib/geometry.ts` is the **only** world↔Three.js conversion file.
3. **`site/`** — plain static submission page deployed to Vercel (project `worldforge`, Root Directory `site`, no build). Keep it separate from `web/`; never replace it with unfinished app code. The demo video is hosted on Vercel Blob and configured in `site/demo-config.js`.

Fixtures live in `server/astra/fixtures.py` and are mirrored as `examples/*.json` plus `examples/world.schema.json`.

## Contracts that span files

- `yaw_deg` is stored in specs and converted to radians exactly once at each compiler boundary (`simulator.py`, `geometry.py`, `web/lib/geometry.ts`) without mutating the spec.
- Frame: XY floor, +Z up, origin at floor centre; bounds are the clear interior and 0.10 m walls extend outward (`conventions.py`). Three.js uses one root group with `rotation.x = -π/2`; picking goes through `root.worldToLocal`.
- Rates 500/50/20 Hz (`PHYSICS_DT` 0.002, control every 10 steps, telemetry every 25).
- MuJoCo geom groups: 0 floor, 1 walls/objects, 2 robot. Collision masks are set explicitly via contype/conaffinity (non-blocking objects get contype 0); only group {1,2} contacts above 1 N count as collisions.
- `test_pipeline.py` parity test compares real Three.js meshes from `export-scene.mjs` against MuJoCo geoms (atol 1e-6) — change both sides together.
- Status names: `INVALID_MISSION`, `PLAN_FAILED`, `SUCCESS`. A blocked route is `PLAN_FAILED`, never a collision. Invalid edit batches are rejected atomically; valid-but-unreachable edits are kept with warnings.
- AI is visitor-funded: the visitor's key lives only in server RAM behind an HttpOnly cookie; spend is reserved per call in a file-locked ledger (`data/ai-spend.json`) before the request. Live AI has never been verified (`live_verified: False` in `ai.py`) — don't claim otherwise.
- If a kinematic fallback is ever shown, it must use the exact label from Plan section 17.

## Demo-video tooling (local only)

`scripts/{time-short-narration,build-short-demo,create-short-review-page,serve-demo-review,prepare-demo-voiceover}.py` build the narrated cut from `SampleRec.mp4` (318 MB, never commit) using `docs/demo-short-edit.json` / `docs/demo-narration.json`; outputs go to gitignored `artifacts/voiceover/`. Order and flags are recorded in `PROJECT.md`.
