# Perception Current Action and History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox checkpoints so each behavior is verified before integration.

**Goal:** Replace the Perception panel's raw system-state output with one privacy-safe current-action sentence and an expandable, user-operation-only history.

**Architecture:** Add a pure presentation layer that converts structured local perception, confirmed realtime observations, and committed behavior sessions into a small display vocabulary. The panel consumes only this normalized result, so raw prompts, evidence strings, backend intent labels, and internal pipeline events never enter the visible Perception UI. Existing recognition and experiment recording remain unchanged.

**Tech Stack:** React, TypeScript, Vite, Node test runner, CSS.

## Global Constraints

- Preserve the existing backend recognition, websocket, and experiment-recording paths.
- Never display `LivePerception.evidence` or arbitrary model/backend summary text.
- Render typed input only as `User is describing an intended change.`
- Show only human operations in history; exclude SYS, INIT, AI, encoding, retrieval, and model reasoning events.
- Keep the current FlowStudio visual language and existing panel positioning.
- Do not stage or overwrite unrelated working-tree changes.

---

## Task 1: Build the privacy-safe Perception presenter

**Files:**

- Create: `frontend/src/utils/perceptionDisplay.ts`
- Create: `frontend/tests/perceptionDisplay.test.ts`

- [x] Write failing tests for the approved sentence vocabulary, including add, draw, sculpt, reshape, inspect, survey, describe-intent, review, and idle states.
- [x] Write a failing privacy test proving raw typed text and arbitrary backend summaries never appear in current output or history.
- [x] Write failing selection tests for local freshness, confirmed observations, recent committed behavior, stale-to-review transition, and idle fallback.
- [x] Write failing history tests for newest-first order, 12-item default limit, 50-item hard cap, and 1.5-second aggregation of orbit/zoom/hover events.
- [x] Run `node --experimental-strip-types --test tests/perceptionDisplay.test.ts` from `frontend/` and confirm the expected failures.
- [x] Implement normalized operation mapping, trusted target extraction, sentence generation, current-candidate selection, and history aggregation.
- [x] Re-run the focused test and confirm it passes.

## Task 2: Integrate the presenter into the Perception panel

**Files:**

- Modify: `frontend/src/components/panels/PerceptionPanel.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/accessibility.test.ts`

- [x] Add failing UI-contract assertions for the expandable operation-history region, accessible toggle state, and removal of the legacy mixed system log.
- [x] Pass `behaviorSessions` into `PerceptionPanel`; remove legacy session/action-atom/hover presentation dependencies from the panel contract.
- [x] Compute the normalized current sentence and history through the new presenter.
- [x] Add an 800 ms minimum display duration for non-geometry status changes while allowing explicit geometry actions to replace immediately.
- [x] Add a small clock tick so an inactive current action transitions to review/idle after eight seconds.
- [x] Render the header status dots, one prominent current-action sentence, and a dropdown containing only timestamped operation rows.
- [x] Restyle the header/body separation, typography, chevron, and compact history rows while retaining existing palette, radius, and panel position.
- [x] Run the focused accessibility and presenter tests and confirm they pass.

## Task 3: Regression and live-page verification

**Files:**

- Verify only; modify implementation files only if a regression is found.

- [x] Run all frontend interaction tests with `node --experimental-strip-types --test tests/*.test.ts`.
- [x] Run the frontend production build with `npm run build`.
- [x] Open `http://127.0.0.1:5173/` and verify collapsed and expanded Perception states at the target viewport.
- [x] Confirm the panel never shows raw typed text, evidence, internal stage names, or model reasoning.
- [x] Confirm dropdown keyboard focus, `aria-expanded`, scroll behavior, and empty-history state.
- [x] Review the final diff and report any unrelated pre-existing changes separately.
