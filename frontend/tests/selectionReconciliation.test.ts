import assert from "node:assert/strict";
import test from "node:test";

import type { PromptToken } from "../src/types.ts";
import {
  reconcileSelectedPromptTokens,
  resolveServerSelectedCandidateIds,
} from "../src/utils/selectionReconciliation.ts";

const tokenA: PromptToken = {
  token_id: "token-a",
  candidate_id: "candidate-a",
  label: "歪戴绒球",
  group_key: "shape",
};

const tokenB: PromptToken = {
  token_id: "token-b",
  candidate_id: "candidate-b",
  label: "星星贴布",
  group_key: "surface",
};

test("pending optimistic selection wins over a stale empty poll", () => {
  assert.deepEqual(
    reconcileSelectedPromptTokens({
      availableTokens: [tokenA, tokenB],
      serverSelectedCandidateIds: [],
      optimisticTokens: [tokenA, tokenB],
      persistencePending: true,
    }),
    [tokenA, tokenB],
  );
});

test("settled polling hydrates the authoritative server selection", () => {
  assert.deepEqual(
    reconcileSelectedPromptTokens({
      availableTokens: [tokenA, tokenB],
      serverSelectedCandidateIds: ["candidate-b"],
      optimisticTokens: [tokenA],
      persistencePending: false,
    }),
    [tokenB],
  );
});

test("intent revision selection wins when the four-stage run has not mirrored it", () => {
  assert.deepEqual(
    resolveServerSelectedCandidateIds({
      revisionSelectedCandidateIds: ["candidate-a", "candidate-b"],
      runSelectedCandidateIds: [],
    }),
    ["candidate-a", "candidate-b"],
  );
});
