import type { IntentRevision, SolutionBatch } from "../types.ts";

export type InteractionTaskType = "intent_planning" | "semantic_divergence" | "solution_generation";
export type InteractionTaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled" | "superseded";

export type InteractionTask = {
  task_id: string;
  task_type: InteractionTaskType;
  project_id?: string | null;
  session_id: string;
  revision_id?: string | null;
  status: InteractionTaskStatus;
  input_json: Record<string, unknown>;
  result_ref?: string | null;
  progress: number;
  attempt: number;
  max_attempts: number;
  lease_owner?: string | null;
  lease_expires_at?: string | null;
  idempotency_key: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  cancel_requested: boolean;
  updated_at: string;
};

export type InteractionEvent = {
  event_id: string;
  event_type: string;
  session_id: string;
  revision_id?: string | null;
  aggregate_type: "intent_revision" | "divergence_selection" | "generation_task";
  aggregate_id: string;
  aggregate_version: number;
  event_cursor: number;
  correlation_id?: string | null;
  payload: Record<string, unknown>;
};

export type InteractionProjection = {
  revisions: IntentRevision[];
  tasks: InteractionTask[];
  solution_batches: SolutionBatch[];
  last_event_cursor: number;
};

export type InteractionPhase =
  | "observing"
  | "planning_intent"
  | "awaiting_gate"
  | "preparing_keywords"
  | "choosing_keywords"
  | "ready_to_generate"
  | "generating"
  | "reviewing_solutions"
  | "needs_attention";

export type InteractionState = {
  revisions: Record<string, IntentRevision>;
  tasks: Record<string, InteractionTask>;
  solutionBatches: Record<string, SolutionBatch>;
  seenEventIds: Set<string>;
  aggregateVersions: Record<string, number>;
  phaseByRevision: Record<string, InteractionPhase>;
  connected: boolean;
  recovering: boolean;
  lastEventCursor: number;
  error: string | null;
};

export type InteractionAction =
  | { type: "projection_received"; projection: InteractionProjection }
  | { type: "ack_received"; revision?: IntentRevision; task?: InteractionTask | null; batch?: SolutionBatch | null }
  | { type: "event_received"; event: InteractionEvent }
  | { type: "connection_changed"; connected: boolean }
  | { type: "recovery_started" }
  | { type: "recovery_failed"; error: string };

export function emptyInteractionState(): InteractionState {
  return {
    revisions: {},
    tasks: {},
    solutionBatches: {},
    seenEventIds: new Set(),
    aggregateVersions: {},
    phaseByRevision: {},
    connected: false,
    recovering: false,
    lastEventCursor: 0,
    error: null,
  };
}
