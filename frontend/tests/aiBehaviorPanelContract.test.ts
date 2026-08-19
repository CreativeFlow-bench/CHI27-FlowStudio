import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

test("AI Behavior keeps the approved insight hierarchy around More Creative", async () => {
  const originalWindow = globalThis.window;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { protocol: "http:", hostname: "localhost" } },
  });
  const server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL("..", import.meta.url)),
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });

  try {
    const { AIBehaviorPanel } = await server.ssrLoadModule(
      "/src/components/panels/AIBehaviorPanel.tsx",
    );
    const groups = ["shape", "connection", "surface", "semantic_transfer"];
    const divergenceKeywords = groups.flatMap((group, groupIndex) =>
      Array.from({ length: 5 }, (_, index) => ({
        token_id: `${group}-${index}`,
        candidate_id: `${group}-${index}`,
        label: `Choice ${groupIndex + 1}.${index + 1}`,
        group_key: group,
      })),
    );
    const html = renderToStaticMarkup(createElement(AIBehaviorPanel, {
      presentation: { narrative: "Ready", details: null, creativeState: "ready" },
      projectNotice: null,
      onDismissNotice: () => undefined,
      intentBubble: { scope: "Snowman", phase: "confirmed" },
      divergenceKeywords,
      selectedPromptTokens: [divergenceKeywords[0]],
      interpretation: null,
      session: {},
      asset: {},
      generationBusy: false,
      solutionSpaceGenerating: false,
      onTogglePromptToken: () => undefined,
      onGenerate: () => undefined,
      divergenceTemperature: 0.5,
      onDivergenceTemperatureChange: () => undefined,
      divergencePerGroupCount: 5,
      onDivergencePerGroupCountChange: () => undefined,
      onDivergenceParametersCommit: () => undefined,
      semanticDivergence: null,
      semanticDivergenceLoading: false,
      semanticDivergenceError: null,
      selectionPersistenceError: null,
      inheritedKeywords: [],
    }));

    assert.match(html, /More Creative\?/);
    assert.match(html, /Waiting for your design\. I(?:'|&#x27;)ll give you more inspiration\./);
    assert.doesNotMatch(html, />CURRENT PHENOMENON</);
    assert.doesNotMatch(html, />MODEL DETAILS</);
    assert.doesNotMatch(html, /Confirm scope to start divergence/);
    assert.doesNotMatch(html, /请先选择至少一个当前发散候选/);
    assert.match(html, />DIVERGENCE</);
    assert.match(html, />CONTENT</);
    assert.match(html, />SHAPE</);
    assert.match(html, />CONNECTION</);
    assert.match(html, />SURFACE</);
    assert.match(html, />TRANSFER</);
    assert.equal((html.match(/>Generate<\/button>/g) ?? []).length, 1);
    assert.match(html, /class="more-creative-card"/);

    const css = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
    const layoutCss = await readFile(new URL("../src/workspaceLayout.css", import.meta.url), "utf8");
    assert.doesNotMatch(css, /先确认当前改动范围/);
    assert.match(
      layoutCss,
      /--ai-behavior-width:\s*378px/,
    );
    assert.match(
      css,
      /\.ai-behavior-header\s*\{[^}]*min-height:\s*68px[^}]*padding:\s*18px 20px/s,
    );
    assert.match(
      css,
      /\.ai-insight-card\s*\{[^}]*background:\s*transparent/s,
    );
    assert.match(
      css,
      /\.more-creative-card \.more-creative-title\s*\{[^}]*font-size:\s*23px/s,
    );
  } finally {
    await server.close();
    if (originalWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
    }
  }
});
