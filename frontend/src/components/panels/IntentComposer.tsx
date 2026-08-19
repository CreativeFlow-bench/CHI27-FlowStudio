/**
 * Intent composer float panel: prompt input, sculpt/annotation tool bar,
 * primitive menu and pending behavior atom tray (refactor plan P1a).
 */
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { MousePointer2, Paintbrush, Pencil, Plus, Send, Trash2, X } from "lucide-react";
import type {
  ActionAtom,
  AssetRecord,
  BehaviorSession,
  CanvasPrimitive,
  SculptTool,
  SessionRecord,
} from "../../types";

export function IntentComposer({
  intentText,
  onIntentChange,
  onIntentFocus,
  onIntentBlur,
  hoverMode,
  onToggleHoverMode,
  sculptTool,
  onToggleSculptTool,
  canShowBrush,
  canShowDrag,
  canShowSculpt,
  annotationMode,
  onToggleAnnotationMode,
  addMenuOpen,
  onToggleAddMenu,
  canvasPrimitive,
  asset,
  activeVersionMeshReady = false,
  generationBusy,
  session,
  visibleBehaviorAtoms,
  behaviorSessions,
  canSendIntent,
  onSend,
  onCreatePrimitive,
  onDeleteBehavior,
  divergenceBusy = false,
  canTriggerDivergence = false,
  onTriggerDivergence,
}: {
  intentText: string;
  onIntentChange: (value: string) => void;
  onIntentFocus: () => void;
  onIntentBlur: () => void;
  hoverMode: boolean;
  onToggleHoverMode: () => void;
  sculptTool: SculptTool | null;
  onToggleSculptTool: (next: SculptTool) => void;
  canShowBrush: boolean;
  canShowDrag: boolean;
  canShowSculpt: boolean;
  annotationMode: boolean;
  onToggleAnnotationMode: () => void;
  addMenuOpen: boolean;
  onToggleAddMenu: () => void;
  canvasPrimitive: CanvasPrimitive;
  asset: AssetRecord | null;
  activeVersionMeshReady?: boolean;
  generationBusy: boolean;
  session: SessionRecord | null;
  visibleBehaviorAtoms: ActionAtom[];
  behaviorSessions: BehaviorSession[];
  canSendIntent: boolean;
  onSend: () => void;
  onCreatePrimitive: (primitive: Exclude<CanvasPrimitive, null>) => void;
  onDeleteBehavior?: (behaviorId: string) => void;
  divergenceBusy?: boolean;
  canTriggerDivergence?: boolean;
  onTriggerDivergence?: () => void;
}) {
  const intentRef = useRef<HTMLTextAreaElement>(null);
  const [selectedBehaviorId, setSelectedBehaviorId] = useState<string | null>(null);
  const behaviors = useMemo(
    () => [...behaviorSessions].sort((a, b) => a.behavior_seq - b.behavior_seq),
    [behaviorSessions],
  );
  const selectedBehavior = behaviors.find((item) => item.behavior_id === selectedBehaviorId) ?? null;
  const sendDisabled = !session || generationBusy || (!canSendIntent && !intentText.trim());

  const handleDeleteBehavior = (behaviorId: string) => {
    onDeleteBehavior?.(behaviorId);
    setSelectedBehaviorId((current) => (current === behaviorId ? null : current));
  };

  useLayoutEffect(() => {
    const field = intentRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${field.scrollHeight}px`;
  }, [intentText]);

  return (
    <div className="canvas-composer-shell">
      {behaviors.length ? (
        <div className="behavior-history-rail" aria-label="Behavior history">
          <div className="behavior-history-label">Action History</div>
          <div className="behavior-dot-list">
            {behaviors.map((behavior) => (
              <div className="behavior-dot-wrap" key={behavior.behavior_id}>
                <button
                  type="button"
                  className={`behavior-dot ${behavior.tool}${behavior.status === "active" ? " is-active" : ""}${selectedBehaviorId === behavior.behavior_id ? " is-selected" : ""}`}
                  data-tooltip={`${behavior.behavior_seq}. ${behavior.tool} · ${behavior.stroke_count} 笔 · ${String(behavior.target.label ?? behavior.target.part_id ?? "整体")}`}
                  aria-label={`查看 Behavior ${behavior.behavior_seq}`}
                  onClick={() => setSelectedBehaviorId((current) => current === behavior.behavior_id ? null : behavior.behavior_id)}
                >
                  {behavior.behavior_seq}
                </button>
                {onDeleteBehavior ? (
                  <button
                    type="button"
                    className="behavior-dot-delete"
                    data-tooltip={`删除 Behavior ${behavior.behavior_seq}`}
                    aria-label={`删除 Behavior ${behavior.behavior_seq}`}
                    onClick={() => handleDeleteBehavior(behavior.behavior_id)}
                  >
                    <X size={7} strokeWidth={2.75} />
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {selectedBehavior ? (
        <section className="behavior-history-inspector" aria-label={`Behavior ${selectedBehavior.behavior_seq} details`}>
          <div className="behavior-inspector-head">
            <strong>Behavior {selectedBehavior.behavior_seq} · {selectedBehavior.tool}</strong>
            <div className="behavior-inspector-actions">
              {onDeleteBehavior ? (
                <button
                  type="button"
                  aria-label={`删除 Behavior ${selectedBehavior.behavior_seq}`}
                  data-tooltip="删除该 behavior"
                  onClick={() => handleDeleteBehavior(selectedBehavior.behavior_id)}
                >
                  <Trash2 size={13} />
                </button>
              ) : null}
              <button type="button" aria-label="Close behavior details" onClick={() => setSelectedBehaviorId(null)}>
                <X size={13} />
              </button>
            </div>
          </div>
        </section>
      ) : null}

      <div
        className={`canvas-composer float-panel${addMenuOpen ? " has-menu" : " is-compact"}`}
        aria-label="Intent composer"
      >
      <textarea
        ref={intentRef}
        name="design-intent"
        rows={1}
        autoComplete="off"
        value={intentText}
        aria-label="Design intent"
        onFocus={onIntentFocus}
        onChange={(event) => onIntentChange(event.target.value)}
        onBlur={onIntentBlur}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && !sendDisabled) {
            event.preventDefault();
            onSend();
          }
        }}
        placeholder="Make this snowman cuter…"
      />
      <div className="canvas-composer-row">
        <div className="composer-tools" aria-label="Intent composer tools">
          <div className="composer-tool-group">
            <button
              type="button"
              className={`icon-tool ${hoverMode ? "is-active" : ""}`}
              aria-label={hoverMode ? "Commit hover mode" : "Hover mode"}
              data-tooltip="Hover Mode (Arrow)"
              disabled={!asset}
              onClick={onToggleHoverMode}
            >
              <MousePointer2 size={17} />
            </button>
            <button type="button" aria-label="Brush sculpt" className={`icon-tool ${sculptTool === "brush" ? "is-active" : ""}`} data-tooltip="Brush Sculpt (Brush)" disabled={!canShowBrush || generationBusy} onClick={() => onToggleSculptTool("brush")}>
              <Paintbrush size={17} />
            </button>
            <button type="button" aria-label="Annotation" className={`icon-tool ${annotationMode ? "is-active" : ""}`} data-tooltip="Annotation (Pencil)" disabled={!asset} onClick={onToggleAnnotationMode}>
              <Pencil size={17} />
            </button>
          </div>
          
          <div className="composer-tool-divider" />
          
          <div className="composer-tool-group">
            <button type="button" aria-label="Drag sculpt" className={`icon-tool tool-asset ${sculptTool === "drag" ? "is-active" : ""}`} data-tooltip="Drag Sculpt (3D Deformation)" disabled={!canShowDrag || generationBusy} onClick={() => onToggleSculptTool("drag")}>
              <img src={`${import.meta.env.BASE_URL}icons/drag.svg`} alt="" width={34} height={38} draggable={false} />
            </button>
            <button type="button" aria-label="Smooth sculpt" className={`icon-tool tool-asset ${sculptTool === "smooth" ? "is-active" : ""}`} data-tooltip="Smooth Sculpt (3D Brush)" disabled={!canShowSculpt} onClick={() => onToggleSculptTool("smooth")}>
              <img src={`${import.meta.env.BASE_URL}icons/smooth.svg`} alt="" width={34} height={38} draggable={false} />
            </button>
            <button
              type="button"
              className={`icon-tool tool-pink${canvasPrimitive ? " is-active" : ""}`}
              aria-label="Add primitive"
              data-tooltip="Add Primitive (Plus)"
              disabled={!asset && !canvasPrimitive && !activeVersionMeshReady}
              onClick={onToggleAddMenu}
            >
              <Plus size={18} />
            </button>
          </div>
          
          <div className="composer-tool-divider" />

          <button
            type="button"
            className={`icon-tool tool-asset${divergenceBusy ? " is-active" : ""}`}
            aria-label="Keyword divergence"
            data-tooltip="Keyword Divergence (Magic Potion)"
            disabled={!canTriggerDivergence || divergenceBusy || generationBusy}
            onClick={() => onTriggerDivergence?.()}
          >
            <img src={`${import.meta.env.BASE_URL}icons/mana.svg`} alt="" width={38} height={38} draggable={false} />
          </button>
        </div>
        <div className="composer-actions">
          <button
            type="button"
            className="composer-action send"
            aria-label="Send intent"
            data-tooltip="提交到四阶段管线（推进方向决策 / 触发生成）"
            disabled={sendDisabled}
            onClick={onSend}
          >
            <Send size={17} />
          </button>
        </div>
      </div>
      {addMenuOpen ? (
        <div className="primitive-menu" aria-label="Add primitive menu">
          {(
            [
              ["plane", "Plane"],
              ["cube", "Cube"],
              ["circle", "Circle"],
              ["sphere", "UV Sphere"],
              ["ico_sphere", "Ico Sphere"],
              ["cylinder", "Cylinder"],
              ["cone", "Cone"],
              ["torus", "Torus"],
            ] as Array<[Exclude<CanvasPrimitive, null>, string]>
          ).map(([primitive, label]) => (
            <button
              key={primitive}
              type="button"
              onClick={() => {
                onToggleAddMenu();
                onCreatePrimitive(primitive);
              }}
            >
              <span className={`wire ${primitive === "sphere" || primitive === "ico_sphere" || primitive === "torus" ? "sphere" : primitive === "cylinder" || primitive === "cone" ? "cylinder" : ""}`} />
              {label}
            </button>
          ))}
        </div>
      ) : null}
      </div>
    </div>
  );
}
