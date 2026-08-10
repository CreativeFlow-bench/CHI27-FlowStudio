# FlowStudio Figure 4 Workspace Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the FlowStudio desktop workspace match the user-selected Figure 4 composition, fit completely at 1280×720, and project each Gate/status message in exactly one UI location.

**Architecture:** Keep `IntentRevision` as the authoritative Gate aggregate, stop copying Gate prompts into `UiBrief`, and add one pure frontend presentation selector before React rendering. Replace layout-owned uses of `ResizableShell` with static semantic surfaces, drive the two workspace arrangements from a single `has-solution-space` root state, and isolate final spatial rules in one stylesheet imported after the legacy visual stylesheet.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, pytest, React 19, TypeScript, Vite, Node test runner, native CSS, existing FlowStudio/Three.js canvas.

## Global Constraints

- The selected Superdesign draft `30c41c55-e05f-4332-9f86-7ad7f3430464` and `docs/superpowers/specs/2026-08-10-flowstudio-figure4-workspace-convergence-design.md` are the visual and behavioral contract.
- At `1280×720`, Brand, Perception, Solution Space when present, AI Behavior, Active Editor, Canvas navigation, and Composer must all remain inside the viewport.
- With no Solution Space, AI Behavior stays on the right side in the middle-upper usable region; with Solution Space, AI Behavior moves below the rail with a 16px gap.
- `IntentRevision.gate_question` is the only Gate question source; the question renders only in `PlannerClarificationOverlay`.
- Perception renders one current verifiable action, maximum two lines; history remains behind its disclosure.
- AI Behavior renders one short narrative, More Creative controls, and collapsed model details; it does not render four-stage status, Gate status/question, duplicate next-action cards, or generation progress.
- Solution Space owns generation progress and candidate results.
- Do not add dependencies, `transition: all`, new layout `!important` declarations, or destructive schema changes.
- Preserve unrelated worktree changes; stage and commit only files listed by each task.

---

## File Structure

- `backend/app/services/intent/realtime_observation.py`: build `UiBrief` without Gate interaction authority.
- `backend/tests/test_realtime_observation.py`: protect the Gate/UiBrief ownership boundary.
- `frontend/src/utils/workspacePresentation.ts`: pure AI Behavior view-model selector; no React or store access.
- `frontend/tests/workspacePresentation.test.ts`: cover narrative fallback and creative-control state precedence.
- `frontend/src/components/panels/AIBehaviorPanel.tsx`: render the compact right-side behavior panel from the presentation model.
- `frontend/tests/workspaceBrowserContract.ts`: inspect the real Vite-rendered DOM for hierarchy, accessibility, overflow, and panel geometry.
- `frontend/tests/panelVisualHierarchy.test.ts`: retain the existing menu test and remove the obsolete source-text AI hierarchy test.
- `frontend/src/components/panels/SolutionSpaceRail.tsx`: static layout-owned result rail without inline React dimensions.
- `frontend/src/main.tsx`: compute presentation once, mark the root layout state, and pass narrowed props.
- `frontend/src/workspaceLayout.css`: single Figure 4 spatial contract and responsive rules.
- `frontend/src/styles.css`: remove only the obsolete fixed-dock blocks that use `!important` and compete with the new contract.
- `frontend/tests/accessibility.test.ts`: retain existing legacy coverage; new workspace semantics are verified against the rendered DOM contract.

---

### Task 1: Remove Gate duplication from the backend UiBrief projection

**Files:**
- Modify: `backend/tests/test_realtime_observation.py:247-262`
- Modify: `backend/app/services/intent/realtime_observation.py:852-897`

**Interfaces:**
- Consumes: `IntentRevision.status`, `IntentRevision.gate_question`, `IntentRevision.gate_id`, and `RealtimeObservationSnapshot.revisions`.
- Produces: pending-Gate `UiBrief` values with `status="awaiting_gate"`, `pending_decision_count > 0`, `next_question=""`, `requires_response=False`, and `question_id=None`.

- [ ] **Step 1: Write the failing backend ownership test**

