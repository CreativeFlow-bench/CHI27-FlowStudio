import assert from "node:assert/strict";
import test from "node:test";

import {
  candidateSeriesLabel,
  fourStageCandidateFromArtifact,
  fourStageCandidateId,
  fourStageRunIdFromCandidate,
  inheritedKeywordsFromRevisions,
  normalizeGenerationArtifacts,
  summarizeKeywords,
  visibleInheritedKeywords,
} from "../src/state/studioInteraction.ts";

test("four-stage candidate ids prefer durable artifact ids", () => {
  assert.equal(fourStageCandidateId("run_a", 0, { candidate_id: "cand_gen_01" }), "cand_gen_01");
  assert.equal(fourStageCandidateId("run_a", 0), "fourstage_run_a_1");
});

test("series labels name the generation round and keywords", () => {
  assert.equal(candidateSeriesLabel(2, 0, ["卷曲帽檐", "柔和插接"]), "Gen2 · 1 · 卷曲帽檐 · 柔和插接");
  assert.equal(summarizeKeywords(["a", "b", "c", "d"]), "a · b · c +1");
});

test("inherited keywords can be dismissed without losing the rest", () => {
  const inherited = inheritedKeywordsFromRevisions(
    [
      { intent_seq: 1, status: "accepted", effective_keywords: ["旧词", "保留"] },
      { intent_seq: 2, status: "accepted", effective_keywords: [] },
    ],
    2,
  );
  assert.deepEqual(inherited, ["旧词", "保留"]);
  assert.deepEqual(visibleInheritedKeywords(inherited, ["旧词"]), ["保留"]);
});

test("streamed and persisted four-stage cards share one candidate id", () => {
  const streamed = fourStageCandidateFromArtifact({
    runId: "run_x",
    index: 0,
    artifact: { candidate_id: "cand_gen_01", kind: "png", url: "/files/a.png" },
    sessionId: "s",
    assetId: "a",
    partId: null,
    intentSeq: 3,
    keywords: ["新词"],
  });
  const persisted = fourStageCandidateFromArtifact({
    runId: "run_x",
    index: 0,
    artifact: { candidate_id: "cand_gen_01", kind: "png", url: "/files/a.png" },
    sessionId: "s",
    assetId: "a",
    partId: null,
    intentSeq: 3,
    keywords: ["新词"],
  });
  assert.equal(streamed.candidate_id, persisted.candidate_id);
  assert.equal(streamed.label, "Gen3 · 1 · 新词");
});

test("generation artifacts keep durable candidate ids", () => {
  assert.deepEqual(
    normalizeGenerationArtifacts([
      { candidate_id: "cand_gen_01", kind: "png", url: "/files/a.png" },
      { file_url: "/files/b.png", type: "png" },
    ]),
    [
      { url: "/files/a.png", kind: "png", candidate_id: "cand_gen_01" },
      { url: "/files/b.png", kind: "png" },
    ],
  );
});

test("Hy3D uses the four-stage run on the candidate, not a second HTTP path", () => {
  assert.equal(
    fourStageRunIdFromCandidate({ candidate_id: "cand_gen_01", metadata: { run_id: "run_live" } }, "run_fallback"),
    "run_live",
  );
  assert.equal(
    fourStageRunIdFromCandidate({ candidate_id: "fourstage_run_x_2", metadata: {} }),
    "run_x",
  );
});
