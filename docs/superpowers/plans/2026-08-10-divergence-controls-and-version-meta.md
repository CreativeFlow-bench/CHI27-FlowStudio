# Divergence Controls and Version Meta Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make keyword selection stable, generate 5–8 candidates in every semantic dimension, and replace the active version overlay with a compact `V1 / Snowman / history icon` capsule.

**Architecture:** Keep server responses authoritative only after pending per-revision selection writes settle. Extend the existing semantic divergence parameter object with a per-group quota and derive the total request count from the four canonical groups. Keep the UI changes inside the existing AI Behavior and VersionCanvas components, using small pure utilities for reconciliation and label normalization.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, pytest, React 19, TypeScript, Node test runner, vanilla CSS.

## Global Constraints

- Local changes only; do not access or deploy to GPU/remote systems.
- Do not start Hunyuan3D or any 3D generation path.
- Per-group content amount range is 5–8; default is 5.
- Semantic dimensions are exactly `shape`, `connection`, `surface`, and `semantic_transfer`.
- UI strictness stays fixed at `0.6` and is not user-facing.
- Preserve existing dirty-worktree changes and stage only task-owned files.

---

### Task 1: Balanced semantic divergence contract

**Files:**
- Modify: `backend/app/models/semantic_divergence.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/divergence/semantic_model_clients.py`
- Modify: `backend/app/services/divergence/semantic_validator.py`
- Test: `backend/tests/test_semantic_divergence_models.py`
- Test: `backend/tests/test_semantic_divergence_service.py`

**Interfaces:**
- Produces: `SemanticDivergenceParams.per_group_count: int`, bounded 5–8.
- Produces: `SemanticDivergenceParams.candidate_count == per_group_count * 4`.
- Produces: validator rejection counts `minimum_<group>` for underfilled groups.

- [ ] **Step 1: Write failing model and payload tests**

```python
def test_semantic_divergence_defaults_to_five_candidates_per_group():
    params = SemanticDivergenceParams()
    assert params.per_group_count == 5
    assert params.candidate_count == 20

def test_model_payload_requests_all_four_group_quotas():
    content = payload_content(SemanticDivergenceParams(per_group_count=6))
    assert content["response_schema"]["candidate_count"] == 24
    assert content["response_schema"]["group_quotas"] == {
        "shape": 6, "connection": 6, "surface": 6, "semantic_transfer": 6,
    }
```

- [ ] **Step 2: Run tests and verify RED**

Run: `backend/.venv/bin/pytest backend/tests/test_semantic_divergence_models.py backend/tests/test_semantic_divergence_service.py -q`

Expected: failures because `per_group_count` and `group_quotas` are absent and the payload still requests 9.

- [ ] **Step 3: Implement quota derivation and payload contract**

Add the bounded `per_group_count`, derive total count, and build the response schema from `request.params` instead of a literal 9. Require exactly the requested number in every canonical group. Expand the global compatibility ceiling to 32, and make response parsing validate the current request's exact count so legacy persisted 9–15 candidate requests remain readable.

- [ ] **Step 4: Add and verify the validator group-quota test**

```python
def test_validator_requires_requested_quota_in_every_group(...):
    request = request_factory(params={"per_group_count": 5})
    candidates = balanced_candidates(per_group=5)
    candidates.pop()
    report = validator.validate(request, candidates)
    assert report.needs_fallback is True
    assert report.rejection_counts["minimum_semantic_transfer"] == 1
```

Run the same focused pytest command and expect PASS.

---

### Task 2: Stable optimistic keyword selection

**Files:**
- Create: `frontend/src/utils/selectionReconciliation.ts`
- Modify: `frontend/src/state/studioStore.ts`
- Create: `frontend/tests/selectionReconciliation.test.ts`

**Interfaces:**
- Produces: `reconcileSelectedPromptTokens(input): PromptToken[]`.
- Consumes: server-selected candidate IDs, available tokens, optimistic tokens, and `persistencePending`.

