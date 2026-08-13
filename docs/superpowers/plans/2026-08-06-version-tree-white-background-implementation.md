# FlowStudio White-Background Version Tree Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every visible generated candidate is a complete single object on pure white, then turn a dropped candidate into a persistent Version Graph node that appears immediately as an image and upgrades in place to editable 3D.

**Architecture:** Extend the four-stage generation contract with explicit image constraints and enforce them again in the remote image QA filter. Persist a small version graph in the existing four-stage SQLite store and expose it through the realtime snapshot/API. Replace the frontend's derived `acceptedCandidateIds` layout with explicit graph nodes, a pure deterministic tree-layout helper, and one idempotent drop action shared by HTML drag-and-drop and the keyboard/touch button.

**Tech Stack:** FastAPI, Pydantic, SQLite, React 19, TypeScript, native HTML Drag and Drop, Three.js, Node test runner, pytest, Pillow.

## Global Constraints

- Do not commit, push GitHub, or deploy GitHub Pages.
- A candidate is visible only after pure-white, complete-single-object QA passes.
- Solution Space contains 6–8 accepted candidates per generation batch.
- Dropping a candidate creates the image node within 300ms and starts Hy3D asynchronously.
- Hy3D updates the same `node_id`; it never creates a second version node.
- Version history and active node survive refresh and WebSocket reconnect.
- Keep existing always-on Observation, multi-intent Gate, keyword inheritance, and append-only Solution Space behavior unchanged.

---

## File Structure

- `backend/app/models/four_stage.py`: generation image constraints.
- `backend/app/services/generation/four_stage_spec_builder.py`: white-background/full-object prompt contract.
- `backend/app/models/realtime_observation.py`: persisted Version Graph models and requests.
- `backend/app/services/storage/four_stage_store.py`: SQLite storage for graph state.
- `backend/app/services/intent/realtime_observation.py`: idempotent graph operations and snapshot aggregation.
- `backend/app/api/realtime_observation.py`: graph create/update/activate endpoints.
- `remote_worker/variation_stage2_images.py`: visual acceptance hard gate.
- `frontend/src/types.ts`: Version Graph API types.
- `frontend/src/utils/versionGraph.ts`: deterministic tree layout and status helpers.
- `frontend/src/state/studioStore.ts`: hydrate, create, activate, upgrade, retry.
- `frontend/src/components/panels/SolutionSpaceRail.tsx`: draggable candidate cards and used-version labels.
- `frontend/src/components/StudioCanvas.tsx`: drop target, graph nodes, curved links, status and retry UI.
- `frontend/src/main.tsx`: prop wiring.
- `frontend/src/styles.css`: active path, drop state and node presentation.

---

### Task 1: Make white-background/full-object constraints part of GenerationSpec

**Files:**
- Modify: `backend/app/models/four_stage.py`
- Modify: `backend/app/services/generation/four_stage_spec_builder.py`
- Test: `backend/tests/test_four_stage_generation.py`

**Interfaces:**
- Produces: `GenerationSpec.require_white_background: bool`, `require_single_object: bool`, `require_full_object: bool`.
- Produces: every `prompt_candidates[]` entry ending with the same immutable framing contract.
- Consumes: existing `GenerationSpecBuilder.build(run, selected_option_id)` inputs.

- [ ] **Step 1: Write the failing generation-contract test**

Add a test that builds a part-scope spec and asserts:

```python
assert spec.require_white_background is True
assert spec.require_single_object is True
assert spec.require_full_object is True
for prompt in spec.prompt_candidates:
    normalized = prompt.lower()
    assert "pure white rgb(255,255,255) background" in normalized
    assert "one complete object only" in normalized
    assert "no crop" in normalized
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_four_stage_generation.py -k white_background -q
```

Expected: failure because `GenerationSpec` lacks the three fields and prompts do not contain the immutable suffix.

- [ ] **Step 3: Add the explicit fields and immutable suffix**

