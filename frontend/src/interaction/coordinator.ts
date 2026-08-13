import type { DivergenceSelection, IntentRevision } from "../types.ts";
import { commandMeta, gatePayload, selectionPayload, type CommandIdentity } from "./commands.ts";
import { interactionReducer } from "./reducer.ts";
import { fetchInteractionEvents, fetchInteractionProjection } from "./recovery.ts";
import type { InteractionAction, InteractionEvent, InteractionProjection, InteractionState, InteractionTask } from "./types.ts";
import { emptyInteractionState } from "./types.ts";

type Api = <T>(path: string, init?: RequestInit) => Promise<T>;

export function createInteractionCoordinator({
  api,
  sessionId,
  onState,
}: {
  api: Api;
  sessionId: string;
  onState?: (state: InteractionState) => void;
}) {
  let state = emptyInteractionState();
  const dispatch = (action: InteractionAction) => {
    state = interactionReducer(state, action);
    onState?.(state);
    return state;
  };
  const projection = (value: InteractionProjection) => dispatch({ type: "projection_received", projection: value });

  return {
    getState: () => state,
    dispatch,
    async recover() {
      dispatch({ type: "recovery_started" });
      try {
        // Read the durable cursor before replacing local state. The projection
        // is a snapshot, while events after the prior cursor close the race
        // between a websocket drop and the snapshot request.
        const cursor = state.lastEventCursor;
        const missed = await fetchInteractionEvents(api, sessionId, cursor);
        const next = await fetchInteractionProjection(api, sessionId);
        projection(next);
        for (const event of missed.events) dispatch({ type: "event_received", event });
        return state;
      } catch (error) {
        dispatch({ type: "recovery_failed", error: String(error) });
        throw error;
      }
    },
    receiveEvent(event: InteractionEvent) {
      return dispatch({ type: "event_received", event });
    },
    setConnected(connected: boolean) {
      return dispatch({ type: "connection_changed", connected });
    },
    async acceptGate(
      revision: IntentRevision,
      options: Record<string, unknown> = {},
      identity?: Partial<CommandIdentity>,
    ) {
      const meta = commandMeta(`gate_${revision.revision_id}`, revision.version, identity);
      const next = await api<IntentRevision>(`/api/v1/intent-revisions/${revision.revision_id}/gate`, {
        method: "POST",
        body: JSON.stringify(gatePayload(true, meta, options)),
      });
      dispatch({ type: "ack_received", revision: next });
      return next;
    },
    async rejectGate(revision: IntentRevision, reason?: string, identity?: Partial<CommandIdentity>) {
      const meta = commandMeta(`gate_${revision.revision_id}`, revision.version, identity);
      const next = await api<IntentRevision>(`/api/v1/intent-revisions/${revision.revision_id}/gate`, {
        method: "POST",
        body: JSON.stringify(gatePayload(false, meta, { reason })),
      });
      dispatch({ type: "ack_received", revision: next });
      return next;
    },
    async saveSelection(
      revision: IntentRevision,
      selection: DivergenceSelection,
      identity?: Partial<CommandIdentity>,
    ) {
      const expectedVersion = selection.expected_version ?? revision.version;
      const meta = commandMeta(`selection_${revision.revision_id}`, expectedVersion, identity);
      const versionedSelection = {
        ...selection,
        expected_version: expectedVersion,
        expected_selection_version: selection.expected_selection_version ?? revision.selection_version,
      };
      const next = await api<IntentRevision>(`/api/v1/intent-revisions/${revision.revision_id}/divergence-selection`, {
        method: "PUT",
        body: JSON.stringify(selectionPayload(versionedSelection, meta)),
      });
      dispatch({ type: "ack_received", revision: next });
      return next;
    },
    async startGeneration(revision: IntentRevision, identity?: Partial<CommandIdentity>) {
      const meta = commandMeta(`generation_${revision.revision_id}`, revision.version, identity);
      const next = await api<{ revision: IntentRevision; task: InteractionTask }>(
        `/api/v1/intent-revisions/${revision.revision_id}/generation-tasks`,
        { method: "POST", body: JSON.stringify(meta) },
      );
      dispatch({ type: "ack_received", revision: next.revision, task: next.task });
      return next;
    },
    async retryTask(task: InteractionTask) {
      const next = await api<InteractionTask>(`/api/v1/interaction-tasks/${task.task_id}/retry`, { method: "POST" });
      dispatch({ type: "ack_received", task: next });
      return next;
    },
    async cancelTask(task: InteractionTask) {
      const next = await api<InteractionTask>(`/api/v1/interaction-tasks/${task.task_id}/cancel`, { method: "POST" });
      dispatch({ type: "ack_received", task: next });
      return next;
    },
  };
}
