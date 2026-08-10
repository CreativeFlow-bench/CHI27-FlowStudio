export type WorkspaceContractResult = {
  ok: boolean;
  errors: string[];
  gateQuestionCount: number;
  narrativeCount: number;
};

type Rectangle = { top: number; right: number; bottom: number; left: number; width: number; height: number };

export type WorkspaceLayoutResult = {
  ok: boolean;
  errors: string[];
  hasSolutionSpace: boolean;
  rects: Record<string, Rectangle | null>;
};

function visible(element: Element): boolean {
  const style = window.getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
}

function rectangle(element: Element | null): Rectangle | null {
  if (!element || !visible(element)) return null;
  const value = element.getBoundingClientRect();
  return {
    top: value.top,
    right: value.right,
    bottom: value.bottom,
    left: value.left,
    width: value.width,
    height: value.height,
  };
}

export function inspectWorkspaceHierarchy(root: Document = document): WorkspaceContractResult {
  const errors: string[] = [];
  const behavior = root.querySelector('.ai-behavior-float[aria-label="AI Behavior"]');
  if (!(behavior instanceof HTMLElement) || !visible(behavior)) {
    errors.push("AI Behavior is missing or hidden");
  }

  const narrativeCount = root.querySelectorAll(".ai-behavior-float .ai-behavior-narrative").length;
  if (narrativeCount !== 1) errors.push(`expected one AI narrative, found ${narrativeCount}`);

  const forbiddenCount = root.querySelectorAll(
    ".ai-behavior-float .four-stage-mini, .ai-behavior-float .four-stage-gate, .ai-behavior-float .ai-next-action-card",
  ).length;
  if (forbiddenCount) errors.push(`found ${forbiddenCount} duplicate status or Gate regions`);

  const gateQuestions = Array.from(
    root.querySelectorAll('.planner-clarification-overlay[aria-label="Intent Gate questions"] .planner-bubble > span'),
  ).filter(visible);
  const gateQuestionCount = gateQuestions.length;
  if (gateQuestionCount > 1) errors.push(`expected at most one visible Gate question, found ${gateQuestionCount}`);

  const creative = root.querySelector(".ai-behavior-float .creative-controls-disclosure");
  if (!(creative instanceof HTMLDetailsElement)) errors.push("More Creative disclosure is missing");

  return { ok: errors.length === 0, errors, gateQuestionCount, narrativeCount };
}

export function inspectWorkspaceLayout(root: Document = document): WorkspaceLayoutResult {
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const rects = {
    canvas: rectangle(root.querySelector(".version-canvas-shell")),
    perception: rectangle(root.querySelector(".perception-float")),
    solution: rectangle(root.querySelector(".solution-space-rail")),
    behavior: rectangle(root.querySelector(".ai-behavior-float")),
    composer: rectangle(root.querySelector(".canvas-composer-shell")),
    navigation: rectangle(root.querySelector(".canvas-nav")),
  };
  const errors: string[] = [];
  for (const [name, rect] of Object.entries(rects)) {
    if (!rect && name !== "solution") errors.push(`${name} is missing`);
    if (rect && (rect.left < 0 || rect.top < 0 || rect.right > viewport.width || rect.bottom > viewport.height)) {
      errors.push(`${name} leaves the viewport`);
    }
  }
  if (viewport.width >= 900 && rects.perception && Math.abs(rects.perception.top - 68) > 1) {
    errors.push("Perception top changes with workspace layout state");
  }
  if (root.documentElement.scrollWidth !== root.documentElement.clientWidth) errors.push("horizontal page overflow");
  if (root.documentElement.scrollHeight !== root.documentElement.clientHeight) errors.push("vertical page overflow");
  if (rects.solution && rects.behavior && rects.behavior.top < rects.solution.bottom + 15) {
    errors.push("AI Behavior does not move below Solution Space");
  }
  if (rects.navigation) {
    for (const [name, rect] of Object.entries(rects)) {
      if (name === "navigation" || !rect) continue;
      const horizontalOverlap = Math.min(rects.navigation.right, rect.right) - Math.max(rects.navigation.left, rect.left);
      const verticalOverlap = Math.min(rects.navigation.bottom, rect.bottom) - Math.max(rects.navigation.top, rect.top);
      if (horizontalOverlap > 0 && verticalOverlap > 0) errors.push(`Canvas navigation overlaps ${name}`);
    }
  }
  return {
    ok: errors.length === 0,
    errors,
    hasSolutionSpace: Boolean(rects.solution),
    rects,
  };
}
