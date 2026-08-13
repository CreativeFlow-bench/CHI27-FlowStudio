import assert from "node:assert/strict";
import test from "node:test";

import { mergeRealtimeRevisions } from "../src/utils/optimisticRevisions.ts";
import type { IntentRevision } from "../src/types.ts";

function revision(
  id: string,
  status: IntentRevision["status"],
  intentSeq: number,
  createdAt = "2026-08-12T06:00:00Z",
): IntentRevision {
  return {
    revision_id: id,
    session_id: "sess_test",
    intent_seq: intentSeq,
    parent_revision_id: null,
    window_start_seq: 1,
    cutoff_seq: 0,
    behavior_ids: [],
    user_text: `intent ${intentSeq}`,
    source_context: { asset_id: "asset_test", object_type: "snowman" },
    status,
    run_id: null,
    gate_id: null,
    gate_question: null,
    gate_target: null,
    gate_scope: null,
    base_keywords: [],
    delta_keywords: [],
    effective_keywords: [],
    divergence_selection: null,
    error: null,
    created_at: createdAt,
    updated_at: createdAt,
  };
}

test("keeps local planning revisions while realtime polling has not returned them", () => {
  const now = Date.parse("2026-08-12T06:00:30Z");
  const merged = mergeRealtimeRevisions(
    [revision("intent_server_1", "awaiting_gate", 1)],
    [revision("intent_server_1", "awaiting_gate", 1), revision("local_intent_2", "planning", 2)],
    now,
  );
  assert.deepEqual(merged.map((item) => item.revision_id), ["intent_server_1", "local_intent_2"]);
});

test("drops a planning placeholder after the matching server intent sequence arrives", () => {
  const merged = mergeRealtimeRevisions(
    [revision("intent_server_2", "awaiting_gate", 2)],
    [revision("local_intent_2", "planning", 2)],
  );
  assert.deepEqual(merged.map((item) => item.revision_id), ["intent_server_2"]);
});

test("drops stale local planning placeholders so the spinner cannot stick forever", () => {
  const now = Date.parse("2026-08-12T06:05:00Z");
  const merged = mergeRealtimeRevisions(
    [revision("intent_server_1", "awaiting_gate", 1)],
    [revision("local_intent_2", "planning", 2, "2026-08-12T06:00:00Z")],
    now,
  );
  assert.deepEqual(merged.map((item) => item.revision_id), ["intent_server_1"]);
});
