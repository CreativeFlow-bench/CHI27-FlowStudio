/**
 * Planner clarification bubbles near the target (refactor plan P1a).
 */
import type { CSSProperties } from "react";
import { Check, X } from "lucide-react";
import type { BubbleScope, Interpretation, PlannerClarificationBubble, SemanticTarget } from "../../types";
import { inferredChangeScope } from "../../utils/scope";
import type { ModelAnchor } from "../StudioCanvas";

export type GateBubbleMode = {
  id?: string;
  intentSeq?: number;
  status?: "planning" | "pending" | "accepted";
  provisional?: boolean;
  question?: string | null;
  busy?: boolean;
  active?: boolean;
  onSelect?: () => void;
  onAccept?: () => void;
  onReject?: () => void;
};

function bubblePlacement(anchor: ModelAnchor | null | undefined, index: number) {
  if (!anchor) {
    const side = index % 3 === 1 ? "right" : index % 3 === 2 ? "top" : "left";
    return { side, style: undefined as CSSProperties | undefined };
  }
  const bubbleWidth = 220;
  const gap = 16;
  const top = Math.max(12, Math.min(
    anchor.columnHeight - 120,
    anchor.top + anchor.height * 0.35 - 24 + index * 96,
  ));
  // Frame-local coords: hang beside the mesh, never clamp back onto it.
  const rightLeft = anchor.left + anchor.width + gap;
  const leftLeft = anchor.left - bubbleWidth - gap;
  const preferLeft = anchor.left >= anchor.columnWidth - (anchor.left + anchor.width);
  const left = preferLeft ? leftLeft : rightLeft;
  return {
    side: preferLeft ? "left" : "right",
    style: {
      position: "absolute",
      left: `${Math.round(left)}px`,
      top: `${Math.round(top)}px`,
      right: "auto",
      bottom: "auto",
      transform: "none",
    } satisfies CSSProperties,
  };
}

