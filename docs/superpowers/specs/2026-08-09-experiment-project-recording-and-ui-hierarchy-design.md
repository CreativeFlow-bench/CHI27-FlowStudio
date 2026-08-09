# FlowStudio Experiment Project Recording and UI Hierarchy Design

**Date:** 2026-08-09  
**Status:** Approved direction, pending implementation-plan review  
**Scope:** Durable experiment files, append-only research records, project-aware frontend hierarchy, decision-only bubbles, and bounded model output

## 1. Objective

FlowStudio must support two operating modes without weakening its existing CreativeFlow and four-stage pipeline:

1. **Temporary workspace:** users may test uploads, tools, prompts, and generation without creating a durable experiment file.
2. **Experiment project:** after the user selects **New experiment file** in the left Studio menu, FlowStudio records the experiment as a durable, reopenable project with immutable chronological evidence, stable asset references, divergence parameters and results, generation outputs, and the complete version tree.

The frontend must retain the current Flow Studio visual language while making three responsibilities distinct:

- **Canvas bubble:** one immediate question that requires a user decision.
- **AI Behavior panel:** one current phenomenon and one next question, with raw model detail collapsed.
- **Experiment timeline:** the durable, chronological account of everything that happened.

## 2. Design Principles

### 2.1 Recording starts at an explicit boundary

Opening FlowStudio creates the existing temporary Session and does not create an experiment project. Clicking **New experiment file** creates the recording boundary. Pre-project actions are never silently backfilled as if they happened during the experiment.

When creating a project, the user chooses:

- **Start blank** (default): create a clean experiment run and reset the workspace through the established reset boundary.
- **Use current state as baseline:** preserve the current asset, canvas, tool state, and version-tree snapshot as one `baseline_snapshot` event. Earlier temporary actions remain outside the experiment timeline.

### 2.2 Append-only, not cryptographically immutable

Research events cannot be updated or deleted through product APIs. A correction, exclusion, or user edit appends another event that references the original event. The first version does not add digital signatures, hash chains, WORM storage, or a complex permissions system.

Project management fields remain editable: title, participant code, condition label, notes, and tags.

### 2.3 Complete evidence without an unbounded row explosion

“Record every user input” means every research-relevant input and every committed UI state transition is recoverable in order. High-frequency data is grouped into trace artifacts rather than stored as one database row per pointer move.

- Text is recorded as ordered draft snapshots after a 500 ms idle debounce, plus mandatory snapshots on blur and submit.
- Brush, drag, smooth, and annotation pointer samples are stored as immutable compressed trace artifacts, referenced by one event per gesture/behavior.
- Uploads, selections, button decisions, parameter commits, undo/redo, candidate operations, version-tree edits, and run/project commands each create an event.
- Pure presentation actions such as panel resizing, ordinary scrolling, hover styling, and opening a disclosure are not research events unless they change a design/tool/model state.

### 2.4 Server assets, stable references, complete export

Images, OBJ/GLB files, screenshots, masks, generated candidates, and trace blobs remain in server-controlled storage or OSS. Project records contain stable asset IDs, checksums, media types, byte sizes, storage keys, and provenance—not expiring signed URLs.

An export job creates a self-contained ZIP containing the project manifest, ordered event stream, current snapshots, model/audit payloads, version-tree data, and copied asset binaries with checksums.

### 2.5 Preserve the production generation mainline

The project layer records the existing four-stage and CreativeFlow paths; it does not replace, bypass, or simplify them. `pipeline_transfer_engine.py`, Hunyuan3D post-processing, OSS upload, case registration, and the old `pipeline.py` remain available according to their current responsibilities.

## 3. Domain Model

### 3.1 `ProjectFile`

A durable research container.

| Field | Meaning |
|---|---|
| `project_id` | Stable `proj_*` identifier |
| `title` | User-editable display name |
| `participant_code` | Experiment participant identifier; optional outside formal studies |
| `condition_label` | Experimental condition or cohort |
| `notes`, `tags` | Editable management metadata |
| `status` | `active`, `completed`, or `archived` |
| `created_at`, `updated_at` | Server timestamps |
| `active_run_id` | Current resumable run, if any |

