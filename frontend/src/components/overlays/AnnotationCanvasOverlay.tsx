/**
 * 2D brush annotation overlay (P2).
 *
 * Brush-stamp rendering on a Canvas 2D layer: pen (two ends thin, middle
 * thick), marker (uniform translucent), pencil (fine grain) and eraser.
 * Width is driven by pressure (PointerEvent.pressure) and velocity so the
 * pen stroke looks like a Procreate-style pen nib.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Eraser, Highlighter, Pencil, PenTool, RotateCcw, X } from "lucide-react";
import type { AnnotationPoint, AnnotationStroke, ModelScreenBounds } from "../../types";
import { clamp01 } from "../../utils/format";

export type BrushKind = "pen" | "marker" | "pencil" | "eraser";

export type BrushStroke = {
  brush: BrushKind;
  points: AnnotationPoint[];
};

const BRUSH_OPTIONS: Array<{
  id: BrushKind;
  label: string;
  Icon: typeof PenTool;
}> = [
  { id: "pen", label: "钢笔", Icon: PenTool },
  { id: "marker", label: "马克笔", Icon: Highlighter },
  { id: "pencil", label: "铅笔", Icon: Pencil },
  { id: "eraser", label: "橡皮", Icon: Eraser },
];

const BRUSH_COLORS: Record<Exclude<BrushKind, "eraser">, string> = {
  pen: "#1d4ed8",
  marker: "#f59e0b",
  pencil: "#334155",
};

function stampRadius(
  brush: BrushKind,
  pressure: number,
  velocity: number,
  progress: number,
): number {
  const base = brush === "pen" ? 5.5 : brush === "marker" ? 7 : brush === "pencil" ? 2.2 : 9;
  let width = 1;
  if (brush === "pen") {
    // Two ends thin, middle thick; capped so the nib never gets bloated.
    const taper = 0.42 + 0.58 * Math.sin(Math.PI * clamp01(progress));
    width = taper * (0.72 + 0.28 * clamp01(pressure)) * (0.78 + 0.22 * velocity);
  } else if (brush === "marker") {
    width = 0.9 * (0.8 + 0.2 * pressure);
  } else if (brush === "pencil") {
    width = 0.85;
  } else {
    width = 1.1;
  }
  return Math.max(1.2, base * width);
}

function strokeLength(points: AnnotationPoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const point = points[i];
    total += Math.hypot(point.x - prev.x, point.y - prev.y);
  }
  return Math.max(total, 1e-6);
}

/** Normalized (0..1) points -> canvas pixels within the overlay box. */
function pointToPx(point: AnnotationPoint, width: number, height: number) {
  return { x: point.x * width, y: point.y * height };
}