Add this test next to `test_snapshot_exposes_bounded_ui_brief`:

```python
def test_pending_gate_lives_on_revision_not_ui_brief() -> None:
    sid = _session()
    revision = _revision(sid, "change the hat connection")

    snapshot = client.get(f"/api/v1/sessions/{sid}/realtime-observation")

    assert snapshot.status_code == 200
    payload = snapshot.json()
    locked = next(
        item for item in payload["revisions"]
        if item["revision_id"] == revision["revision_id"]
    )
    brief = payload["ui_brief"]
    assert locked["gate_question"] == "你想改变这个 hat 的形状或连接吗？"
    assert brief["status"] == "awaiting_gate"
    assert brief["pending_decision_count"] == 1
    assert brief["next_question"] == ""
    assert brief["requires_response"] is False
    assert brief["question_id"] is None
    assert locked["gate_question"] not in brief["phenomenon"]
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
PYTHONPATH=backend /opt/anaconda3/bin/python -m pytest \
  backend/tests/test_realtime_observation.py::test_pending_gate_lives_on_revision_not_ui_brief -q
```

Expected: FAIL because `_ui_brief()` currently copies `active.gate_question` and sets response metadata.

- [ ] **Step 3: Make UiBrief informational during a pending Gate**

Replace the pending branch in `_ui_brief()` with:

```python
if pending:
    active = pending[0]
    phenomenon = observation.intent_summary or (
        f"已识别到一个关于{active.gate_scope or '当前对象'}的调整意图。"
    )
    next_question = ""
    requires_response = False
    question_id = None
    details_ref = active.revision_id
    status = "awaiting_gate"
```

Do not remove fields from the Pydantic model; older clients keep receiving the same schema.

- [ ] **Step 4: Run backend projection regression tests**

Run:

```bash
PYTHONPATH=backend /opt/anaconda3/bin/python -m pytest \
  backend/tests/test_realtime_observation.py -k "ui_brief or gate_compression" -q
```

Expected: PASS.

- [ ] **Step 5: Commit the backend projection boundary**

```bash
git add backend/app/services/intent/realtime_observation.py backend/tests/test_realtime_observation.py
git commit -m "fix: keep gate prompts out of ui brief"
```

---

### Task 2: Add one frontend AI Behavior presentation selector

**Files:**
- Create: `frontend/src/utils/workspacePresentation.ts`
- Create: `frontend/tests/workspacePresentation.test.ts`

**Interfaces:**
- Consumes: `UiBrief | null`, planner fallback strings, semantic-divergence loading/error/content flags.
- Produces: `AiBehaviorPresentation` with `narrative`, `details`, and `creativeState`.

- [ ] **Step 1: Write the failing selector tests**

Create `frontend/tests/workspacePresentation.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { buildAiBehaviorPresentation } from "../src/utils/workspacePresentation.ts";

test("AI Behavior exposes one narrative and never projects UiBrief next_question", () => {
  const gateQuestion = "你想改变这个帽子的形状或连接吗？";
  const view = buildAiBehaviorPresentation({
    uiBrief: {
      phenomenon: "正在理解你对帽子的调整。",
      next_question: gateQuestion,
      requires_response: true,
      question_id: "gate-1",
      status: "awaiting_gate",
      confidence: 0.9,
      details_ref: "revision-1",
      pending_decision_count: 1,
    },
    plannerTypedText: "fallback narrative",
    plannerNarration: "full model evidence",
    semanticDivergenceLoading: false,
    semanticDivergenceError: null,
    hasDivergenceContent: false,
  });

  assert.equal(view.narrative, "正在理解你对帽子的调整。");
  assert.equal(view.details, "full model evidence");
  assert.equal(view.creativeState, "locked");
  assert.doesNotMatch(JSON.stringify(view), new RegExp(gateQuestion));
});

test("creative state uses error, loading, ready, locked precedence", () => {
  const base = {
    uiBrief: null,
    plannerTypedText: "Waiting for the user's next move.",
    plannerNarration: "",
    semanticDivergenceLoading: false,
    semanticDivergenceError: null,
    hasDivergenceContent: false,
  };

  assert.equal(buildAiBehaviorPresentation({ ...base, semanticDivergenceError: "offline" }).creativeState, "error");
  assert.equal(buildAiBehaviorPresentation({ ...base, semanticDivergenceLoading: true }).creativeState, "loading");
  assert.equal(buildAiBehaviorPresentation({ ...base, hasDivergenceContent: true }).creativeState, "ready");
  assert.equal(buildAiBehaviorPresentation(base).creativeState, "locked");
});
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
node --experimental-strip-types --test frontend/tests/workspacePresentation.test.ts
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND`.

