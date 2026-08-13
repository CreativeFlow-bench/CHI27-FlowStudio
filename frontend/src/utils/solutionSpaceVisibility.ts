export type SolutionSpaceVisibilityAction =
  | { type: "new_batch" }
  | { type: "content_updated" }
  | { type: "collapse" }
  | { type: "expand" }
  | { type: "source_changed" }
  | { type: "intent_advanced" };

/** `released=true` means the rail is hidden.
 *  Explicit collapse sticks until the user expands (or a brand-new generation starts).
 *  Mid-flight progress / batch signature changes must not force-expand. */
export function reduceSolutionSpaceVisibility(
  released: boolean,
  action: SolutionSpaceVisibilityAction,
): boolean {
  if (action.type === "collapse") return true;
  if (action.type === "expand" || action.type === "source_changed") return false;
  // new_batch / content_updated / intent_advanced: keep user collapse sticky
  return released;
}

export type SolutionSpaceRoundChip = {
  intentSeq: number;
  count: number;
};

/** Resolve which intent round a candidate belongs to. */
export function candidateIntentSeq(
  candidate: {
    job_id?: string | null;
    metadata?: Record<string, unknown> | null;
  },
  lookup: {
    batches?: Array<{ run_id: string; intent_seq: number }>;
    revisions?: Array<{ run_id: string | null; intent_seq: number }>;
    activeRunId?: string | null;
    activeIntentSeq?: number | null;
  } = {},
): number | null {
  const metaSeq = candidate.metadata?.intent_seq;
  if (typeof metaSeq === "number" && Number.isFinite(metaSeq)) return metaSeq;
  const runId = String(candidate.metadata?.run_id ?? candidate.job_id ?? "");
  if (runId) {
    const fromBatch = lookup.batches?.find((item) => item.run_id === runId);
    if (fromBatch) return fromBatch.intent_seq;
    const fromRevision = lookup.revisions?.find((item) => item.run_id === runId);
    if (fromRevision) return fromRevision.intent_seq;
    if (runId === lookup.activeRunId && typeof lookup.activeIntentSeq === "number") {
      return lookup.activeIntentSeq;
    }
  }
  return null;
}

export function buildSolutionSpaceRoundChips(
  counts: Map<number, number>,
  liveIntentSeq: number | null = null,
): SolutionSpaceRoundChip[] {
  const seqs = new Set<number>(counts.keys());
  if (typeof liveIntentSeq === "number" && liveIntentSeq > 0) seqs.add(liveIntentSeq);
  return [...seqs]
    .sort((a, b) => a - b)
    .map((intentSeq) => ({ intentSeq, count: counts.get(intentSeq) ?? 0 }));
}