Archiving a project hides it from the default list. The first release has no permanent-delete endpoint.

### 3.2 `ExperimentRun`

A continuous working period inside one project.

| Field | Meaning |
|---|---|
| `run_id` | Stable `exprun_*` identifier |
| `project_id` | Owning project |
| `session_id` | Runtime Session used by this run |
| `run_number` | Monotonic within the project |
| `baseline_mode` | `blank` or `current_state` |
| `started_at`, `ended_at` | Run lifecycle |
| `next_event_seq` | Server-owned monotonic sequence counter |
| `recording_status` | `healthy`, `degraded`, `paused`, or `ended` |

An active run resumes after a page reload or recoverable browser crash. After the user ends a run, reopening the project creates the next run rather than mutating the ended run.

### 3.3 `ExperimentEvent`

The canonical append-only ledger row.

| Field | Meaning |
|---|---|
| `event_id` | Stable `expev_*` identifier |
| `project_id`, `run_id`, `session_id` | Ownership and runtime correlation |
| `seq` | Gap-free server-assigned sequence within a run |
| `event_type` | Versioned event name |
| `actor` | `user`, `model`, `system`, or `worker` |
| `occurred_at` | Client-observed timestamp when relevant |
| `recorded_at` | Authoritative server timestamp |
| `correlation_id` | Connect request, model work, artifacts, and results |
| `parent_event_id` | Original event for corrections/exclusions |
| `payload` | Versioned JSON payload |
| `asset_refs` | Stable referenced assets |
| `schema_version` | Event-payload schema version |

Uniqueness is enforced on `(run_id, seq)` and on a client-provided idempotency key for browser-originated events.

### 3.4 Event families

The initial schema covers:

- `project.created`, `project.metadata_changed`, `run.started`, `run.ended`, `baseline.captured`
- `input.text_snapshot`, `input.asset_uploaded`, `input.reference_added`, `input.selection_changed`
- `behavior.started`, `behavior.committed`, `behavior.cancelled`, `behavior.undo`, `behavior.redo`
- `intent.submitted`, `intent.encoded`, `intent.revision_created`
- `gate.question_presented`, `gate.answered`, `gate.rejected`
- `divergence.parameters_changed`, `divergence.requested`, `divergence.completed`, `divergence.failed`, `divergence.selection_changed`
- `generation.requested`, `generation.progressed`, `generation.completed`, `generation.failed`, `generation.cancelled`
- `candidate.selected`, `candidate.accepted`, `candidate.rejected`, `candidate.added_to_canvas`
- `version.node_created`, `version.node_updated`, `version.active_changed`, `version.retry_requested`
- `model.ui_brief_emitted`, `model.raw_output_recorded`, `model.fallback_used`
- `event.excluded_from_analysis`, `event.annotation_added`, `recording.health_changed`

Events that represent an attempted user mutation are recorded before the mutation. A paired result event records success or failure with the same correlation ID. This preserves failed attempts and prevents successful work from becoming invisible in the study record.

### 3.5 Asset references and trace artifacts

`ProjectAssetReference` connects a project to an existing FlowStudio asset or artifact:

- stable `asset_id` or `artifact_id`
- `sha256`, byte size, MIME type, logical role
- local storage key or OSS object key
- source event, source job, candidate, version node, and original filename where applicable

Trace artifacts use gzipped NDJSON or JSON payloads for ordered pointer/stroke samples. Their event contains tool, target, coordinate space, sample count, start/end timestamps, and checksum.

## 4. Storage and Recording Architecture

### 4.1 Dedicated SQLite store

Experiment records live in a dedicated `backend/storage/experiment_projects.sqlite3` database using SQLite WAL mode. This separates durable research evidence from the prototype Studio snapshot and from the current four-stage database while allowing explicit joins through IDs.

The existing “clear session history” operation must not delete project ledgers or project asset references. A project archive/export lifecycle is separate from temporary-session cleanup.

### 4.2 Recorder service

One `ExperimentRecorder` owns all ledger writes and sequence assignment. Backend routes and services call typed recorder methods instead of writing arbitrary event dictionaries. Browser-only actions use a whitelisted batch event endpoint with idempotency keys.