export function PlannerClarificationOverlay({
  visible,
  scope,
  interpretation,
  selectedPartLabel,
  clarificationTarget,
  rejectedTargetIds,
  busy,
  onDecide,
  gateMode,
  gateModes,
  modelAnchor = null,
}: {
  visible: boolean;
  scope: BubbleScope | null;
  interpretation: Interpretation | null;
  selectedPartLabel?: string | null;
  clarificationTarget?: SemanticTarget | null;
  rejectedTargetIds?: string[];
  busy?: "accepted" | "rejected" | null;
  onDecide?: (decision: "accepted" | "rejected", label: string) => void;
  gateMode?: GateBubbleMode | null;
  gateModes?: GateBubbleMode[];
  modelAnchor?: ModelAnchor | null;
}) {
  if (!visible) return null;
  const visibleGateModes = gateModes?.length ? gateModes : gateMode ? [gateMode] : [];
  if (visibleGateModes.length) {
    return (
      <div className="planner-clarification-overlay pending multi-gate is-anchored" aria-label="Intent Gate questions">
        {visibleGateModes.map((mode, index) => {
          const placement = bubblePlacement(modelAnchor, index);
          return (
          <div
            className={`planner-bubble ${placement.side} axis revision-slot-${index}${mode.active ? " is-active-revision" : ""}${mode.onSelect ? " is-selectable" : ""}`}
            key={mode.id ?? index}
            style={placement.style}
            role={mode.onSelect ? "button" : undefined}
            tabIndex={mode.onSelect ? 0 : undefined}
            onClick={mode.onSelect}
            onKeyDown={mode.onSelect ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                mode.onSelect?.();
              }
            } : undefined}
          >
            <span>{mode.question || "确认改变这个范围吗？"}</span>
            {mode.status !== "accepted" && mode.onAccept && mode.onReject ? <div className="planner-bubble-actions">
              <button type="button" className="accept" aria-label={`确认意图 ${mode.intentSeq ?? index + 1} 的改变范围`} title="确认改变范围" disabled={mode.busy} onClick={(event) => { event.stopPropagation(); mode.onAccept?.(); }}>
                <Check size={13} />
              </button>
              <button type="button" className="reject" aria-label={`拒绝意图 ${mode.intentSeq ?? index + 1} 的改变范围`} title="暂不改变" disabled={mode.busy} onClick={(event) => { event.stopPropagation(); mode.onReject?.(); }}>
                <X size={13} />
              </button>
            </div> : null}
          </div>
          );
        })}
      </div>
    );
  }
  const bubbles = clarificationTarget
    ? plannerClarificationBubbles(interpretation, selectedPartLabel, clarificationTarget)
    : interpretation
    ? plannerClarificationBubbles(interpretation, selectedPartLabel, null, rejectedTargetIds)
      : scope
        ? [
            {
              id: "planner-primary",
              label: scope === "material" ? "Change material?" : scope === "part" ? "Change part?" : "Change contour?",
              detail:
                scope === "material"
                  ? "确认要改材质/颜色/表面风格吗？"
                  : scope === "part"
                    ? "确认要改当前部件吗？"
                    : "确认要改整体轮廓吗？",
              kind: scope === "part" ? ("target" as const) : ("axis" as const),
              position: "right" as const,
            },
          ]
        : [];
  if (!bubbles.length) return null;
  return (
    <div className="planner-clarification-overlay pending is-anchored" aria-label="Planner clarification bubbles">
      {bubbles.map((bubble, index) => {
        const placement = bubblePlacement(modelAnchor, index);
        return (
        <div
          className={`planner-bubble ${placement.side} ${bubble.kind}`}
          key={bubble.id}
          style={placement.style}
        >
          <span>{bubble.label}</span>
          <strong>{bubble.detail}</strong>
          {onDecide ? (
            <div className="planner-bubble-actions">
              <button
                type="button"
                className="accept"
                aria-label="Accept this change scope"
                title="Accept this change scope"
                onClick={() => onDecide("accepted", bubble.label)}
              >
                <Check size={13} />
              </button>
              <button
                type="button"
                className="reject"
                aria-label="Reject this change scope"
                title="Reject this change scope"
                onClick={() => onDecide("rejected", bubble.label)}
              >
                <X size={13} />
              </button>
            </div>
          ) : null}
        </div>
        );
      })}
    </div>
  );
}
export function plannerClarificationBubbles(
  interpretation: Interpretation | null,
  selectedPartLabel?: string | null,
  clarificationTarget?: SemanticTarget | null,
  rejectedTargetIds?: string[],
): PlannerClarificationBubble[] {
  if (clarificationTarget) {
    const labelZh =
      clarificationTarget.semantic?.label_zh ??
      (clarificationTarget.level === "part"
        ? selectedPartLabel ?? "部件"
        : clarificationTarget.level === "material_region"
          ? "材质区域"
          : "整体轮廓");
    return [
      {
        id: `planner-target-${clarificationTarget.target_id ?? "clarify"}`,
        label: `${labelZh} Change?`,
        detail: `目标层级：${clarificationTarget.level} · 置信 ${Math.round((clarificationTarget.confidence ?? 0) * 100)}%${
          clarificationTarget.requires_clarification ? " · 需确认" : ""
        }`,
        kind: clarificationTarget.level === "part" ? "target" : "axis",
        position: "right",
      },
    ];
  }
  if (!interpretation) return [];
  // Only the first non-rejected target is offered at a time; rejecting it
  // surfaces the next hypothesis instead of stacking bubbles.
  const rejected = new Set(rejectedTargetIds ?? []);
  const targets = (interpretation.semantic_targets ?? []).filter(
    (target) => !rejected.has(target.target_id),
  );
  if (targets.length) {
    return targets.slice(0, 1).map((target, index) => {
      const labelZh =
        target.semantic?.label_zh ??
        (target.level === "silhouette"
          ? "整体轮廓"
          : target.level === "material_region"
            ? "材质区域"
            : target.level === "part"
              ? selectedPartLabel ?? "部件"
              : "整体");
      return {
        id: `planner-target-${index}`,
        label: `${labelZh} Change?`,
        detail: `目标层级：${target.level} · 置信 ${Math.round((target.confidence ?? 0) * 100)}%${
          target.requires_clarification ? " · 需澄清" : ""
        }`,
        kind: target.level === "part" ? "target" : "axis",
        position: index === 0 ? "right" : index === 1 ? "left" : "top",
      };
    });
  }
  const scope = inferredChangeScope(interpretation, selectedPartLabel);
  return [
    {
      id: "planner-primary",
      label: scope === "material" ? "Change material?" : scope === "part" ? "Change part?" : "Change contour?",
      detail:
        scope === "material"
          ? "确认要改材质/颜色/表面风格吗？"
          : scope === "part"
            ? "确认要改当前部件吗？"
            : "确认要改整体轮廓吗？",
      kind: scope === "part" ? "target" : "axis",
      position: "right",
    },
  ];
}