- [ ] **Step 3: Implement the pure selector**

Create `frontend/src/utils/workspacePresentation.ts`:

```ts
import type { UiBrief } from "../types";
import { normalizeUiBrief } from "./uiBrief";

export type CreativeControlState = "locked" | "loading" | "ready" | "error";

export type AiBehaviorPresentation = {
  narrative: string;
  details: string | null;
  creativeState: CreativeControlState;
};

export function buildAiBehaviorPresentation({
  uiBrief,
  plannerTypedText,
  plannerNarration,
  semanticDivergenceLoading,
  semanticDivergenceError,
  hasDivergenceContent,
}: {
  uiBrief: UiBrief | null;
  plannerTypedText: string;
  plannerNarration: string;
  semanticDivergenceLoading: boolean;
  semanticDivergenceError: string | null;
  hasDivergenceContent: boolean;
}): AiBehaviorPresentation {
  const brief = uiBrief ? normalizeUiBrief(uiBrief) : null;
  const creativeState: CreativeControlState = semanticDivergenceError
    ? "error"
    : semanticDivergenceLoading
      ? "loading"
      : hasDivergenceContent
        ? "ready"
        : "locked";

  return {
    narrative: brief?.phenomenon || plannerTypedText || "Waiting for the user's next move.",
    details: plannerNarration.trim() || null,
    creativeState,
  };
}
```

- [ ] **Step 4: Run selector and existing UiBrief tests**

Run:

```bash
node --experimental-strip-types --test \
  frontend/tests/workspacePresentation.test.ts \
  frontend/tests/uiBrief.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the presentation selector**

```bash
git add frontend/src/utils/workspacePresentation.ts frontend/tests/workspacePresentation.test.ts
git commit -m "refactor: centralize AI behavior presentation"
```

---

### Task 3: Collapse AI Behavior to one narrative and More Creative

**Files:**
- Create: `frontend/tests/workspaceBrowserContract.ts`
- Modify: `frontend/tests/panelVisualHierarchy.test.ts`
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx:1-359`
- Modify: `frontend/src/main.tsx:1-35,490-507,729-768`

**Interfaces:**
- Consumes: `AiBehaviorPresentation` from Task 2 plus existing divergence controls/actions.
- Produces: static `<aside className="ai-behavior-float float-panel">` with one `.ai-behavior-narrative`, one More Creative disclosure, and optional collapsed `.behavior-details`.

- [ ] **Step 1: Write a real-browser hierarchy contract and remove the obsolete source-text test**

Delete only the AI Behavior source-reading test from `frontend/tests/panelVisualHierarchy.test.ts`; keep the Studio Menu test unchanged.

Create `frontend/tests/workspaceBrowserContract.ts`:

