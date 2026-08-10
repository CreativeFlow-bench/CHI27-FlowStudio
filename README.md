# FlowStudio Prototype

FlowStudio is an interaction-aware CreativeFlow prototype. It includes:

- a FastAPI backend aligned with `FLOWSTUDIO_API_CONTRACT_V0.md`,
- a rule-based MVP of the Interaction Understanding Layer,
- a clean React + Three.js debug frontend,
- a remote FastAPI worker for wrapping GPU CreativeFlow, PartField, and legacy
  optional AutoPartGen boundaries.

## Current Local API Runtime

The active local development profile uses external model APIs only:

```text
Fast intent + multimodal perception: gemini-3.6-flash
Reasoning + re-representation:      gpt-5.5
Image generation + editing:         gpt-image-2
Legacy Qwen/local VLM adapters:      disabled
Remote worker/Hunyuan3D:             disabled
```

Configure the shared OpenAI-compatible relay with neutral names. Existing
`GEMINI_API_BASE` and `GEMINI_API_KEY` remain credential compatibility
fallbacks, so the previous local key can continue to be used without copying it
into source control.

```bash
MODEL_API_BASE=https://128api.cn/v1
MODEL_API_KEY=...
MODEL_FAST_TEXT=gemini-3.6-flash
MODEL_REASONING_TEXT=gpt-5.5
MODEL_IMAGE=gpt-image-2
ENABLE_LEGACY_LOCAL_MODELS=false
ENABLE_3D_GENERATION=false
```

Start the local-only backend and frontend on the fixed development ports:

```bash
FLOWSTUDIO_KEEP_RUNNING=1 scripts/dev_stack.sh
# backend:  http://127.0.0.1:18001
# frontend: http://127.0.0.1:5184
```

The rollback adapters remain in the repository, but the startup inventory does
not instantiate, probe, or launch them unless
`ENABLE_LEGACY_LOCAL_MODELS=true` is explicitly set before process start.
Likewise, every Hy3D endpoint returns `3D_GENERATION_DISABLED` unless
`ENABLE_3D_GENERATION=true` is explicitly set before process start.

Before any paid evaluation, list exact relay capabilities. Text and image calls
are separate opt-ins; artifacts are written below `outputs/api_model_eval/` and
the manifest never includes the API key.

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python \
  scripts/probe_model_api.py --list-models
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python \
  scripts/probe_model_api.py --text-only
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python \
  scripts/probe_model_api.py --with-images
```

## Local Backend

The frontend is a client of the FastAPI service; it is not a standalone page.
Start the full local stack with the helper below when possible. The separate
backend command is useful when debugging the API itself.

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python \
  -m uvicorn app.main:app --reload --host 127.0.0.1 --port 18001
```

Useful endpoints:

```text
GET  /health
POST /api/v1/sessions
POST /api/v1/assets
POST /api/v1/assets/upload
POST /api/v1/parts/discover
POST /api/v1/generation/replace
POST /api/v1/generation/drag
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/candidates
GET  /api/v1/candidates/{candidate_id}
POST /api/v1/cases
GET  /api/v1/cases/{case_id}
WS   /ws/sessions/{session_id}
```

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5184
```

`npm run dev` uses a same-origin Vite proxy for `/api`, `/health`, `/files`,
and `/ws`, forwarding to `http://127.0.0.1:18001`. Override that target with
`FLOWSTUDIO_DEV_API_TARGET` when the backend runs elsewhere. The current local
target is `http://127.0.0.1:18001`. If the backend is
not running, the page now shows a retryable connection error instead of an
infinite initialization spinner.

The frontend creates a session, registers a demo speaker asset, opens a WebSocket,
shows a Three.js 3D canvas, supports `.glb/.obj/.zip` upload, loads uploaded
`.glb`, `.obj`, and proxied PartField `.ply` files in the canvas, sends brush/drag events, displays intent hypotheses
and six-signal interpretation previews, requests generation candidates, previews
candidate GLB/OBJ meshes, previews PartField segmented part discovery output,
accepts/rejects candidates, and saves the current result as a
case with a generated report URL. The setup panel also shows the latest
part-discovery adapter/status/remote diagnostics after clicking `Parts`.

## Local Stack Helpers

The repo includes small helper scripts for repeatable local checks:

```bash
scripts/health_check.sh
FLOWSTUDIO_KEEP_RUNNING=1 scripts/dev_stack.sh
```

`health_check.sh` checks the local backend, frontend, and remote worker tunnel.
It uses these defaults:

```text
FLOWSTUDIO_API_URL=http://127.0.0.1:8000
FLOWSTUDIO_WEB_URL=http://127.0.0.1:5173
REMOTE_CREATIVEFLOW_WORKER_URL=http://127.0.0.1:18100
```

`dev_stack.sh` starts the local backend and Vite frontend with the remote worker
URL wired into the backend process. It uses `backend/.venv` when available and
falls back to `.flowstudio-run/py312-test-venv`; set `FLOWSTUDIO_PYTHON_BIN` to
choose another environment. By default it expects a worker on
`http://127.0.0.1:18100`. If you use the SSH tunnel helper, it switches to the
tunnel endpoint `http://127.0.0.1:18101`. It does not store SSH credentials;
start or restore the SSH tunnel separately when the remote worker is needed.

## Cloud Collaboration Runtime

The shared prototype should run on the cloud server. Localhost is only a
developer debug mode.

Current cloud paths:

```text
Cloud backend/API gateway: /root/flowstudio_backend
Remote worker:             /root/flowstudio_remote_worker
Backend port:              18000
Worker port:               18100
```

Start or restart the cloud services on the server:

```bash
cd /root/flowstudio_backend
bash scripts/cloud_start.sh
```

Check the cloud services on the server:

```bash
cd /root/flowstudio_backend
.venv/bin/python scripts/cloud_health_check.py
.venv/bin/python scripts/cloud_backend_smoke.py
```

`cloud_start.sh` starts:

```text
cloud FlowStudio backend -> http://127.0.0.1:18000
remote worker            -> http://127.0.0.1:18100
```

The static frontend defaults to the browser host's `:18000` API and derives its
WebSocket URL from that origin. For a provider mapping or HTTPS reverse proxy,
set `FLOWSTUDIO_PUBLIC_API_BASE` and `FLOWSTUDIO_PUBLIC_WS_BASE` before running
`cloud_start.sh`; it writes these values to `frontend/dist/runtime-config.js`
without requiring a rebuild.

That same rule applies to `npm run preview`: a local preview of a production
build must either point the runtime config at the local `:8000` backend or use
the dev server, which already uses the Vite proxy.

The cloud backend calls the internal worker directly, so geometry, Blender
rendering, PartField, CreativeFlow, and Hy3D jobs do not depend on a developer's
laptop.

If the cloud provider has not exposed port `18000`, collaborators can temporarily
open a local tunnel:

```bash
FLOWSTUDIO_REMOTE_PASSWORD=... scripts/start_cloud_backend_tunnel.expect
```

Then point the frontend/API client to:

```text
http://127.0.0.1:18000
```

For a real team handoff, prefer a provider-level port mapping or HTTPS reverse
proxy over per-person tunnels.

## Tests

```bash
cd backend
.venv/bin/pytest -q

cd ../frontend
npm run build
```

## Remote CreativeFlow Worker

The remote worker skeleton is in `remote_worker/`.

It is intended to run on the GPU server and expose:

```text
GET  /health
POST /assets/upload
POST /jobs/transfer
POST /jobs/creativeflow-global
POST /jobs/creativeflow-form
POST /jobs/creativeflow-part
POST /jobs/creativeflow-texture
POST /jobs/hy3d
POST /jobs/autopartgen
POST /jobs/partfield
POST /geometry/normalize
POST /geometry/bbox
POST /geometry/extract-region
POST /geometry/extract-faces
POST /geometry/attachment-boundary
POST /geometry/deform-preview
POST /geometry/fit-candidate
POST /geometry/seam-blend
POST /geometry/cleanup
POST /geometry/convert
GET  /geometry/jobs/{job_id}
POST /render/thumbnail
POST /render/multiview
POST /render/turntable
POST /render/before-after
POST /render/mask-visualization
POST /render/candidate-card
POST /render/part-preview
GET  /render/jobs/{job_id}
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
GET  /artifacts/{artifact_id}
```

Server paths discovered during audit:

```text
/root/creativeflow_pipeline
/root/creativeflow_vlm_service
/root/creativeflow_image_service
/root/autodl-tmp/venvs/torch5090
/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct
/root/autodl-tmp/models/Qwen-Image
/root/autodl-tmp/models/Hunyuan3D-2mv
```

Run on the server after copying `remote_worker/`:

```bash
cd remote_worker
/root/autodl-tmp/venvs/torch5090/bin/python -m uvicorn app:app --host 127.0.0.1 --port 18100
```

Point the local backend to it with:

```bash
export REMOTE_CREATIVEFLOW_WORKER_URL=http://SERVER_HOST:18100
```

When using an SSH tunnel:

