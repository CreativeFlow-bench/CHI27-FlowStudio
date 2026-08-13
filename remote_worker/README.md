# FlowStudio Remote CreativeFlow Worker

This worker is intended to run on the GPU server. It wraps the existing
CreativeFlow command-line pipeline behind a small HTTP job API.

Target server paths from the initial audit:

```text
CreativeFlow pipeline:
  /root/creativeflow_pipeline

Python environment:
  /root/autodl-tmp/venvs/torch5090/bin/python

Transfer script:
  /root/creativeflow_pipeline/pipeline_transfer_engine.py

Hunyuan3D post script:
  /root/creativeflow_pipeline/pipeline_hunyuan3d_post.py
```

Run on the server:

```bash
cd /path/to/remote_worker
/root/autodl-tmp/venvs/torch5090/bin/uvicorn app:app --host 0.0.0.0 --port 18100
```

Endpoints:

```text
GET  /health
POST /assets/upload
POST /jobs/transfer
POST /jobs/hy3d
POST /jobs/autopartgen
POST /jobs/partfield
GET  /jobs/{job_id}
POST /jobs/{job_id}/cancel
GET  /artifacts/{artifact_id}
```

The local FlowStudio backend should call this worker over HTTP through
`RemoteCreativeFlowWorkerAdapter`. The user-facing frontend API remains unchanged.
When a completed worker job produces a small JSON result file, the worker places
its parsed content in `job.result.result_json` for the local backend to consume.

Legacy optional AutoPartGen preparation on the GPU server:

AutoPartGen was prepared during early exploration, but it is not the current
FlowStudio part-replacement path. The active path is PartField part discovery
plus CreativeFlow-Part. Keep AutoPartGen as a legacy optional reproduction
record unless the project explicitly returns to that model.

```text
/root/autodl-tmp/AutoPartGen
/root/autodl-tmp/venvs/autopartgen
/root/autodl-tmp/setup_autopartgen_env.log
```

`/jobs/autopartgen` defaults to dry-run in development so it can validate command
and script generation without loading the full model.

The AutoPartGen environment is expected at:

```text
/root/autodl-tmp/venvs/autopartgen
```

The released default checkpoints are required for real inference:

```text
/root/autodl-tmp/AutoPartGen/checkpoints/autopartgen_dit.pth
/root/autodl-tmp/AutoPartGen/checkpoints/autopartgen_vae.pth
```

`facebook/autopartgen` is gated on Hugging Face, so checkpoint download requires
authorized access. Missing AutoPartGen checkpoints are expected in the current
setup and are not a blocker for the PartField + CreativeFlow-Part path.

PartField preparation on the GPU server:

```text
/root/autodl-tmp/PartField
/root/autodl-tmp/venvs/partfield
/root/flowstudio_remote_worker/setup_partfield_env.sh
/root/flowstudio_remote_worker/flowstudio_partfield_worker.py
```

Install or refresh PartField:

```bash
cd /root/flowstudio_remote_worker
PARTFIELD_ROOT=/root/autodl-tmp/PartField \
PARTFIELD_ENV=/root/autodl-tmp/venvs/partfield \
./setup_partfield_env.sh
```

The setup script uses Python 3.10 and the Objaverse checkpoint at
`model/model_objaverse.ckpt`. On the current RTX PRO 6000 Blackwell server,
FlowStudio uses PyTorch 2.10.0 with CUDA 12.8 because older cu124 wheels do not
support `sm_120`. The worker also ships a lightweight `torch_scatter` shim for
the PartField inference path, then runs feature extraction via
`partfield_inference.py` and clustering via `run_part_clustering.py`.

`/jobs/partfield` accepts a server-readable mesh path and writes
`partfield_manifest.json` with:

```text
parts[]
face_labels_path
segmented_mesh_path
feature_root
cluster_root
```

The local FlowStudio backend treats PartField as the preferred part-discovery
worker. When PartField is unavailable or only dry-run metadata is available, the
backend returns a failed / empty part-discovery response instead of creating
deterministic mock semantic parts.

## Geometry Processing Worker

The remote worker also exposes deterministic geometry operations so PartField
regions and CreativeFlow / Hunyuan3D candidates can be processed close to the
server-side assets:

```text
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
```

The geometry worker is CPU-only in v0 and writes outputs under
`/root/autodl-tmp/flowstudio_worker_runs/{job_id}/geometry`. Outputs are served
through `/artifact-file?path=...`, using the same allowlist as other worker
artifacts. It only reads paths inside the worker run root, uploaded asset root,
or benchmark input root.

Smoke examples:

```bash
curl -X POST http://127.0.0.1:18100/geometry/bbox \
  -H 'Content-Type: application/json' \
  -d '{"flowstudio_job_id":"geom_smoke","source_mesh_path":"/root/autodl-tmp/flowstudio_worker_assets/example/source.obj"}'

curl -X POST http://127.0.0.1:18100/geometry/extract-region \
  -H 'Content-Type: application/json' \
  -d '{"flowstudio_job_id":"geom_smoke","source_mesh_path":"/root/autodl-tmp/flowstudio_worker_assets/example/source.obj","part":{"part_id":"pf_part_01","metadata":{"source_part_id":"cluster_3","face_labels_path":"/root/autodl-tmp/flowstudio_worker_assets/example/labels.npy"}}}'
```

## Render Preview Worker

The remote worker uses a portable Blender install for cached preview rendering:

```text
Blender binary:
  /root/autodl-tmp/blender/blender-5.0.0-linux-x64/blender

Installed from:
  https://download.blender.org/release/Blender5.0/blender-5.0.0-linux-x64.tar.xz
```

The remote render endpoints are:

```text
POST /render/thumbnail
POST /render/multiview
POST /render/turntable
POST /render/before-after
POST /render/mask-visualization
POST /render/candidate-card
POST /render/part-preview
GET  /render/jobs/{job_id}
```

Outputs are written under
`/root/autodl-tmp/flowstudio_worker_runs/{job_id}/render` and served through
`/artifact-file?path=...`.

Smoke example:

```bash
curl -X POST http://127.0.0.1:18100/render/thumbnail \
  -H 'Content-Type: application/json' \
  -d '{"flowstudio_job_id":"render_smoke","source_mesh_path":"/root/autodl-tmp/flowstudio_worker_assets/example/source.obj"}'
```

The local backend falls back to this remote render worker when local Blender is
not installed, so `/api/v1/render/thumbnail` can still return real PNG previews.
