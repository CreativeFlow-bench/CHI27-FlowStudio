import type { UiBrief } from "../types.ts";

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

export function isMeshJargonLabel(value: string | null | undefined): boolean {
  const text = String(value || "").trim();
  if (!text) return true;
  if (/^(this part|discovered part)/i.test(text)) return true;
  if (/^(cube\.|mball\.|obj_group_|mesh_|mesh\.|asset_)/i.test(text)) return true;
  if (/^(cube|mball|sphere|cylinder|torus|plane|mesh)(?:\.\d+)?$/i.test(text)) return true;
  return /^[A-Za-z][A-Za-z0-9]*\.\d+$/.test(text);
}

export function isObjectStateNarrative(text: string | null | undefined): boolean {
  const stripped = String(text || "").trim();
  if (!/^(this is|it is|it's)\b/i.test(stripped)) return false;
  if (/\b(?:this part|obj_group_|mball|sphere|cylinder|torus|mesh_)\b/i.test(stripped)) return false;
  return !/\b(?:you(?:'re| are)|the user|holding|observing|looking at|watching|orbit|hover|inspect|brushing|before taking)\b/i.test(
    stripped,
  );
}

export function humanizeObserveNarrative(text: string): string {
  const cleaned = text
    .replace(/\basset_[a-z0-9]+\b/gi, "the model")
    .replace(/\b(?:obj_group_|mesh_)[a-z0-9_]+\b/gi, "this part")
    .replace(/\b(?:Cube|Mball|Sphere|Cylinder|Torus|Plane|Mesh)(?:\.\d+)?\b/gi, "this part")
    .replace(/\s+/g, " ")
    .trim();
  return /\bthis part\b/i.test(cleaned) ? "" : cleaned;
}

export const EMPTY_CANVAS_CHATS = [
  "Nothing on the canvas yet. I'm here when you drop in a model.",
  "Empty studio. Load a model or start with a primitive whenever you're ready.",
  "No object in view — we can just hang out until you bring something in.",
];

export function isEmptyCanvasChat(text: string | null | undefined): boolean {
  return EMPTY_CANVAS_CHATS.includes(String(text || "").trim());
}

function observeNarrativeForPresentation(liveObserveNarrative?: string | null): string {
  const text = String(liveObserveNarrative || "").trim();
  if (isObjectStateNarrative(text)) return humanizeObserveNarrative(text) || EMPTY_CANVAS_CHATS[0];
  if (isEmptyCanvasChat(text)) return text;
  return EMPTY_CANVAS_CHATS[0];
}

export function buildAiBehaviorPresentation({
  plannerNarration,
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
  const creativeState: CreativeControlState = semanticDivergenceError
    ? "error"
    : semanticDivergenceLoading
      ? "loading"
      : hasDivergenceContent
        ? "ready"
        : "locked";

  return {
    // Object screenshot when a model is present; idle chat when the canvas is empty.
    narrative: observeNarrativeForPresentation(liveObserveNarrative),
    details: plannerNarration.trim() || null,
    creativeState,
  };
}
