import type { IntentRevision } from "../types";

/** Keep optimistic planning slots until the server publishes the same intent sequence. */
const STALE_LOCAL_PLANNING_MS = 90_000;

export function mergeRealtimeRevisions(
  serverRevisions: IntentRevision[],
  currentRevisions: IntentRevision[],
  nowMs = Date.now(),
): IntentRevision[] {
  const serverSequences = new Set(serverRevisions.map((item) => item.intent_seq));
  const pendingLocal = currentRevisions.filter((item) => {
    if (item.status !== "planning" || serverSequences.has(item.intent_seq)) return false;
    const createdAt = Date.parse(item.created_at);
    if (Number.isFinite(createdAt) && nowMs - createdAt > STALE_LOCAL_PLANNING_MS) return false;
    return true;
  });
  return [...serverRevisions, ...pendingLocal].sort((a, b) => a.intent_seq - b.intent_seq);
}
