# CreativeFlow Generation API v1

## Purpose

This API is the stable boundary between a separately developed frontend/backend
and the large CreativeFlow GPU generation worker. Internal planners, KG
retrieval, prompts, Qwen-Image and Hunyuan3D may continue to evolve without
forcing the caller to change.

The API is asynchronous:

1. upload source assets;
2. submit a variation job;
3. poll the job;
4. download image, GLB, OBJ and multiview artifacts from returned URLs.

Interactive OpenAPI documentation is available at `/docs`.

## Deployment environment

Set these values before starting the worker:

```bash
export CF_API_KEY='replace-with-a-long-random-secret'
export CF_API_CORS_ORIGINS='https://frontend.example.com,http://localhost:3000'
```

Put the worker behind an HTTPS reverse proxy. Do not expose SSH credentials,
raw filesystem paths, Qwen's loopback port, or the Uvicorn development port to
the browser.

All v1 requests use:

```http
X-CreativeFlow-Key: replace-with-a-long-random-secret
```

## 1. Discover supported parameters

```http
GET /api/v1/variations/capabilities
```

This is the source of truth for defaults and required assets.

## 2. Upload an asset

```bash
curl -X POST "$BASE/api/v1/assets" \
  -H "X-CreativeFlow-Key: $CF_KEY" \
  -F "flowstudio_asset_id=snowman-source-image" \
  -F "session_id=demo-001" \
  -F "file=@snowman.png"
```

The response contains an opaque `asset_id`. Pass that ID in job requests.
Supported uploads include PNG/JPEG/WebP, GLB/OBJ/ZIP, JSON and NPY.

## 3. Submit a variation

All three variations use one route:

```http
POST /api/v1/variation-jobs
```

Example:

```json
{
  "client_job_id": "ui-material-demo-001",
  "variation": "texture",
  "object_type": "snowman",
  "source": {
    "image_asset_id": "rasset_0123456789"
  },
  "prompt": "Generate diverse material analogies while preserving all geometry and identity cues.",
  "kg": {
    "top_k": 8,
    "candidate_pool_size": 20,
    "scoring_enabled": true,
    "generate_all_retrieved": false,
    "cache_mode": "cache_first",
    "request_timeout_sec": 8
  },
  "image": {
    "width": 768,
    "height": 768,
    "steps": 20,
    "seed": 42,
    "source_strength": 0.62,
    "attempts_per_candidate": 3,
    "require_white_background": true
  },
  "mesh": {
    "enabled": true,
    "max_candidates": 4
  }
}
```

`client_job_id` is an idempotency key for a variation type: retrying the same
request does not start another expensive GPU job unless the prior job failed.

### Low Fidelity

Set `"variation": "low_fidelity"`. Required:

- `source.image_asset_id`
- concrete `object_type`

The source identity and visible identity cues remain locked while global
silhouette/massing changes.

### Part

Set `"variation": "part"`. Required:

- `source.image_asset_id`
- `source.mesh_asset_id`
- `source.brush_mask_asset_id` (semantic-resolution evidence only)
- `source.sam3d_manifest_asset_id`
- `source.part_semantics_asset_id`

The manifest and semantics must come from a real SAM3D run. A fake part or
fake mask is rejected. Optional `target_part`, `socket_constraints` and
`sam3d_projection_mask_asset_id` can carry attachment information.

### Texture / material

Set `"variation": "texture"`. Required:

- `source.image_asset_id`
- concrete `object_type`

The Stage 1 planner extracts source material attributes, expands graph queries,
retrieves KG candidates, maps the selected attributes, and sends the mapped
prompts plus the source image to Qwen-Image. Hunyuan3D/PBR post-processing is
controlled by `mesh.enabled`.

## 4. Poll status and retrieve results

```http
GET /api/v1/variation-jobs/{job_id}
```

Important fields:

- `status`: `queued`, `running`, `completed`, `failed`, `cancelled`
- `stage`: current pipeline stage
- `progress`: 0 to 1
- `message` and `error`
- `candidates[]`
- `candidates[].image_url`
- `candidates[].mesh_glb_url`
- `candidates[].mesh_obj_url`
- `candidates[].multiview_url`
- `result_manifest_url`

Jobs and completed results survive an API restart. A process that was running
during a restart is marked `worker_restarted`; it is not falsely reported as
completed.

## 5. Cancel

```http
POST /api/v1/variation-jobs/{job_id}/cancel
```

## Parameter semantics

| Parameter | Meaning |
| --- | --- |
| `kg.top_k` | number of mapped KG directions retained for generation |
| `kg.candidate_pool_size` | Stage 1 retrieval/planning pool before top-k selection |
| `kg.scoring_enabled` | enable current KG candidate scoring |
| `kg.generate_all_retrieved` | bypass top-k and generate every retrieved candidate |
| `image.source_strength` | conditioned generation strength; defaults differ by variation |
| `image.attempts_per_candidate` | Qwen retries when visual QA fails |
| `mesh.enabled` | continue from generated images into Hunyuan3D/PBR |
| `mesh.max_candidates` | maximum directions sent to the heavy 3D stage |

When `generate_all_retrieved=true`, `top_k` is intentionally ignored.

## Compatibility policy

- Internal generation logic and defaults may change at any time.
- Existing v1 field meanings and response structure remain backward compatible.
- New optional fields may be added to v1.
- Removing/renaming fields or changing their meaning requires `/api/v2`.
- Experimental controls remain server-side until they are actually wired and
  stable; they must not appear as fake public parameters.
