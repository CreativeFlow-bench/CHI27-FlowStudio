import type { InteractionEvent } from "./types.ts";

export function eventRevisionId(event: InteractionEvent) {
  return event.revision_id ?? (typeof event.payload.revision_id === "string" ? event.payload.revision_id : null);
}

export function isStaleEvent(event: InteractionEvent, stateVersion: number | undefined) {
  return stateVersion !== undefined && event.aggregate_version < stateVersion;
}

export function eventDedupeKey(event: InteractionEvent) {
  return event.event_id || `${event.aggregate_id}:${event.aggregate_version}:${event.event_type}`;
}
