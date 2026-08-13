# FlowStudio White Model Cleanup Report

Date: 2026-08-02

## What changed

All source zip files were extracted and organized by content:

- `OBJ_Y217.zip` → `whiteModel/extracted/bakery/`
- `OBJ_Y1316.zip` → `whiteModel/extracted/christmas/`
- `07.zip` → `whiteModel/extracted/toy_animals_toy_animal_collection_07/`

The original zip archives were preserved, but renamed and moved to:

- `whiteModel/_archives/bakery_obj_y217.zip`
- `whiteModel/_archives/christmas_obj_y1316.zip`
- `whiteModel/_archives/toy_animals_collection_07.zip`

Vendor / advertisement files were moved to:

- `whiteModel/_ignored_vendor_files/`

Generated content manifest:

- `whiteModel/WHITE_MODEL_CONTENT_MANIFEST.json`

## Active model library

Active OBJ models remain in:

- `whiteModel/extracted/bakery/`
- `whiteModel/extracted/christmas/`

The active local frontend white-model manifest now contains 34 selectable local white models.

## High-poly quarantine

The following assets were removed from the active frontend selectable library and moved to quarantine:

| Asset | Reason | Approx faces | Path |
|---|---:|---:|---|
| Christmas Chimney | high-poly over 500k faces | 1,013,740 | `whiteModel/_quarantine_highpoly/christmas/Chimney.obj` |
| Toy animal collection 07 | high-poly and caused browser timeout | 725,020 | `whiteModel/_quarantine_highpoly/toy_animals_toy_animal_collection_07/toy_animal_collection_07.obj` |

The Toy Animal 07 FBX/C4D source files were also moved into the same quarantine folder to avoid accidental loading.

## Frontend manifest update

Updated:

- `backend/storage/files/white-models/manifest.json`

Removed from active `assets`:

- `white:christmas:chimney`
- `white:toy_animals:toy-animal-collection-07`

Added `quarantined_assets` metadata so the removal is explainable and reversible.

Verification:

- Local white models exposed by `/api/v1/benchmark-assets`: 34
- `white:christmas:chimney`: not present
- `white:toy_animals:toy-animal-collection-07`: not present

## GPU / Qwen-image / image-to-3D adjustment

The previous E2E run did not finish Qwen-image or image-to-3D because the backend was started without a configured remote worker.

Confirmed old health state:

- `remote_worker_configured: false`
- `remote_worker_ok: false`

Adjusted local config:

- Added `.env.example`
- Created local ignored `.env`
- Created local ignored `backend/.env`
- Restarted backend on `127.0.0.1:8001`

Current health state:

- `remote_worker_configured: true`
- `remote_worker_ok: false`
- Current remote error: worker endpoint unavailable / HTTP 502

Meaning:

- The backend is now correctly configured to look for the GPU worker.
- The actual GPU worker is still not reachable on the expected local endpoint.
- Once the GPU worker / SSH tunnel is up, Qwen-image and Hy3D should be able to run through the real worker path instead of silently staying in a local generating state.

Updated config docs/scripts:

- `.env.example`
- `scripts/dev_stack.sh`
- `scripts/health_check.sh`
- `README.md`
- `backend/README.md`