Project mode is fail-closed for research mutations:

1. Append the requested user event.
2. Execute the underlying mutation.
3. Append success or failure.

If step 1 fails, the mutation is blocked and the UI shows **Recording paused—your action was not applied**. Temporary mode continues to use existing behavior and is not blocked by recorder availability.

### 4.3 Snapshot projection

The ledger is canonical, but opening a project must not replay every event in the browser. The server maintains a replaceable `ProjectProjection` containing:

- current session/asset/tool state
- latest divergence parameters and selected semantic candidates
- latest solution batch and generation statuses
- full version graph projection
- latest UI brief
- timeline cursors and referenced-asset summary

Projection rows may be rebuilt from events. They are not treated as original research evidence.

## 5. API Surface

The first release adds:

- `POST /api/v1/projects` — create project and first run with blank/current baseline mode
- `GET /api/v1/projects` — list active/completed/archived projects
- `GET /api/v1/projects/{project_id}` — project metadata and current projection
- `PATCH /api/v1/projects/{project_id}` — edit management metadata only
- `POST /api/v1/projects/{project_id}/runs` — start the next run
- `POST /api/v1/projects/{project_id}/runs/{run_id}/end` — end recording cleanly
- `GET /api/v1/projects/{project_id}/events` — cursor-paginated ordered timeline
- `POST /api/v1/projects/{project_id}/runs/{run_id}/events:batch` — whitelisted browser-originated events
- `POST /api/v1/projects/{project_id}/events/{event_id}/exclude` — append an exclusion event
- `POST /api/v1/projects/{project_id}/export` — create an asynchronous export job
- `GET /api/v1/projects/{project_id}/exports/{export_id}` — export status and download URL

Existing Session, four-stage, generation, candidate, and version-graph endpoints retain their behavior. When an active project run is attached to the Session, their service-layer operations additionally emit typed project events.

## 6. Frontend Information Architecture

### 6.1 Left Studio menu

A new Project section appears above Source.

Temporary mode shows:

- **Temporary workspace** and a neutral **Not recording** pill
- explanatory text: normal testing is available; a project is required for durable experiment history
- primary **New experiment file** button
- secondary **Open file** action

Project mode shows:

- project title and participant/condition summary
- red recording dot, run number, elapsed time, and autosave/recording health
- **Timeline**, **Version tree**, **End run**, and **Export experiment package** actions

Creating a project opens a compact modal with title, participant code, condition, notes, and blank/current baseline choice. The default is blank.

### 6.2 Canvas decision bubble

At most one active decision bubble is shown near the target object/part. It contains only:

- a short **Needs your decision** label
- one direct question
- explicit answer controls
- an optional one-line consequence, not a model explanation

It does not repeat the current phenomenon, model prose, candidate list, or progress. Answering it removes it from the canvas and appends it to the experiment timeline. If several revisions need confirmation, they form a queue; the AI Behavior panel displays the remaining count.

Saved intent drafts no longer appear as large bubble-like cards around the object. They move to the timeline/drafts area, with only a small count affordance on canvas when relevant.

### 6.3 AI Behavior panel

The default panel order is fixed:

1. **Current phenomenon:** one sentence, maximum 140 display characters.
2. **Next question:** one sentence, maximum 100 display characters. If it requires an answer, the panel says it is waiting on the canvas bubble.
3. Compact state pills for the current four-stage state and recording health.
4. **View details** disclosure.
5. **More Creative** controls only when scope is confirmed and divergence candidates are ready.

Raw planner narration is not rendered directly in the default panel. The details disclosure may show structured evidence, confidence, model/fallback identity, raw-output reference, and technical error detail.

### 6.4 Perception, Solution Space, and model output

- Perception remains a compact one-line observation surface; its history moves to the project timeline.
- Solution Space remains the generated-candidate rail and does not duplicate model narration.
- Model output is normalized into a `UiBrief` contract:

```json
{
  "phenomenon": "Your recent operations stay concentrated on the hat brim.",
  "next_question": "Should this change affect only the hat?",
  "requires_response": true,
  "question_id": "gate_...",
  "status": "awaiting_gate",
  "confidence": 0.86,
  "details_ref": "expev_..."
}
```

