# Experiment Project Recording V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-shaped version of durable FlowStudio experiment files: append-only recording, stable asset references and export, a temporary/project dual-mode workflow, a Flow Studio-consistent Project menu and decision bubble, and bounded AI Behavior output.

**Architecture:** Add an independent SQLite/WAL experiment ledger keyed by Project → Run → ordered Event, then wire it into the existing FastAPI services without replacing Session, four-stage, CreativeFlow, Hunyuan3D, OSS, or version-graph stores. The React store owns temporary/project mode and sends whitelisted browser-only events while backend services emit authoritative model/version events. The UI consumes a structured `UiBrief`, keeping raw output in the ledger/details disclosure.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, sqlite3, pytest/TestClient, React 19, TypeScript, Vite, Node test runner, existing FlowStudio CSS variables.

## Global Constraints

- Temporary workspace remains fully usable and creates no project events.
- Project events are append-only; corrections and exclusions append new events.
- Project-mode research mutations fail closed when the first event cannot be recorded.
- High-frequency pointer data is referenced as an artifact/behavior payload, not expanded into one SQL row per sample.
- Stable IDs/checksums/storage keys are persisted; expiring signed URL query strings are not.
- Session reset must never delete project ledgers.
- At most one unanswered decision bubble is visible.
- AI Behavior defaults to one current phenomenon (≤140 display characters) and one next question (≤100 display characters); raw output stays available in details and the event ledger.
- Reuse current FlowStudio tokens, components, panel radii, point-grid canvas, and blue/pink decision language; add no UI framework.
- Preserve `pipeline_transfer_engine.py`, Hunyuan3D post-processing, OSS/case sync, and the old `pipeline.py` unchanged.
- Work in the current checkout because its authoritative source is largely untracked; touch only files listed below.

---

### Task 1: Experiment domain models and append-only SQLite store

**Files:**
- Create: `backend/app/models/experiment_project.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/storage/experiment_project_store.py`
- Create: `backend/tests/test_experiment_project_store.py`

**Interfaces:**
- Produces: `ProjectFile`, `ExperimentRun`, `ExperimentEvent`, `ProjectDetail`, `ProjectCreateRequest`, `ProjectUpdateRequest`, `ProjectEventCreate`, `ProjectEventBatchRequest`, `ProjectExportRecord`, `UiBrief`.
- Produces: `ExperimentProjectStore.create_project`, `append_event`, `append_events`, `list_events`, `update_project`, `end_run`, `start_run`, `project_for_session`, `set_recording_status`, `create_export_record`.

- [ ] **Step 1: Write failing store behavior tests**

```python
def test_project_events_are_gap_free_idempotent_and_append_only(tmp_path):
    store = ExperimentProjectStore(tmp_path / "projects.sqlite3")
    project = store.create_project(
        ProjectCreateRequest(title="Study 01", session_id="sess_a", baseline_mode="blank")
    )
    first = store.append_event(project.active_run.run_id, ProjectEventCreate(
        event_type="input.text_snapshot", actor="user",
        idempotency_key="text-1", payload={"text": "rounder hat"},
    ))
    duplicate = store.append_event(project.active_run.run_id, ProjectEventCreate(
        event_type="input.text_snapshot", actor="user",
        idempotency_key="text-1", payload={"text": "rounder hat"},
    ))
    second = store.append_event(project.active_run.run_id, ProjectEventCreate(
        event_type="event.excluded_from_analysis", actor="user",
        idempotency_key="exclude-1", parent_event_id=first.event_id,
        payload={"reason": "participant correction"},
    ))
    assert [first.seq, duplicate.seq, second.seq] == [1, 1, 2]
    assert store.list_events(project.project.project_id)[0].payload["text"] == "rounder hat"
```

Also cover concurrent appends, an ended run rejecting new events, active-run lookup by Session, project metadata updates leaving events unchanged, and SQLite `journal_mode=wal`.

- [ ] **Step 2: Run the test and verify RED**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_experiment_project_store.py -q`

Expected: collection fails because `app.models.experiment_project` and `ExperimentProjectStore` do not exist.

- [ ] **Step 3: Implement typed models and store**

Use Pydantic enums for project/run/recording statuses. Use `BEGIN IMMEDIATE` for sequence assignment, unique indexes on `(run_id, seq)` and `(run_id, idempotency_key)`, JSON serialization via `model_dump(mode="json")`, and no update/delete method for event rows.

The schema must include `projects`, `experiment_runs`, `experiment_events`, `project_asset_refs`, and `project_exports`. `create_project` appends `project.created`, `run.started`, and `baseline.captured` in that order.

- [ ] **Step 4: Run store tests and the existing reset regression**

Run:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_experiment_project_store.py \
  backend/tests/test_realtime_observation.py::test_reset_session_clears_realtime_and_four_stage_history -q
```

