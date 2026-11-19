# WorldForge product vision

Recorded 19 November 2026 from the user's stated intent. This sets the forward
direction. `Plan.md` remains the contract for the MVP that was built and is
unchanged. Each phase below needs the user's go-ahead before code depends on it
(see "Open decisions").

## The intent, in one line

A **completely browser-based, prompt-native robot simulation editor**. It offers
the kind of capability people go to NVIDIA Isaac Sim for, with the ease of use of
prompt-to-product tools like Lovable or Claude Design. You describe a world and a
robot task, and the AI builds the scene, places assets and robots, sets up the
mission and runs it. You then refine everything by prompting or by direct
manipulation.

## What the user asked for

1. **Fully in the browser.** No workstation GPU and no local install. A link is
   all a user needs.
2. **AI-native editing.** Prompt in, editable 3D simulation out. Iterate in
   conversation, as in Lovable or Claude Design.
3. **A choice of models:**
   - frontier models with strong 3D and spatial skills, such as Claude Opus 5.5
     (`claude-opus-5-5`), Claude Fable 5.2 (`claude-fable-5-2`) and GPT-6.1 Sol;
   - open-weight models.
4. **A large asset library.** NVIDIA SimReady assets plus other openly licensed
   models of robots, props and environments.
5. **Two ways to pay for AI:**
   - **Bring your own key:** users connect their own provider account.
   - **A WorldForge subscription:** users pay a monthly fee and use models
     through WorldForge.

## Positioning

- **Isaac Sim** is powerful but asks a lot. It needs an RTX workstation or a cloud
  GPU, Omniverse, a USD and PhysX workflow, Python scripting, and long setup.
- **WorldForge's niche** is the first 80% of a simulation task, done in minutes
  and in a browser tab:
  - lay out an environment;
  - drop in a real robot;
  - define a task;
  - see whether it works and why not.
  
  When high-fidelity work is needed, the user exports to Isaac Sim, Gazebo or
  MuJoCo.
- **Naming:** describe WorldForge as a "browser-based, AI-native alternative" or as
  working "alongside Isaac Sim". Never present it as a version of Isaac Sim, and
  never use NVIDIA branding.

## What carries over from the current build

These are the moat. LLMs are not reliable at precise 3D placement, so the product
has to stand on deterministic checks behind the model:

- **A typed world spec as the single source of truth.** The model emits typed tool
  calls, never raw meshes or code.
- **Deterministic checks behind the model:** schema, overlap and navigability
  checks, plus atomic edit batches. Failed edits leave the world unchanged.
- **Proof that the view matches the physics:** the parity test between the browser
  scene and the physics geometry.
- **Repeatable runs:** a deterministic result hash.
- **Honest labels:** failures have names, and physics is never claimed when it
  was not run.
- **Visitor-key handling and the spend ledger.** These become the basis for both
  billing modes.

## What must change from the MVP rules

| MVP rule (AGENTS.md / Plan.md) | Vision needs | Notes |
|---|---|---|
| 8 primitive object types | Asset library: meshes with collision proxies and physical metadata | Keep primitives as the collision and physics layer; meshes are what users see. |
| Two AMRs (Boxer, RB-THERON) | Robot library: wheeled robots, arms, mobile manipulators, legged robots later | Import from URDF and MJCF. MuJoCo Menagerie is the obvious first source. |
| Headless MuJoCo on a server VM | Physics in the browser | MuJoCo has a WebAssembly build. Check that its official bindings are current and that results stay deterministic across browsers. |
| Python validator and planner | Same logic available in the browser | Either port it to TypeScript with parity tests against the Python reference, or keep a thin server for validation only. Decision needed. |
| OpenAI Responses API only | Model-agnostic agent layer | One tool schema with adapters for Anthropic, OpenAI and OpenAI-compatible open-weight endpoints. |
| No accounts, no database | Accounts, saved projects, billing | Required for subscriptions and cloud projects. |
| Kinematic AMR velocity control | Richer dynamics, sensors (lidar, depth, RGB), multiple robots | Already listed in Plan §19. |

## Proposed architecture

- **Editor (browser):** Next.js with React Three Fiber, as today. It has a chat
  panel beside a live 3D viewport and a scene outliner. Direct manipulation and
  prompts edit the same spec.
- **Physics (browser):** MuJoCo WebAssembly in a Web Worker at fixed
  500/50/20 Hz. The spec is compiled to MJCF in the browser, using the same
  conventions as `server/astra/simulator.py` and verified by a parity test.