function renderStamp(
  ctx: CanvasRenderingContext2D,
  brush: BrushKind,
  x: number,
  y: number,
  radius: number,
  alpha: number,
) {
  ctx.save();
  ctx.translate(x, y);
  if (brush === "eraser") {
    ctx.globalCompositeOperation = "destination-out";
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#000";
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    return;
  }
  ctx.globalAlpha = alpha;
  if (brush === "pencil") {
    // Fine grain: a small speckled disc.
    ctx.fillStyle = BRUSH_COLORS.pencil;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, Math.PI * 2);
    ctx.fill();
    for (let i = 0; i < 5; i += 1) {
      const a = (i / 5) * Math.PI * 2 + 0.7;
      ctx.fillRect(Math.cos(a) * radius * 0.55, Math.sin(a) * radius * 0.55, radius * 0.5, radius * 0.5);
    }
  } else {
    // Soft radial nib for pen/marker.
    const gradient = ctx.createRadialGradient(0, 0, radius * 0.08, 0, 0, radius);
    if (brush === "marker") {
      gradient.addColorStop(0, `${BRUSH_COLORS.marker}cc`);
      gradient.addColorStop(1, `${BRUSH_COLORS.marker}22`);
    } else {
      gradient.addColorStop(0, `${BRUSH_COLORS.pen}f2`);
      gradient.addColorStop(1, `${BRUSH_COLORS.pen}18`);
    }
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

export function drawBrushStrokes(
  ctx: CanvasRenderingContext2D,
  strokes: BrushStroke[],
  width: number,
  height: number,
  now = Date.now(),
) {
  void now;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const stroke of strokes) {
    if (stroke.points.length < 2) continue;
    const totalLength = strokeLength(stroke.points);
    let elapsed = 0;
    for (let i = 0; i < stroke.points.length; i += 1) {
      const point = stroke.points[i];
      const px = pointToPx(point, width, height);
      const dt = Math.max(0, (point.t ?? 0) - (stroke.points[i - 1]?.t ?? 0));
      const dx = i > 0 ? px.x - pointToPx(stroke.points[i - 1], width, height).x : 0;
      const dy = i > 0 ? px.y - pointToPx(stroke.points[i - 1], width, height).y : 0;
      const speed = dt > 0 ? Math.hypot(dx, dy) / dt : 0;
      const velocity = clamp01(1 - speed / 2600);
      const pressure = clamp01(point.p ?? 0.5);
      const progress = elapsed / totalLength;
      elapsed += Math.hypot(dx, dy);
      const radius = stampRadius(stroke.brush, pressure, velocity, progress);
      const alpha = stroke.brush === "marker" ? 0.38 : stroke.brush === "pencil" ? 0.85 : 0.9;
      renderStamp(ctx, stroke.brush, px.x, px.y, radius, alpha);
      if (i > 0) {
        // Bridge gaps with a fading line so fast strokes stay connected.
        const prevPx = pointToPx(stroke.points[i - 1], width, height);
        ctx.save();
        if (stroke.brush === "eraser") {
          ctx.globalCompositeOperation = "destination-out";
          ctx.globalAlpha = 1;
          ctx.strokeStyle = "#000";
        } else {
          ctx.globalAlpha = alpha * 0.35;
          ctx.strokeStyle = BRUSH_COLORS[stroke.brush];
        }
        ctx.lineWidth = Math.max(1, radius * 0.7);
        ctx.beginPath();
        ctx.moveTo(prevPx.x, prevPx.y);
        ctx.lineTo(px.x, px.y);
        ctx.stroke();
        ctx.restore();
      }
    }
  }
  ctx.restore();
}

