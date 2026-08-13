import type { IntentRevision } from "../types.ts";
import { phaseFor } from "./reducer.ts";
import type { InteractionPhase, InteractionState, InteractionTask } from "./types.ts";

export function selectRevision(state: InteractionState, revisionId: string | null) {
  return revisionId ? state.revisions[revisionId] ?? null : null;
}

export function selectRevisionTasks(state: InteractionState, revisionId: string) {
  return Object.values(state.tasks).filter((task) => task.revision_id === revisionId).sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function selectRevisionPhase(state: InteractionState, revisionId: string): InteractionPhase {
  const revision = state.revisions[revisionId];
  if (!revision) return "observing";
  return state.phaseByRevision[revisionId] ?? phaseFor(revision, selectRevisionTasks(state, revisionId).at(-1));
}

export function selectActiveRevision(state: InteractionState): IntentRevision | null {
  return Object.values(state.revisions).sort((a, b) => a.intent_seq - b.intent_seq).at(-1) ?? null;
}

export function selectTaskForRevision(state: InteractionState, revisionId: string, type?: InteractionTask["task_type"]) {
  return selectRevisionTasks(state, revisionId).filter((task) => !type || task.task_type === type).at(-1) ?? null;
}
