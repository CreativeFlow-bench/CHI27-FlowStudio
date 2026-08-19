import type { UiBrief } from "../types.ts";
import { normalizeUiBrief } from "./uiBrief.ts";

export type CreativeControlState = "locked" | "loading" | "ready" | "error";

export type AiBehaviorPresentation = {
  narrative: string;
  details: string | null;
  creativeState: CreativeControlState;
};

export type SemanticDivergenceUiState = {
  loading: boolean;
  error: string | null;
};

const DIVERGENCE_STRICTNESS = 0.6;

export function normalizePerGroupCount(value: number): number {
  const rounded = Number.isFinite(value) ? Math.round(value) : 5;
  return Math.min(8, Math.max(5, rounded));
}

export function formatPerGroupCount(value: number): string {
  return `${normalizePerGroupCount(value)} per group`;
}

export function buildSemanticDivergenceParameters({
  temperature,
  perGroupCount,
}: {
  temperature: number;
  perGroupCount: number;
}) {
  return {
    temperature,
    strictness: DIVERGENCE_STRICTNESS,
    per_group_count: normalizePerGroupCount(perGroupCount),
  };
}

export function deriveSemanticDivergenceUiState({
  revisionStatus,
  revisionError,
  resultStatus,
  hasCandidates,
}: {
  revisionStatus: "running" | "completed" | "failed" | null;
  revisionError: string | null;
  resultStatus: "running" | "completed" | "failed" | null;
  hasCandidates: boolean;
}): SemanticDivergenceUiState {
  if (revisionStatus === "failed" || resultStatus === "failed") {
    return { loading: false, error: revisionError || "semantic divergence unavailable" };
  }
  if (resultStatus === "completed" && hasCandidates) {
    return { loading: false, error: null };
  }
  return {
    loading:
      revisionStatus === "running" ||
      revisionStatus === "completed" ||
      resultStatus === "running",
    error: null,
  };
}

export function humanizeObserveNarrative(text: string): string {
  return text
    .replace(/\basset_[a-z0-9]+\b/gi, "the model")
    .replace(/\b(?:obj_group_|mesh_)[a-z0-9_]+\b/gi, "this part")
    .replace(/\bCube\.\d+\b/gi, "this part")
    .replace(/\borbiting the viewport\b/gi, "turning the model around")
    .replace(/\brepeatedly hovering over local details\b/gi, "looking closely at a small area")
    .replace(/\s+/g, " ")
    .trim();
}

export function buildAiBehaviorPresentation({
  uiBrief,
  plannerTypedText,
  plannerNarration,
  phenomenon,
  liveObserveNarrative,
  semanticDivergenceLoading,
  semanticDivergenceError,
  hasDivergenceContent,
}: {
  uiBrief: UiBrief | null;
  plannerTypedText: string;
  plannerNarration: string;
  phenomenon?: string | null;
  liveObserveNarrative?: string | null;
  semanticDivergenceLoading: boolean;
  semanticDivergenceError: string | null;
  hasDivergenceContent: boolean;
}): AiBehaviorPresentation {
  const brief = uiBrief ? normalizeUiBrief(uiBrief) : null;
  const creativeState: CreativeControlState = semanticDivergenceError
    ? "error"
    : semanticDivergenceLoading
      ? "loading"
      : hasDivergenceContent
        ? "ready"
        : "locked";

  return {
    // Live canvas LLM observe > revision phenomenon > planner text > brief
    narrative: humanizeObserveNarrative(
      liveObserveNarrative || phenomenon || plannerTypedText || brief?.phenomenon || "Waiting for the next move.",
    ),
    details: plannerNarration.trim() || null,
    creativeState,
  };
}
