import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("multi-intent bubbles reserve the Solution Space rail", async () => {
  const css = await read("../src/styles.css");
  assert.match(css, /\.multi-gate \.revision-slot-2\s*\{[^}]*top:\s*(?:2[8-9]|[3-9]\d)%/s);
});

test("intent bubbles cannot intercept visible Solution Space controls", async () => {
  const css = await read("../src/styles.css");
  assert.match(css, /\.solution-space-rail\s*\{[^}]*z-index:\s*2[4-9]/s);
  assert.match(css, /\.intent-bead-overlay\s*\{[^}]*z-index:\s*1[0-9]/s);
});

test("movable panel header stays reachable while panel content scrolls", async () => {
  const css = await read("../src/styles.css");
  assert.match(css, /\.resizable-shell-body\s*>\s*\.float-panel-label\s*\{[^}]*position:\s*sticky[^}]*top:\s*0/s);
});

test("movable panels can be repositioned from the keyboard", async () => {
  const source = await read("../src/components/ui/primitives.tsx");
  assert.match(source, /onMoveKeyDown/);
  assert.match(source, /tabIndex=\{movable \? 0 : undefined\}/);
  assert.match(source, /onKeyDown=\{onMoveKeyDown\}/);
});

test("small screens keep AI Behavior and Gate interactions available", async () => {
  const css = await read("../src/styles.css");
  const layout = await read("../src/workspaceLayout.css");
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  const mobile = css.slice(css.indexOf("@media (max-width: 900px)"));
  const mobileLayout = layout.slice(layout.indexOf("@media (max-width: 899px)"));
  assert.doesNotMatch(mobileLayout, /\.ai-behavior-float\s*\{[^}]*display:\s*none/s);
  assert.doesNotMatch(mobile, /\.intent-bead-overlay\s*\{[^}]*display:\s*none/s);
  assert.match(mobileLayout, /\.ai-behavior-float\s*\{[^}]*max-height:/s);
  assert.match(mobileLayout, /\.ai-behavior-float:not\(\.is-mobile-open\)/);
  assert.match(panel, /mobileOpen/);
  assert.match(panel, /aria-expanded=\{mobileOpen\}/);
  assert.match(panel, /mobile-panel-toggle/);
});

test("Gate-started divergence automatically reveals AI Behavior on small screens", async () => {
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  assert.match(
    panel,
    /useEffect\(\(\) => \{\s*if \(semanticDivergenceLoading\) setMobileOpen\(true\);\s*\}, \[semanticDivergenceLoading\]\);/s,
  );
});

test("canvas navigation stays viewport-anchored instead of covering top workspace panels", async () => {
  const layout = await read("../src/workspaceLayout.css");
  const css = await read("../src/styles.css");
  const canvas = await read("../src/components/StudioCanvas.tsx");

  assert.match(layout, /\.canvas-nav\s*\{[^}]*position:\s*fixed;[^}]*bottom:/s);
  assert.match(layout, /@media \(max-width:\s*1149px\)[\s\S]*?\.canvas-nav\s*\{[^}]*--workspace-safe-bottom/s);
  assert.match(css, /\.version-canvas-shell\s*\{[^}]*position:\s*absolute;[^}]*inset:\s*0/s);
  assert.match(canvas, /createPortal\(shell, shellHost\)/);
  assert.match(layout, /--active-editor-width:\s*calc\(100vw - var\(--workspace-safe-left\) - var\(--workspace-safe-right\)\)/);
});

