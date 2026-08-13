# FlowStudio Interaction Orchestration and Workspace Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the interaction kernel authoritative, resumable, fast on user commands, and expose it through a responsive 3D workspace that keeps editing, history, perception, and AI controls usable together.

**Architecture:** Extend the existing SQLite-backed observation layer with explicit task, audit-event, domain-event, and outbox records. Keep the existing model services as asynchronous processors behind command endpoints. Add a small frontend interaction package that owns command acknowledgement, versioned event reduction, projection recovery, and per-revision view models; keep existing generation and Three.js algorithms behind those boundaries.

**Tech Stack:** FastAPI, Pydantic v2, sqlite3, pytest, React 19, TypeScript, Vite, Three.js, native WebSocket, existing FlowStudio CSS variables and GPU sync scripts.

## Global Constraints

- Four-stage services remain background capabilities, not user-facing sequential steps.
- Perception exposes only low-level, verifiable behavior summaries.
- Gate acknowledgement, selection save, and generation task creation do not call a model synchronously.
- Raw experiment events and domain events are append-only; projection sync is retryable and non-blocking.
- No new Redis, Celery, Kafka, model, or 3D-editing dependency in this pass.
- A failed gate, task, WebSocket, or projection must preserve other intent revisions.
- The frontend build must remain deployable through the existing GPU synchronization path.

---

### Task 1: Persist interaction aggregates, tasks, events, and outbox records

**Files:**
- Modify: `backend/app/models/realtime_observation.py`
- Modify: `backend/app/models/four_stage.py`
- Modify: `backend/app/services/storage/four_stage_store.py`
- Create: `backend/app/services/interaction/domain.py`
- Test: `backend/tests/test_interaction_orchestration.py`

**Interfaces:**
- `InteractionTask`, `InteractionAuditEvent`, `InteractionDomainEvent`, and `InteractionOutboxRecord` are validated Pydantic contracts.
- `FourStageStore.create_interaction_command(...)` atomically persists the command audit, aggregate payload, domain events, and outbox rows.
- `FourStageStore.claim_interaction_tasks(...)`, `renew_interaction_task(...)`, `complete_interaction_task(...)`, and `fail_interaction_task(...)` implement lease-safe task lifecycle operations.

- [x] Add explicit task/status/event models and validation for idempotency keys, progress, lease expiry, aggregate version, and event cursor.
- [x] Add SQLite tables and indexes with additive schema initialization; do not delete existing four-stage data.
- [x] Implement atomic command persistence and idempotent replay by `(session_id, idempotency_key)`.
- [x] Implement queued/running lease recovery, cancellation request, retry count, and outbox cursor allocation.
- [x] Add regression coverage for terminal transitions, duplicate commands, task lease recovery, and append-only outbox ordering.

### Task 2: Expose fast command and recovery APIs

**Files:**
- Create: `backend/app/api/interaction.py`
- Modify: `backend/app/services/intent/realtime_observation.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_interaction_orchestration.py`

**Interfaces:**
- `POST /api/v1/intent-revisions/{revision_id}/gate` returns a revision projection and queued divergence task without model calls.
- `PUT /api/v1/intent-revisions/{revision_id}/divergence-selection` saves a versioned snapshot.
- `POST /api/v1/intent-revisions/{revision_id}/generation-tasks` returns a queued generation task only when selection is saved.
- `GET /api/v1/interaction-tasks/{task_id}` and `GET /api/v1/sessions/{session_id}/interaction-projection` support recovery.
- `POST /api/v1/interaction-tasks/{task_id}/retry|cancel` are resource-scoped and idempotent.

- [x] Route Gate, selection, generation, retry, cancel, and projection commands through one service boundary.
- [x] Keep existing legacy endpoints as compatibility shims, while the updated UI sends canonical command metadata.
- [x] Add bounded task worker execution, lease renewal, retry/cancel handling, and publish outbox events after durable state changes.
- [x] Verify fast acknowledgement and durable projection/event visibility with `scripts/interaction_orchestration_smoke.py`.

### Task 3: Add cursor-aware WebSocket delivery and recovery

**Files:**
- Modify: `backend/app/services/storage/websocket_manager.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/models/store.py`
- Test: `backend/tests/test_interaction_orchestration.py`

**Interfaces:**
- WebSocket messages carry `event_cursor`, `aggregate_version`, and `correlation_id`.
- Client hello may include `last_event_cursor`; server replays available outbox records or directs the client to projection recovery.

