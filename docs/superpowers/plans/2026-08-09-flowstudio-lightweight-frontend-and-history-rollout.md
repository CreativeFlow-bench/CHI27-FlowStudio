# FlowStudio Lightweight Frontend and History Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the interrupted 47501 history-cleanup rollout, then apply only small frontend fixes that make the clean workspace responsive, keyboard-operable, and easier to understand.

**Architecture:** Keep the current React component structure, four-stage pipeline, version graph, and backend storage model. First close the incomplete deployment with backups and evidence; then make surgical changes in `ResizableShell`, the menu handle, the intent composer, Solution Space controls, and CSS. Do not split `useStudioStore`, replace the state layer, or add dependencies in this pass.

**Tech Stack:** React 19, TypeScript, Vite, Node test runner, FastAPI, SQLite, pytest, SSH deployment to `/root/flowstudio_app` on port 47501.

## Global Constraints

- No new frontend or backend dependencies.
- Do not change CreativeFlow generation, Hunyuan3D, OSS, four-stage, Gate, or version-graph semantics.
- Preserve `pipeline.py` and the structured transfer pipeline unchanged.
- Back up remote storage before clearing any history.
- Clear only persisted test/workspace history; preserve benchmark assets, model files, environment variables, and service configuration.
- Use targeted file sync because the local worktree contains unrelated changes.
- Treat a clean first-load page as the baseline before judging remaining overlay problems.

---

## Verified Baseline (2026-08-09)

- Local `frontend/tests/interactionReliability.test.ts`: 16/16 passing.
- Local source renders explicit `收起` and `展开 Solution Space · N` text.
- Remote `frontend/dist` hashes match local `frontend/dist`; the deployed bundle contains both strings.
- Remote frontend source is stale, so the next remote rebuild could regress the text unless source is synchronized.
- Remote backend `main.py` and `four_stage_store.py` hashes match local and contain `clear_four_stage_session=four_stage_store.clear_session` plus deletion of revisions, batches, and version-graph tables.
- Remote backend process started at 14:59, before those files were synchronized at 18:50; runtime has not loaded the fix.
- Remote persisted state is not clean: 208 sessions, 114 assets, 59 intent revisions, 28 solution batches, and 10 version nodes.
- Remote backend test file is stale and does not contain `test_reset_session_clears_realtime_and_four_stage_history`.

---

### Task 1: Close the Interrupted 47501 Rollout

**Files:**
- Sync: `frontend/src/components/panels/SolutionSpaceRail.tsx`
- Sync: `frontend/src/main.tsx`
- Sync: `frontend/src/styles.css`
- Sync: `frontend/tests/interactionReliability.test.ts`
- Sync: `frontend/dist/**`
- Sync: `backend/app/main.py`
- Sync: `backend/app/api/sessions.py`
- Sync: `backend/app/services/storage/four_stage_store.py`
- Sync: `backend/tests/test_realtime_observation.py`
- Preserve: `/root/flowstudio_app/.env`
- Back up: `/root/flowstudio_app/backend/storage/state/latest.json`
- Back up: `/root/flowstudio_app/backend/storage/four_stage.sqlite3`

**Interfaces:**
- Consumes: `POST /api/v1/sessions/{session_id}/reset`.
- Produces: a running backend where reset clears Studio state and four-stage state in one request.

- [ ] **Step 1: Re-run the local frontend regression test**

Run:

```bash
node --experimental-strip-types --test frontend/tests/interactionReliability.test.ts
```

Expected: `tests 16`, `pass 16`, `fail 0`.

- [ ] **Step 2: Build the exact frontend bundle to deploy**

Run:

```bash
cd frontend
npm run build
```

Expected: Vite exits 0 and `dist/index.html` references existing hashed JS and CSS assets.

- [ ] **Step 3: Create a recoverable remote backup**

Run on 47501:

```bash
cd /root/flowstudio_app
stamp=$(date +%Y%m%d_%H%M%S)
backup=/root/flowstudio_backups/history_cleanup_$stamp
mkdir -p "$backup"
cp -a backend/storage/state/latest.json "$backup/"
cp -a backend/storage/four_stage.sqlite3 "$backup/"
cp -a frontend/dist "$backup/frontend_dist"
printf '%s\n' "$backup"
```

Expected: one explicit backup directory containing both stores and the previous frontend.

- [ ] **Step 4: Synchronize only the listed runtime and test files**

Create a tarball containing only the files in this task, copy it to `/tmp`, and extract it under `/root/flowstudio_app`. Do not use a whole-worktree sync command.

Expected verification:

```bash
grep -n '<span>收起</span>' /root/flowstudio_app/frontend/src/components/panels/SolutionSpaceRail.tsx
grep -n 'clear_four_stage_session=four_stage_store.clear_session' /root/flowstudio_app/backend/app/main.py
grep -n 'test_reset_session_clears_realtime_and_four_stage_history' /root/flowstudio_app/backend/tests/test_realtime_observation.py
```

- [ ] **Step 5: Run the backend reset test in an isolated temporary copy**

Run on 47501:

```bash
tmp=$(mktemp -d /tmp/flowstudio-reset-test.XXXXXX)
mkdir -p "$tmp/backend/storage/state"
cp -a /root/flowstudio_app/backend/app "$tmp/backend/"
cp -a /root/flowstudio_app/backend/tests "$tmp/backend/"
cd "$tmp"
PYTHONPATH="$tmp/backend" /root/flowstudio_app/.venv/bin/python -m pytest \
  backend/tests/test_realtime_observation.py::test_reset_session_clears_realtime_and_four_stage_history -q
```

Expected: `1 passed`; production storage paths are not touched because `app/main.py` resolves storage inside the temporary copy.

- [ ] **Step 6: Restart only the backend process**

Stop the listener on port 18000 and restart the same `uvicorn app.main:app` command from `/root/flowstudio_app/backend`. Do not restart Qwen-Image, the planner, or the worker.

Expected checks:

```bash
curl -fsS http://127.0.0.1:18000/health
ps -eo pid,lstart,cmd | grep 'uvicorn app.main:app' | grep -v grep
```

The backend start time must be later than the synchronized file timestamps.

- [ ] **Step 7: Clear persisted test/workspace history through the fixed reset endpoint**

Read session IDs from the backed-up/current `latest.json`, then call the reset endpoint once per session. Preserve the SessionRecord objects so existing browser local-storage IDs reopen as blank workspaces.

Expected after cleanup:

- Studio assets, jobs, candidates, artifacts, action atoms, and intent drafts: `0`.
- Four-stage runs, behaviors, revisions, solution batches, version nodes/states, and generation jobs: `0`.
- Benchmark storage and white models remain present.

- [ ] **Step 8: Reload the user-facing page and perform a clean-state smoke test**

Verify:

- no previous snowman candidate cards or version branches;
- `Flow Studio`, Source, Runtime, Perception, AI Behavior, and intent composer render;
- selecting a white model creates only Version 1;
- Solution Space remains absent until a new generation batch exists;
- console contains no errors.

---

### Task 2: Add Responsive Bounds Without Rebuilding the Layout