```ts
export type WorkspaceContractResult = {
  ok: boolean;
  errors: string[];
  gateQuestionCount: number;
  narrativeCount: number;
};

function visible(element: Element): boolean {
  const style = window.getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
}

export function inspectWorkspaceHierarchy(root: Document = document): WorkspaceContractResult {
  const errors: string[] = [];
  const behavior = root.querySelector('.ai-behavior-float[aria-label="AI Behavior"]');
  if (!(behavior instanceof HTMLElement) || !visible(behavior)) {
    errors.push("AI Behavior is missing or hidden");
  }

  const narrativeCount = root.querySelectorAll(".ai-behavior-float .ai-behavior-narrative").length;
  if (narrativeCount !== 1) errors.push(`expected one AI narrative, found ${narrativeCount}`);

  const forbiddenCount = root.querySelectorAll(
    ".ai-behavior-float .four-stage-mini, .ai-behavior-float .four-stage-gate, .ai-behavior-float .ai-next-action-card",
  ).length;
  if (forbiddenCount) errors.push(`found ${forbiddenCount} duplicate status or Gate regions`);

  const gateQuestions = Array.from(
    root.querySelectorAll('.planner-clarification-overlay[aria-label="Intent Gate questions"] .planner-bubble > span'),
  ).filter(visible);
  const gateQuestionCount = gateQuestions.length;
  if (gateQuestionCount > 1) errors.push(`expected at most one visible Gate question, found ${gateQuestionCount}`);

  const creative = root.querySelector(".ai-behavior-float .creative-controls-disclosure");
  if (!(creative instanceof HTMLDetailsElement)) errors.push("More Creative disclosure is missing");

  return { ok: errors.length === 0, errors, gateQuestionCount, narrativeCount };
}
```

- [ ] **Step 2: Import the contract in the current Vite page and verify RED**

With the existing local frontend open at `http://127.0.0.1:5173`, evaluate:

```js
const contract = await import(`/tests/workspaceBrowserContract.ts?red=${Date.now()}`);
contract.inspectWorkspaceHierarchy(document);
```

Expected: `ok === false`; errors include the missing single narrative and duplicate status/Gate regions.

- [ ] **Step 3: Narrow AIBehaviorPanel props and static shell**

In `AIBehaviorPanel.tsx`:

- Remove `fourStageStageLabel`, `FourStageUiState`, `UiBrief`, `normalizeUiBrief`, `fourStage`, `pendingRevisionCount`, `uiBrief`, `plannerTypedText`, and `plannerNarration`.
- Import `AiBehaviorPresentation` from `../../utils/workspacePresentation`.
- Add `presentation: AiBehaviorPresentation` to props.
- Replace `scopeReady` with `presentation.creativeState !== "locked"`.
- Replace `<ResizableShell ...>` with:

```tsx
<aside className={`ai-behavior-float float-panel${mobileOpen ? " is-mobile-open" : ""}`} aria-label="AI Behavior">
```

Keep the existing header as the first child. Insert `<div className="ai-behavior-panel-body">` immediately after the header and close that div immediately before `</aside>`, so the narrative, project notice, More Creative disclosure, and model evidence share one deliberate scroll owner.

- Replace the stage, Gate, and two-card insight stack with:

```tsx
<p className="ai-behavior-narrative" aria-live="polite">
  {presentation.narrative}
</p>
```

- Keep the existing project notice, More Creative parameters, keywords, Generate action, and errors.
- Render details after More Creative so the default hierarchy follows the approved draft:

```tsx
{presentation.details ? (
  <details className="behavior-details">
    <summary>Model evidence</summary>
    <p>{presentation.details}</p>
  </details>
) : null}
```

- Close the static shell with `</aside>`.

- [ ] **Step 4: Build the presentation once in main.tsx**

Import `buildAiBehaviorPresentation` and compute it before `return`:

```ts
const aiBehaviorPresentation = buildAiBehaviorPresentation({
  uiBrief,
  plannerTypedText,
  plannerNarration,
  semanticDivergenceLoading,
  semanticDivergenceError,
  hasDivergenceContent: Boolean(semanticDivergence || divergenceKeywords.length),
});
```

Pass `presentation={aiBehaviorPresentation}` and remove the deleted AI Behavior props. Keep divergence inputs/actions unchanged.

- [ ] **Step 5: Re-run the real hierarchy contract, Gate unit tests, and build**

Evaluate in the same Vite page:

```js
const contract = await import(`/tests/workspaceBrowserContract.ts?green=${Date.now()}`);
contract.inspectWorkspaceHierarchy(document);
```

Expected: `ok === true`.

Then run:

