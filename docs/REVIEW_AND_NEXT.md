# WorldForge — review, directions and LinkedIn draft

Reviewed 18 November 2026 from the code, `PROJECT.md`, `Plan.md`, `docs/` and the live sites.

## 1. What is done

**Working end to end, locally (verified by 26 passing backend tests and recorded runs):**

- A typed world format (`WorldSpec`) with 8 primitive object types, zones, categories, JSON import/export and a published JSON schema.
- Deterministic validation: schema checks, overlap checks (separating axis theorem), and a conservative occupancy grid inflated for the larger of two real AMRs (Clearpath Boxer, Robotnik RB-THERON). Dimensions come from datasheets, and estimates are labelled.
- A route planner (A* with shortcutting and smoothing, re-checked against the inflated grid) with named outcomes: `SUCCESS`, `PLAN_FAILED`, `INVALID_MISSION`.
- A real MuJoCo run in an isolated worker: 500/50/20 Hz fixed rates, explicit collision filtering, contact classification and a deterministic result hash. Reference run: crossdock, RB-THERON, success in 28.3 s over 21.95 m with 0 obstacle contacts.
- A parity test proving the browser's Three.js meshes match the MuJoCo geometry to 1e-6 m, using the real frontend source.
- A browser editor (Next.js + React Three Fiber): prompt-first entry, lab with editing, undo, categories, save/load, route plan, run and replay. Adding a barrier demonstrates an explained planning failure; undo restores the world.
- A visitor-funded AI connection. The visitor's own OpenAI key is held only in server memory, and spend is reserved before each call in a file-locked daily ledger. The model output is a strict function call that is revalidated. **This is tested with mocks only; it has never made a live call.**
- A static submission page on Vercel with analytics and a 74-second narrated demo (captions available).

**Not done / gaps:**

- **No public simulator.** The backend runs only on your own machine (localhost); the hosted site says so honestly.
- **Live AI generation is unverified.**
- **There is no record of a Product Hunt submission.** `PROJECT.md` says none was made; confirm before claiming it.
- **The old `worldforge-nine` alias returns 404.** All references to it were removed on 19 November; the live page is **https://worldforge-lab.vercel.app/**.
- **The site has no `og:image` or Twitter card**, so LinkedIn and X will show a bare link. There is also no video poster frame, and `/favicon.ico` returns 404. The video is unreadable at phone width.
- **Some work is not committed.** Doc, site and narration-script changes are uncommitted on `codex/local-demo`.

## 2. What it could become

> **Chosen direction (19 Nov):** the user wants a fully browser-based, prompt-native robot simulation editor. It would be an easy-to-use alternative to Isaac Sim, with multiple AI models, a large asset library, and either bring-your-own-key or subscription billing. The full analysis is in [VISION.md](VISION.md). The options below remain useful as **first use cases** inside that product. Option 3 is closest to the vision; option 1 is the easiest first market to sell to.

The strongest asset is not the 3D editor. It is the **honest, deterministic chain from layout to measured robot result**: the scene the user sees, the plan and the physics share one world. Directions that build on that, in order of fit:

1. **A pre-deployment AMR layout checker for warehouse planners.** Upload or draw a floor layout and pick a robot from a library of real AMR datasheets. You then get clearance heat-maps, unreachable zones, narrowest-aisle reports and travel-time estimates per mission. This is the closest to what exists, with buyers who are integrators and operations engineers. It needs a robot library, DXF/CAD import, and batch missions.
2. **Scenario-testing harness for robotics teams ("CI for robot layouts").** Worlds as JSON in git, deterministic hashes as regression baselines, and a CLI/GitHub Action that fails when a layout change breaks a mission. The deterministic hash and the typed specs already make this natural.
3. **AI world generation as a front-end for real simulators.** Keep the typed spec as the source of truth, but export to Gazebo/SDF, Isaac Sim USD and ROS 2 nav2 maps. The value is "describe a warehouse → validated, simulator-ready world in seconds". Plan §19 already lists these adapters.
4. **Teaching / outreach tool.** A browser sandbox that shows why clearance, inflation and path smoothing matter. It needs the least new tech, but it is the weakest business case.

`docs/MARKET_DISCOVERY.md` already says to prioritise robotics engineers and to get ≥3 pilot commitments before building further. Directions 1 and 2 fit that. Run the planned 5–8 interviews before choosing.

## 3. Sensible next steps

**Immediate:**

- Add an `og:image`, a video poster, captions on by default, and a favicon to `site/`.
- Commit the pending docs and scripts (not `SampleRec.mp4`).

**Next product gate:**

- Host the backend (one Docker VM, as in the plan) with the §13 limits, so the link is a working demo rather than a video.
- Run one funded live AI call and record the evidence.

**Product depth:**

- Multiple missions and robots per run, dynamic obstacles, run comparison and redo.
- Wheel dynamics in place of the planar velocity model.
- Simulator export (SDF/USD/nav2 map).
- GLB props with primitive collision proxies.

**Market:** 5–8 interviews with AMR integrators or robotics engineers, using the existing interview guide.

## 4. LinkedIn post draft

> I built a browser tool where a warehouse layout, a route planner and a physics simulation all share one world.
>
> **WorldForge** started as my entry for the GPT-6 Astra Challenge. You shape a warehouse from racks, pallets, barriers and chargers. Then you pick a real mobile robot (Clearpath Boxer or Robotnik RB-THERON, sized from their datasheets), plan a route and run it in MuJoCo.
>
> What I cared about most was honesty between layers:
> • The 3D scene in the browser matches the physics geometry to a micrometre. A test checks it on every change.
> • Routes are planned against a map inflated for the robot's real footprint. Every smoothed shortcut is re-checked before it is kept.
> • Runs are deterministic: same world, same result, same hash.
> • Failures have names. Block an aisle and the tool says *why* the route failed, instead of quietly crashing the robot.
>
> In the reference run, the robot covers 22 m through a cross-dock in 28 s with zero obstacle contacts.
>
> There's also an AI path: describe a warehouse and a model proposes it as a typed spec, which is validated before it ever reaches the scene. Visitors bring their own API key, and spending is capped per day.
>
> It's a local prototype today. The simulator isn't publicly hosted yet, so the link below is a 74-second demo.
>
> Where I'm taking it: a fully browser-based, prompt-first robot simulator. Describe the world and the task; the AI builds the scene from a library of real robots and assets, runs it, and you refine it by chatting or dragging. You choose the model, frontier or open-weight. No GPU workstation and no install. Deterministic checks sit behind every AI edit, so what you see is what was actually simulated.
>
> If you build or test robots, what's the most painful part of getting a first simulation running today?
>
> 🎥 Demo: https://worldforge-lab.vercel.app/
> 💻 Code: https://github.com/rithish007/WorldForge
>
> #Robotics #MobileRobots #MuJoCo #Simulation #WarehouseAutomation #AI

*Before posting:*

- Add an `og:image` so the link shows a preview, or attach a screenshot or the video directly. LinkedIn favours native video.
- Only mention a Product Hunt submission or placement if you have confirmation.
