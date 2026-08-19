/**
 * Version canvas shell: pannable/zoomable canvas with ThreeViewport,
 * branch thumbnails and sculpt controls panel.
 */
import { cloneElement, useEffect, useLayoutEffect, useRef, useState, type ReactElement } from "react";
import { createPortal } from "react-dom";
import { Box, GripHorizontal, Maximize2, RotateCcw, Trash2, X } from "lucide-react";
import type {
  AnnotationStroke,
  AssetRecord,
  BehaviorSession,
  BehaviorViewSet,
  CanvasDisplayMode,
  Candidate,
  CanvasPrimitive,
  CanvasTool,
  ModelScreenBounds,
  PartRecord,
  SculptTool,
  VersionNodeStatus,
  ViewportInteractionSignal,
} from "../types";
import type { ThreeViewportHandle } from "../types";
import { ThreeViewport } from "./ThreeViewport";
import { AnnotationCanvasOverlay } from "./overlays/AnnotationCanvasOverlay";
import { compactVersionLabel, FLOWSTUDIO_CANDIDATE_MIME } from "../utils/versionGraph";
import { partSegmentationUrl } from "../utils/appHelpers";

// Native drag payload: application/x-flowstudio-candidate.

export type VersionCanvasNode = {
  id: string;
  kind: "source" | "branch";
  versionNumber: number;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  previewUrl: string | null;
  meshUrl: string | null;
  objUrl: string | null;
  status: VersionNodeStatus;
  error: string | null;
  isActivePath: boolean;
  candidate: Candidate | null;
};

export type VersionCanvasLink = {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  controlX1: number;
  controlX2: number;
  isActivePath: boolean;
};

function Hy3dProgressTicker({
  active,
  message,
  progress,
}: {
  active: boolean;
  message: string | null;
  progress: number;
}) {
  if (!active) return null;
  const pct = Math.round(Math.max(0, Math.min(1, progress)) * 100);
  const text = (message ?? "").trim() || "Hunyuan3D 运行中";
  const line = pct > 0 ? `${text} · ${pct}%` : text;
  return (
    <div className="version-hy3d-progress" role="status" aria-live="polite" aria-label="3D 生成进度">
      <span key={line} className="version-hy3d-progress-line">{line}</span>
    </div>
  );
}

function VersionPreviewImage({ src, alt }: { src: string; alt: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [fallback, setFallback] = useState(false);
  useEffect(() => {
    let revoked = false;
    setFallback(false);
    const img = new Image();
    if (/^https?:/i.test(src) && !src.startsWith(window.location.origin)) {
      img.crossOrigin = "anonymous";
    }
    img.onload = () => {
      const canvas = canvasRef.current;
      if (!canvas || revoked) return;
      canvas.width = img.naturalWidth || 520;
      canvas.height = img.naturalHeight || 520;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        setFallback(true);
        return;
      }
      ctx.drawImage(img, 0, 0);
      try {
        const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const pixels = data.data;
        for (let i = 0; i < pixels.length; i += 4) {
          const r = pixels[i];
          const g = pixels[i + 1];
          const b = pixels[i + 2];
          const luma = 0.299 * r + 0.587 * g + 0.114 * b;
          const spread = Math.max(r, g, b) - Math.min(r, g, b);
          if (luma > 242 && spread < 18) pixels[i + 3] = 0;
        }
        ctx.putImageData(data, 0, 0);
      } catch {
        setFallback(true);
      }
    };
    img.onerror = () => setFallback(true);
    img.src = src;
    return () => {
      revoked = true;
    };
  }, [src]);
  return (
    <>
      <canvas className="version-active-image" ref={canvasRef} aria-label={alt} hidden={fallback} />
      {fallback ? <img className="version-active-image" src={src} alt={alt} width={520} height={520} /> : null}
    </>
  );
}

export type CanvasPanState = { x: number; y: number };

export type EditorSceneLike = {
  setGeometry(geometry: unknown): void;
  canUndo: boolean;
  canRedo: boolean;
  editOps(): unknown[];
};

export type CanvasDragRef = {
  active: boolean;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
};

export type ModelAnchor = {
  left: number;
  top: number;
  width: number;
  height: number;
  columnWidth: number;
  columnHeight: number;
};