```bash
node --experimental-strip-types --test \
  frontend/tests/gateContract.test.ts \
  frontend/tests/workspacePresentation.test.ts
npm --prefix frontend run build
```

Expected: PASS; the build emits `frontend/dist` without duplicate-prop or type errors.

- [ ] **Step 6: Commit the information hierarchy refactor**

```bash
git add \
  frontend/src/components/panels/AIBehaviorPanel.tsx \
  frontend/src/main.tsx \
  frontend/tests/workspaceBrowserContract.ts \
  frontend/tests/panelVisualHierarchy.test.ts
git commit -m "refactor: simplify AI behavior hierarchy"
```

---

### Task 4: Implement the two-state Figure 4 workspace layout

**Files:**
- Create: `frontend/src/workspaceLayout.css`
- Modify: `frontend/tests/workspaceBrowserContract.ts`
- Modify: `frontend/src/components/panels/SolutionSpaceRail.tsx:1-150`
- Modify: `frontend/src/main.tsx:508-509,687-730`
- Modify: `frontend/src/styles.css:3196-3317,4275-4292,4301-4339`

**Interfaces:**
- Consumes: existing `liveSolutionSpaceVisible` boolean.
- Produces: root class `has-solution-space`, a static `.solution-space-rail`, and CSS variables used by Active Editor, AI Behavior, Perception, Composer, and rail layout.

- [ ] **Step 1: Extend the real-browser contract with viewport geometry**

Append to `frontend/tests/workspaceBrowserContract.ts`:

```ts
type Rectangle = { top: number; right: number; bottom: number; left: number; width: number; height: number };

export type WorkspaceLayoutResult = {
  ok: boolean;
  errors: string[];
  hasSolutionSpace: boolean;
  rects: Record<string, Rectangle | null>;
};

function rectangle(element: Element | null): Rectangle | null {
  if (!element || !visible(element)) return null;
  const value = element.getBoundingClientRect();
  return {
    top: value.top,
    right: value.right,
    bottom: value.bottom,
    left: value.left,
    width: value.width,
    height: value.height,
  };
}

export function inspectWorkspaceLayout(root: Document = document): WorkspaceLayoutResult {
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const rects = {
    perception: rectangle(root.querySelector(".perception-float")),
    solution: rectangle(root.querySelector(".solution-space-rail")),
    behavior: rectangle(root.querySelector(".ai-behavior-float")),
    composer: rectangle(root.querySelector(".canvas-composer-shell")),
  };
  const errors: string[] = [];
  for (const [name, rect] of Object.entries(rects)) {
    if (!rect && name !== "solution") errors.push(`${name} is missing`);
    if (rect && (rect.left < 0 || rect.top < 0 || rect.right > viewport.width || rect.bottom > viewport.height)) {
      errors.push(`${name} leaves the viewport`);
    }
  }
  if (root.documentElement.scrollWidth !== root.documentElement.clientWidth) errors.push("horizontal page overflow");
  if (root.documentElement.scrollHeight !== root.documentElement.clientHeight) errors.push("vertical page overflow");
  if (rects.solution && rects.behavior && rects.behavior.top < rects.solution.bottom + 15) {
    errors.push("AI Behavior does not move below Solution Space");
  }
  return {
    ok: errors.length === 0,
    errors,
    hasSolutionSpace: Boolean(rects.solution),
    rects,
  };
}
```

- [ ] **Step 2: Run the geometry contract on the current page and verify RED**

At viewport `1280×720`, evaluate:

```js
const contract = await import(`/tests/workspaceBrowserContract.ts?layoutRed=${Date.now()}`);
contract.inspectWorkspaceLayout(document);
```

Expected: `ok === false`; the current page reports Composer/panel overflow or AI Behavior overlapping the Solution Space vertical region.

- [ ] **Step 3: Make Solution Space a static semantic rail**

In `SolutionSpaceRail.tsx`, remove the `ResizableShell` import and replace its wrapper with:

```tsx
<section
  className={`solution-space-rail${compactLoading ? " is-loading" : ""}`}
  aria-label="Solution Space"
>
```