Add to `GenerationSpec`:

```python
require_white_background: bool = True
require_single_object: bool = True
require_full_object: bool = True
```

Append exactly one suffix in `GenerationSpecBuilder` after scenario-specific prompt construction:

```python
_IMAGE_FRAMING_CONTRACT = (
    "One complete object only, centered with at least 5% clear margin on every side; "
    "pure white RGB(255,255,255) background; no crop, no cut-off parts, no floor, "
    "no shadow, no scene, no text, no watermark, and no additional objects."
)
```

Deduplicate the suffix rather than adding it separately inside every scenario branch.

- [ ] **Step 4: Run focused and neighboring spec tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_four_stage_generation.py tests/test_four_stage_e2e.py -q
```

Expected: all pass.

---

### Task 2: Enforce white background, safe margins and one connected subject in the remote worker

**Files:**
- Modify: `remote_worker/variation_stage2_images.py`
- Create: `remote_worker/tests/test_variation_stage2_images.py`

**Interfaces:**
- Consumes: `visual_acceptance(path: Path, *, stage: str) -> dict[str, Any]`.
- Produces: QA keys `accepted`, `reasons`, `border_white_ratio`, `subject_bbox`, `safe_margin_ratio`, `component_count`, `nonwhite_ratio`.

- [ ] **Step 1: Create synthetic-image failing tests**

Use Pillow to create temporary 256×256 inputs:

```python
from PIL import Image, ImageDraw

def draw_fixture(path, *, background=(255, 255, 255), boxes=((32, 28, 224, 228),)):
    image = Image.new("RGB", (256, 256), background)
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.ellipse(box, fill=(70, 80, 95))
    image.save(path)

def test_accepts_one_complete_subject_on_pure_white(tmp_path):
    path = tmp_path / "valid.png"
    draw_fixture(path)
    assert visual_acceptance(path, stage="part")["accepted"] is True

def test_rejects_gray_or_colored_background(tmp_path):
    path = tmp_path / "gray.png"
    draw_fixture(path, background=(230, 232, 236))
    assert "background_not_pure_white" in visual_acceptance(path, stage="part")["reasons"]

def test_rejects_subject_touching_any_edge(tmp_path):
    path = tmp_path / "cropped.png"
    draw_fixture(path, boxes=((0, 28, 224, 228),))
    assert "subject_touches_frame" in visual_acceptance(path, stage="part")["reasons"]

def test_rejects_two_separate_large_subjects(tmp_path):
    path = tmp_path / "two.png"
    draw_fixture(path, boxes=((22, 60, 112, 190), (144, 60, 234, 190)))
    assert "multiple_large_subjects" in visual_acceptance(path, stage="part")["reasons"]
```

The valid fixture is a single dark ellipse within `[32, 28, 224, 228]` on `(255,255,255)`. The cropped fixture touches `x=0`. The multiple-subject fixture contains two similarly sized disconnected ellipses.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 -m pytest remote_worker/tests/test_variation_stage2_images.py -q
```

Expected: the stricter `0.95` border threshold, bbox margin and single-subject assertions fail.

- [ ] **Step 3: Tighten `visual_acceptance`**

Implement:

```python
MIN_BORDER_WHITE_RATIO = 0.95
MIN_SAFE_MARGIN_RATIO = 0.05
MIN_SUBJECT_RATIO = 0.10
MAX_SUBJECT_RATIO = 0.70
```

Compute a foreground bbox from the downsampled non-white mask. Reject with stable reason codes:

```python
"background_not_pure_white"
"subject_touches_frame"
"multiple_large_subjects"
"subject_too_small"
"subject_too_large"
```

Require exactly one large connected component after allowing small attached/noise components below `8%` of the largest component.

- [ ] **Step 4: Verify the worker writes only accepted artifacts**

