# Transparent Centered Active Canvas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the expanded active canvas card and center the loaded 3D model on the browser viewport without moving FlowStudio's floating panels.

**Architecture:** Keep the existing transparent Three.js renderer and version graph. Extend the real-browser layout contract, replace the legacy 520px centering assumption with the expanded editor dimensions, and make only the expanded active frame transparent; history thumbnails remain unchanged.

**Tech Stack:** React 19, TypeScript, Three.js, CSS custom properties, Node test runner, Vite.

## Global Constraints

- The active editor horizontal center must be within 2px of `50vw`.
- The active frame and node must have transparent backgrounds and no box shadow.
- The model must remain above the Composer's reserved area.
- Perception, AI Behavior, Composer, Solution Space, and navigation keep their current ownership and anchoring.
- Do not change backend APIs, model parsing, camera fitting, lighting, selection, sculpting, or generation behavior.

---

### Task 1: Transparent, viewport-centered active editor

**Files:**
- Modify: `frontend/tests/workspaceBrowserContract.ts:64-102`
- Modify: `frontend/src/state/studioStore.ts:125-134`
- Modify: `frontend/src/styles.css:3153-3166`
- Verify: `frontend/src/workspaceLayout.css`

**Interfaces:**
- Consumes: the active node's stable layout anchor at `x = 640`, the viewport width/height, and the existing `--workspace-safe-top` / `--workspace-safe-bottom` CSS contract.
- Produces: `centeredActiveCanvasPan(): { x: number; y: number }`, an active editor centered on `50vw`, and a browser contract that rejects opaque or off-center active frames.

- [ ] **Step 1: Extend the browser contract before changing production code**

Add `activeEditor` to `inspectWorkspaceLayout` and inspect the expanded frame style:

```ts
const activeEditorElement = root.querySelector(".version-node.active");
const activeFrameElement = root.querySelector(".version-node.active .version-node-frame");
const rects = {
  canvas: rectangle(root.querySelector(".version-canvas-shell")),
  activeEditor: rectangle(activeEditorElement),
  // existing entries remain unchanged
};

if (rects.activeEditor) {
  const centerX = (rects.activeEditor.left + rects.activeEditor.right) / 2;
  if (Math.abs(centerX - viewport.width / 2) > 2) {
    errors.push("active editor is not centered on the viewport");
  }
}
if (activeFrameElement instanceof HTMLElement) {
  const style = window.getComputedStyle(activeFrameElement);
  if (style.backgroundColor !== "rgba(0, 0, 0, 0)") errors.push("active editor frame is opaque");
  if (style.boxShadow !== "none") errors.push("active editor frame still has a shadow");
}
```

- [ ] **Step 2: Run the real 1280×720 contract and capture RED**

Load `Christmas · Snowman` in `http://127.0.0.1:5184/` and inspect the real DOM. Expected failure before implementation:

```text
active editor is not centered on the viewport
active editor frame is opaque
active editor frame still has a shadow
```

- [ ] **Step 3: Replace the fixed 520px pan calculation**

Update `centeredActiveCanvasPan` so its target width matches the expanded editor and its vertical placement uses the unobstructed editing band:

```ts
function centeredActiveCanvasPan() {
  const width = typeof window === "undefined" ? 1440 : window.innerWidth;
  const height = typeof window === "undefined" ? 900 : window.innerHeight;
  const editorWidth = Math.min(720, Math.max(320, width - 48));
  const safeTop = 64;
  const safeBottom = width < 900 ? 148 : 118;
  const editorHeight = Math.min(620, Math.max(320, height - safeTop - safeBottom - 24));
  const availableHeight = height - safeTop - safeBottom;
  return {
    x: Math.round((width - editorWidth) / 2 - 640),
    y: Math.max(0, Math.round((availableHeight - editorHeight) / 2) - 8),
  };
}
```

The CSS expanded editor width must use the same `720px` cap:

```css
.version-node.active {
  width: min(720px, calc(100vw - 48px)) !important;
  max-width: calc(100vw - 48px);
}
```

- [ ] **Step 4: Remove only the expanded active frame treatment**

Keep thumbnail cards unchanged and override the expanded frame:

```css
.version-node.active,
.version-node.active .version-node-frame {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}

.version-node.active .version-node-frame {
  border-radius: 0;
}
```

- [ ] **Step 5: Run the browser contract and capture GREEN**

At 1280×720 with Snowman loaded, verify:

```text
active editor center = 640 ±2px
active frame background = rgba(0, 0, 0, 0)
active frame shadow = none
version canvas bottom = 720
document = 1280×720
browser console errors = 0
```

Take a screenshot confirming the dotted workspace remains visible behind the model and the model is not hidden behind the Composer.

- [ ] **Step 6: Run the complete frontend verification**

Run:

```bash
node --experimental-strip-types --test frontend/tests/*.test.ts
./frontend/node_modules/.bin/tsc -p frontend/tsconfig.json --noEmit
cd frontend && npm run build
```

Expected: 47 tests pass, TypeScript exits 0, Vite exits 0. Existing ONNX `eval` and chunk-size warnings are non-blocking.

- [ ] **Step 7: Commit**

```bash
git add frontend/tests/workspaceBrowserContract.ts frontend/src/state/studioStore.ts frontend/src/styles.css
git commit -m "fix: center model on transparent workspace"
```