Expected: all pass and project storage is independent from Session reset.

---

### Task 2: Project APIs, lifecycle, stable export, and application wiring

**Files:**
- Create: `backend/app/api/projects.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_project_api.py`

**Interfaces:**
- Consumes: Task 1 models/store.
- Produces: `/api/v1/projects` lifecycle, ordered event pagination, exclusion append, event batch, export creation/status/download.
- Produces: module-level `experiment_project_store` for authoritative service integration.

- [ ] **Step 1: Write failing API acceptance tests**

```python
def test_temporary_session_can_become_a_recorded_project(client, isolated_project_store):
    session = client.post("/api/v1/sessions", json={"title": "Temporary"}).json()
    created = client.post("/api/v1/projects", json={
        "title": "Participant P07",
        "participant_code": "P07",
        "condition_label": "A",
        "session_id": session["session_id"],
        "baseline_mode": "current_state",
        "baseline_snapshot": {"active_asset_id": None, "version_graph": {"nodes": []}},
    })
    assert created.status_code == 200
    events = client.get(f"/api/v1/projects/{created.json()['project']['project_id']}/events").json()
    assert [item["event_type"] for item in events["items"]] == [
        "project.created", "run.started", "baseline.captured"
    ]
```

Add tests that temporary Session reset leaves project events intact, event batches reject non-whitelisted types and duplicate keys, exclusions preserve originals, ended runs return `409 run_ended`, and export ZIP contains `manifest.json`, `events.jsonl`, `projection.json`, and `checksums.json`.

- [ ] **Step 2: Run API tests and verify RED**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_project_api.py -q`

Expected: `404` for `/api/v1/projects`.

- [ ] **Step 3: Implement router and wire a dedicated database**

Instantiate `ExperimentProjectStore()` in tests and reopen it at `backend/storage/experiment_projects.sqlite3` only outside pytest, matching the existing four-stage storage pattern. Include the router from `create_app()`.

The browser batch whitelist is:

```python
BROWSER_EVENT_TYPES = {
    "input.text_snapshot", "input.asset_uploaded", "input.reference_added",
    "input.selection_changed", "behavior.undo", "behavior.redo",
    "gate.answered", "divergence.parameters_changed",
    "divergence.selection_changed", "generation.requested",
    "candidate.selected", "candidate.accepted", "candidate.rejected",
    "candidate.added_to_canvas", "version.retry_requested",
}
```

Strip URL query strings recursively from payload strings before persistence. Reject secrets by key names `authorization`, `cookie`, `api_key`, `token`, and `password`.

- [ ] **Step 4: Implement completed-export job semantics**

`POST /export` creates an export record, writes a ZIP under `storage/files/project_exports/<project_id>/`, and marks it `completed`; the API remains job-shaped so a later worker can make it asynchronous without changing clients. Copy only resolvable project asset references, calculate SHA-256, and report missing refs in the manifest instead of claiming completeness.

- [ ] **Step 5: Run project API plus core API tests**

Run:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_project_api.py \
  backend/tests/test_api.py \
  backend/tests/test_realtime_observation.py -q
```

Expected: all pass.

---

### Task 3: Authoritative backend recording hooks and `UiBrief`

**Files:**
- Modify: `backend/app/services/intent/realtime_observation.py`
- Modify: `backend/app/models/realtime_observation.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_realtime_observation.py`
- Modify: `backend/tests/test_project_api.py`

**Interfaces:**
- Consumes: `ExperimentProjectStore.project_for_session` and `append_system_event(session_id, event_type, actor, payload, correlation_id)`.
- Produces: `RealtimeObservationSnapshot.ui_brief: UiBrief`.
- Produces authoritative events for behaviors, model observation/revision/gate/divergence/generation, and version graph transitions.

- [ ] **Step 1: Write failing integration tests**

```python
def test_recorded_session_emits_model_and_version_events(client, recorded_project):
    sid = recorded_project["session_id"]
    client.post(f"/api/v1/sessions/{sid}/behaviors", json={
        "tool": "brush", "target": {"part_id": "hat"}, "stroke_count": 2
    })
    client.post(f"/api/v1/sessions/{sid}/version-nodes", json={
        "label": "Source", "preview_url": "/files/source.png", "status": "image_ready"
    })
    snapshot = client.get(f"/api/v1/sessions/{sid}/realtime-observation").json()
    assert snapshot["ui_brief"]["phenomenon"]
    assert len(snapshot["ui_brief"]["phenomenon"]) <= 140
    event_types = [item["event_type"] for item in project_events(client, recorded_project)]
    assert "behavior.committed" in event_types
    assert "version.node_created" in event_types
    assert "model.ui_brief_emitted" in event_types
```