- **Agent layer:** a provider-agnostic tool set:
  - `add_asset`, `move`, `delete`
  - `set_robot`, `define_mission`
  - `run_simulation`, `query_scene`
  - `render_view`, which returns screenshots so vision models can check their own
    work.
  
  Every tool call is validated before it is applied. Model IDs are configurable,
  and each model must pass a committed eval suite (placement accuracy, edit
  correctness, refusal of invalid layouts) before it is offered.
- **Asset library:** a manifest entry per asset with:
  - source, licence, attribution and verified dimensions (or an "estimate" label);
  - mass, collision proxy and physics material;
  - a GLB for display.
  
  Conversion pipeline: USD or other source formats → GLB plus primitive or
  convex-hull collision proxies.
- **Thin backend (still needed even when "browser-based"):**
  - key handling;
  - subscription metering;
  - asset CDN;
  - project storage;
  - optional heavy jobs: batch runs, export.

## Asset sources to evaluate (licences must be checked per asset)

- **NVIDIA SimReady assets:** USD with physics metadata. Licence terms must allow
  hosting and serving them from a third-party web app. Do not assume they do.
  Large USD files will also need conversion to GLB for the web.
- **Robots:** MuJoCo Menagerie and `robot_descriptions`. Licences are per model.
  Also manufacturer URDFs, such as Clearpath and Robotnik.
- **Props and environments:**
  - Poly Haven and Kenney (CC0);
  - Objaverse and Sketchfab, filtered to CC0 and CC-BY with attribution.

## AI access and billing

- **Bring your own key:** API keys for Anthropic, OpenAI, OpenRouter-style
  gateways and self-hosted OpenAI-compatible servers (vLLM, Ollama).
  - Consumer chat subscriptions such as ChatGPT Plus or Claude Pro generally
    cannot be plugged into third-party apps. Users need API keys, unless a
    provider offers third-party OAuth. Check current provider terms before
    promising "connect your subscription".
  - Today's rule is that keys stay on the server. Calling providers directly from
    the browser would change that; it is a decision for the user (see below).
- **WorldForge subscription:**
  - requires accounts, Stripe (or similar) billing and per-plan credit metering;
  - requires a database-backed version of today's spend-reservation ledger.
  - Price from measured tokens per session, not guesses. Frontier 3D editing
    sessions with screenshot feedback are expensive, and today's ledger already
    reserves about $1.23 per call.
- **Free tier:** templates, manual editing and samples, with no AI. An optional
  small open-weight model could be added, but it carries a GPU cost.

## Phased roadmap

0. **Housekeeping (now):**
   - Keep the public site pointing only at working URLs.
   - Commit pending work.
   - Make one live, recorded AI call with one provider.
1. **Model-agnostic agent:**
   - Adapters for Anthropic, OpenAI and OpenAI-compatible endpoints.
   - Bring-your-own-key for all of them.
   - Committed edit and placement evals per model.
2. **Browser physics:**
   - MuJoCo WebAssembly prototype.
   - Parity and determinism tests against the server.
   - Publicly hosted interactive demo.
3. **Asset and robot library v1:**
   - CC0 props and Menagerie robots, with a licence manifest.
   - Display meshes with collision proxies.
   - URDF and MJCF import.
4. **Accounts and subscription:**
   - Saved projects.
   - Billing with metered credits.
5. **Fidelity and interop:**
   - SimReady and USD import (if the licence allows).
   - Sensors and multiple robots.
   - Export to Isaac Sim (USD), Gazebo (SDF) and ROS 2 nav2 maps.

## Open decisions (need the user's answer before dependent work)

1. **Physics location:** run fully in the browser with MuJoCo WebAssembly, or keep
   a server worker as the reference and fallback?
2. **Validator and planner:** port to TypeScript, or keep them as a thin server API?
3. **Key handling:** keys only on the server (current rule), or an option to keep
   them in the browser and call providers directly?
4. **First providers:** which go first (Anthropic, OpenAI, an open-weight
   gateway), and which model is the default?
5. **Subscription:** price points, credit units, and whether to launch it before
   or after bring-your-own-key.
6. **First robot domain beyond AMRs:** arms, mobile manipulators or legged robots?
7. **SimReady:** proceed only after a licence review, or start with CC0 and
   Menagerie only?

## Risks

- **LLM spatial precision.** Mitigation: typed tools, deterministic validation,
  render-and-check loops and per-model evals.
- **Browser physics limits.** Large scenes and contact-rich manipulation may not
  run well on low-end devices. Mitigation: scene budgets and a server fallback.
- **Asset licensing and redistribution,** especially for NVIDIA assets.
- **Margin on subscriptions** with frontier models.
- **Scope.** Each phase should ship something demonstrable, and the honest-label
  rules still apply.
