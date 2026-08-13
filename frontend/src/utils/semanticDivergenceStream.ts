/**
 * SSE consumer for semantic-divergence progress. The backend emits a sequence
 * of `phase` events describing the work in progress and a final `done` event
 * carrying the full SemanticDivergenceResponse. Callers receive partial
 * responses as soon as each stage completes so the UI can show incremental
 * progress instead of a single long-loading blank state.
 */
import type { SemanticDivergenceResponse } from "../types";
import { sseFetch, type SseEvent } from "../api";

export interface SemanticDivergenceStreamHandlers {
  onPhase?: (event: Record<string, unknown>) => void;
  /** Called when the backend decides to short-circuit with a cached response. */
  onPartial?: (response: SemanticDivergenceResponse) => void;
}

interface SemanticDivergencePhaseEvent {
  phase?: string;
  message?: string;
  request_key?: string;
  status?: string;
}

/**
 * Returns a short human-readable description of the current divergence phase.
 * Used to drive loading text in the AI Behavior panel; the full payload is
 * also forwarded to the optional caller hook for richer rendering.
 */
export function describeDivergencePhase(event: Record<string, unknown>): string | null {
  const phase = typeof event.phase === "string" ? event.phase : "";
  const message = typeof event.message === "string" ? event.message : null;
  if (phase === "evidence") {
    return message ?? "Collecting knowledge evidence…";
  }
  if (phase === "primary_call") {
    return message ?? "Calling primary model…";
  }
  if (phase === "primary_returned") {
    const generated = readNumber(event, "generated");
    const accepted = readNumber(event, "accepted");
    if (generated !== null && accepted !== null) {
      return `Primary model returned ${generated} candidates (${accepted} accepted). Validating…`;
    }
    return "Primary model returned candidates. Validating…";
  }
  if (phase === "primary_failed") {
    return message ?? "Primary model failed, switching to fallback…";
  }
  if (phase === "fallback_call") {
    return message ?? "Calling fallback model…";
  }
  if (phase === "fallback_returned") {
    const generated = readNumber(event, "generated");
    const accepted = readNumber(event, "accepted");
    if (generated !== null && accepted !== null) {
      return `Fallback returned ${generated} candidates (${accepted} accepted). Merging…`;
    }
    return "Fallback returned candidates. Merging…";
  }
  if (phase === "fallback_failed") {
    return message ?? "Fallback model failed.";
  }
  if (phase === "final_failed") {
    return message ?? "Validation failed.";
  }
  if (phase === "completed") {
    const accepted = readNumber(event, "accepted");
    return accepted !== null
      ? `Selected ${accepted} candidates.`
      : "Merging final candidates.";
  }
  if (phase === "short_circuit") {
    return "Reusing cached results.";
  }
  return message;
}

function readNumber(event: Record<string, unknown>, key: string): number | null {
  const value = event[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

/**
 * POST to the SSE endpoint and yield progress events until the final response
 * arrives. The returned promise resolves with the full SemanticDivergenceResponse.
 */
export async function streamSemanticDivergence(
  runId: string,
  payload: Record<string, unknown>,
  handlers: SemanticDivergenceStreamHandlers = {},
): Promise<SemanticDivergenceResponse> {
  const path = `/api/v1/four-stage/runs/${runId}/semantic-divergence/stream`;
  let finalResponse: SemanticDivergenceResponse | null = null;
  const onPhase = handlers.onPhase;
  const onPartial = handlers.onPartial;
  for await (const event of sseFetch(path, {
    method: "POST",
    body: JSON.stringify(payload),
  })) {
    handleEvent(event, onPhase, onPartial, (response) => {
      finalResponse = response;
    });
    if (finalResponse) {
      return finalResponse;
    }
  }
  throw new Error("semantic divergence stream ended without a final response");
}

function handleEvent(
  event: SseEvent,
  onPhase: ((event: Record<string, unknown>) => void) | undefined,
  onPartial: ((response: SemanticDivergenceResponse) => void) | undefined,
  setFinal: (response: SemanticDivergenceResponse) => void,
): void {
  if (event.event === "phase") {
    const phaseEvent = (event.data ?? {}) as Record<string, unknown>;
    if (onPhase) onPhase(phaseEvent);
    if (onPartial) {
      const candidates = Array.isArray(phaseEvent.candidates) ? phaseEvent.candidates : null;
      if (candidates && candidates.length) {
        onPartial(
          buildPartialResponse({
            request_key: typeof phaseEvent.request_key === "string" ? phaseEvent.request_key : undefined,
            candidates,
            status: phaseEvent.phase === "completed" ? "completed" : "running",
            generator_model:
              typeof phaseEvent.generator_model === "string" ? phaseEvent.generator_model : undefined,
          }),
        );
      }
    }
    return;
  }
  if (event.event === "final") {
    if (onPhase) onPhase((event.data ?? {}) as Record<string, unknown>);
    return;
  }
  if (event.event === "done") {
    const response = event.data as SemanticDivergenceResponse;
    if (response && typeof response === "object" && response.status) {
      setFinal(response);
    }
    return;
  }
  if (event.event === "error") {
    const detail =
      (event.data as { detail?: string } | null)?.detail ?? "semantic divergence stream error";
    throw new Error(detail);
  }
}

function buildPartialResponse(raw: {
  request_key?: string;
  candidates?: unknown[];
  status?: string;
  generator_model?: string;
}): SemanticDivergenceResponse {
  return {
    schema_version: "flowstudio.semantic-divergence.v1",
    divergence_id: `partial_${raw.request_key ?? "unknown"}`,
    run_id: "",
    decision_id: "",
    request_key: raw.request_key ?? "",
    status: (raw.status as SemanticDivergenceResponse["status"]) ?? "running",
    generator_model: raw.generator_model ?? "",
    fallback_used: false,
    fallback_reason: null,
    knowledge_route: { mode: "model_only", use_wikidata: false, use_getty_aat: false, use_asknature: false, reasons: [], source_statuses: {} },
    validation_counts: {},
    latency_ms: 0,
    prompt_version: "semantic-divergence-v1",
    candidates: Array.isArray(raw.candidates)
      ? (raw.candidates as SemanticDivergenceResponse["candidates"])
      : [],
  };
}