The complete raw output is recorded as a model event and referenced by `details_ref`; it is not discarded merely because the UI is concise.

### 6.5 Visual system

The redesign reuses the current CSS variables and visual language:

- `--canvas-bg` point-grid background
- Manrope UI typography and the existing handwritten Flow Studio/More Creative accent
- translucent `--panel-bg`, `--panel-border`, and 18–22 px radii
- current cyan/violet/pink status dots
- existing blue primary actions and blue/pink decision-bubble gradient

No new component library or visual framework is introduced.

## 7. Failure and Recovery Behavior

- A project mutation is disabled while recording health is `paused`.
- Failed browser batches remain retryable with the same idempotency keys.
- Page reload discovers and resumes an active run from the server.
- A stale browser cannot append to an ended run; the server returns `409 run_ended`.
- Asset export reports missing or checksum-mismatched assets explicitly and does not claim a complete archive.
- Model failure still emits a concise failure `UiBrief`; the raw exception/fallback chain remains in the event ledger.
- Project database backup is included in deployment and migration procedures before any schema change.

## 8. Privacy and Analysis Controls

- Participant code is a study identifier, not a required real name.
- Secrets, authorization headers, server environment values, and signed URL query strings are never stored in event payloads.
- Researchers may append `event.excluded_from_analysis` with a reason; the original event remains available to authorized exports.
- Default timeline views visually distinguish user, model, worker, and system events.

## 9. Testing and Acceptance

### Backend

- Project creation establishes a clean event sequence and active run.
- Current-state mode records one baseline snapshot without importing earlier temporary events.
- Concurrent event appends receive unique, ordered sequence numbers.
- Duplicate idempotency keys do not duplicate events.
- Existing Session/four-stage/generation/version operations emit the expected requested/result event pairs in project mode and emit no project events in temporary mode.
- Exclusion appends a new event and leaves the original unchanged.
- Session reset does not remove project events.
- Export contains manifest, ordered events, projections, checksums, and referenced assets.

### Frontend

- Temporary mode allows ordinary testing and clearly shows that it is not recording.
- New file supports blank and current-state baselines.
- Recording state survives reload and exposes degraded/paused status.
- Only one unanswered decision bubble is visible; answering it advances the queue.
- AI Behavior renders bounded `UiBrief` text and keeps raw detail collapsed.
- More Creative is hidden or inactive until the confirmed divergence stage.
- Keyboard and screen-reader users can create/open projects, answer bubbles, inspect details, end a run, and export.
- Desktop and 390 px layouts keep the Project section, active bubble, composer, and AI summary reachable.

### Production acceptance

One representative concrete project must be exercised through: create project, upload/choose source, record tool and text inputs, confirm gate, adjust divergence parameters, select candidates, generate images, add a candidate to the canvas, complete Hunyuan3D where configured, create a version branch, reload, reopen, end run, and export. The exported timeline and version graph must reproduce the visible workflow without relying on expiring URLs.

## 10. Delivery Decomposition

Implementation is divided into three independently reviewable deliverables:

1. **Experiment project foundation:** project/run/event/asset-reference store, recorder service, APIs, export, and backend integration hooks.
2. **Project workflow and visual hierarchy:** left-menu Project section, create/open flow, recording indicator, timeline access, decision-only bubble, and Flow Studio-consistent layout.
3. **Model-output contraction:** `UiBrief` producer/consumer contract, AI Behavior summary panel, detail disclosure, queue semantics, and migration away from raw planner narration in the default UI.

The foundation is delivered first. The UI can then consume stable project APIs, and output contraction can be validated without compromising raw experimental evidence.

## 11. Non-goals for the First Release

- cryptographic tamper proofing or digital signatures
- multi-user concurrent editing
- permanent project deletion from the UI
- arbitrary user-authored event types
- recording every scroll, panel drag, mouse hover, or animation frame
- replacing existing four-stage, CreativeFlow, Hunyuan3D, OSS, or case-library pipelines
- broad frontend framework or component-library migration