Add a temporary-session case that emits none of these project events and a multi-revision case proving `pending_decision_count` while only one `active_question` is returned.

- [ ] **Step 2: Run targeted tests and verify RED**

Run:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_project_api.py::test_recorded_session_emits_model_and_version_events \
  backend/tests/test_realtime_observation.py -q
```

Expected: `ui_brief` missing and authoritative project event assertions fail.

- [ ] **Step 3: Inject the recorder into `RealtimeObservationService`**

Extend the constructor with an optional recorder so hermetic tests remain simple. Record from the same service methods that commit behaviors, revisions, gate actions, batches, and version nodes. Use stable object IDs as correlation IDs. Extend `_emit` to record whitelisted authoritative events before websocket broadcast.

- [ ] **Step 4: Derive a bounded `UiBrief` on the backend**

Priority rules:

1. Pending gate: phenomenon from observation summary; next question from gate; `requires_response=true`.
2. Divergence loading/ready: phenomenon describes confirmed scope; next question asks for keyword selection or generation.
3. Generation: phenomenon reports completed/total artifacts; next question is empty until an action is needed.
4. Idle: phenomenon is current operation/scope; next question prompts the next meaningful input.

Truncate at Unicode code-point boundaries to 140/100 characters. Store raw gate/model detail in the event payload referenced by `details_ref`.

- [ ] **Step 5: Run backend recording and four-stage suites**

Run:

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_project_api.py \
  backend/tests/test_realtime_observation.py \
  backend/tests/test_four_stage.py \
  backend/tests/test_four_stage_e2e.py -q
```

Expected: all pass.

---