export function AnnotationCanvasOverlay({
  active,
  onCommit,
  onCancel,
  modelBounds = null,
}: {
  active: boolean;
  onCommit: (strokes: AnnotationStroke[], brushStrokes: BrushStroke[]) => void;
  onCancel: () => void;
  modelBounds?: ModelScreenBounds | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const [brush, setBrush] = useState<BrushKind>("pen");
  const [strokes, setStrokes] = useState<BrushStroke[]>([]);
  const [draft, setDraft] = useState<BrushStroke | null>(null);
  const [completed, setCompleted] = useState<{ count: number } | null>(null);
  const [flyPreview, setFlyPreview] = useState<string | null>(null);
  const startTimeRef = useRef(0);
  const brushRef = useRef<BrushKind>("pen");
  const drawingRef = useRef(false);
  const draftRef = useRef<BrushStroke | null>(null);
  brushRef.current = brush;
  draftRef.current = draft;

  const commitDraft = useCallback((finalPoint?: AnnotationPoint) => {
    const current = draftRef.current;
    drawingRef.current = false;
    draftRef.current = null;
    setDraft(null);
    if (!current) return;
    const points = finalPoint ? [...current.points, finalPoint] : current.points;
    if (points.length >= 2) {
      setStrokes((all) => [...all, { ...current, points }]);
    }
  }, []);

  const stopDrawing = useCallback(() => {
    drawingRef.current = false;
    draftRef.current = null;
    setDraft(null);
  }, []);

  const redraw = useCallback((all: BrushStroke[], current: BrushStroke | null) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let rect: DOMRect | null = null;
    try {
      rect = canvas.getBoundingClientRect();
    } catch {
      rect = null;
    }
    if (!rect) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    drawBrushStrokes(ctx, current ? [...all, current] : all, width, height);
  }, []);

  useEffect(() => {
    if (!active) {
      setStrokes([]);
      stopDrawing();
      setCompleted(null);
      setFlyPreview(null);
      return;
    }
    requestAnimationFrame(() => redraw(strokes, null));
  }, [active]);

  useEffect(() => {
    if (!active) return;
    redraw(strokes, draft);
  }, [active, strokes, draft, redraw]);

  useEffect(() => {
    if (!flyPreview) return undefined;
    const timer = window.setTimeout(() => setFlyPreview(null), 780);
    return () => window.clearTimeout(timer);
  }, [flyPreview]);

  // Safety net: if the browser drops pointerup/lostcapture, hovering must not keep inking.
  useEffect(() => {
    if (!active) return undefined;
    const endIfNoButton = (event: PointerEvent) => {
      if (!drawingRef.current) return;
      if ((event.buttons & 1) === 0) commitDraft();
    };
    const endOnBlur = () => {
      if (drawingRef.current) commitDraft();
    };
    window.addEventListener("pointerup", endIfNoButton);
    window.addEventListener("pointercancel", endIfNoButton);
    window.addEventListener("blur", endOnBlur);
    return () => {
      window.removeEventListener("pointerup", endIfNoButton);
      window.removeEventListener("pointercancel", endIfNoButton);
      window.removeEventListener("blur", endOnBlur);
    };
  }, [active, commitDraft]);

  const normalizePoint = useCallback((event: React.PointerEvent<HTMLDivElement>): AnnotationPoint => {
    const target = event.currentTarget ?? event.target;
    if (!(target instanceof HTMLElement)) {
      return { x: 0, y: 0, t: Math.max(0, Date.now() - startTimeRef.current), p: 0.5 };
    }
    let rect: DOMRect | null = null;
    try {
      rect = target.getBoundingClientRect();
    } catch {
      rect = null;
    }
    if (!rect) return { x: 0, y: 0, t: Math.max(0, Date.now() - startTimeRef.current), p: 0.5 };
    return {
      x: clamp01((event.clientX - rect.left) / Math.max(rect.width, 1)),
      y: clamp01((event.clientY - rect.top) / Math.max(rect.height, 1)),
      t: Math.max(0, Date.now() - startTimeRef.current),
      p: clamp01(typeof event.pressure === "number" && event.pressure > 0 ? event.pressure : 0.5),
    };
  }, []);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (completed) return;
    // Primary button only — ignore hover / right-click / stylus hover proximity.
    if (event.button !== 0) return;
    if (event.pointerType === "mouse" && event.buttons !== 1) return;
    event.preventDefault();
    event.stopPropagation();
    const target = event.currentTarget;
    if (target instanceof HTMLElement) {
      try {
        target.setPointerCapture(event.pointerId);
      } catch {
        // pointer capture can throw when the element is not attached; ignore.
      }
    }
    startTimeRef.current = Date.now();
    const next = { brush: brushRef.current, points: [normalizePoint(event)] };
    drawingRef.current = true;
    draftRef.current = next;
    setDraft(next);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drawingRef.current) return;
    // Require primary button held — bare hover must never ink.
    if ((event.buttons & 1) === 0) {
      commitDraft(normalizePoint(event));
      return;
    }
    setDraft((current) => {
      if (!current) return current;
      const next = normalizePoint(event);
      const last = current.points[current.points.length - 1];
      if (last && Math.hypot(last.x - next.x, last.y - next.y) < 0.0025) return current;
      const updated = { ...current, points: [...current.points, next].slice(-360) };
      draftRef.current = updated;
      return updated;
    });
  };

  const finishDrawing = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drawingRef.current) return;
    commitDraft(normalizePoint(event));
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // ignore
    }
  };

  const hasStrokes = useMemo(
    () => strokes.some((stroke) => stroke.points.length >= 2) || (draft?.points.length ?? 0) >= 2,
    [strokes, draft],
  );

  const handleDone = () => {
    const committed = strokes.filter((stroke) => stroke.points.length >= 2);
    if (!committed.length) return;
    const preview = canvasRef.current?.toDataURL("image/jpeg", 0.72) ?? null;
    if (preview) setFlyPreview(preview);
    setCompleted({ count: committed.length });
    const legacyStrokes: AnnotationStroke[] = committed.map((stroke) => stroke.points);
    onCommit(legacyStrokes, committed);
  };

  const doneBarStyle = useMemo(() => {
    if (!modelBounds) return undefined;
    return {
      left: Math.max(12, modelBounds.x + modelBounds.width / 2),
      top: Math.min(
        (overlayRef.current?.clientHeight ?? 640) - 56,
        modelBounds.y + modelBounds.height + 14,
      ),
      bottom: "auto",
      transform: "translateX(-50%)",
    } as React.CSSProperties;
  }, [modelBounds]);

  if (!active) return null;

  return (
    <div
      ref={overlayRef}
      className={`annotation-canvas-overlay${completed ? " is-completed" : ""}`}
      role="presentation"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishDrawing}
      onLostPointerCapture={() => {
        if (!drawingRef.current) return;
        commitDraft();
      }}
      onPointerCancel={() => {
        commitDraft();
      }}
    >
      <canvas ref={canvasRef} className="annotation-brush-canvas" />
      {!completed ? (
        <div className="annotation-hint">
          <span>Please draw — it will be sent to the planner</span>
        </div>
      ) : null}
      {!completed ? (
        <div
          className="annotation-brush-palette"
          role="toolbar"
          aria-label="笔刷"
          onPointerDown={(event) => event.stopPropagation()}
        >
          {BRUSH_OPTIONS.map((option) => {
            const Icon = option.Icon;
            return (
              <button
                key={option.id}
                type="button"
                className={option.id === brush ? "is-active" : ""}
                title={option.label}
                aria-label={option.label}
                aria-pressed={option.id === brush}
                onClick={(event) => {
                  event.stopPropagation();
                  setBrush(option.id);
                }}
              >
                <Icon size={16} strokeWidth={option.id === "marker" ? 2.4 : 2} />
              </button>
            );
          })}
        </div>
      ) : null}
      {!completed ? (
        <div className="annotation-actions" onPointerDown={(event) => event.stopPropagation()}>
          <button type="button" disabled={!strokes.length} onClick={() => setStrokes((current) => current.slice(0, -1))}>
            Undo
          </button>
          <button type="button" disabled={!hasStrokes} onClick={() => setStrokes([])}>
            Clear
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="primary" type="button" disabled={!hasStrokes} onClick={handleDone}>
            Done
          </button>
        </div>
      ) : null}
      {flyPreview ? (
        <div className="annotation-fly-shot" aria-hidden="true">
          <img src={flyPreview} alt="" />
          <span>发给 Planner</span>
        </div>
      ) : null}
      {completed ? (
        <div
          className="annotation-done-bar"
          role="group"
          aria-label="标注完成"
          style={doneBarStyle}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <span className="annotation-done-ask">继续画？</span>
          <button
            type="button"
            className="annotation-done-icon"
            title="继续标注"
            aria-label="继续标注"
            onClick={() => {
              setCompleted(null);
              setStrokes([]);
              setDraft(null);
            }}
          >
            <RotateCcw size={15} />
          </button>
          <button
            type="button"
            className="annotation-done-icon is-primary"
            title="完成退出"
            aria-label="完成退出"
            onClick={onCancel}
          >
            <X size={15} />
          </button>
        </div>
      ) : null}
    </div>
  );
}
