# Experiment Project V1 Acceptance

Date: 2026-08-09  
Workspace: `/Users/primav/Documents/博一/CHI27-FlowStudio`

## Accepted scope

- Temporary workspace remains usable and does not create project events.
- New experiment files support blank and current-state baselines.
- Project events use an append-only SQLite/WAL ledger with ordered sequence and idempotency keys.
- Browser payloads are type-whitelisted, secret-filtered, and stripped of signed URL query strings.
- Session reset does not remove project events.
- Project files retain stable asset references; export copies resolvable assets and reports missing references.
- Left menu shows temporary/recording/ended state, New/Open, timeline, end Run, and export actions.
- AI Behavior defaults to one current phenomenon and one next question; raw narration is collapsed under details.
- Only one unanswered decision bubble is placed on the canvas.

## Automated verification

Backend project/four-stage regression:

```bash
PYTHONPATH=backend .flowstudio-run/py312-test-venv/bin/python -m pytest \
  backend/tests/test_project_api.py \
  backend/tests/test_realtime_observation.py \
  backend/tests/test_four_stage.py \
  backend/tests/test_four_stage_e2e.py -q
```

Result: **80 passed**, 2 pre-existing warnings.

Frontend:

```bash
node --experimental-strip-types --test frontend/tests/*.test.ts
cd frontend && npm run build
```

Result: **70 passed**; Vite production build completed. Existing third-party `onnxruntime-web` eval and chunk-size warnings remain.

Export acceptance ZIP members:

```text
manifest.json
events.jsonl
projection.json
checksums.json
assets/source.glb
```

## Browser acceptance

Checked at `http://127.0.0.1:5173/` against the local backend:

- Desktop: concise AI Behavior hierarchy, locked More Creative before scope acceptance, and left-menu project entry render correctly.
- Created `UI acceptance P07` from the current-state baseline and observed `正在记录 · Run 01`.
- Reload restored the active project and its authoritative timeline.
- Timeline displayed `project.created`, `run.started`, `baseline.captured`, and `model.ui_brief_emitted` in order.
- 390×844: timeline remains readable, controls remain visible, and rows do not overflow horizontally.
- Ending the Run removed the end action and appended `run.ended` as event #5.

## Full-suite baseline limitations

The complete backend test directory currently reports **309 passed, 28 failed**. The failures are outside this feature path and cluster around the pre-existing `SemanticTarget` model-name collision/supervision chain, a missing `toy_animals` fixture category, and isolated four-stage tests that construct an orchestrator without semantic divergence. The project, realtime observation, four-stage, and end-to-end suites listed above remain green. These unrelated mainline failures were not modified in this lightweight rollout.