Close with `</section>`. Keep loading, cards, horizontal scrolling, collapse, selection, and drag/drop behavior unchanged.

- [ ] **Step 4: Mark the root layout state and import the contract last**

In `main.tsx`:

```ts
import "./styles.css";
import "./workspaceLayout.css";
```

Update the main shell:

```tsx
<main className={`studio-shell${studioDrawerOpen ? " menu-open" : ""}${liveSolutionSpaceVisible ? " has-solution-space" : ""}`}>
```

This class must describe what is actually rendered, so use `liveSolutionSpaceVisible`, not candidate count or generation status independently.

- [ ] **Step 5: Add the single spatial contract stylesheet**

Create `frontend/src/workspaceLayout.css` with this base structure and fill the named component sections exactly once:

```css
.studio-shell {
  --workspace-edge: clamp(12px, 1.4vw, 22px);
  --workspace-gap: 16px;
  --perception-width: clamp(280px, 24vw, 340px);
  --solution-space-left: clamp(360px, 34vw, 440px);
  --solution-space-height: clamp(152px, 22vh, 176px);
  --ai-behavior-width: clamp(292px, 22vw, 340px);
  --ai-behavior-top: clamp(148px, 22vh, 190px);
  --composer-reserve: 132px;
  --workspace-safe-top: 64px;
  --workspace-safe-right: calc(var(--ai-behavior-width) + var(--workspace-edge) + var(--workspace-gap));
  --workspace-safe-bottom: var(--composer-reserve);
  width: 100vw;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

.studio-shell.has-solution-space {
  --ai-behavior-top: calc(var(--workspace-edge) + var(--solution-space-height) + var(--workspace-gap));
  --workspace-safe-top: calc(var(--workspace-edge) + var(--solution-space-height));
}

.workspace,
.canvas-column,
.workspace-chrome {
  min-width: 0;
  min-height: 0;
}

.perception-float {
  top: 68px;
  left: var(--workspace-edge);
  width: var(--perception-width);
  max-width: var(--perception-width);
  padding: 0;
  overflow: hidden;
}

.perception-float .float-panel-label {
  min-height: 36px;
  margin: 0;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(57, 70, 85, 0.08);
}

.perception-float .observe-current {
  padding: 12px 14px 14px;
}

.perception-float .observe-sentence {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font-size: 13px;
  line-height: 1.4;
}

.solution-space-rail {
  position: fixed;
  top: var(--workspace-edge);
  left: var(--solution-space-left);
  right: calc(var(--ai-behavior-width) + var(--workspace-edge) + var(--workspace-gap));
  z-index: 24;
  height: var(--solution-space-height);
  min-width: 0;
  padding: 10px 12px;
  overflow: hidden;
}

.solution-space-rail .solution-space-scroll {
  min-width: 0;
  height: calc(100% - 30px);
  overflow-x: auto;
  overflow-y: hidden;
}

.ai-behavior-float {
  position: fixed;
  top: var(--ai-behavior-top);
  right: var(--workspace-edge);
  z-index: 24;
  width: var(--ai-behavior-width);
  height: auto;
  max-height: calc(100dvh - var(--ai-behavior-top) - var(--workspace-edge) - 104px);
  transition: top 180ms ease, max-height 180ms ease;
}

.ai-behavior-float .ai-behavior-panel-body {
  max-height: inherit;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.canvas-composer-shell {
  bottom: 24px;
  width: min(720px, calc(100vw - 48px));
  max-height: calc(100dvh - 48px);
}

@media (max-width: 1279px) {
  .studio-shell {
    --workspace-gap: 12px;
    --perception-width: clamp(250px, 23vw, 300px);
    --solution-space-left: clamp(320px, 31vw, 390px);
    --ai-behavior-width: clamp(280px, 24vw, 312px);
  }
}

@media (max-width: 899px) {
  .studio-shell,
  .studio-shell.has-solution-space {
    --workspace-safe-top: 64px;
    --workspace-safe-right: 0px;
    --workspace-safe-bottom: 148px;
  }

  .perception-float {
    width: min(240px, calc(100vw - 184px));
    max-width: min(240px, calc(100vw - 184px));
  }

  .solution-space-rail {
    top: 64px;
    left: 12px;
    right: 12px;
    height: 148px;
  }

  .ai-behavior-float {
    top: 72px;
    right: 12px;
    width: min(330px, calc(100vw - 24px));
    max-height: min(62vh, 560px);
  }

  .ai-behavior-float:not(.is-mobile-open) {
    width: 164px;
    max-height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ai-behavior-float {
    transition: none;
  }
}
```

