import type { IntentRevision } from "../types.ts";
import { eventDedupeKey, eventRevisionId, isStaleEvent } from "./events.ts";
import type { InteractionAction, InteractionEvent, InteractionState, InteractionTask } from "./types.ts";
import { emptyInteractionState, type InteractionPhase } from "./types.ts";

function phaseFor(revision: IntentRevision, task?: InteractionTask): InteractionPhase {
  if (revision.status === "planning") return "planning_intent";
  if (revision.status === "awaiting_gate") return "awaiting_gate";
  if (revision.status === "accepted") {
    if (task?.task_type === "semantic_divergence" && ["queued", "running"].includes(task.status)) return "preparing_keywords";
    return revision.delta_keywords.length ? "ready_to_generate" : "choosing_keywords";
  }
  if (revision.status === "generating") return "generating";
  if (revision.status === "completed") return "reviewing_solutions";
  if (revision.status === "failed") return "needs_attention";
  return "observing";
}

function mergeRevision(state: InteractionState, revision: IntentRevision) {
  const currentVersion = state.aggregateVersions[revision.revision_id] ?? 0;
  if ((revision.version ?? 1) < currentVersion) return state;
  const next = { ...state, revisions: { ...state.revisions, [revision.revision_id]: revision } };
  next.aggregateVersions = { ...state.aggregateVersions, [revision.revision_id]: revision.version ?? 1 };
  const task = Object.values(next.tasks).filter((item) => item.revision_id === revision.revision_id).at(-1);
  next.phaseByRevision = { ...state.phaseByRevision, [revision.revision_id]: phaseFor(revision, task) };
  return next;
}

function mergeTask(state: InteractionState, task: InteractionTask) {
  const next = { ...state, tasks: { ...state.tasks, [task.task_id]: task } };
  if (task.revision_id && next.revisions[task.revision_id]) {
    next.phaseByRevision = {
      ...next.phaseByRevision,
      [task.revision_id]: phaseFor(next.revisions[task.revision_id], task),
    };
  }
  return next;
}

function applyEvent(state: InteractionState, event: InteractionEvent): InteractionState {
  const key = eventDedupeKey(event);
  if (state.seenEventIds.has(key)) return state;
  const revisionId = eventRevisionId(event);
  if (isStaleEvent(event, state.aggregateVersions[event.aggregate_id])) return state;
  const seen = new Set(state.seenEventIds);
  seen.add(key);
  let next: InteractionState = {
    ...state,
    seenEventIds: seen,
    lastEventCursor: Math.max(state.lastEventCursor, event.event_cursor),
    aggregateVersions: { ...state.aggregateVersions, [event.aggregate_id]: event.aggregate_version },
  };
  if (revisionId && next.revisions[revisionId]) {
    const revision = { ...next.revisions[revisionId], version: event.aggregate_version };
    if (event.event_type === "GateAccepted") revision.status = "accepted";
    if (event.event_type === "GateRejected") revision.status = "rejected";
    if (event.event_type === "SelectionSaved") revision.selection_version = Number(event.payload.selection_version ?? revision.selection_version ?? 0);
    next = mergeRevision(next, revision);
  }
  if (
    event.event_type === "DivergenceQueued" ||
    event.event_type === "DivergenceStarted" ||
    event.event_type === "DivergenceCompleted" ||
    event.event_type === "DivergenceFailed" ||
    event.event_type === "GenerationQueued" ||
    event.event_type === "GenerationStarted" ||
    event.event_type === "GenerationCompleted" ||
    event.event_type === "GenerationFailed"
  ) {
    const task = event.payload.task as InteractionTask | undefined;
    if (task) next = mergeTask(next, task);
  }
  return next;
}

export function interactionReducer(state: InteractionState = emptyInteractionState(), action: InteractionAction): InteractionState {
  switch (action.type) {
    case "projection_received": {
      let next: InteractionState = {
        ...state,
        revisions: {},
        tasks: {},
        solutionBatches: {},
        recovering: false,
        error: null,
        lastEventCursor: action.projection.last_event_cursor,
      };
      for (const revision of action.projection.revisions) next = mergeRevision(next, revision);
      for (const task of action.projection.tasks) next = mergeTask(next, task);
      for (const batch of action.projection.solution_batches) next.solutionBatches[batch.batch_id] = batch;
      return next;
    }
    case "ack_received": {
      let next = state;
      if (action.revision) next = mergeRevision(next, action.revision);
      if (action.task) next = mergeTask(next, action.task);
      if (action.batch) next = { ...next, solutionBatches: { ...next.solutionBatches, [action.batch.batch_id]: action.batch } };
      return next;
    }
    case "event_received":
      return applyEvent(state, action.event);
    case "connection_changed":
      return { ...state, connected: action.connected };
    case "recovery_started":
      return { ...state, recovering: true, error: null };
    case "recovery_failed":
      return { ...state, recovering: false, error: action.error };
    default:
      return state;
  }
}

export { phaseFor };
