/**
 * Scope inference helpers (refactor plan P1a).
 */
import type { BubbleScope } from "../types";

export function inferredChangeScope(
  interpretation: { primary_intent: string; evidence?: string[]; features?: { design_state_ir?: { query_terms?: string[] } } },
  selectedPartLabel?: string | null,
): "contour" | "part" | "material" {
  const text = [
    interpretation.primary_intent,
    ...(interpretation.evidence ?? []),
    ...(interpretation.features?.design_state_ir?.query_terms ?? []),
  ].join(" ").toLowerCase();
  return inferChangeScopeFromText(text, selectedPartLabel);
}

export function inferChangeScopeFromText(text: string, _selectedPartLabel?: string | null): "contour" | "part" | "material" {
  const normalized = text.toLowerCase();
  if (/material|texture|surface|color|fabric|finish|材质|纹理|颜色|表面/.test(normalized)) return "material";
  if (/part|component|local|brush|部件|组件|局部|某个部分|当前部分/.test(normalized)) return "part";
  return "contour";
}

export function explicitScopeFromText(text: string): "contour" | "part" | "material" | null {
  const normalized = text.toLowerCase();
  if (/material|texture|surface|color|fabric|finish|材质|纹理|颜色|表面/.test(normalized)) return "material";
  if (/part|component|local|brush|部件|组件|局部|某个部分|当前部分/.test(normalized)) return "part";
  if (/contour|silhouette|outline|shape|form|整体|轮廓|外形|形体|造型/.test(normalized)) return "contour";
  return null;
}

export function nextBubbleScope(scope: BubbleScope | null): BubbleScope {
  if (scope === "contour") return "material";
  if (scope === "material") return "part";
  return "contour";
}