Add these component visual rules in the same file after the base positioning rules:

```css
.ai-behavior-float.float-panel {
  padding: 0;
  overflow: hidden;
  border-color: rgba(167, 178, 191, 0.62);
  background: rgba(247, 248, 249, 0.94);
  box-shadow: 0 12px 32px rgba(42, 52, 66, 0.1);
}

.ai-behavior-float .float-panel-label {
  position: relative;
  min-height: 44px;
  margin: 0;
  padding: 11px 14px;
  border-bottom: 1px solid rgba(57, 70, 85, 0.08);
  cursor: default;
  touch-action: auto;
}

.ai-behavior-float .float-panel-label::after {
  position: absolute;
  inset: 0 14px auto;
  height: 2px;
  border-radius: 0 0 999px 999px;
  background: linear-gradient(90deg, #2ad4e8, #9b7bff 50%, #ff4f9a);
  content: "";
}

.ai-behavior-panel-body {
  max-height: calc(100dvh - var(--ai-behavior-top) - var(--workspace-edge) - 44px);
  padding: 12px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
}

.ai-behavior-narrative {
  display: -webkit-box;
  margin: 0 0 12px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  padding: 14px;
  border: 1px solid rgba(43, 57, 70, 0.08);
  border-radius: 15px;
  background: rgba(255, 255, 255, 0.9);
  color: #26323b;
  font-size: 13px;
  font-weight: 650;
  line-height: 1.48;
}

.ai-behavior-float .creative-controls-disclosure {
  margin: 0;
}

.ai-behavior-float .behavior-details {
  margin: 10px 2px 0;
}

@media (max-width: 899px) {
  .ai-behavior-float:not(.is-mobile-open) .ai-behavior-panel-body,
  .ai-behavior-float:not(.is-mobile-open) .status-dots {
    display: none;
  }

  .ai-behavior-float .mobile-panel-toggle {
    display: inline-flex;
    min-height: 28px;
    padding: 4px 9px;
  }
}
```

Reuse only the existing CSS variables and values from `.superdesign/design-system.md`; do not add a second layout section.

- [ ] **Step 6: Remove obsolete fixed-dock declarations from styles.css**

Delete the fixed/full-height AI Behavior blocks beginning at these comments/selectors:

- `/* Interaction orchestration workspace contract... */` only the `.ai-behavior-float` and its descendant rules; keep Active Editor rules.
- `/* Final fixed-dock overrides keep inline ResizableShell dimensions... */` at both duplicate locations.
- Mobile `.ai-behavior-float` width/height declarations that contain `!important`.

Do not delete shared More Creative token, slider, keyword, focus, or reduced-motion styles.

- [ ] **Step 7: Re-run hierarchy and geometry contracts, then build checks**

At `1280×720`, evaluate:

```js
const contract = await import(`/tests/workspaceBrowserContract.ts?layoutGreen=${Date.now()}`);
({
  hierarchy: contract.inspectWorkspaceHierarchy(document),
  layout: contract.inspectWorkspaceLayout(document),
});
```

Expected: both results have `ok === true`.

Then run:

```bash
node --experimental-strip-types --test \
  frontend/tests/accessibility.test.ts \
  frontend/tests/viewportPresentation.test.ts \
  frontend/tests/viewportResolution.test.ts
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 8: Commit the Figure 4 spatial contract**

```bash
git add \
  frontend/src/components/panels/SolutionSpaceRail.tsx \
  frontend/src/main.tsx \
  frontend/src/styles.css \
  frontend/src/workspaceLayout.css \
  frontend/tests/workspaceBrowserContract.ts