```bash
ssh -fN -L 18101:127.0.0.1:18100 -p 47501 root@connect.westd.seetacloud.com
export REMOTE_CREATIVEFLOW_WORKER_URL=http://127.0.0.1:18101
```

Check the bridge through the local backend:

```bash
curl http://127.0.0.1:8000/api/v1/remote-worker/health
```

The current local backend can submit HTTP transfer, staged CreativeFlow, Hy3D,
and PartField jobs to the remote worker. Transfer and staged CreativeFlow still
default to dry-run unless real generation is enabled through environment flags;
PartField discovery defaults to real execution when the remote worker is
configured and a server-readable mesh is available. Completed remote PartField
manifests are mapped into frontend-friendly `pf_part_01` style records while
preserving raw cluster ids, face counts, labels, and segmented mesh paths in
metadata. When the source
asset was uploaded locally, the backend syncs it to the worker through
`POST /assets/upload` so the remote request receives a server-readable
`mesh_path`.

Only enable real remote CreativeFlow transfer jobs intentionally:

```bash
export REMOTE_CREATIVEFLOW_REAL_JOBS=true
export REMOTE_CREATIVEFLOW_TRANSFER_VARIANT=minimal
```

To automatically run Hy3D after a real transfer and attach mesh metadata to the
local candidates:

```bash
export REMOTE_CREATIVEFLOW_AUTO_HY3D=true
export REMOTE_CREATIVEFLOW_HY3D_MAX_CANDIDATES=1
```

Verified real minimal transfer path:

```text
local backend -> remote worker /jobs/transfer -> pipeline_transfer_engine_minimal.py
-> transfer_engine_result.json -> FlowStudio candidates
-> optional /jobs/hy3d -> mesh.glb / mesh.obj / multiview metadata
```

The verified candidate labels were parsed from the remote transfer rationale
metadata, for example `Remote transfer: Dali-like` and
`Remote transfer: Feitian-like`.

Verified remote Hy3D output from a Qwen Image transfer candidate:

```text
job_id=rw_hy3d_36d5a30a59
mesh_glb=/root/autodl-tmp/flowstudio_worker_runs/rw_hy3d_36d5a30a59/hy3d/01_rat_4e278045/mesh.glb
mesh_obj=/root/autodl-tmp/flowstudio_worker_runs/rw_hy3d_36d5a30a59/hy3d/01_rat_4e278045/mesh.obj
oss_prefix=creativeflow/flowstudio/rw_hy3d_36d5a30a59/flowstudio_asset_test_image/01_rat_4e278045
```

## Staged CreativeFlow

The backend and remote worker now support stage-aware generation:

```text
silhouette -> low-fidelity global image previews
rough_form -> medium-fidelity global form directions
part       -> semantic part divergence with fit contracts
texture    -> geometry-preserving material / surface directions
```

Global creative divergence remains part of the core flow. The staged path is:

```text
early ideation  -> broad silhouette exploration, low precision, many options
middle ideation -> rough form exploration plus local part alternatives
late refinement -> texture, material, and surface-detail variants
```

`generation.metadata.stage` chooses the creative target. `generation.metadata.fidelity`
chooses the generation budget and output promise: low fidelity can be preview-only,
medium can produce inspectable rough meshes, and high should preserve fitting or
geometry constraints.

Stage selection is not exclusive. Early sessions should favor low-fidelity
global silhouette divergence, middle sessions can alternate between rough global
form and local part alternatives, and late sessions should default to
geometry-preserving texture/material variants unless the user explicitly reopens
shape exploration.

The frontend sends stage hints through `generation.metadata.stage` and
`generation.metadata.fidelity`. With `REMOTE_CREATIVEFLOW_REAL_JOBS=true`, the
remote worker can call Qwen Image for real staged preview images. Verified low
fidelity silhouette generation produced remote preview PNGs and registered them
as candidate `metadata.remote_image_path` values in the local backend.

The current React prototype exposes the staged channels directly in the Studio
panel as outline, form, part, and texture steps. It also shows the active
divergence axes, expected commit policy, selected part socket summary, and
segmentation artifact status so the user can see whether a request is broad
global exploration or PartField-backed local replacement.

The 3D canvas is height-constrained in the app shell so WebGL rendering stays
inspectable on both desktop and mobile layouts instead of letting the canvas
intrinsic size stretch the page. Runtime checks use Chrome screenshots and pixel
analysis to confirm the viewport is nonblank and controls do not overlap.

