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

  assert.match(layout, /\.canvas-nav\s*\{[^}]*position:\s*fixed;[^}]*bottom:/s);
  assert.match(layout, /@media \(max-width:\s*1149px\)[\s\S]*?\.canvas-nav\s*\{[^}]*--workspace-safe-bottom/s);
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
  assert.match(rail, />\s*收起\s*</);
  assert.match(css, /\.solution-space-collapse\s*\{[^}]*min-width:\s*56px/s);
  assert.match(main, /type: "expand"/);
  assert.match(visibility, /action\.type === "expand"\) return false/);
  assert.match(store, /solutionSpaceReadyPulse/);
});

test("version canvas is an accessible candidate drop target", async () => {
  const canvas = await read("../src/components/StudioCanvas.tsx");
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
  assert.match(canvas, /正在生成 3D/);
  assert.match(canvas, /可编辑 3D/);
  assert.match(canvas, /3D 失败/);
  assert.match(canvas, /aria-label=\{`重试 Version \$\{node\.versionNumber\} 的 3D 生成`\}/);
  assert.match(css, /\.version-canvas-shell\.is-drop-target/);
  assert.match(css, /\.version-link\.is-active-path/);
});

test("version focus has an explicit overview exit and every thumbnail can re-enter", async () => {
  const canvas = await read("../src/components/StudioCanvas.tsx");
  const main = await read("../src/main.tsx");
  assert.match(canvas, /aria-label="查看全部版本"/);
  assert.match(canvas, /versionViewMode === "active"/);
  assert.match(main, /versionViewMode=\{versionViewMode\}/);
  assert.match(main, /onShowOverview=\{\(\) => focusVersionCanvas\("all"\)\}/);
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
