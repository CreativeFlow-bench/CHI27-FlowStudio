import type { BehaviorSession, LiveObservationState, LivePerception } from "../types";

export type PerceptionDisplayOperation =
  | "add"
  | "draw"
  | "sculpt"
  | "reshape"
  | "smooth"
  | "focus"
  | "inspect"
  | "survey"
  | "compare"
  | "describe_intent"
  | "review"
  | "idle";

type PerceptionScope = "silhouette" | "whole" | "part" | "region" | "detail";

export type PerceptionDisplayEvent = {
  id: string;
  operation: PerceptionDisplayOperation;
  scope: PerceptionScope;
  targetLabel?: string;
  sentence: string;
  timestamp: number;
  count: number;
  source: "local" | "confirmed" | "history" | "fallback";
  explicit: boolean;
};

const STALE_AFTER_MS = 8_000;
const RECENT_BEHAVIOR_MS = 2_500;
const ATTENTION_MERGE_MS = 1_500;
const DEFAULT_HISTORY_LIMIT = 12;
const MAX_HISTORY_LIMIT = 50;

const explicitOperations = new Set<PerceptionDisplayOperation>([
  "add",
  "draw",
  "sculpt",
  "reshape",
  "smooth",
  "describe_intent",
]);

const attentionOperations = new Set<PerceptionDisplayOperation>(["focus", "inspect", "survey"]);

function normalizeScope(value: unknown): PerceptionScope {
  const scope = String(value ?? "").trim().toLowerCase();
  if (scope.includes("silhouette")) return "silhouette";
  if (scope.includes("part")) return "part";
  if (scope.includes("region") || scope.includes("mask") || scope.includes("selection")) return "region";
  if (scope.includes("detail") || scope.includes("local")) return "detail";
  return "whole";
}