- [ ] **Step 1: Write the failing reconciliation test**

```ts
test("pending optimistic selection wins over a stale empty poll", () => {
  assert.deepEqual(reconcileSelectedPromptTokens({
    availableTokens: [tokenA, tokenB],
    serverSelectedCandidateIds: [],
    optimisticTokens: [tokenA, tokenB],
    persistencePending: true,
  }), [tokenA, tokenB]);
});
```

- [ ] **Step 2: Run test and verify RED**

Run: `node --experimental-strip-types --test tests/selectionReconciliation.test.ts`

Expected: module or export missing.

- [ ] **Step 3: Implement the pure reconciliation utility**

Return optimistic tokens while persistence is pending. Otherwise filter available tokens by the authoritative server IDs.

- [ ] **Step 4: Integrate with polling and persistence**

In `refreshFourStageUiFromRun`, inspect the active revision's persistence tracker. Do not clear selected tokens while `tracker.latest` is unsettled. On the latest successful response, update revision state and allow authoritative hydration. On failure, retain selected tokens and keep Generate disabled through the existing error map.

- [ ] **Step 5: Run focused tests and TypeScript check**

Run:

```bash
node --experimental-strip-types --test tests/selectionReconciliation.test.ts tests/optimisticRevisions.test.ts
./node_modules/.bin/tsc -p tsconfig.json --noEmit
```

Expected: PASS and exit 0.

---

### Task 3: Content amount UI and request propagation

**Files:**
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx`
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/workspacePresentation.test.ts`

**Interfaces:**
- Produces: `divergencePerGroupCount` state, default 5.
- Produces: panel props `divergencePerGroupCount`, `onDivergencePerGroupCountChange`.
- Sends: `{ temperature, strictness: 0.6, per_group_count }` for Gate acceptance and reruns.

- [ ] **Step 1: Write failing pure UI projection tests**

Add `formatPerGroupCount(5) === "5 / 维"` and bounds tests to `workspacePresentation.test.ts`.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --experimental-strip-types --test tests/workspacePresentation.test.ts`

Expected: missing formatter failure.

- [ ] **Step 3: Implement state, request propagation, and panel control**

Replace the second slider with a 5–8 range labeled `内容数量`; show the formatter output. Keep strictness at the module constant `0.6` when constructing requests and request keys.

- [ ] **Step 4: Run focused tests and TypeScript check**

Run:

```bash
node --experimental-strip-types --test tests/workspacePresentation.test.ts tests/gateContract.test.ts
./node_modules/.bin/tsc -p tsconfig.json --noEmit
```

Expected: PASS and exit 0.

---

### Task 4: Compact active version metadata

**Files:**
- Modify: `frontend/src/components/StudioCanvas.tsx`
- Modify: `frontend/src/utils/versionGraph.ts`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/versionGraph.test.ts`
- Test: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Produces: `compactVersionLabel(label: string): string`.
- UI output: `V{versionNumber}`, normalized object label, and an icon-only button with `aria-label="查看全部版本"`.

- [ ] **Step 1: Write failing label-normalization and rendered-contract tests**

```ts
assert.equal(compactVersionLabel("Christmas · Snowman"), "Snowman");
assert.equal(compactVersionLabel("Snowman"), "Snowman");
```

The component contract must render `V{node.versionNumber}`, use a Lucide version-tree icon, and omit the active node status label.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --experimental-strip-types --test tests/versionGraph.test.ts tests/interactionReliability.test.ts`

Expected: helper missing and old active metadata copy still present.

- [ ] **Step 3: Implement component and CSS**

Use a translucent white capsule with the existing panel border, blur, compact `V1` badge, plain object label, and 28px circular icon action. Preserve focus-visible styling and the existing accessible name.

- [ ] **Step 4: Run focused tests and TypeScript check**

Run the same tests and `./node_modules/.bin/tsc -p tsconfig.json --noEmit`; expect PASS.

---

### Task 5: Restore the approved full AI Behavior hierarchy

**Files:**
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/workspaceLayout.css`
- Test: `frontend/tests/aiBehaviorPanelContract.test.ts`