git commit -m "feat: converge workspace on Figure 4 layout"
```

---

### Task 5: Full regression and real-browser acceptance

**Files:**
- Modify only if a regression is proven: files already listed in Tasks 1-4.
- Produce local evidence: browser screenshots at `1280×720`, `1440×900`, and `1920×1080`; do not commit temporary screenshots.

**Interfaces:**
- Consumes: the completed backend projection, frontend presentation selector, compact panels, and two-state layout.
- Produces: passing full test/build results and measured browser evidence.

- [ ] **Step 1: Run the complete automated suites**

Run:

```bash
PYTHONPATH=backend /opt/anaconda3/bin/python -m pytest backend/tests/test_realtime_observation.py -q
node --experimental-strip-types --test frontend/tests/*.test.ts
npm --prefix frontend run build
```

Expected: all commands exit 0.

- [ ] **Step 2: Open the local frontend and verify both layout states**

Use `http://127.0.0.1:5173` with the existing local backend at `http://127.0.0.1:8000`.

For each desktop viewport (`1280×720`, `1440×900`, `1920×1080`), inspect these values in the browser:

```js
({
  root: {
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientHeight: document.documentElement.clientHeight,
    scrollHeight: document.documentElement.scrollHeight,
  },
  perception: document.querySelector('.perception-float')?.getBoundingClientRect().toJSON(),
  solution: document.querySelector('.solution-space-rail')?.getBoundingClientRect().toJSON(),
  behavior: document.querySelector('.ai-behavior-float')?.getBoundingClientRect().toJSON(),
  composer: document.querySelector('.canvas-composer-shell')?.getBoundingClientRect().toJSON(),
})
```

Acceptance:

- `scrollWidth === clientWidth` and `scrollHeight === clientHeight`.
- Every returned rectangle is within the viewport.
- Without Solution Space, AI Behavior is on the right side and below the top brand line.
- With Solution Space, `behavior.top >= solution.bottom + 15`.
- Composer bottom is at most `clientHeight` and its full height is visible.
- The visible Gate question count is exactly one.

- [ ] **Step 3: Capture screenshots and compare to the selected draft**

Capture both no-Solution-Space and with-Solution-Space states at `1280×720`. Compare spatial hierarchy against:

```text
https://p.superdesign.dev/draft/30c41c55-e05f-4332-9f86-7ad7f3430464
```

The comparison is accepted when panel proportions, negative space, central-model priority, and bottom Composer placement agree even though real model/candidate content differs from the design stand-ins.

- [ ] **Step 4: Run a forbidden-pattern scan**

Run:

```bash
rg -n "four-stage-mini|four-stage-gate|ai-next-action-card|brief\?\.next_question" \
  frontend/src/components/panels/AIBehaviorPanel.tsx
rg -n "transition:\s*all|!important" frontend/src/workspaceLayout.css
```

Expected: both commands return no matches.

- [ ] **Step 5: Commit only proven acceptance fixes**

If browser verification required a code correction, stage only the corrected Task 1-4 files and commit:

```bash
git commit -m "fix: complete Figure 4 viewport acceptance"
```

If no corrections were required, do not create an empty commit.

---

## Self-Review Record

- Spec coverage: Gate ownership, UiBrief compatibility, one narrative, More Creative preservation, two layout states, 1280×720 fit, responsive behavior, accessibility, no new dependencies, and browser evidence each map to Tasks 1-5.
- Completeness scan: the plan contains no red-flag omissions, deferred implementation, or unspecified test step.
- Type consistency: Task 2 defines `AiBehaviorPresentation` and `buildAiBehaviorPresentation`; Task 3 imports and consumes those exact names.
- State consistency: `liveSolutionSpaceVisible` controls both rail rendering and the `has-solution-space` layout class.
- Worktree safety: every commit command stages an explicit file list and does not include unrelated existing changes.
