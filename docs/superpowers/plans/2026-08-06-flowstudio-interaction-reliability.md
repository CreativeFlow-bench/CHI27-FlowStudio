# FlowStudio Interaction Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Gate scope, feedback latency, white-model loading, panel interaction, accessibility, and initial bundle behavior satisfy the approved August 5 product definition.

**Architecture:** Keep the existing revision and observation APIs. Add deterministic preservation-aware scope compression in the backend; add optimistic revision placeholders and lazy segmentation at the frontend boundary; keep semantic discovery asynchronous and improve the existing reusable panel primitive.

**Tech Stack:** FastAPI/Pydantic/Pytest, React 19/TypeScript/Vite, Three.js, ONNX Runtime loaded dynamically.

## Global Constraints

- Do not commit, push, or deploy GitHub.
- Keep multiple simultaneous Gate bubbles.
- Observation continues while revisions are planned/generated.
- Generate 6–8 solutions by appending batches rather than replacing prior accepted results.

---

### Task 1: Preservation-aware Gate compression

**Files:**
- Modify: `backend/tests/test_realtime_observation.py`
- Modify: `backend/app/services/encoding/four_stage_encoding.py`
- Modify: `backend/app/services/intent/realtime_observation.py`

- [ ] Add failing tests for 帽子 + 保持整体身份 and 围巾 + 不改变轮廓.
- [ ] Run focused tests and observe whole-scope failures.
- [ ] Add 围巾 to known parts and ignore preservation-clause whole markers when a positive part target exists.
- [ ] Run focused and complete observation tests.

### Task 2: Immediate immutable revision feedback

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/overlays/PlannerClarificationOverlay.tsx`

- [ ] Add a source-level verifier for immediate placeholder insertion and reconciliation.
- [ ] Observe verifier failure.
- [ ] Insert a local planning revision at click time and reconcile/remove it on success/failure.
- [ ] Verify rapid Sends produce distinct stable placeholders.

### Task 3: Non-blocking model and lazy segmentation

**Files:**
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/utils/segmenter.ts`

- [ ] Add source/build assertions that ONNX is not statically imported and discovery is fire-and-forget.
- [ ] Observe bundle/source assertion failure.
- [ ] Dynamically import the segmenter on first segmentation request.
- [ ] Preserve the existing asynchronous discovery path and remove loading-state coupling.

### Task 4: Accessible floating interactions

**Files:**
- Modify: `frontend/src/components/ui/primitives.tsx`
- Modify: `frontend/src/components/panels/IntentComposer.tsx`
- Modify: `frontend/src/components/overlays/PlannerClarificationOverlay.tsx`
- Modify: `frontend/src/components/StudioCanvas.tsx`
- Modify: `frontend/src/components/panels/SolutionSpaceRail.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Add source assertions for labels, focus-visible styling, and keyboard resize.
- [ ] Observe assertion failure.
- [ ] Add accessible names, keyboard resize semantics, explicit image dimensions/aspect ratio, and visible focus.
- [ ] Run TypeScript/Vite build.

### Task 5: Deploy and acceptance-test

**Files:**
- Modify on GPU: `/root/flowstudio_app` synchronized files only.

- [ ] Run backend test suite and frontend production build locally.
- [ ] Sync changed files without Git operations.
- [ ] Restart GPU backend/frontend on canonical ports 18000/5173.
- [ ] Verify health, WebSocket, white-model usability, two immediate Gates, correct 帽子/围巾 questions, panel scrolling/dragging, and console logs.

