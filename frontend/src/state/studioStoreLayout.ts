import type { LiveSignals } from "../types";
import { computeCenteredActiveCanvasPan } from "../utils/versionGraph";

export function isGenericMeshId(value: string | null | undefined) {
  const text = String(value || "").trim();
  if (!text) return true;
  const lower = text.toLowerCase();
  if (["object", "unknown", "item", "thing", "model", "asset", "部件", "当前部件"].includes(lower)) {
    return true;
  }
  return /^(obj_group_|cube_|mesh_|mball)/i.test(text)
    || /^(cube|sphere|plane|cylinder|torus|mesh|nurbs|suzanne|ico_sphere)(?:\.\d+)?$/i.test(text);
}

export const EMPTY_LIVE_SIGNALS: LiveSignals = {
  dwell_ms: 0,
  compare_dwell_ms: 0,
  new_case_attempt_rate: 0,
  mask_coverage: 0,
  view_mode: "empty",
  viewport_orbit_count: 0,
  viewport_zoom_count: 0,
  local_zoom_count: 0,
  semantic_distance: 0,
  drawing_content: "",
  tool_switch_count: 0,
  reference_match_count: 0,
  hover_count: 0,
  brush_count: 0,
  annotation_count: 0,
};

export function freeCanvasBand(shell?: HTMLElement | null) {
  const shellWidth = shell?.clientWidth
    ?? (typeof window === "undefined" ? 1440 : window.innerWidth);
  const shellHeight = shell?.clientHeight
    ?? (typeof window === "undefined" ? 900 : window.innerHeight);
  let left = 0;
  let top = 0;
  let right = shellWidth;
  let bottom = shellHeight;
  if (shell && typeof window !== "undefined") {
    const shellRect = shell.getBoundingClientRect();
    const perception = document.querySelector<HTMLElement>(".perception-float");
    const ai = document.querySelector<HTMLElement>(".ai-behavior-float");
    const composer = document.querySelector<HTMLElement>(".canvas-composer-shell, .intent-composer-shell, .composer-float");
    const solution = document.querySelector<HTMLElement>(".solution-space-rail");
    const leftBound = Math.max(shellRect.left, perception?.getBoundingClientRect().right ?? shellRect.left);
    const rightBound = Math.min(shellRect.right, ai?.getBoundingClientRect().left ?? shellRect.right);
    const topBound = Math.max(shellRect.top, solution?.getBoundingClientRect().bottom ?? shellRect.top);
    const bottomBound = Math.min(shellRect.bottom, composer?.getBoundingClientRect().top ?? shellRect.bottom);
    if (rightBound > leftBound + 80) {
      left = leftBound - shellRect.left;
      right = rightBound - shellRect.left;
    }
    if (bottomBound > topBound + 80) {
      top = topBound - shellRect.top;
      bottom = bottomBound - shellRect.top;
    }
  }
  return {
    shellWidth,
    shellHeight,
    width: right - left,
    height: bottom - top,
    centerX: (left + right) / 2,
    centerY: (top + bottom) / 2,
  };
}

export function centeredActiveCanvasPan(shell?: HTMLElement | null) {
  const band = freeCanvasBand(shell);
  const active = shell?.querySelector<HTMLElement>(".version-node.active");
  const nodeX = active ? Number.parseFloat(active.style.left || "") || 640 : 640;
  const nodeY = active ? Number.parseFloat(active.style.top || "") || 0 : 0;
  // CSS overrides layout 520 with --active-editor-* — always prefer measured box.
  const nodeWidth = active?.offsetWidth || Math.max(320, band.shellWidth - 48);
  const nodeHeight = active?.offsetHeight || Math.max(360, band.shellHeight - 64);

  return computeCenteredActiveCanvasPan({
    shellWidth: band.shellWidth,
    shellHeight: band.shellHeight,
    targetCenterX: band.centerX,
    targetCenterY: band.shellHeight / 2,
    nodeX,
    nodeY,
    nodeWidth,
    nodeHeight,
  });
}

// Gate is a single transient scope question.  Ignoring it closes the bubble;
// it must never silently accept a direction or start generation.
export const GATE_TIMEOUT_MS = 10_000;
// ponytail: Hunyuan + GPU queue is 3–15 min. 120×1s used to stop watching
// while the worker was still running, so the version card looked hung.
export const HY3D_POLL_MS = 5_000;
export const HY3D_POLL_ATTEMPTS = 360;
export const REVISION_GATED_INTERACTION = true;