Generated candidates include a `metadata.pipeline_evidence` summary. The
frontend displays this evidence in each candidate card: remote worker job,
direction id, fit status, result artifact, and PartField socket evidence when
available. This gives UI collaborators a stable contract for debugging real
CreativeFlow-Part results without depending on raw remote-worker JSON shape.

Saved case reports also include this pipeline evidence for accepted candidates:
remote job, stage, direction id, socket evidence, preview/mesh/OBJ links, and
remote result path. This makes a saved FlowStudio case auditable enough to trace
which CreativeFlow or CreativeFlow-Part worker result produced each design
direction.

Generated remote previews are served back to the browser through the local
backend proxy:

```text
GET /api/v1/remote-worker/artifact-file?path=/root/autodl-tmp/...
```

Staged candidates set `thumbnail_url` to this proxy path, so the frontend can
render preview images directly in the candidate cards.

For `rough_form` and `part` stages, the worker can also run Hunyuan3D after the
staged preview image is generated. The resulting GLB/OBJ paths are proxied back
through the same local artifact endpoint and registered as `candidate.mesh_url`
and `candidate.obj_url`.

The frontend candidate panel can preview generated meshes directly in the
Three.js canvas by selecting `Preview` on a candidate with `mesh_url`.
Accepting a mesh/OBJ candidate promotes it to the active asset; image-only
candidates can be accepted as direction feedback without replacing the canvas
asset.

Generation requests are also sent as realtime `generation_requested` events, so
the Interaction Understanding Layer records the selected stage, fidelity, and
divergence axes before the REST generation job starts.

When a real PartField part is selected for `stage=part`, the frontend now carries
the selected part record and PartField metadata through `selection.metadata`.
The backend expands that metadata into the remote worker's `target_part` and
`socket_constraints`, including source cluster id, face count, 3D bbox, face
labels path, and segmented mesh path. This is the current contract for
CreativeFlow-Part fitting.

## Legacy Optional AutoPartGen

AutoPartGen was prepared during early exploration, but it is not the current
FlowStudio part-replacement path. The active path is PartField part discovery
plus CreativeFlow-Part replacement and fitting. AutoPartGen remains documented
only as a legacy optional reproduction record.

Current server preparation:

```text
source: /root/autodl-tmp/AutoPartGen
tarball: /root/autodl-tmp/autopartgen-main.tar.gz
env: /root/autodl-tmp/venvs/autopartgen
setup script: /root/autodl-tmp/setup_autopartgen_env.sh
setup log: /root/autodl-tmp/setup_autopartgen_env.log
```

Verified:

```text
torch 2.5.1+cu121
diffusers 0.32.2
transformers 4.57.6
trimesh 4.12.2
autopartgen import ok
```

Remote worker supports a safe dry-run endpoint:

```text
POST /jobs/autopartgen
```

The full model reproduction still requires the released checkpoints from
`facebook/autopartgen`:

```text
checkpoints/autopartgen_dit.pth
checkpoints/autopartgen_vae.pth
```

The model repo is gated on Hugging Face. Checkpoint download currently fails
without authorized access. Missing AutoPartGen checkpoints are not a current
FlowStudio blocker because the active part pipeline uses PartField.
See `AUTOPARTGEN_ACCESS.md` and `remote_worker/download_autopartgen_checkpoints.sh`
for the token-safe access and download flow.

## PartField Part Discovery

PartField is the preferred immediate substitute for gated AutoPartGen part
discovery. The local `/api/v1/parts/discover` endpoint now tries the remote
`/jobs/partfield` worker path first when a remote worker is configured, then
falls back to deterministic local part records if the remote worker is not ready.

Server-side files:

```text
/root/flowstudio_remote_worker/flowstudio_partfield_worker.py
/root/flowstudio_remote_worker/setup_partfield_env.sh
```

Current worker health exposes:

```text
partfield_root_exists
partfield_python_exists
partfield_model_exists
partfield_worker_script_exists
```

Real PartField inference still requires running the setup script on the GPU
server and downloading the Objaverse checkpoint from the upstream PartField
Hugging Face repository. The setup script first tries `git clone`; if the GPU
server's GitHub TLS connection fails or hangs, it falls back to the GitHub
codeload tarball. The codeload tarball is saved at
`/root/autodl-tmp/partfield-main.tgz` and uses resume-capable downloads on
reruns. A complete tarball has also been uploaded from the local machine to that
path to avoid the GPU server's slow GitHub download path. The setup script uses
conda Python 3.10 when available, matching the upstream PartField environment
recommendation. It also re-validates `partfield_inference.py` before dependency
installation and re-extracts the persisted tarball if the source tree is missing.
