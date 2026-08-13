/**
 * Session-memory readers (refactor plan P1a).
 */
import type { SessionRecord } from "../types";
import { stringValue } from "./format";

export function readCandidateMemory(session: SessionRecord | null) {
  const memory = session?.metadata?.candidate_memory;
  if (!memory || typeof memory !== "object") {
    return {
      lastAcceptedStage: "none",
      lastCommitPolicy: "none",
      lastAcceptedCandidateId: "none",
      directionCount: 0,
      rejectedCount: 0,
      lastRejectedCandidateId: "none",
      lastRejectedStage: "none",
    };
  }
  const record = memory as Record<string, unknown>;
  const directions = Array.isArray(record.accepted_direction_ids)
    ? record.accepted_direction_ids
    : [];
  const rejected = Array.isArray(record.rejected) ? record.rejected : [];
  return {
    lastAcceptedStage: stringValue(record.last_accepted_stage),
    lastCommitPolicy: stringValue(record.last_commit_policy),
    lastAcceptedCandidateId: stringValue(record.last_accepted_candidate_id),
    directionCount: directions.length,
    rejectedCount: rejected.length,
    lastRejectedCandidateId: stringValue(record.last_rejected_candidate_id),
    lastRejectedStage: stringValue(record.last_rejected_stage),
  };
}
