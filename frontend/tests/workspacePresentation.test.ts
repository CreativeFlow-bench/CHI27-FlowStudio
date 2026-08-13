import assert from "node:assert/strict";
import test from "node:test";

import * as workspacePresentation from "../src/utils/workspacePresentation.ts";

const { buildAiBehaviorPresentation } = workspacePresentation;

test("content amount is presented as an exact per-dimension count", () => {
  const format = (workspacePresentation as typeof workspacePresentation & {
    formatPerGroupCount?: (value: number) => string;
  }).formatPerGroupCount;

  assert.equal(typeof format, "function", "per-dimension content amount formatter is missing");
  assert.equal(format?.(5), "5 / 维");
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
