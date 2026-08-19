/**
 * SSE consumer and divergence phase message: contract tests.
 *
 * Tests the behaviour of the streaming infrastructure without needing a real browser
 * or backend. Uses the same Vite SSR server approach as other tests.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const read = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

// ─── 1. SSE fetch helper ────────────────────────────────────────────────────

test("sseFetch is exported from semanticDivergenceStream.ts", async () => {
  const stream = await read("../src/utils/semanticDivergenceStream.ts");
  // streamSemanticDivergence uses sseFetch internally.
  assert.match(stream, /for await \(const event of sseFetch/);
});

test("describeDivergencePhase: returns human-readable text for each backend phase", async () => {
  const { describeDivergencePhase } = await loadModule("/src/utils/semanticDivergenceStream.ts");

  const cases: [Record<string, unknown>, string | null | RegExp][] = [
    [{ phase: "evidence" }, "Collecting knowledge evidence…"],
    [{ phase: "primary_call" }, "Calling primary model…"],
    // When generated + accepted are both provided, show both.
    [{ phase: "primary_returned", generated: 20, accepted: 17 }, /Primary model returned 20 candidates \(17 accepted\)\. Validating/],
    // When only generated is provided (accepted is null), show generated only.
    [{ phase: "primary_returned", generated: 20 }, /Primary model returned candidates\. Validating/],
    [{ phase: "primary_returned", generated: 8, accepted: 4 }, /Primary model returned 8 candidates \(4 accepted\)\. Validating/],
    [{ phase: "primary_failed" }, "Primary model failed, switching to fallback…"],
    [{ phase: "fallback_call" }, "Calling fallback model…"],
    [{ phase: "fallback_returned", generated: 12, accepted: 9 }, /Fallback returned 12 candidates \(9 accepted\)\. Merging/],
    [{ phase: "fallback_failed" }, "Fallback model failed."],
    [{ phase: "final_failed" }, "Validation failed."],
    [{ phase: "completed", accepted: 18 }, /Selected 18 candidates/],
    [{ phase: "completed" }, "Merging final candidates."],
    [{ phase: "short_circuit" }, "Reusing cached results."],
    [{ phase: "unknown_phase", message: "my custom message" }, "my custom message"],
    [{ phase: "evidence", message: "Looking up concepts…" }, "Looking up concepts…"],
    [{}, null], // Unknown phase with no message → null (hide from UI)
  ];

  for (const [input, expected] of cases) {
    const result = describeDivergencePhase(input);
    if (expected instanceof RegExp) {
      assert.match(result ?? "", expected, `describeDivergencePhase(${JSON.stringify(input)}) should match ${expected}`);
    } else {
      assert.equal(result, expected, `describeDivergencePhase(${JSON.stringify(input)}) = ${result}`);
    }
  }
});

// ─── 2. Store integration ───────────────────────────────────────────────────

test("studioStore: exports divergencePhaseMessage", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /const \[divergencePhaseMessage, setDivergencePhaseMessage\]/);
  assert.match(store, /divergencePhaseMessage,$/m); // in return object
});

test("studioStore: commitDivergenceParameters sets phase message on loading", async () => {
  const store = await read("../src/state/studioStore.ts");
  // When loading starts, a connecting message should appear immediately.
  assert.match(store, /setDivergencePhaseMessage\("Connecting to model…"\)/);
});

test("studioStore: commitDivergenceParameters clears phase message on completion", async () => {
  const store = await read("../src/state/studioStore.ts");
  // applyCurrentResponse clears the phase message.
  assert.match(store, /setDivergencePhaseMessage\(null\)/);
});

test("studioStore: commitDivergenceParameters calls streamSemanticDivergence", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /await streamSemanticDivergence\(/);
  assert.match(store, /onPhase:/);
  assert.match(store, /onPartial:/);
});

test("studioStore: onPhase calls describeDivergencePhase and setDivergencePhaseMessage", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /const message = describeDivergencePhase\(event\)/);
  assert.match(store, /if \(message\) setDivergencePhaseMessage\(message\)/);
});

test("studioStore: slider commit waits then diverges with latest temperature", async () => {
  const store = await read("../src/state/studioStore.ts");
  assert.match(store, /divergenceTemperatureRef\.current = value/);
  assert.match(store, /const temperature = options\?\.temperature \?\? divergenceTemperatureRef\.current/);
  assert.match(store, /semanticDivergenceLiveRequestRef/);
  assert.match(store, /scheduleDivergenceParametersCommit/);
  assert.match(store, /temperature: divergenceTemperatureRef\.current/);
  assert.match(store, /perGroupCount: divergencePerGroupCountRef\.current/);
  assert.match(store, /, 2000\);/);
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  assert.match(panel, /onDivergenceTemperatureChange\(Number\(event\.currentTarget\.value\)\)/);
  assert.match(panel, /onDivergenceParametersCommit\(\)/);
});

test("studioStore: error branch clears divergencePhaseMessage", async () => {
  const store = await read("../src/state/studioStore.ts");
  // Extract the catch block inside commitDivergenceParameters.
  // The error handler sets divergencePhaseMessage(null) before setSemanticDivergenceError.
  const fnStart = store.indexOf("const commitDivergenceParameters");
  const fnEnd = store.indexOf("\n  };\n", fnStart) + 5;
  const fnBody = store.slice(fnStart, fnEnd);
  const catchBlock = fnBody.match(/catch \([\s\S]*?return null;[\s\S]*?\n    \}/)?.[0] ?? "";
  assert.ok(catchBlock, "catch block found in commitDivergenceParameters");
  assert.match(catchBlock, /setDivergencePhaseMessage\(null\)/);
  // The null assignment must come before the error message is set.
  const phaseNullIdx = catchBlock.indexOf("setDivergencePhaseMessage(null)");
  const errorIdx = catchBlock.indexOf("setSemanticDivergenceError");
  assert.ok(phaseNullIdx >= 0, "setDivergencePhaseMessage(null) found in catch");
  assert.ok(errorIdx >= 0, "setSemanticDivergenceError found in catch");
  assert.ok(phaseNullIdx < errorIdx, "phase message cleared before error is set");
});

// ─── 3. AIBehaviorPanel rendering ──────────────────────────────────────────

test("AIBehaviorPanel receives divergencePhaseMessage prop", async () => {
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  assert.match(panel, /divergencePhaseMessage,/);
  assert.match(panel, /divergencePhaseMessage: string \| null/);
});

test("AIBehaviorPanel renders phase message inside loading skeleton", async () => {
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  assert.match(panel, /divergencePhaseMessage \?\? "Connecting to model…"/);
  assert.match(panel, /semantic-keyword-status is-phase-tick/);
  assert.match(panel, /is-keyword-enter/);
});

test("AIBehaviorPanel mobile open effect triggers on divergence loading", async () => {
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  assert.match(
    panel,
    /if \(semanticDivergenceLoading\) setMobileOpen\(true\);/,
  );
});

// ─── 4. API layer ──────────────────────────────────────────────────────────

test("api.ts exports sseFetch and SseEvent type", async () => {
  const api = await read("../src/api.ts");
  assert.match(api, /export async function\* sseFetch/);
  assert.match(api, /export type SseEvent/);
  assert.match(api, /export type SseEventKind/);
});

test("semanticDivergenceStream.ts imports sseFetch and SseEvent from api.ts", async () => {
  const stream = await read("../src/utils/semanticDivergenceStream.ts");
  // sseFetch is imported
  assert.ok(stream.includes('import { sseFetch, type SseEvent } from "../api"'),
    "import line found");
});

// ─── Helper ─────────────────────────────────────────────────────────────────

async function loadModule(url: string) {
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
    return await server.ssrLoadModule(url);
  } finally {
    await server.close();
    if (originalWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
    }
  }
}