**Interfaces:**
- Preserves all existing `AIBehaviorPanel` props and callbacks.
- Produces an outer `AI BEHAVIOR` panel with phenomenon, next action, model details, and a nested `More Creative?` card.
- Exposes four semantic groups with accessible headings and one full-width Generate action.

- [ ] **Step 1: Write the failing panel contract test**

The test must render the real `AIBehaviorPanel` with a quota-complete four-group fixture and assert:

```ts
assert.match(html, /More Creative\?/);
assert.match(html, /AI BEHAVIOR/);
assert.match(html, /CURRENT PHENOMENON/);
assert.match(html, /NEXT ACTION/);
assert.match(html, /MODEL DETAILS/);
assert.match(html, /DIVERGENCE/);
assert.match(html, /CONTENT/);
assert.match(html, /SHAPE/);
assert.match(html, /CONNECTION/);
assert.match(html, /SURFACE/);
assert.match(html, /SEMANTIC TRANSFER/);
assert.equal((html.match(/>Generate</g) ?? []).length, 1);
assert.match(css, /\.more-creative-card[\s\S]*?\.more-creative-title\s*\{[^}]*font-size:\s*26px/);
```

- [ ] **Step 2: Run the test and verify RED**

Run: `node --experimental-strip-types --test tests/aiBehaviorPanelContract.test.ts`

Expected: FAIL because the flattened component omits the approved outer AI Behavior hierarchy and styles More Creative as a larger primary title.

- [ ] **Step 3: Implement the approved structure**

Restore the outer header, status dots, current-phenomenon card, next-action card, and model-details label. Put the current divergence controls in a nested More Creative card, keep the mobile toggle available, use the dynamic accepted scope when present, and retain the current loading/error/persistence behavior. Move Generate below the child card without changing its enablement logic.

- [ ] **Step 4: Implement the approved styling**

Match the supplied reference with a translucent light-grey outer shell, compact uppercase AI Behavior header, two large insight cards, a bordered More Creative child card, two equal-width parameter cards, segmented content indicator, outlined wrap-friendly chips, blue selected pills, a scrollable semantic-section body, and a full-width blue Generate button below the child card. Keep the More Creative title at `26px`, below the `30px` Flow Studio wordmark. Preserve visible focus rings and the existing small-screen collapse behavior.

- [ ] **Step 5: Run focused verification**

```bash
node --experimental-strip-types --test tests/aiBehaviorPanelContract.test.ts tests/workspacePresentation.test.ts tests/selectionReconciliation.test.ts
./node_modules/.bin/tsc -p tsconfig.json --noEmit
```

Expected: PASS and exit 0.

---

### Task 6: End-to-end local verification

**Files:**
- Verify only; no new production files.

- [ ] **Step 1: Run focused backend tests**

Run: `backend/.venv/bin/pytest backend/tests/test_semantic_divergence_models.py backend/tests/test_semantic_divergence_service.py -q`

- [ ] **Step 2: Run the complete frontend test suite**

Run: `node --experimental-strip-types --test tests/*.test.ts`

Record any pre-existing unrelated failure separately; do not hide it.

- [ ] **Step 3: Run static and build verification**

```bash
./node_modules/.bin/tsc -p tsconfig.json --noEmit
npm run build
git diff --check
```

- [ ] **Step 4: Browser acceptance on `http://127.0.0.1:5184/`**

Verify rapid multi-chip selection remains selected across at least two 2-second polls, content amount reads `5 / 维`, every group shows at least five chips after a fresh API run, and active metadata shows only `V1`, `Snowman`, and the icon action.