- [x] Add durable outbox records, global cursor allocation, replay by session cursor, and event-id/version dedupe on the client.
- [x] Preserve existing observation/job message types while adding canonical `interaction.event` messages.
- [x] Add reducer coverage for duplicate/stale events; full browser reconnect validation remains a cloud/runtime check.

### Task 4: Create the frontend Interaction Coordinator package

**Files:**
- Create: `frontend/src/interaction/types.ts`
- Create: `frontend/src/interaction/commands.ts`
- Create: `frontend/src/interaction/events.ts`
- Create: `frontend/src/interaction/reducer.ts`
- Create: `frontend/src/interaction/selectors.ts`
- Create: `frontend/src/interaction/coordinator.ts`
- Create: `frontend/src/interaction/recovery.ts`
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/types.ts`
- Test: `frontend/tests/interactionCoordinator.test.ts`

**Interfaces:**
- `interactionReducer(state, action)` merges acknowledgements/events by event ID and aggregate version.
- `createInteractionCoordinator({ api, sessionId, onState })` dispatches commands and exposes `connect`, `recover`, `acceptGate`, `rejectGate`, `saveSelection`, `startGeneration`, `retryTask`, and `cancelTask`.
- Selectors expose `observing`, `awaiting_gate`, `preparing_keywords`, `choosing_keywords`, `ready_to_generate`, `generating`, `reviewing_solutions`, and `needs_attention` view models.

- [x] Add reducer tests for duplicate/stale events and A/B revision isolation, plus projection recovery ordering.
- [x] Integrate coordinator state into the existing store without deleting legacy four-stage state.
- [x] Replace the active revision Gate/selection/Generate handlers with coordinator commands; legacy four-stage compatibility handlers remain behind `REVISION_GATED_INTERACTION=true` and retain their protocol for rollback.

### Task 5: Redesign workspace layout and AI Behavior Dock

**Files:**
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx`
- Modify: `frontend/src/components/overlays/PlannerClarificationOverlay.tsx`
- Modify: `frontend/src/components/StudioCanvas.tsx`
- Modify: `frontend/src/utils/versionGraph.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/tests/interactionReliability.test.ts`
- Test: `frontend/tests/viewportPresentation.test.ts`

**Interfaces:**
- Active mode mounts one full-size `ThreeViewport`; Overview mode renders 220px history nodes and does not mount full editor viewports.
- `--workspace-safe-top/right/bottom/left` are the only layout inputs shared with version graph positioning.
- AI Behavior uses one `.ai-panel-scroll` container and fixed desktop width 380–420px with explicit mobile drawer mode.

- [x] Decouple active editor safe-area sizing from compact history-node geometry and add shared safe-area CSS variables.
- [x] Make the AI Behavior area a fixed desktop/mobile dock with one scroll owner; disable its arbitrary resize handle.
- [x] Keep Gate/Generate feedback and hit-area/accessibility regressions covered by the existing frontend suite.
- [x] Preserve the reduced Perception hierarchy and existing editor/version navigation behavior.
- [x] Run keyboard/pointer, Generate precondition, editor navigation, and composer non-blocking frontend tests.

### Task 6: GPU sync, build, smoke, and evidence

**Files:**
- Modify: `scripts/sync_runtime_to_gpu.expect`
- Modify: `scripts/sync_frontend_dist.expect`
- Modify: `scripts/cloud_health_check.py`
- Create: `scripts/interaction_orchestration_smoke.py`
- Modify: `README.md`

- [x] Keep the existing GPU sync scripts scoped to source/dist payloads and preserve server `.env`/storage files.
- [x] Add `scripts/interaction_orchestration_smoke.py` for projection recovery, Gate acknowledgement, queued task, and event visibility.
- [x] Run backend tests (340 offline), frontend tests (83), TypeScript, Vite build, and real HTTP interaction/worker smokes.
- [x] Run the remote GPU/cloud health and sync checks through the configured SeetaCloud SSH tunnel; remote backend, worker, VLM, Qwen-Image, frontend artifact serving, and all 13 remote worker tests were verified, including a real Gate→divergence→Generate batch.

### Task 7: Requirement-by-requirement verification

- [x] Re-read the strategy document and map the implemented kernel, projection, UI, and verification evidence against its invariants.
- [x] Keep completion claims bounded to fresh test/runtime evidence; distinguish offline deterministic tests from online VLM/cloud behavior.
- [x] Record the exact deployment evidence and remaining boundary: offline suites are deterministic; remote cloud was verified through a temporary local tunnel and the remote services remain deployed/running.