test("resizing AI Behavior does not reflow the 3D editor layer", async () => {
  const main = await read("../src/main.tsx");
  const store = await read("../src/state/studioStore.ts");
  assert.doesNotMatch(main, /setAiBehaviorWidth\(size\.w\)/);
  assert.doesNotMatch(store, /\.canvas-composer-shell".*observer\.observe/s);
  assert.match(store, /only recenter on window \/ canvas shell size/);
});

test("open chrome panels reflow siblings through workspace safe-area tokens", async () => {
  const layout = await read("../src/workspaceLayout.css");
  const overlay = await read("../src/components/overlays/PlannerClarificationOverlay.tsx");
  assert.match(layout, /\.studio-shell\.has-solution-space\s*\{[^}]*--ai-behavior-top:\s*calc\(var\(--solution-space-height\)/s);
  assert.match(layout, /\.studio-shell:has\(\.canvas-tool-dock\)\s*\{[^}]*--workspace-safe-left:/s);
  assert.match(layout, /\.canvas-tool-dock\s*\{[^}]*left:\s*var\(--chrome-left\)/s);
  assert.match(layout, /\.ai-behavior-float\s*\{[^}]*max-height:\s*calc\(100dvh - var\(--ai-behavior-top\) - var\(--workspace-safe-bottom\)\)/s);
  assert.match(
    layout,
    /\.planner-clarification-overlay\.is-anchored,\s*\.version-node-frame > \.planner-clarification-overlay\s*\{[^}]*inset:\s*0/s,
  );
  assert.match(overlay, /Math\.max\(8, anchor\.left - bubbleWidth - gap\)/);
  assert.doesNotMatch(overlay, /preferLeft/);
});

test("collapsing Perception does not shift the rest of the workspace", async () => {
  const layout = await read("../src/workspaceLayout.css");
  assert.match(layout, /\.studio-shell\.perception-collapsed \.perception-float\s*\{/);
  assert.doesNotMatch(
    layout,
    /\.studio-shell\.perception-collapsed\s*\{[^}]*--workspace-safe-left/s,
  );
});

test("collapsing AI Behavior does not shift the rest of the workspace", async () => {
  const layout = await read("../src/workspaceLayout.css");
  assert.match(layout, /\.studio-shell\.ai-behavior-collapsed \.ai-behavior-float\s*\{/);
  assert.doesNotMatch(
    layout,
    /\.studio-shell\.ai-behavior-collapsed\s*\{[^}]*--workspace-safe-right/s,
  );
});

test("motion-heavy UI honors reduced-motion preferences", async () => {
  const css = await read("../src/styles.css");
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
});

test("all runtime images reserve dimensions", async () => {
  const files = [
    "../src/components/StudioCanvas.tsx",
    "../src/components/ThreeViewport.tsx",
    "../src/components/panels/AIBehaviorPanel.tsx",
    "../src/components/menu/StudioMenu.tsx",
    "../src/components/panels/IntentComposer.tsx",
  ];
  for (const file of files) {
    const source = await read(file);
    for (const tag of source.match(/<img\b[^>]*>/g) ?? []) {
      assert.match(tag, /\bwidth=/, `${file}: image is missing width: ${tag}`);
      assert.match(tag, /\bheight=/, `${file}: image is missing height: ${tag}`);
    }
  }
});

test("solution candidates use real drag data; canvas drop owns version creation", async () => {
  const rail = await read("../src/components/panels/SolutionSpaceRail.tsx");
  const canvas = await read("../src/components/StudioCanvas.tsx");
  assert.match(rail, /FLOWSTUDIO_CANDIDATE_MIME/);
  assert.match(rail, /draggable=\{Boolean\(previewUrl\)\}/);
  assert.match(rail, /dataTransfer\.setData\(FLOWSTUDIO_CANDIDATE_MIME/);
  assert.doesNotMatch(rail, />添加到画布<\/button>/);
  assert.match(canvas, /onDrop=/);
  assert.match(canvas, /onDropCandidate\(candidate\)/);
});

test("Solution Space can be collapsed, reopened, and stays collapsed while images append", async () => {
  const main = await read("../src/main.tsx");
  const rail = await read("../src/components/panels/SolutionSpaceRail.tsx");
  const css = await read("../src/styles.css");
  const store = await read("../src/state/studioStore.ts");
  const visibility = await read("../src/utils/solutionSpaceVisibility.ts");
  assert.match(main, /aria-label="Open Solution Space"/);
  assert.match(main, /is-ready/);
  assert.match(main, /is-generating/);
  assert.match(css, /solution-space-generating/);
  assert.match(rail, />\s*收起\s*</);
  assert.doesNotMatch(rail, /roundChips\.length\) return null/);
  assert.match(css, /\.solution-space-collapse\s*\{[^}]*min-width:\s*56px/s);
  assert.match(main, /type: "expand"/);
  assert.match(visibility, /action\.type === "expand"\) return false/);
  assert.match(store, /solutionSpaceReadyPulse/);
});

test("version canvas is an accessible candidate drop target", async () => {
  const canvas = await read("../src/components/StudioCanvas.tsx");
  assert.match(canvas, /cloneElement\(gateOverlay/);
  assert.match(canvas, /aria-label="Version history canvas drop target"/);
  assert.match(canvas, /onDragOver=/);
  assert.match(canvas, /onDrop=/);
  assert.match(canvas, /application\/x-flowstudio-candidate/);
  assert.match(canvas, /创建下一版本/);
});

test("version graph is persisted and upgrades the same node in place", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /dropCandidateIntoVersionGraph/);
  assert.match(store, /\/version-nodes/);
  assert.match(store, /active-version/);
  assert.match(store, /mesh_ready/);
  assert.match(store, /mesh_failed/);
  assert.doesNotMatch(store, /const branchCandidates = acceptedCandidateIds/);
});

test("source-node bootstrap waits for the persisted version graph snapshot", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /versionGraphHydrated/);
  assert.match(store, /if \(!versionGraphHydrated\) return;/);
  assert.match(store, /setVersionGraphHydrated\(true\)/);
});