function normalizeOperation(value: unknown): PerceptionDisplayOperation | null {
  const operation = String(value ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (!operation) return null;
  if (["add", "primitive", "primitive_added", "create", "insert"].includes(operation)) return "add";
  if (["annotation", "annotate", "draw", "drawing", "sketch"].includes(operation)) return "draw";
  if (["brush", "clay", "sculpt", "sculpting"].includes(operation)) return "sculpt";
  if (["drag", "move", "grab", "deform", "reshape"].includes(operation)) return "reshape";
  if (["smooth", "smoothing"].includes(operation)) return "smooth";
  if (["hover", "select", "focus"].includes(operation)) return "focus";
  if (["zoom", "inspect", "inspection"].includes(operation)) return "inspect";
  if (["orbit", "pan", "survey", "rotate"].includes(operation)) return "survey";
  if (["compare", "comparison"].includes(operation)) return "compare";
  if (["text", "intent", "typed_intent", "describe_intent", "language"].includes(operation)) return "describe_intent";
  if (operation === "review") return "review";
  if (operation === "idle") return "idle";
  return null;
}

function operationFromSafeSummary(summary: string): PerceptionDisplayOperation | null {
  const value = summary.trim().toLowerCase();
  if (!value) return null;
  if (value === "user typed an intent." || value.includes("describing an intended change")) return "describe_intent";
  if (value.includes("drawing on the silhouette") || value.includes("is drawing on the part")) return "draw";
  if (value.includes("adding to the silhouette") || value.includes("added a primitive")) return "add";
  if (value.includes("sculpt") || value.includes("brush")) return "sculpt";
  if (value.includes("reshap") || value.includes("dragging")) return "reshape";
  if (value.includes("smooth")) return "smooth";
  if (value.includes("focusing on")) return "focus";
  if (value.includes("inspect") || value.includes("zoom")) return "inspect";
  if (value.includes("survey") || value.includes("orbit")) return "survey";
  if (value.includes("compar")) return "compare";
  return null;
}

function safeTargetLabel(target: Record<string, unknown> | null | undefined, confidence = 1): string | undefined {
  if (!target || confidence < 0.6) return undefined;
  const candidate = target.part_label ?? target.label ?? target.part_name ?? target.part_id;
  if (typeof candidate !== "string") return undefined;
  const normalized = candidate.trim().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
  if (!normalized || normalized.length > 40 || !/^[\p{L}\p{N} .()]+$/u.test(normalized)) return undefined;
  return normalized;
}

export function formatPerceptionSentence({
  operation,
  scope,
  targetLabel,
}: {
  operation: PerceptionDisplayOperation;
  scope: PerceptionScope;
  targetLabel?: string;
}): string {
  switch (operation) {
    case "add":
      return "User is adding to the silhouette.";
    case "draw":
      return scope === "part" && targetLabel
        ? `User is drawing on the ${targetLabel}.`
        : "User is drawing on the silhouette.";
    case "sculpt":
      return "User is sculpting the selected region.";
    case "reshape":
      return targetLabel ? `User is reshaping the ${targetLabel}.` : "User is reshaping the selected part.";
    case "smooth":
      return "User is smoothing the selected region.";
    case "focus":
      return targetLabel ? `User is focusing on the ${targetLabel}.` : "User is focusing on a selected part.";
    case "inspect":
      return scope === "whole" ? "User is inspecting the object." : "User is inspecting a local detail.";
    case "survey":
      return "User is surveying the whole structure.";
    case "compare":
      return "User is comparing design alternatives.";
    case "describe_intent":
      return "User is describing an intended change.";
    case "review":
      return "User is reviewing the current form.";
    case "idle":
      return "Waiting for the user's next move.";
  }
}

function createEvent(input: Omit<PerceptionDisplayEvent, "sentence" | "count" | "explicit"> & { count?: number }): PerceptionDisplayEvent {
  return {
    ...input,
    sentence: formatPerceptionSentence(input),
    count: input.count ?? 1,
    explicit: explicitOperations.has(input.operation),
  };
}

function eventFromPerception(value: LivePerception): PerceptionDisplayEvent | null {
  const operation = operationFromSafeSummary(value.summary);
  const timestamp = Date.parse(value.updatedAt);
  if (!operation || !Number.isFinite(timestamp)) return null;
  return createEvent({
    id: `perception-${timestamp}-${operation}`,
    operation,
    scope: operation === "draw" || operation === "add" ? "silhouette" : operation === "inspect" ? "detail" : "whole",
    timestamp,
    source: "local",
  });
}

function eventFromObservation(value: LiveObservationState): PerceptionDisplayEvent | null {
  const operation = normalizeOperation(value.operation);
  const timestamp = Date.parse(value.updated_at);
  if (!operation || !Number.isFinite(timestamp)) return null;
  const scope = normalizeScope(value.scope);
  return createEvent({
    id: `observation-${value.latest_behavior_seq}-${timestamp}`,
    operation,
    scope,
    targetLabel: safeTargetLabel(value.target, value.confidence),
    timestamp,
    source: "confirmed",
  });
}

function eventFromBehavior(value: BehaviorSession): PerceptionDisplayEvent | null {
  if (value.status !== "committed") return null;
  const operation = normalizeOperation(value.tool);
  const timestamp = Date.parse(value.ended_at ?? value.started_at);
  if (!operation || !Number.isFinite(timestamp)) return null;
  const scope = normalizeScope(value.target.scope ?? value.target.target_scope);
  return createEvent({
    id: value.behavior_id,
    operation,
    scope,
    targetLabel: safeTargetLabel(value.target),
    timestamp,
    source: "history",
    count: operation === "sculpt" || operation === "draw" ? Math.max(1, value.stroke_count) : 1,
  });
}

function aggregateAttention(events: PerceptionDisplayEvent[]): PerceptionDisplayEvent[] {
  const result: PerceptionDisplayEvent[] = [];
  for (const event of events) {
    const previous = result[result.length - 1];
    if (
      previous
      && attentionOperations.has(previous.operation)
      && attentionOperations.has(event.operation)
      && previous.timestamp - event.timestamp <= ATTENTION_MERGE_MS
    ) {
      previous.count += event.count;
      previous.id = `${previous.id}+${event.id}`;
      previous.operation = "inspect";
      previous.scope = "detail";
      previous.sentence = formatPerceptionSentence(previous);
      continue;
    }
    result.push({ ...event });
  }
  return result;
}

function fallbackEvent(hasModel: boolean, now: number): PerceptionDisplayEvent {
  const operation: PerceptionDisplayOperation = hasModel ? "review" : "idle";
  return createEvent({
    id: `fallback-${operation}`,
    operation,
    scope: "whole",
    timestamp: now,
    source: "fallback",
  });
}

export function buildPerceptionDisplay({
  livePerception,
  liveObservation = null,
  behaviors,
  hasModel,
  now = Date.now(),
  historyLimit = DEFAULT_HISTORY_LIMIT,
}: {
  livePerception: LivePerception;
  liveObservation?: LiveObservationState | null;
  behaviors: BehaviorSession[];
  hasModel: boolean;
  now?: number;
  historyLimit?: number;
}): { current: PerceptionDisplayEvent; history: PerceptionDisplayEvent[] } {
  const history = aggregateAttention(
    behaviors
      .map(eventFromBehavior)
      .filter((event): event is PerceptionDisplayEvent => Boolean(event))
      .sort((left, right) => right.timestamp - left.timestamp),
  ).slice(0, Math.min(MAX_HISTORY_LIMIT, Math.max(0, historyLimit)));

  const perceptionEvent = eventFromPerception(livePerception);
  const observationEvent = liveObservation ? eventFromObservation(liveObservation) : null;
  const recentBehavior = history.find((event) => now - event.timestamp <= RECENT_BEHAVIOR_MS) ?? null;
  const candidates = [perceptionEvent, observationEvent, recentBehavior]
    .filter((event): event is PerceptionDisplayEvent => Boolean(event))
    .filter((event) => now - event.timestamp <= STALE_AFTER_MS)
    .sort((left, right) => {
      if (left.explicit !== right.explicit) return left.explicit ? -1 : 1;
      return right.timestamp - left.timestamp;
    });

  return {
    current: candidates[0] ?? fallbackEvent(hasModel, now),
    history,
  };
}
