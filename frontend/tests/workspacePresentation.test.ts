import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import * as workspacePresentation from "../src/utils/workspacePresentation.ts";

const { buildAiBehaviorPresentation } = workspacePresentation;

test("observe narrative hides asset ids and mesh jargon", () => {
  assert.equal(
    workspacePresentation.humanizeObserveNarrative(
      "This is a Santa Head made from asset_0a8a397439 with Mball.005.",
    ),
    "",
  );
  assert.equal(
    workspacePresentation.humanizeObserveNarrative(
      "This is a Santa Head made from asset_0a8a397439 with a wrinkled face.",
    ),
    "This is a Santa Head made from the model with a wrinkled face.",
  );
});

test("user-action observe lines are not treated as 3D object state", () => {
  assert.equal(
    workspacePresentation.isObjectStateNarrative(
      "You are holding the Santa head model and observing it carefully before taking any action.",
    ),
    false,
  );
  assert.equal(
    workspacePresentation.isObjectStateNarrative("This is a cute Santa Claus head with rounded, wrinkled clay-like features."),
    true,
  );
  assert.equal(
    workspacePresentation.isObjectStateNarrative(
      "This is a Christmas Santa Head with this part this part, Sphere.",
    ),
    false,
  );
});

test("mesh jargon labels are not treated as 3D context parts", () => {
  assert.equal(workspacePresentation.isMeshJargonLabel("Mball.005"), true);
  assert.equal(workspacePresentation.isMeshJargonLabel("Cube.001"), true);
  assert.equal(workspacePresentation.isMeshJargonLabel("Sphere"), true);
  assert.equal(workspacePresentation.isMeshJargonLabel("Santa hat"), false);
});

test("content amount is presented as an exact per-dimension count", () => {
  const format = (workspacePresentation as typeof workspacePresentation & {
    formatPerGroupCount?: (value: number) => string;
  }).formatPerGroupCount;

  assert.equal(typeof format, "function", "per-dimension content amount formatter is missing");
  assert.equal(format?.(5), "5 per group");
});

test("content amount is rounded and constrained to five through eight per dimension", () => {
  const normalize = (workspacePresentation as typeof workspacePresentation & {
    normalizePerGroupCount?: (value: number) => number;
  }).normalizePerGroupCount;

  assert.equal(typeof normalize, "function", "per-dimension content amount normalization is missing");
  assert.equal(normalize?.(4), 5);
  assert.equal(normalize?.(9), 8);
  assert.equal(normalize?.(6.4), 6);
});

test("semantic divergence requests keep strictness internal and send the per-dimension count", () => {
  const build = (workspacePresentation as typeof workspacePresentation & {
    buildSemanticDivergenceParameters?: (input: {
      temperature: number;
      perGroupCount: number;
    }) => Record<string, number>;
  }).buildSemanticDivergenceParameters;

  assert.equal(typeof build, "function", "semantic divergence parameter builder is missing");
  assert.deepEqual(build?.({ temperature: 0.3, perGroupCount: 7 }), {
    temperature: 0.3,
    strictness: 0.6,
    per_group_count: 7,
  });
});

test("AI Behavior narrative is the 3D object state, not a Gate question", () => {
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
    plannerTypedText: "User is orbiting to inspect the form's parts.",
    plannerNarration: "full model evidence",
    liveObserveNarrative: "This is a Santa Claus head with a wrinkled face.",
    semanticDivergenceLoading: false,
    semanticDivergenceError: null,
    hasDivergenceContent: false,
  });

  assert.equal(view.narrative, "This is a Santa Claus head with a wrinkled face.");
  assert.equal(view.details, "full model evidence");
  assert.equal(view.creativeState, "locked");
  assert.doesNotMatch(JSON.stringify(view), new RegExp(gateQuestion));
  assert.doesNotMatch(view.narrative, /orbiting|inspect/i);
});

test("AI Behavior drops user-action observe lines", () => {
  const view = buildAiBehaviorPresentation({
    uiBrief: null,
    plannerTypedText: "",
    plannerNarration: "",
    liveObserveNarrative:
      "You are holding the Santa head model and observing it carefully before taking any action.",
    semanticDivergenceLoading: false,
    semanticDivergenceError: null,
    hasDivergenceContent: false,
  });
  assert.equal(view.narrative, workspacePresentation.EMPTY_CANVAS_CHATS[0]);
});

test("AI Behavior chats when the canvas is empty", () => {
  const view = buildAiBehaviorPresentation({
    uiBrief: null,
    plannerTypedText: "",
    plannerNarration: "",
    liveObserveNarrative: workspacePresentation.EMPTY_CANVAS_CHATS[1],
    semanticDivergenceLoading: false,
    semanticDivergenceError: null,
    hasDivergenceContent: false,
  });
  assert.equal(view.narrative, workspacePresentation.EMPTY_CANVAS_CHATS[1]);
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

test("Gate acknowledgement keeps divergence visibly loading until candidates hydrate", () => {
  const derive = (workspacePresentation as typeof workspacePresentation & {
    deriveSemanticDivergenceUiState?: (input: {
      revisionStatus: "running" | "completed" | "failed" | null;
      revisionError: string | null;
      resultStatus: "running" | "completed" | "failed" | null;
      hasCandidates: boolean;
    }) => { loading: boolean; error: string | null };
  }).deriveSemanticDivergenceUiState;

  assert.equal(typeof derive, "function", "semantic divergence UI state projection is missing");
  assert.deepEqual(
    derive?.({ revisionStatus: "running", revisionError: null, resultStatus: null, hasCandidates: false }),
    { loading: true, error: null },
  );
  assert.deepEqual(
    derive?.({ revisionStatus: "completed", revisionError: null, resultStatus: null, hasCandidates: false }),
    { loading: true, error: null },
  );
  assert.deepEqual(
    derive?.({ revisionStatus: "completed", revisionError: null, resultStatus: "completed", hasCandidates: true }),
    { loading: false, error: null },
  );
  assert.deepEqual(
    derive?.({ revisionStatus: "failed", revisionError: "model timeout", resultStatus: null, hasCandidates: false }),
    { loading: false, error: "model timeout" },
  );
});

test("observe narrative looks at a viewport screenshot instead of part names", async () => {
  const store = await readFile(new URL("../src/state/studioStore.ts", import.meta.url), "utf8");
  const start = store.indexOf("look at the viewport screenshot");
  const block = store.slice(start, store.indexOf("solutionSpaceSignature", start));
  assert.match(block, /captureJpeg\?\.\(360, 0\.48\)/);
  assert.match(block, /preview_image: preview/);
  assert.match(block, /parts: \[\]/);
  assert.match(block, /viewport_orbit_count/);
  assert.match(block, /EMPTY_CANVAS_CHATS/);
  assert.match(block, /hasObject/);
  assert.doesNotMatch(block, /humanParts/);
});