test("candidate drop renders an optimistic image node before waiting for persistence", async () => {
  const store = await read("../src/state/studioStore.ts");
  const actionStart = store.indexOf("const dropCandidateIntoVersionGraph");
  const optimisticNode = store.indexOf("const optimisticNode", actionStart);
  const createRequest = store.indexOf("await api<VersionGraphNode>", actionStart);
  assert.ok(actionStart >= 0, "drop action is missing");
  assert.ok(optimisticNode > actionStart, "drop action does not create an optimistic image node");
  assert.ok(createRequest > optimisticNode, "version persistence blocks the first image-node render");
});

test("version nodes expose status and retry affordances", async () => {
  const canvas = await read("../src/components/StudioCanvas.tsx");
  const css = await read("../src/styles.css");
  assert.match(canvas, /Version \{node\.versionNumber\}/);
  assert.doesNotMatch(canvas, /<span>\{node\.label\}<\/span>/);
  assert.doesNotMatch(canvas, /3D 失败/);
  assert.match(canvas, /aria-label=\{`重试 Version \$\{node\.versionNumber\} 的 3D 生成`\}/);
  assert.match(canvas, /hy3dProgress\?\.message/);
  assert.doesNotMatch(canvas, /HY3D_PROGRESS_LINES/);
  assert.doesNotMatch(canvas, /setInterval/);
  assert.match(css, /\.version-hy3d-progress\s*\{/);
  assert.match(css, /\.version-canvas-shell\.is-drop-target/);
  assert.match(css, /\.version-link\.is-active-path/);
  assert.match(canvas, /luma > 242 && spread < 18/);
  assert.match(canvas, /const liveMesh = Boolean/);
  assert.match(canvas, /version-thumb-media/);
  assert.match(css, /mix-blend-mode:\s*multiply/);
  assert.match(css, /\.version-thumb-media/);
  assert.match(canvas, /!src\.startsWith\(window\.location\.origin\)/);
  assert.match(css, /\.version-active-image\s*\{[^}]*background:\s*transparent/s);
  assert.doesNotMatch(css, /e8edf4/);
});

test("Hy3D success adopts the mesh and forces SAM3D part discovery", async () => {
  const store = await read("../src/state/studioStore.ts");
  const canvas = await read("../src/components/StudioCanvas.tsx");
  const helpers = await read("../src/utils/appHelpers.ts");
  assert.match(store, /adoptHy3dMeshAsActiveAsset/);
  assert.match(store, /source: "hy3d_generated"/);
  assert.match(store, /remote_asset: remotePath \? \{ path: remotePath \}/);
  assert.match(store, /discoverPartsForAsset\(adopted, "hy3d"\)/);
  assert.match(store, /sam3d_real: true/);
  assert.match(store, /wait_timeout_sec: 120/);
  assert.match(canvas, /partSegmentationUrl\(parts\) \?\? node\.meshUrl/);
  assert.match(helpers, /export function remoteWorkerPathFromUrl/);
  assert.match(helpers, /export function partViewportMatchName/);
});

test("add primitive has Done, scale handle, screenshots, and a left tool dock", async () => {
  const store = await read("../src/state/studioStore.ts");
  const canvas = await read("../src/components/StudioCanvas.tsx");
  const main = await read("../src/main.tsx");
  const viewport = await read("../src/components/ThreeViewport.tsx");
  const layout = await read("../src/workspaceLayout.css");
  assert.match(store, /trigger: "primitive_add_done"/);
  assert.match(store, /viewport_screenshot_url: screenshotUrl/);
  assert.match(store, /const cancelPrimitiveBehavior/);
  assert.match(store, /endViews,/);
  assert.match(canvas, /Add primitive controls/);
  assert.match(canvas, /busy \? "…" : "Done"/);
  assert.match(canvas, /已保存截图/);
  assert.match(canvas, /aria-label="Scale"/);
  assert.match(canvas, /behaviorViewSrc/);
  assert.match(canvas, /onTransformMode/);
  assert.match(main, /PrimitiveControlsPanel/);
  assert.match(main, /finalizePrimitiveBehavior/);
  assert.match(main, /canvas-tool-dock/);
  assert.match(main, /setPrimitiveTransformMode/);
  assert.match(layout, /\.canvas-tool-dock/);
  assert.match(viewport, /scale: new Set\(\["XY", "YZ", "XZ"\]\)/);
  assert.match(viewport, /setPrimitiveTransformMode/);
});

test("version cards keep their own mesh and retry does not replace earlier versions", async () => {
  const store = await read("../src/state/studioStore.ts");
  const canvas = await read("../src/components/StudioCanvas.tsx");
  const composer = await read("../src/components/panels/IntentComposer.tsx");
  assert.doesNotMatch(store, /isSource \? asset\?\.mesh_url/);
  assert.match(store, /editingThisNode/);
  assert.match(store, /targetId && versionViewModeRef\.current === "overview"/);
  assert.match(store, /item\.parent_node_id !== null/);
  assert.match(canvas, /asset=\{null\}/);
  assert.match(canvas, /const liveMesh = Boolean\(node\.meshUrl \|\| node\.objUrl\)/);
  assert.match(composer, /!asset && !canvasPrimitive && !activeVersionMeshReady/);
});

test("version overview keeps the focused node highlighted and re-enters on double-click", async () => {
  const canvas = await read("../src/components/StudioCanvas.tsx");
  const main = await read("../src/main.tsx");
  const store = await read("../src/state/studioStore.ts");
  const css = await read("../src/styles.css");
  assert.match(canvas, /aria-label="查看全部版本"/);
  assert.match(canvas, /onHighlightVersion/);
  assert.match(canvas, /event.detail >= 2 \|\| versionViewMode !== "overview"/);
  assert.match(canvas, /onDoubleClick=\{\(\) => onActivateVersion/);
  assert.match(canvas, /\.version-node, \.version-node-frame/);
  assert.match(css, /\.version-node\.thumbnail \.version-thumb-viewport \*/);
  assert.match(canvas, /单击高亮接入点/);
  assert.match(main, /onShowOverview=\{\(\) => focusVersionCanvas\("all"\)\}/);
  assert.match(main, /onHighlightVersion=\{\(nodeId, candidate\) => void highlightVersionNode/);
  assert.match(store, /const parentNodeId = activeNode\?\.node_id \?\? sourceNodeId/);
  assert.match(css, /\.version-node\.thumbnail\.is-active-version/);
  assert.match(css, /\.version-node\.thumbnail:not\(\.is-active-version\)/);
});

test("floating panels stay inside the viewport after resize", async () => {
  const primitive = await read("../src/components/ui/primitives.tsx");
  const css = await read("../src/styles.css");
  const layout = await read("../src/workspaceLayout.css");
  assert.match(primitive, /window\.addEventListener\("resize"/);
  assert.match(primitive, /window\.innerWidth\s*-\s*40/);
  assert.match(primitive, /window\.innerHeight\s*-\s*40/);
  assert.match(layout, /\.solution-space-rail\s*\{[^}]*position:\s*fixed[^}]*left:[^}]*right:/s);
  assert.match(layout, /\.ai-behavior-float\s*\{[^}]*position:\s*fixed[^}]*right:[^}]*width:/s);
  const mobile = css.slice(css.indexOf("@media (max-width: 900px)"));
  assert.match(mobile, /\.perception-float,\s*\.float-panel\.observe-float\s*\{[^}]*max-width:\s*calc\(100vw - 40px\)/s);
});

