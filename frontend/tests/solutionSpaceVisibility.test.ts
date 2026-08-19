import assert from "node:assert/strict";
import test from "node:test";

import {
  buildSolutionSpaceRoundChips,
  candidateIntentSeq,
  reduceSolutionSpaceVisibility,
} from "../src/utils/solutionSpaceVisibility.ts";

test("only an explicit expand opens the rail; source change stays collapsed", () => {
  assert.equal(reduceSolutionSpaceVisibility(true, { type: "new_batch" }), true);
  assert.equal(reduceSolutionSpaceVisibility(false, { type: "collapse" }), true);
  assert.equal(reduceSolutionSpaceVisibility(true, { type: "source_changed" }), true);
  assert.equal(reduceSolutionSpaceVisibility(false, { type: "source_changed" }), true);
  assert.equal(reduceSolutionSpaceVisibility(true, { type: "expand" }), false);
});

test("advancing intent does not force-hide or force-expand the rail", () => {
  assert.equal(reduceSolutionSpaceVisibility(false, { type: "intent_advanced" }), false);
  assert.equal(reduceSolutionSpaceVisibility(true, { type: "intent_advanced" }), true);
});

test("generation progress signatures do not reopen a user collapse", () => {
  assert.equal(reduceSolutionSpaceVisibility(true, { type: "new_batch" }), true);
  assert.equal(reduceSolutionSpaceVisibility(true, { type: "content_updated" }), true);
});

test("candidateIntentSeq prefers metadata then batch/run lookup", () => {
  assert.equal(
    candidateIntentSeq({ metadata: { intent_seq: 2 } }),
    2,
  );
  assert.equal(
    candidateIntentSeq(
      { job_id: "run_a", metadata: { four_stage_artifact: true } },
      { batches: [{ run_id: "run_a", intent_seq: 1 }] },
    ),
    1,
  );
  assert.equal(
    candidateIntentSeq(
      { job_id: "run_b", metadata: { run_id: "run_b" } },
      { activeRunId: "run_b", activeIntentSeq: 3 },
    ),
    3,
  );
});

test("round chips keep every generation page including the live empty one", () => {
  const counts = new Map<number, number>([[1, 8]]);
  assert.deepEqual(buildSolutionSpaceRoundChips(counts, 2), [
    { intentSeq: 1, count: 8 },
    { intentSeq: 2, count: 0 },
  ]);
  assert.deepEqual(buildSolutionSpaceRoundChips(counts, 1), [
    { intentSeq: 1, count: 8 },
  ]);
});