export function VersionCanvas({
  shellRef,
  dragRef,
  canvasPan,
  onPanChange,
  canvasZoom,
  zoomCanvasBy,
  spacePanArmed,
  versionNodes,
  versionLinks,
  threeViewportRef,
  asset,
  activePreviewUrl,
  activePreviewLabel,
  onClearPreview,
  selectedPart,
  hoverLabel,
  hoverMaskDataUrl,
  canvasPrimitive,
  canvasTool,
  canvasDisplayMode,
  parts,
  onSelectPart,
  onHoverPart,
  onViewportInteraction,
  sculptTool,
  onSculptAction,
  sculptRadius,
  sculptStrength,
  editorScene,
  annotationMode,
  onCancelAnnotation,
  onCommitAnnotation,
  onPreviewBranch,
  activeVersionId,
  versionViewMode,
  onHighlightVersion,
  onActivateVersion,
  onShowOverview,
  onDeleteVersion,
  versionCandidates,
  onDropCandidate,
  onRetryVersionNode,
  gatePlanning = false,
  acceptedIntentMarkers = [],
  gateOverlay = null,
  hy3dProgress = null,
}: {
  shellRef: React.RefObject<HTMLDivElement | null>;
  dragRef: React.MutableRefObject<CanvasDragRef | null>;
  canvasPan: CanvasPanState;
  onPanChange: (pan: CanvasPanState) => void;
  canvasZoom: number;
  zoomCanvasBy: (factor: number) => void;
  spacePanArmed: boolean;
  versionNodes: VersionCanvasNode[];
  versionLinks: VersionCanvasLink[];
  threeViewportRef: React.RefObject<ThreeViewportHandle | null>;
  asset: AssetRecord | null;
  activePreviewUrl: string | null;
  activePreviewLabel: string | null;
  onClearPreview: () => void;
  selectedPart: string;
  hoverLabel: string | null;
  hoverMaskDataUrl?: string | null;
  canvasPrimitive: CanvasPrimitive;
  canvasTool: CanvasTool;
  canvasDisplayMode: CanvasDisplayMode;
  parts: PartRecord[];
  onSelectPart: (part: string, source: "click" | "hover") => void;
  onHoverPart: (part: string, source: "click" | "hover") => void;
  onViewportInteraction: (signal: ViewportInteractionSignal) => void;
  sculptTool: SculptTool | null;
  onSculptAction: (tool: SculptTool, evidence: Record<string, unknown>) => void;
  sculptRadius: number;
  sculptStrength: number;
  editorScene: EditorSceneLike;
  annotationMode: boolean;
  onCancelAnnotation: () => void;
  onCommitAnnotation: (strokes: AnnotationStroke[], brushStrokes?: Array<{ brush: string; points: AnnotationStroke }>) => void;
  onPreviewBranch: (candidate: Candidate) => void;
  activeVersionId: string;
  versionViewMode: "active" | "overview";
  onHighlightVersion: (nodeId: string, candidate: Candidate | null) => void;
  onActivateVersion: (nodeId: string, candidate: Candidate | null) => void;
  onShowOverview: () => void;
  onDeleteVersion?: (nodeId: string) => void | Promise<void>;
  versionCandidates: Candidate[];
  onDropCandidate: (candidate: Candidate) => void | Promise<void>;
  onRetryVersionNode: (nodeId: string) => void | Promise<void>;
  gatePlanning?: boolean;
  acceptedIntentMarkers?: Array<{ id: string; intentSeq: number; label: string; detail?: string }>;
  gateOverlay?: ReactElement<{ modelAnchor?: ModelAnchor | null }> | null;
  hy3dProgress?: { message: string; progress: number } | null;
}) {
  const [dropTargetActive, setDropTargetActive] = useState(false);
  const [modelBounds, setModelBounds] = useState<ModelScreenBounds | null>(null);
  const [meshAnchor, setMeshAnchor] = useState<ModelAnchor | null>(null);
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const bounds = threeViewportRef.current?.getModelScreenBounds?.() ?? null;
      setModelBounds((current) => {
        if (!bounds && !current) return current;
        if (
          bounds
          && current
          && Math.abs(bounds.x - current.x) < 0.5
          && Math.abs(bounds.y - current.y) < 0.5
          && Math.abs(bounds.width - current.width) < 0.5
          && Math.abs(bounds.height - current.height) < 0.5
        ) {
          return current;
        }
        return bounds;
      });
      const frameEl = shellRef.current?.querySelector(".version-node.active .version-node-frame") as HTMLElement | null;
      if (!bounds || !frameEl) {
        setMeshAnchor(null);
      } else {
        const next = {
          left: bounds.x,
          top: bounds.y,
          width: bounds.width,
          height: bounds.height,
          columnWidth: frameEl.clientWidth,
          columnHeight: frameEl.clientHeight,
        };
        setMeshAnchor((current) => {
          if (
            current
            && Math.abs(current.left - next.left) < 0.5
            && Math.abs(current.top - next.top) < 0.5
            && Math.abs(current.width - next.width) < 0.5
            && Math.abs(current.height - next.height) < 0.5
            && Math.abs(current.columnWidth - next.columnWidth) < 0.5
            && Math.abs(current.columnHeight - next.columnHeight) < 0.5
          ) {
            return current;
          }
          return next;
        });
      }
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [shellRef, threeViewportRef]);
  const [shellHost, setShellHost] = useState<HTMLElement | null>(null);
  useLayoutEffect(() => {
    setShellHost(document.querySelector("main.studio-shell"));
  }, []);
  const shell = (
    <div
      className={`version-canvas-shell${dropTargetActive ? " is-drop-target" : ""}`}
      aria-label="Version history canvas drop target"
      ref={shellRef}
      onDragEnter={(event) => {
        if (!event.dataTransfer.types.includes(FLOWSTUDIO_CANDIDATE_MIME)) return;
        event.preventDefault();
        setDropTargetActive(true);
      }}
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes(FLOWSTUDIO_CANDIDATE_MIME)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDropTargetActive(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDropTargetActive(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDropTargetActive(false);
        const raw = event.dataTransfer.getData(FLOWSTUDIO_CANDIDATE_MIME);
        if (!raw) return;
        try {
          const payload = JSON.parse(raw) as { candidateId?: string };
          const candidate = versionCandidates.find((item) => item.candidate_id === payload.candidateId);
          if (candidate) void onDropCandidate(candidate);
        } catch {
          // Ignore malformed payloads from outside FlowStudio.
        }
      }}
      onWheel={(event) => {
        if (event.ctrlKey || event.metaKey) {
          // Trackpad pinch over the 3D viewport must zoom the camera only;
          // the 2D canvas zoom is reserved for the empty canvas area.
          const target = event.target as HTMLElement | null;
          if (target && !target.closest(".version-node-frame, .version-thumb-viewport")) {
            event.preventDefault();
            zoomCanvasBy(event.deltaY > 0 ? 0.9 : 1.1);
          }
        }
      }}
      onPointerDown={(event) => {
        const target = event.target as HTMLElement | null;
        // Do not steal pointer capture from the active 3D viewport / annotation
        // surface — otherwise OrbitControls / brush miss pointerup and the
        // canvas pan hijacks the stroke into a drag.
        if (
          target?.closest(
            ".viewport, .viewport-wrap, .version-node-frame, .annotation-canvas-overlay, .canvas-drag-handle, button, a, input, textarea, select",
          )
        ) {
          return;
        }
        if (!(spacePanArmed || event.button === 0 || event.button === 1 || event.altKey)) return;
        dragRef.current = {
          active: true,
          startX: event.clientX,
          startY: event.clientY,
          originX: canvasPan.x,
          originY: canvasPan.y,
        };
        (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag?.active) return;
        onPanChange({
          x: drag.originX + (event.clientX - drag.startX),
          y: drag.originY + (event.clientY - drag.startY),
        });
      }}
      onPointerUp={() => {
        if (dragRef.current) dragRef.current.active = false;
      }}
    >
      {dropTargetActive ? <div className="version-drop-hint">释放以创建下一版本</div> : null}
      <button
        type="button"
        className="canvas-drag-handle"
        aria-label="拖动画布"
        title="拖动画布"
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          dragRef.current = {
            active: true,
            startX: event.clientX,
            startY: event.clientY,
            originX: canvasPan.x,
            originY: canvasPan.y,
          };
          (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
          event.stopPropagation();
        }}
      >
        <GripHorizontal size={14} aria-hidden="true" />
        <span>拖动</span>
      </button>
      <div
        className="version-canvas-world"
        style={{ transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${canvasZoom})` }}
      >
        <svg className="version-canvas-links" aria-hidden="true">
          {versionLinks.map((link) => (
            <path
              key={link.id}
              className={`version-link${link.isActivePath ? " is-active-path" : ""}`}
              d={`M ${link.x1} ${link.y1} C ${link.controlX1} ${link.y1}, ${link.controlX2} ${link.y2}, ${link.x2} ${link.y2}`}
            />
          ))}
        </svg>

        {versionNodes.map((node) => {
          const liveMesh = Boolean(
            node.meshUrl
            || node.objUrl
            || (node.kind === "source" && (asset?.mesh_url || asset?.obj_url)),
          );
          return node.id === activeVersionId && versionViewMode === "active" ? (
            <div
              className={`version-node active status-${node.status}${node.isActivePath ? " is-active-path" : ""}`}
              key={node.id}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
            >
              <div className="version-node-meta">
                <strong>V{node.versionNumber}</strong>
                <span>{compactVersionLabel(node.label)}</span>
                <button type="button" aria-label="查看全部版本" title="查看全部版本" onClick={onShowOverview}>
                  <Maximize2 size={15} aria-hidden="true" />
                </button>
                {onDeleteVersion && versionNodes.length > 1 ? (
                  <button
                    type="button"
                    className="is-danger"
                    aria-label={`删除 Version ${node.versionNumber}`}
                    title="删除此版本"
                    onClick={() => void onDeleteVersion(node.id)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                ) : null}
              </div>
              <div className={`version-node-frame${gatePlanning ? " is-gate-planning" : ""}`}>
                {node.status === "mesh_ready" ? <ThreeViewport
                  ref={threeViewportRef}
                  asset={asset}
                  previewMeshUrl={partSegmentationUrl(parts) ?? node.meshUrl ?? node.objUrl ?? activePreviewUrl}
                  previewLabel={activePreviewLabel}
                  onClearPreview={onClearPreview}
                  selectedPart={selectedPart}
                  hoverLabel={hoverLabel}
                  hoverMaskDataUrl={hoverMaskDataUrl}
                  primitive={canvasPrimitive}
                  tool={canvasTool}
                  displayMode={canvasDisplayMode}
                  parts={parts}
                  onSelectPart={(part) => onSelectPart(part, "click")}
                  onHoverPart={(part) => onHoverPart(part, "hover")}
                  onViewportInteraction={onViewportInteraction}
                  sculptTool={sculptTool}
                  onSculptAction={onSculptAction}
                  sculptRadius={sculptRadius}
                  sculptStrength={sculptStrength}
                  canvasZoom={canvasZoom}
                  onGeometryReady={(geometry) => editorScene.setGeometry(geometry)}
                /> : node.previewUrl ? <VersionPreviewImage src={node.previewUrl} alt={node.label} /> : <div className="version-thumb-fallback"><Box size={32} /></div>}
                {node.status === "mesh_ready" ? <AnnotationCanvasOverlay
                  active={annotationMode}
                  onCancel={onCancelAnnotation}
                  onCommit={onCommitAnnotation}
                  modelBounds={modelBounds}
                /> : null}
                <Hy3dProgressTicker
                  active={node.status === "generating_3d"}
                  message={hy3dProgress?.message ?? null}
                  progress={hy3dProgress?.progress ?? 0}
                />
                {node.status !== "mesh_ready" ? (
                <button
                  type="button"
                  className="version-retry"
                  aria-label={node.status === "generating_3d" ? `重试 Version ${node.versionNumber} 的 3D 生成` : `生成 Version ${node.versionNumber} 的 3D`}
                  onClick={(event) => {
                    event.stopPropagation();
                    void onRetryVersionNode(node.id);
                  }}
                >
                  {node.status === "generating_3d" ? "生成中…" : node.status === "mesh_failed" ? "重试 3D" : "生成 3D"}
                </button>
              ) : null}
              {gatePlanning ? (
                  <div className="gate-planning-orbit" role="status" aria-live="polite" aria-label="正在生成 Gate">
                    <span className="gate-planning-ring" aria-hidden="true" />
                    <span className="gate-planning-label">Generating Gate…</span>
                  </div>
                ) : null}
                {acceptedIntentMarkers.length ? (
                  <div
                    className="accepted-intent-markers"
                    aria-label="已接受的意图"
                    style={modelBounds ? {
                      left: Math.max(8, modelBounds.x + 2),
                      top: Math.max(8, modelBounds.y + modelBounds.height - 18),
                      bottom: "auto",
                    } : undefined}
                  >
                    {acceptedIntentMarkers.map((marker) => (
                      <button
                        type="button"
                        className="accepted-intent-dot"
                        key={marker.id}
                        title={`${marker.label}${marker.detail ? `\n${marker.detail}` : ""}`}
                        aria-label={`意图 ${marker.intentSeq}：${marker.label}`}
                      >
                        <span className="accepted-intent-pulse" aria-hidden="true" />
                        <span className="accepted-intent-tooltip" role="tooltip">
                          <strong>意图 {marker.intentSeq}</strong>
                          <span>{marker.label}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
                {gateOverlay ? cloneElement(gateOverlay, { modelAnchor: meshAnchor }) : null}
              </div>
            </div>
          ) : (
            <div
              role="button"
              tabIndex={0}
              className={`version-node thumbnail status-${node.status}${node.isActivePath ? " is-active-path" : ""}${node.id === activeVersionId ? " is-active-version" : ""}${liveMesh ? " has-live-mesh" : ""}`}
              key={node.id}
              style={{
                left: node.x,
                top: node.y,
                width: node.width,
                height: node.height,
              }}
              onClick={() => {
                if (versionViewMode === "overview") {
                  onHighlightVersion(node.id, node.candidate);
                  return;
                }
                onActivateVersion(node.id, node.candidate);
              }}
              onDoubleClick={() => onActivateVersion(node.id, node.candidate)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onActivateVersion(node.id, node.candidate);
                  return;
                }
                if (event.key === " ") {
                  event.preventDefault();
                  onHighlightVersion(node.id, node.candidate);
                }
              }}
              title={
                versionViewMode === "overview"
                  ? (node.id === activeVersionId ? "当前接入点 · 双击进入" : "单击高亮接入点 · 双击进入")
                  : (node.id === activeVersionId ? "重新进入当前版本" : "进入该版本")
              }
            >
              {liveMesh ? (
                <div className="version-thumb-viewport">
                  <ThreeViewport
                    asset={node.kind === "source" ? asset : null}
                    previewMeshUrl={node.meshUrl ?? node.objUrl}
                    previewLabel={null}
                    onClearPreview={() => undefined}
                    selectedPart=""
                    hoverLabel={null}
                    primitive={null}
                    tool="select"
                    displayMode="textured"
                    parts={[]}
                    onSelectPart={() => undefined}
                    onHoverPart={() => undefined}
                    onViewportInteraction={() => undefined}
                    sculptTool={null}
                    onSculptAction={() => undefined}
                    sculptRadius={0.28}
                    sculptStrength={0.35}
                    canvasZoom={canvasZoom}
                  />
                </div>
              ) : node.previewUrl ? (
                <div className="version-thumb-media">
                  <VersionPreviewImage src={node.previewUrl} alt={node.label} />
                </div>
              ) : (
                <div className="version-thumb-fallback">
                  <Box size={22} />
                </div>
              )}
              <strong>Version {node.versionNumber}</strong>
              {node.status !== "mesh_ready" ? (
                <span
                  className="version-retry-inline"
                  role="button"
                  tabIndex={0}
                  aria-label={`重试 Version ${node.versionNumber} 的 3D 生成`}
                  onClick={(event) => {
                    event.stopPropagation();
                    void onRetryVersionNode(node.id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      event.stopPropagation();
                      void onRetryVersionNode(node.id);
                    }
                  }}
                >
                  {node.status === "generating_3d" || node.status === "mesh_failed" ? "重试" : "生成 3D"}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
  return shellHost ? createPortal(shell, shellHost) : shell;
}

export function SculptControlsPanel({
  sculptTool,
  onExit,
  onContinueSculpt,
  sculptRadius,
  onRadiusChange,
  sculptStrength,
  onStrengthChange,
  onCommitVersion,
  onDoneBehavior,
  editorScene,
  asset,
}: {
  sculptTool: SculptTool;
  onExit: () => void;
  onContinueSculpt: () => void;
  sculptRadius: number;
  onRadiusChange: (value: number) => void;
  sculptStrength: number;
  onStrengthChange: (value: number) => void;
  onCommitVersion: () => void;
  onDoneBehavior: () => Promise<{
    behavior: BehaviorSession | null;
    endViews: BehaviorViewSet;
  }>;
  editorScene: EditorSceneLike;
  asset: AssetRecord | null;
}) {
  const [donePreview, setDonePreview] = useState<{
    strokes: number;
    views: BehaviorViewSet;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const strokeCount = editorScene.editOps().length;
  const canDone = strokeCount > 0 && !busy && !donePreview;
  const toolLabel =
    sculptTool === "drag" ? "Drag" : sculptTool === "brush" ? "Brush" : "Smooth";
  const toolHint =
    sculptTool === "drag"
      ? "按住拖动变形"
      : sculptTool === "brush"
        ? "按住雕刻 · Shift 凹陷"
        : "按住平滑";

  const handleDone = async () => {
    if (!canDone) return;
    setBusy(true);
    try {
      const result = await onDoneBehavior();
      if (!result.behavior) return;
      setDonePreview({
        strokes: result.behavior.stroke_count || strokeCount,
        views: result.endViews,
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="sculpt-float-panel" aria-label="Sculpt controls">
        <div className="sculpt-panel-head">
          <span className="sculpt-panel-title">Sculpt · {toolLabel}</span>
          <span className="sculpt-panel-meta">
            {strokeCount} 笔
            {editorScene.canUndo ? " · 可撤销" : ""}
            {asset?.metadata?.current_version_id ? " · 已存版本" : ""}
          </span>
          <button
            className="sculpt-exit"
            type="button"
            title="退出雕刻"
            aria-label="退出雕刻"
            onClick={() => {
              setDonePreview(null);
              onExit();
            }}
          >
            <X size={13} />
          </button>
        </div>
        {!donePreview ? (
          <>
            <div className="sculpt-sliders">
              <label>
                <span>大小</span>
                <input
                  type="range"
                  min="0.05"
                  max="0.8"
                  step="0.05"
                  value={sculptRadius}
                  onChange={(event) => onRadiusChange(Number(event.target.value))}
                />
                <em>{sculptRadius.toFixed(2)}</em>
              </label>
              <label>
                <span>力度</span>
                <input
                  type="range"
                  min="0.05"
                  max="0.6"
                  step="0.05"
                  value={sculptStrength}
                  onChange={(event) => onStrengthChange(Number(event.target.value))}
                />
                <em>{sculptStrength.toFixed(2)}</em>
              </label>
            </div>
            <div className="sculpt-actions">
              <p className="sculpt-hint">{toolHint}</p>
              <button className="sculpt-save" type="button" disabled={busy} onClick={onCommitVersion}>
                保存版本
              </button>
              <button
                className="sculpt-done"
                type="button"
                disabled={!canDone}
                onClick={() => void handleDone()}
              >
                {busy ? "…" : "Done"}
              </button>
            </div>
          </>
        ) : (
          <div className="sculpt-done-summary">
            <strong>已保存 {donePreview.strokes} 笔 · Behavior</strong>
            <div className="sculpt-done-views">
              {(["front", "side", "top"] as const).map((view) => {
                const src = donePreview.views[view];
                return src ? (
                  <img key={view} src={src} alt={view} width={72} height={48} />
                ) : (
                  <span key={view}>{view}</span>
                );
              })}
            </div>
          </div>
        )}
      </div>
      {donePreview ? (
        <div className="sculpt-done-bar" role="group" aria-label="雕刻完成">
          <span className="annotation-done-ask">继续雕？</span>
          <button
            type="button"
            className="annotation-done-icon"
            title="继续雕刻"
            aria-label="继续雕刻"
            onClick={() => {
              onContinueSculpt();
              setDonePreview(null);
            }}
          >
            <RotateCcw size={15} />
          </button>
          <button
            type="button"
            className="annotation-done-icon is-primary"
            title="完成退出"
            aria-label="完成退出"
            onClick={() => {
              setDonePreview(null);
              onExit();
            }}
          >
            <X size={15} />
          </button>
        </div>
      ) : null}
    </>
  );
}