test("Solution Space selects by card click and drops by native drag", async () => {
  const rail = await read("../src/components/panels/SolutionSpaceRail.tsx");
  const css = await read("../src/styles.css");
  assert.doesNotMatch(rail, />添加到画布<\/button>/);
  assert.doesNotMatch(rail, />选择<\/button>/);
  assert.match(rail, /onClick=\{\(\) => \{/);
  assert.match(rail, /onAcceptDirection\(candidate\)/);
  assert.match(rail, /FLOWSTUDIO_CANDIDATE_MIME/);
  assert.match(rail, /accepted-mark/);
  assert.match(css, /\.solution-card-actions\s*\{[^}]*display:\s*none/s);
});

test("stale semantic divergence errors do not flicker during generation", async () => {
  const store = await read("../src/state/studioStore.ts");
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  const main = await read("../src/main.tsx");
  const rail = await read("../src/components/panels/SolutionSpaceRail.tsx");
  assert.match(store, /semanticDivergence\?\.status === "failed"/);
  assert.match(store, /semantic_divergence_status: "failed"/);
  assert.match(store, /if \(solutionSpaceGenerating\) return;/);
  assert.match(panel, /!generationBusy && !solutionSpaceGenerating/);
  assert.match(main, /fourStage.stage === "failed" \? fourStage.error\?\.message/);
  assert.match(rail, /errorMessage && !candidates.length && !loading/);
});

test("Solution Space height grip does not cover the horizontal scrollbar", async () => {
  const rail = await read("../src/components/panels/SolutionSpaceRail.tsx");
  const css = await read("../src/styles.css");
  const layout = await read("../src/workspaceLayout.css");
  assert.match(css, /\.solution-space-resize\s*\{[^}]*width:\s*56px/s);
  assert.doesNotMatch(css, /\.solution-space-resize\s*\{[^}]*left:\s*0;\s*right:\s*0/s);
  assert.match(layout, /\.solution-space-rail\s*\{[^}]*padding:\s*10px 12px 22px/s);
  assert.match(rail, /draggedSideways/);
});

test("Send snapshot includes live signals and drops generic mesh parts from Gate", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /live_signals: liveSignalsAtClick/);
  assert.match(store, /namedPartAtClick/);
  assert.match(store, /function isGenericMeshId/);
  assert.match(store, /inferred_shape: inferredShape/);
  assert.doesNotMatch(store, /dwell_ms: Math\.max\(current\.dwell_ms, current\.dwell_ms \+ 250\)/);
});