At the existing call site around `visual_acceptance(image_path, stage=stage)`, keep rejected items in diagnostic metadata but omit them from the returned `items` list consumed by Solution Space. Preserve the existing retry/backfill loop and stop only at the requested accepted count or its bounded attempt cap.

- [ ] **Step 5: Run worker tests**

Run:

```bash
python3 -m pytest remote_worker/tests/test_variation_stage2_images.py remote_worker/tests/test_variation_contracts.py -q
```

Expected: all pass.

---

### Task 3: Persist Version Graph nodes and active state

**Files:**
- Modify: `backend/app/models/realtime_observation.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/services/storage/four_stage_store.py`
- Modify: `backend/app/services/intent/realtime_observation.py`
- Modify: `backend/app/api/realtime_observation.py`
- Test: `backend/tests/test_realtime_observation.py`

**Interfaces:**
- Produces: `VersionNodeStatus`, `VersionGraphNode`, `VersionGraphNodeCreateRequest`, `VersionGraphNodeUpdateRequest` and `VersionGraphState`.
- Produces endpoints:
  - `POST /api/v1/sessions/{session_id}/version-nodes`
  - `PATCH /api/v1/sessions/{session_id}/version-nodes/{node_id}`
  - `PUT /api/v1/sessions/{session_id}/active-version/{node_id}`
- Extends `RealtimeObservationSnapshot` with `version_graph`.

- [ ] **Step 1: Write failing API persistence tests**

Cover these behaviors with `TestClient`:

```python
def create_node(sid, parent, candidate):
    response = client.post(
        f"/api/v1/sessions/{sid}/version-nodes",
        json={"parent_node_id": parent, "candidate_id": candidate,
              "label": candidate, "preview_url": f"/files/{candidate}.png"},
    )
    assert response.status_code == 200
    return response.json()

def test_version_node_create_is_idempotent_for_parent_and_candidate():
    sid = _session()
    source = create_node(sid, None, "source")
    first = create_node(sid, source["node_id"], "candidate_04")
    repeated = create_node(sid, source["node_id"], "candidate_04")
    assert repeated["node_id"] == first["node_id"]
    assert repeated["version_number"] == first["version_number"]

def test_version_node_mesh_upgrade_preserves_node_identity():
    sid = _session()
    source = create_node(sid, None, "source")
    node = create_node(sid, source["node_id"], "candidate_04")
    updated = client.patch(
        f"/api/v1/sessions/{sid}/version-nodes/{node['node_id']}",
        json={"status": "mesh_ready", "mesh_url": "/files/candidate_04.glb"},
    ).json()
    assert updated["node_id"] == node["node_id"]
    assert updated["parent_node_id"] == source["node_id"]

def test_version_graph_restores_active_node_in_snapshot():
    sid = _session()
    source = create_node(sid, None, "source")
    node = create_node(sid, source["node_id"], "candidate_04")
    assert client.put(f"/api/v1/sessions/{sid}/active-version/{node['node_id']}").status_code == 200
    graph = client.get(f"/api/v1/sessions/{sid}/realtime-observation").json()["version_graph"]
    assert graph["active_node_id"] == node["node_id"]

def test_version_graph_can_branch_from_an_old_parent():
    sid = _session()
    source = create_node(sid, None, "source")
    left = create_node(sid, source["node_id"], "candidate_04")
    right = create_node(sid, source["node_id"], "candidate_05")
    assert left["parent_node_id"] == right["parent_node_id"] == source["node_id"]
    assert left["node_id"] != right["node_id"]
```

The create request is:

```json
{
  "parent_node_id": "version_source",
  "candidate_id": "candidate_04",
  "label": "Version 2",
  "preview_url": "/files/candidate_04.png"
}
```

Assert repeated POST returns the same `node_id` and `version_number` and that PATCH changes only mesh/status fields.