### Task 4: Frontend project client and store state

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/utils/experimentProject.ts`
- Modify: `frontend/src/state/studioStore.ts`
- Create: `frontend/tests/experimentProject.test.ts`

**Interfaces:**
- Consumes: Task 2 project APIs and Task 3 `ui_brief` snapshot field.
- Produces: `project`, `projectList`, `projectEvents`, `projectDialogOpen`, `projectTimelineOpen`, `projectBusy`, `recordingError`.
- Produces actions: `createExperimentProject`, `openExperimentProject`, `endExperimentRun`, `exportExperimentProject`, `recordExperimentEvent`, `refreshProjectTimeline`.

- [ ] **Step 1: Write failing pure behavior tests**

```typescript
test("project recording batches preserve order and stable idempotency keys", async () => {
  const calls: unknown[] = [];
  const recorder = createExperimentEventRecorder({
    postBatch: async (events) => { calls.push(events); return events; },
    now: () => 1000,
  });
  await recorder.record("input.text_snapshot", { text: "rounder" }, "text-7");
  await recorder.record("gate.answered", { accepted: true }, "gate-2");
  assert.deepEqual(calls, [
    [{ event_type: "input.text_snapshot", actor: "user", idempotency_key: "text-7", payload: { text: "rounder" }, occurred_at_ms: 1000 }],
    [{ event_type: "gate.answered", actor: "user", idempotency_key: "gate-2", payload: { accepted: true }, occurred_at_ms: 1000 }],
  ]);
});
```

Also test that no active project is a no-op, a failed critical record changes health to paused and rejects the mutation, URL sanitization removes query strings, and text snapshots debounce for 500 ms but flush on submit.

- [ ] **Step 2: Run test and verify RED**

Run: `node --experimental-strip-types --test frontend/tests/experimentProject.test.ts`

Expected: module-not-found for `experimentProject.ts`; add an empty exported signature only if needed to turn collection into an assertion failure, then rerun RED before implementation.

- [ ] **Step 3: Add types and pure recorder**

Keep queue state outside React so ordering/idempotency is testable. Serialize writes through one promise chain. Do not subscribe the whole UI to high-frequency text; keep debounce timer in a ref and store only project/health changes in React state.

- [ ] **Step 4: Add project actions to `useStudioStore`**

Persist only the active `project_id` in versioned localStorage key `flowstudio.active-project.v1`; always rehydrate authoritative detail from the server. `baseline_mode=blank` first creates a fresh Session through the current blank-workspace path. `current_state` captures asset, action atoms, divergence parameters, selected candidates, and version graph without importing old events.

- [ ] **Step 5: Run project tests and full frontend tests**

Run:

```bash
node --experimental-strip-types --test frontend/tests/experimentProject.test.ts
node --experimental-strip-types --test frontend/tests/*.test.ts
```

Expected: all pass.

---

### Task 5: Project menu, create/open flow, timeline, and recording health

**Files:**
- Create: `frontend/src/components/project/ProjectSection.tsx`
- Create: `frontend/src/components/project/ProjectDialog.tsx`
- Create: `frontend/src/components/project/ProjectTimeline.tsx`
- Modify: `frontend/src/components/menu/StudioMenu.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/accessibility.test.ts`
- Create: `frontend/tests/projectPresentation.test.ts`

**Interfaces:**
- Consumes: Task 4 project state/actions.
- Produces: temporary mode, New/Open file controls, blank/current baseline dialog, project recording status, timeline, end-run and export actions.

- [ ] **Step 1: Write failing presentation/accessibility tests**

Use a minimal server-render harness if React DOM test utilities are present; otherwise extract `projectPresentation(project, run, error)` as a pure view model and test its output while existing source-level accessibility tests only cover markup constraints.

```typescript
test("temporary and recording project modes have unambiguous presentation", () => {
  assert.deepEqual(projectPresentation(null, null), {
    title: "临时工作区", status: "未记录", primaryAction: "新建实验文件"
  });
  assert.deepEqual(projectPresentation(project, run), {
    title: "Participant P07", status: "正在记录 · Run 01", primaryAction: "查看时间线"
  });
});
```

Accessibility assertions must cover dialog labeling, baseline radio group, keyboard-operable open/end/export buttons, `aria-live` recording status, and timeline event actor/time labels.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
node --experimental-strip-types --test \
  frontend/tests/projectPresentation.test.ts \
  frontend/tests/accessibility.test.ts
```

Expected: presentation module/components missing or new accessibility assertions fail.

- [ ] **Step 3: Implement components using existing visual tokens**

Place Project above Source. Reuse `Panel`, existing button styles, `--panel-bg`, `--panel-border`, `--accent-blue`, status dots, 18–22 px radii, Manrope, and the current drawer scroll container. Do not introduce route-level navigation or another component library.

Keep long timeline rows under `content-visibility: auto` and load events by cursor. Render project dialog only while open to avoid unnecessary component work.

- [ ] **Step 4: Run tests and production build**

Run:

```bash
node --experimental-strip-types --test frontend/tests/*.test.ts
cd frontend && npm run build
```

Expected: all tests pass and Vite exits 0.

---

### Task 6: Record key browser inputs and preserve fail-closed semantics

**Files:**
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/components/panels/IntentComposer.tsx`
- Modify: `frontend/tests/experimentProject.test.ts`
- Modify: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Consumes: Task 4 `recordExperimentEvent`.
- Produces ordered research events for text snapshots, asset/reference uploads, behaviors/undo/redo, gate answers, divergence changes/selections, generation requests, candidate actions, and version-tree actions.

- [ ] **Step 1: Add failing orchestration tests**

Test pure command wrappers rather than mocks of the store. A critical command must call the recorder first; a failed record must prevent the supplied mutation callback from running. A successful record runs the callback once and appends a result event.

```typescript
test("critical project mutation is blocked when request recording fails", async () => {
  let mutations = 0;
  await assert.rejects(() => recordedMutation({
    requested: () => Promise.reject(new Error("disk full")),
    mutate: async () => { mutations += 1; return "ok"; },
    completed: async () => undefined,
    failed: async () => undefined,
  }));
  assert.equal(mutations, 0);
});
```

- [ ] **Step 2: Run targeted tests and verify RED**

Run: `node --experimental-strip-types --test frontend/tests/experimentProject.test.ts frontend/tests/interactionReliability.test.ts`

Expected: `recordedMutation` missing or ordering assertion fails.

- [ ] **Step 3: Instrument high-level store actions**

Use one `recordedMutation` helper around user-initiated mutations. Do not duplicate authoritative backend events. Browser events cover request intent and browser-only state; backend hooks cover committed model/version results.

Flush text snapshots on 500 ms idle, blur, and submit. Record trace/evidence refs already produced by behavior/annotation APIs rather than copying image/base64 payloads into project events.

- [ ] **Step 4: Run frontend suites**

Run: `node --experimental-strip-types --test frontend/tests/*.test.ts`

Expected: all pass.

---

### Task 7: Bounded AI Behavior summary and decision-only bubble

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx`
- Modify: `frontend/src/components/overlays/PlannerClarificationOverlay.tsx`
- Modify: `frontend/src/components/overlays/IntentBeadOverlay.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/tests/uiBrief.test.ts`
- Modify: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Consumes: Task 3 `RealtimeObservationSnapshot.ui_brief`.
- Produces: one phenomenon, one next question, collapsed details, one active canvas question, and a compact queued-decision count.

- [ ] **Step 1: Write failing behavior tests**

```typescript
test("ui brief clamps display copy without losing its details reference", () => {
  const brief = normalizeUiBrief({
    phenomenon: "现".repeat(200), next_question: "问".repeat(150),
    requires_response: true, question_id: "gate_1",
    status: "awaiting_gate", confidence: 0.8, details_ref: "expev_raw_1",
    pending_decision_count: 3,
  });
  assert.equal([...brief.phenomenon].length, 140);
  assert.equal([...brief.next_question].length, 100);
  assert.equal(brief.details_ref, "expev_raw_1");
});
```

Add tests that one active question is selected from multiple revisions, answered questions disappear, intent drafts are represented by a count instead of large canvas cards, and More Creative is inactive before accepted scope.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --experimental-strip-types --test frontend/tests/uiBrief.test.ts frontend/tests/interactionReliability.test.ts`

Expected: `normalizeUiBrief` missing and decision-queue behavior fails.

- [ ] **Step 3: Implement the approved Flow Studio A hierarchy**

AI Behavior order: current phenomenon → next question → state pills → details disclosure → stage-gated More Creative. Stop rendering `plannerTypedText` as the primary default content; retain raw narration only inside details and project events.

The bubble renders the question, answer controls, and a one-line consequence only. It reuses the existing blue/pink gradient and circular accept/reject actions. Remove large intent-bead cards from the canvas and expose saved drafts from the Project timeline.

- [ ] **Step 4: Run frontend tests and build**

Run:

```bash
node --experimental-strip-types --test frontend/tests/*.test.ts
cd frontend && npm run build
```

Expected: all pass and build exits 0.

---

### Task 8: End-to-end acceptance, export audit, and workspace hygiene

**Files:**
- Modify: `.gitignore`
- Modify: `backend/tests/test_project_api.py`
- Create: `docs/experiments/experiment-project-v1-acceptance.md`

**Interfaces:**
- Consumes all prior tasks.
- Produces reproducible verification evidence and prevents `.superpowers/` visual scratch files from being committed.

- [ ] **Step 1: Add `.superpowers/` and local runtime exports to ignore rules**

Add exactly:

```gitignore
.superpowers/
backend/storage/files/project_exports/
```

- [ ] **Step 2: Write the failing full project-flow test**

Exercise create project/current baseline, text event, committed behavior, gate question/answer, divergence parameters/result/selection, generation event, candidate add, version-node branch, reload through API, end run, export, and rejection of a post-end append. Assert literal ordered event families and ZIP members.

- [ ] **Step 3: Run the end-to-end test and close any gaps**

Run: `backend/.venv/bin/python -m pytest backend/tests/test_project_api.py::test_complete_recorded_project_can_reopen_end_and_export -q`

Expected: pass.

- [ ] **Step 4: Run complete backend and frontend verification**

Run:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
node --experimental-strip-types --test frontend/tests/*.test.ts
cd frontend && npm run build
```

Expected: zero failures; Vite exits 0. Existing third-party bundle-size/eval warnings may remain but no new warnings are introduced by project recording.

- [ ] **Step 5: Perform browser acceptance at desktop and narrow width**

Verify temporary testing, project creation with both baseline modes, recording state after reload, timeline ordering, one active decision bubble, concise AI Behavior, stage-gated More Creative, end run, and export download. Check desktop and the narrowest browser-supported viewport; retain the automated 390 px boundary tests if direct emulation is unavailable.

- [ ] **Step 6: Record evidence**

Write exact commands, counts, export ZIP member list, browser checks, and any remaining non-blocking limitations to `docs/experiments/experiment-project-v1-acceptance.md`.

---

## Plan Self-Review

- Spec coverage: project/run/event/asset/export, dual mode, append-only semantics, stable references, reset isolation, fail-closed recording, project UI, timeline, decision queue, bounded `UiBrief`, raw detail preservation, recovery, privacy sanitization, desktop/390 px accessibility, and full pipeline preservation each have an implementation task and an acceptance check.
- Scope decomposition: Tasks 1–3 create an independently testable backend foundation; Tasks 4–6 create the independently testable project workflow; Task 7 creates the independently testable output hierarchy; Task 8 proves the integrated result.
- Type consistency: backend and frontend use `project_id`, `run_id`, `event_id`, `seq`, `event_type`, `idempotency_key`, `ui_brief`, `details_ref`, and `pending_decision_count` consistently.
- No placeholder steps or unspecified tests remain.
