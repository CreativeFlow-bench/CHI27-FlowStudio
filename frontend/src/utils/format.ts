/**
 * Small formatting helpers (refactor plan P1a).
 */
export function clamp01(value: number) {
  return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
}

export function formatScore(value?: number | null) {
  if (value === null || value === undefined) return "none";
  return `${Math.round(value * 100)}%`;
}

export function confidenceTone(value?: number | null) {
  if (typeof value !== "number") return "Waiting";
  if (value >= 0.78) return "正在";
  if (value >= 0.55) return "似乎正在";
  return "可能正在";
}

export function isActiveJobStatus(status?: string | null) {
  if (!status) return false;
  return !["completed", "failed", "cancelled"].includes(status);
}

export function stringValue(value: unknown) {
  return typeof value === "string" && value ? value : "none";
}