test("mana potion diverges whole silhouette without writing Action History", async () => {
  const store = await read("../src/state/studioStore.ts");
  const main = await read("../src/main.tsx");
  const fnStart = store.indexOf("const triggerPostGateDivergence");
  const fn = store.slice(fnStart, store.indexOf("const startActiveRevisionGeneration", fnStart));
  assert.match(fn, /scope: "whole"/);
  assert.match(fn, /整体轮廓/);
  assert.match(fn, /\/api\/v1\/sandbox\/diverge\/stream/);
  assert.doesNotMatch(fn, /recordActionAtom/);
  assert.match(main, /setAiBehaviorCollapsed\(false\)/);
});

test("action history records one session from tool enter to exit", async () => {
  const store = await read("../src/state/studioStore.ts");
  const main = await read("../src/main.tsx");
  assert.match(store, /if \(behavior.strokeCount === 0\)/);
  assert.match(store, /After Done → continue: keep the same tool session/);
  assert.match(store, /beginSculptBehavior\("annotation"/);
  assert.doesNotMatch(store, /action: "mode_on"/);
  assert.doesNotMatch(store, /action: "menu_open"/);
  assert.doesNotMatch(store, /action: "menu_close"/);
  assert.match(main, /onDoneBehavior=\{\(\) => snapshotSculptBehavior\(\)\}/);
  assert.match(main, /onCancelAnnotation=\{toggleAnnotationMode\}/);
});

test("annotation eraser punches out ink instead of painting white", async () => {
  const overlay = await read("../src/components/overlays/AnnotationCanvasOverlay.tsx");
  assert.match(overlay, /brush === "eraser"/);
  assert.match(overlay, /destination-out/);
  assert.doesNotMatch(overlay, /eraser:\s*"#ffffff"/);
  assert.doesNotMatch(overlay, /rgba\(255,255,255,1\)/);
});