- [ ] **Step 2: Run focused test and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_realtime_observation.py -k version_graph -q
```

Expected: 404 or missing model fields.

- [ ] **Step 3: Add graph models**

Define:

```python
class VersionNodeStatus(StrEnum):
    image_ready = "image_ready"
    generating_3d = "generating_3d"
    mesh_ready = "mesh_ready"
    mesh_failed = "mesh_failed"

class VersionGraphNode(BaseModel):
    node_id: str
    session_id: str
    version_number: int = Field(ge=1)
    parent_node_id: str | None = None
    candidate_id: str | None = None
    label: str
    preview_url: str | None = None
    mesh_url: str | None = None
    obj_url: str | None = None
    status: VersionNodeStatus
    hy3d_job_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

class VersionGraphState(BaseModel):
    active_node_id: str | None = None
    nodes: list[VersionGraphNode] = Field(default_factory=list)
```

- [ ] **Step 4: Add SQLite storage**

Create tables:

```sql
CREATE TABLE IF NOT EXISTS version_graph_nodes (
  node_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  parent_node_id TEXT,
  candidate_id TEXT,
  version_number INTEGER NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(session_id, parent_node_id, candidate_id)
);
CREATE TABLE IF NOT EXISTS version_graph_states (
  session_id TEXT PRIMARY KEY,
  active_node_id TEXT,
  updated_at TEXT NOT NULL
);
```

Add store methods `save_version_node`, `get_version_node`, `list_version_nodes`, `set_active_version_node`, and `get_version_graph_state`. Include both tables in `clear()`.

- [ ] **Step 5: Add idempotent service methods and API routes**

Create must validate that the parent belongs to the same session, allocate `max(version_number)+1`, and return the existing node for the unique `(session_id,parent,candidate)` key. Update must allow only status, mesh URLs, job id and error. Activate must require an existing node.

- [ ] **Step 6: Extend realtime snapshots and verify**

Populate `RealtimeObservationSnapshot.version_graph` from the store. Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_realtime_observation.py -q
```

Expected: all pass, including existing Observation/Gate/Solution append tests.

---

### Task 4: Build a deterministic left-to-right Version Graph layout

**Files:**
- Create: `frontend/src/utils/versionGraph.ts`
- Create: `frontend/tests/versionGraph.test.ts`
- Modify: `frontend/src/types.ts`

**Interfaces:**
- Produces: `layoutVersionGraph(nodes, activeNodeId): { nodes: VersionCanvasNode[]; links: VersionCanvasLink[] }`.
- Produces: `activePathNodeIds(nodes, activeNodeId): Set<string>`.
- Consumes: persisted `VersionGraphNode[]`; no React or DOM dependency.

- [ ] **Step 1: Write layout tests first**

Test exact invariants rather than pixels tied to viewport size:

```ts
const source = { node_id: "source", parent_node_id: null, version_number: 1 };
const v2 = { node_id: "v2", parent_node_id: "source", version_number: 2 };
const v3 = { node_id: "v3", parent_node_id: "v2", version_number: 3 };
const sibling = { node_id: "sibling", parent_node_id: "source", version_number: 4 };

test("places ancestors left of the active node", () => {
  const result = layoutVersionGraph([source, v2, v3], "v3");
  const byId = Object.fromEntries(result.nodes.map((node) => [node.id, node]));
  assert.ok(byId.source.x < byId.v2.x && byId.v2.x < byId.v3.x);
});

test("stacks sibling branches vertically", () => {
  const result = layoutVersionGraph([source, v2, sibling], "v2");
  const byId = Object.fromEntries(result.nodes.map((node) => [node.id, node]));
  assert.notEqual(byId.v2.y, byId.sibling.y);
});

test("keeps the active node at the main editing anchor", () => {
  const active = layoutVersionGraph([source, v2], "v2").nodes.find((node) => node.id === "v2");
  assert.deepEqual({ x: active?.x, y: active?.y, width: active?.width, height: active?.height },
    { x: 640, y: 0, width: 520, height: 520 });
});

test("returns one link per non-root node", () => {
  assert.equal(layoutVersionGraph([source, v2, v3, sibling], "v3").links.length, 3);
});
```

