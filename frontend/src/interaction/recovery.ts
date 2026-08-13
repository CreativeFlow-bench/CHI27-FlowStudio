import type { InteractionProjection, InteractionEvent } from "./types.ts";

export async function fetchInteractionProjection(
  api: <T>(path: string, init?: RequestInit) => Promise<T>,
  sessionId: string,
) {
  return api<InteractionProjection>(`/api/v1/sessions/${sessionId}/interaction-projection`);
}

export async function fetchInteractionEvents(
  api: <T>(path: string, init?: RequestInit) => Promise<T>,
  sessionId: string,
  afterCursor: number,
) {
  return api<{ events: InteractionEvent[]; last_event_cursor: number }>(
    `/api/v1/sessions/${sessionId}/interaction-events?after_cursor=${afterCursor}`,
  );
}