**Files:**
- Modify: `frontend/src/components/ui/primitives.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Consumes: existing `ResizableShell` props.
- Produces: the same component API with viewport-clamped size and position.

- [ ] **Step 1: Add a failing source-level regression test**

Require `ResizableShell` to listen for `resize`, clamp width to `window.innerWidth - 40`, and permit the effective mobile width to fall below the desktop `minWidth` when the viewport is narrower.

- [ ] **Step 2: Verify the new test fails**

Run the 16-item interaction file plus the new test and confirm the missing resize guard is the failure.

- [ ] **Step 3: Add one viewport-clamping effect**

In `ResizableShell`, import `useEffect` and add a single resize handler that:

```ts
const availableWidth = Math.max(280, window.innerWidth - 40);
const availableHeight = Math.max(220, window.innerHeight - 40);
```

Clamp `size.w`, `size.h`, and any saved `position` into those available bounds. Register and remove one `window.resize` listener.

- [ ] **Step 4: Add CSS safety limits**

Apply `max-width: calc(100vw - 40px)` to Solution Space and movable panels. At `max-width: 900px`, ensure the mobile Solution Space rule uses `max-width` as well as `width`, so an inline width cannot escape the viewport.

- [ ] **Step 5: Run tests and inspect 1280, 1024, 768, and 390px widths**

Expected: every panel stays inside the viewport; Solution Space never reports a negative `x`; Perception never collapses to 50px.

---

### Task 3: Fix the Small Keyboard and Copy Problems

**Files:**
- Modify: `frontend/src/components/menu/StudioMenu.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/panels/IntentComposer.tsx`
- Modify: `frontend/src/components/panels/SolutionSpaceRail.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/accessibility.test.ts`
- Test: `frontend/tests/interactionReliability.test.ts`

**Interfaces:**
- Consumes: existing menu-open setter, `onSend`, and `onDropCandidate` callbacks.
- Produces: keyboard-equivalent actions without changing backend requests.

- [ ] **Step 1: Add failing tests for keyboard and hidden-menu behavior**

Assert that the menu handle has an Enter/Space path, the closed menu is `inert`, and the intent input has a submit-on-Enter path plus `name` and `autoComplete`.

- [ ] **Step 2: Add a keyboard-only menu toggle**

Keep pointer dragging unchanged. Add a small `onMenuToggle` prop and call it only for Enter or Space in `onKeyDown`; do not add a generic click handler that would double-toggle after pointer-up.

- [ ] **Step 3: Remove hidden menu controls from the focus order**

Set the closed `<aside>` to `inert` while retaining `aria-hidden`. Opening it removes both restrictions.

- [ ] **Step 4: Make the intent field behave like a prompt field**

Add `name="design-intent"`, `autoComplete="off"`, and Enter-to-send when the event is not composing and the existing send conditions allow submission. Change the placeholder to `Make this snowman cuter…`.

- [ ] **Step 5: Clarify and enlarge the Solution Space action**

Rename `拖入画布` to `添加到画布`; preserve real drag-and-drop on the card. Raise action button `min-height` from 22px to at least 34px without enlarging the card beyond the bounded rail.

- [ ] **Step 6: Run the complete frontend test set**

Run:

```bash
node --experimental-strip-types --test frontend/tests/*.test.ts
```

Expected: all tests pass with no skipped tests.

---

### Task 4: Final Clean-Page Acceptance

**Files:**
- Verify only; no new production files.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: acceptance evidence for the next frontend iteration.

- [ ] **Step 1: Build and targeted-sync the final frontend dist**

Back up the previous remote `dist`, deploy the new build, and verify remote/local hashes match.

- [ ] **Step 2: Test desktop and narrow-screen interaction**

At 1280×720 and 390×844 verify menu toggle, model selection, Solution Space expand/collapse, horizontal candidate scrolling, add-to-canvas, intent Enter submission, and focus visibility.

- [ ] **Step 3: Verify persistence boundaries**

Create one disposable session, one revision, one solution batch, and one version node; reset only that session; confirm all four histories are empty afterward and unrelated benchmark data remains.

- [ ] **Step 4: Record remaining non-lightweight work separately**

Do not expand this pass into a store rewrite. Record `useStudioStore` decomposition, high-frequency signal isolation, lazy Three.js loading, and a docked desktop layout as a later architecture phase.

---

## Self-Review

- The interrupted deployment, backend restart, recoverable cleanup, and final page reload are covered.
- The plan changes no CreativeFlow pipeline semantics and introduces no dependencies.
- The most visible dirty-history artifact is removed before judging layout.
- Remaining frontend changes are bounded to five existing UI files and two existing test files.
- Larger React performance work is explicitly deferred rather than mixed into this cleanup.