Use source → v2 → v3 plus a second source child. Assert active `x=640,y=0,width=520,height=520`; each ancestor has smaller `x`; sibling nodes have different `y` values.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd frontend
node --experimental-strip-types --test tests/versionGraph.test.ts
```

Expected: module-not-found failure for `versionGraph.ts`.

- [ ] **Step 3: Implement the pure layout helper**

Use parent traversal to compute depth and the active path. Set the active anchor to `(640,0)`, history thumbnail size to `220×220`, depth spacing to `280`, and sibling row spacing to `240`. Produce cubic-link control points or enough endpoint data for the SVG component to draw curves.

- [ ] **Step 4: Run layout and full frontend tests**

Run:

```bash
cd frontend
node --experimental-strip-types --test tests/versionGraph.test.ts tests/*.test.ts
```

Expected: all pass.

---

### Task 5: Add real candidate drag-and-drop and one shared version creation action

**Files:**
- Modify: `frontend/src/components/panels/SolutionSpaceRail.tsx`
- Modify: `frontend/src/components/StudioCanvas.tsx`
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Produces: `dropCandidateIntoVersionGraph(candidate: Candidate): Promise<void>`.
- Produces: card drag MIME `application/x-flowstudio-candidate` with `{candidateId}`.
- Consumes: Task 3 graph endpoints and Task 4 layout helper.

- [ ] **Step 1: Add failing source-contract tests**

Assert that Solution cards are `draggable`, set the FlowStudio MIME payload, VersionCanvas exposes `onDragOver/onDrop`, and the button calls the same `onDropCandidate` callback. Assert the old `acceptedCandidateIds`-derived layout is absent.

- [ ] **Step 2: Run interaction test and verify RED**

Run:

```bash
cd frontend
node --experimental-strip-types --test tests/interactionReliability.test.ts
```

Expected: missing draggable/drop contract assertions fail.

- [ ] **Step 3: Hydrate the persisted graph**

Add TypeScript types matching Task 3. During bootstrap and realtime refresh, merge `snapshot.version_graph` into state. Ensure a source Version 1 node exists once per session and restore `active_node_id`.

- [ ] **Step 4: Implement the shared drop action**

The action must:

1. Validate `candidatePreviewUrl(candidate)`.
2. POST the node immediately using the current active node as parent.
3. Merge the returned node, mark it active, and render its image.
4. Return control to the UI before awaiting Hy3D.
5. Start `runFourStageHy3d` or `generateCandidateHy3d` in a detached promise.
6. PATCH the same node to `mesh_ready` with URLs, or `mesh_failed` with an error.

Repeated action on the same parent/candidate must reuse the returned node and must not start Hy3D when that node is already `generating_3d` or `mesh_ready`.

- [ ] **Step 5: Implement native DnD and accessible fallback**

On each candidate article:

```tsx
draggable={Boolean(previewUrl)}
onDragStart={(event) => {
  event.dataTransfer.effectAllowed = "copy";
  event.dataTransfer.setData(FLOWSTUDIO_CANDIDATE_MIME, JSON.stringify({ candidateId }));
}}
```

The existing “拖入画布” button calls `onDropCandidate(candidate)`. VersionCanvas parses the payload and resolves the candidate through a passed callback; invalid payloads are ignored without throwing.

- [ ] **Step 6: Verify interaction tests and TypeScript**

Run:

```bash
cd frontend
node --experimental-strip-types --test tests/*.test.ts
npx tsc --noEmit
```

Expected: all pass.

---

### Task 6: Render the active version, historical tree, statuses and retry behavior

**Files:**
- Modify: `frontend/src/components/StudioCanvas.tsx`
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Consumes: `layoutVersionGraph` and `VersionGraphNode.status`.
- Produces: `onRetryVersionNode(nodeId)`; updates the same node only.

- [ ] **Step 1: Add failing status and accessibility tests**

Assert node markup exposes `Version N`, the candidate label, localized status text, an accessible retry button only for `mesh_failed`, and a drop-target label. Assert active-path classes and reduced-motion styles exist.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd frontend
node --experimental-strip-types --test tests/interactionReliability.test.ts
```

- [ ] **Step 3: Replace derived nodes with persisted graph layout**

Remove the version-node derivation based on `acceptedCandidateIds`. Render Task 4 nodes and links. Current active node is 520×520 at the main anchor; history nodes are 220×220 left of it. Draw SVG cubic paths, highlight the active ancestry, and dim unrelated branches.

- [ ] **Step 4: Separate image and mesh active-node rendering**

For `image_ready`, `generating_3d`, or `mesh_failed`, render the candidate `<img>` inside the active frame and disable sculpt/part-selection controls. For `mesh_ready`, pass the node mesh URL to `ThreeViewport` and enable editing. This avoids treating a PNG URL as `previewMeshUrl`.

- [ ] **Step 5: Add retry-in-place**

`onRetryVersionNode(nodeId)` PATCHes the existing node to `generating_3d`, reruns Hy3D using its `candidate_id`, then PATCHes success/failure. It never POSTs a new node.

- [ ] **Step 6: Style and verify**

Add drop-hover outline, state badge, active-path connectors, history thumbnails, and failure controls. Keep panels above the version world and honor `prefers-reduced-motion`.

Run:

```bash
cd frontend
node --experimental-strip-types --test tests/*.test.ts
npx tsc --noEmit
npm run build
```

Expected: all pass; production build completes.

---

### Task 7: GPU synchronization and end-to-end acceptance

**Files:**
- Sync only the files modified by Tasks 1–6 and `frontend/dist/` to `/root/flowstudio_app`.
- Do not modify Git state.

**Interfaces:**
- Consumes: local verified build and remote services.
- Produces: browser and API evidence for the full white-image → drop → Version 2 → mesh upgrade flow.

- [ ] **Step 1: Run all focused tests locally**

```bash
backend/.venv/bin/python -m pytest backend/tests/test_four_stage_generation.py backend/tests/test_realtime_observation.py -q
python3 -m pytest remote_worker/tests/test_variation_stage2_images.py remote_worker/tests/test_variation_contracts.py -q
cd frontend
node --experimental-strip-types --test tests/*.test.ts
npx tsc --noEmit
npm run build
```

- [ ] **Step 2: Copy exact artifacts and restart only affected services**

Validate existing PIDs and commands before TERM. Restart backend `:18000`, frontend `:5173`, and the image worker only if worker Python files changed and its process command matches the expected service. Confirm health endpoints return 200.

- [ ] **Step 3: Verify white candidate QA with real generation**

Generate one 6–8 candidate batch. For every visible image, record border-white ratio, bbox margin, component count and dimensions. Fail acceptance if any candidate is non-white, cropped or contains an extra subject.

- [ ] **Step 4: Verify real drag/drop and immediate Version 2**

Drag a candidate card to the canvas. Capture evidence that Version 2 image appears before Hy3D completes, Version 1 moves left, and a parent-child connector exists. Confirm the “拖入画布” button produces the identical graph operation.

- [ ] **Step 5: Verify in-place mesh upgrade and persistence**

Wait for Hy3D. Confirm the same `node_id` changes from `generating_3d` to `mesh_ready`, coordinates remain stable, and sculpt interaction becomes available. Refresh the page and confirm the graph and active node restore. Branch once from Version 1 and confirm the sibling is vertically separated.

- [ ] **Step 6: Report evidence and remaining limitations**

Report test totals, service health, real node IDs/status transitions, QA metrics, and screenshots. Do not claim completion if a real image fails the hard gate or a refresh loses the tree.
