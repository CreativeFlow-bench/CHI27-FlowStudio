import type { IntentRevision, UiBrief } from "../types";

const clamp = (value: string, length: number) => [...(value ?? "")].slice(0, length).join("");

export function normalizeUiBrief(brief: UiBrief): UiBrief {
  return {
    ...brief,
    phenomenon: clamp(brief.phenomenon, 140),
    next_question: clamp(brief.next_question, 100),
    pending_decision_count: Math.max(0, brief.pending_decision_count ?? 0),
  };
}

export function selectActiveDecision<T extends Pick<IntentRevision, "revision_id" | "intent_seq" | "status">>(
  revisions: T[],
): T | null {
  return [...revisions]
    .filter((item) => item.status === "awaiting_gate")
    .sort((left, right) => left.intent_seq - right.intent_seq)[0] ?? null;
}
