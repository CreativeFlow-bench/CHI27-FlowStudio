/**
 * Generic UI primitives (refactor plan P1a).
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function ResizableShell({
  className,
  ariaLabel,
  defaultWidth,
  defaultHeight,
  minWidth = 200,
  minHeight = 120,
  maxWidth = 720,
  maxHeight = 900,
  handleCorner = "se",
  handlePosition = "absolute",
  movable = false,
  resizable = true,
  style,
  children,
  onSizeChange,
}: {
  className: string;
  ariaLabel?: string;
  defaultWidth: number;
  defaultHeight?: number;
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  handleCorner?: "se" | "sw" | "ne" | "nw";
  handlePosition?: "absolute" | "static";
  movable?: boolean;
  resizable?: boolean;
  style?: React.CSSProperties;
  children: React.ReactNode;
  onSizeChange?: (size: { w: number; h: number }) => void;
}) {
  const [size, setSize] = useState({ w: defaultWidth, h: defaultHeight ?? 0 });
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startW: number;
    startH: number;
  } | null>(null);
  const moveRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const onSizeChangeRef = useRef(onSizeChange);
  onSizeChangeRef.current = onSizeChange;

  const clampSize = (current: { w: number; h: number }) => {
    const viewportMaxWidth = Math.max(1, Math.min(maxWidth, window.innerWidth - 40));
    const viewportMaxHeight = Math.max(1, Math.min(maxHeight, window.innerHeight - 40));
    return {
      w: Math.min(viewportMaxWidth, Math.max(Math.min(minWidth, viewportMaxWidth), current.w)),
      h: Math.min(viewportMaxHeight, Math.max(Math.min(minHeight, viewportMaxHeight), current.h)),
    };
  };

  useEffect(() => {
    const keepInsideViewport = () => {
      const nextSize = clampSize(size);
      setSize(nextSize);
      setPosition((current) => current ? {
        x: Math.max(0, Math.min(window.innerWidth - nextSize.w, current.x)),
        y: Math.max(0, Math.min(window.innerHeight - nextSize.h, current.y)),
      } : null);
    };
    keepInsideViewport();
    window.addEventListener("resize", keepInsideViewport);
    return () => window.removeEventListener("resize", keepInsideViewport);
  }, [maxHeight, maxWidth, minHeight, minWidth, size.h, size.w]);

  useEffect(() => {
    onSizeChangeRef.current?.(size);
  }, [size.h, size.w]);

  const onMoveStart = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!movable || event.button !== 0 || !(event.target as Element).closest(".float-panel-label")) return;
    const rect = event.currentTarget.getBoundingClientRect();
    moveRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: rect.left,
      originY: rect.top,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const move = moveRef.current;
    if (!move || move.pointerId !== event.pointerId) return;
    setPosition({
      x: Math.max(0, Math.min(Math.max(0, window.innerWidth - size.w), move.originX + event.clientX - move.startX)),
      y: Math.max(0, Math.min(Math.max(0, window.innerHeight - size.h), move.originY + event.clientY - move.startY)),
    });
  };

  const onMoveEnd = (event: React.PointerEvent<HTMLDivElement>) => {
    if (moveRef.current?.pointerId === event.pointerId) moveRef.current = null;
  };

  const onMoveKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!movable || event.target !== event.currentTarget) return;
    const step = event.shiftKey ? 40 : 16;
    const delta = {
      ArrowLeft: { x: -step, y: 0 },
      ArrowRight: { x: step, y: 0 },
      ArrowUp: { x: 0, y: -step },
      ArrowDown: { x: 0, y: step },
    }[event.key];
    if (!delta) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    setPosition({
      x: Math.max(0, Math.min(Math.max(0, window.innerWidth - size.w), rect.left + delta.x)),
      y: Math.max(0, Math.min(Math.max(0, window.innerHeight - size.h), rect.top + delta.y)),
    });
  };

  const onPointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startW: size.w,
      startH: size.h,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;
    const dx = handleCorner === "sw" || handleCorner === "nw" ? -deltaX : deltaX;
    const dy = handleCorner === "ne" || handleCorner === "nw" ? -deltaY : deltaY;
    setSize(clampSize({
      w: drag.startW + dx,
      h: drag.startH + dy,
    }));
  };

  const onPointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  };

  const onResizeKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    const step = event.shiftKey ? 40 : 16;
    const delta = {
      ArrowLeft: { w: -step, h: 0 },
      ArrowRight: { w: step, h: 0 },
      ArrowUp: { w: 0, h: -step },
      ArrowDown: { w: 0, h: step },
    }[event.key];
    if (!delta) return;
    event.preventDefault();
    setSize((current) => clampSize({ w: current.w + delta.w, h: current.h + delta.h }));
  };

  const shellStyle: React.CSSProperties = handlePosition === "static"
    ? {
        ...style,
        // Static mode: don't claim position. Surface size as CSS variables so
        // the inner panel can opt in via `width: var(--shell-width, …)`.
        ["--shell-width" as string]: `${size.w}px`,
        ["--shell-height" as string]: `${size.h}px`,
        ["--shell-min-width" as string]: `${minWidth}px`,
        ["--shell-min-height" as string]: `${minHeight}px`,
        ["--shell-max-width" as string]: `${maxWidth}px`,
        ["--shell-max-height" as string]: `${maxHeight}px`,
      }
    : {
        ...style,
        width: size.w,
        height: size.h,
        ...(position ? { left: position.x, top: position.y, right: "auto", transform: "none" } : {}),
      };

  // In static mode, the inner panel owns its own positioning (usually
  // `position: fixed`). The wrapper itself is zero-sized, so any absolute
  // resize handle rendered inside the wrapper will end up anchored to a
  // 0×0 box at (0, 0). Re-parent the handle into the inner panel via a
  // portal so it sits on the panel corner instead.
  useEffect(() => {
    if (handlePosition !== "static") {
      setAnchor(null);
      return;
    }
    const shell = shellRef.current;
    if (!shell) return;
    const body = shell.querySelector(".resizable-shell-body");
    const target = body?.firstElementChild as HTMLElement | null;
    setAnchor(target ?? null);
  }, [handlePosition, children]);

  const handleButton = resizable ? (
    <button
      type="button"
      className={`resize-handle corner-${handleCorner}`}
      title="Drag to resize"
      aria-label={`Resize ${ariaLabel ?? "panel"}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onResizeKeyDown}
    />
  ) : null;

  return (
    <div
      ref={shellRef}
      className={`${className} resizable-shell${handlePosition === "static" ? " resizable-shell--static" : ""}`}
      aria-label={ariaLabel}
      style={shellStyle}
      onPointerDown={onMoveStart}
      onPointerMove={onMove}
      onPointerUp={onMoveEnd}
      onPointerCancel={onMoveEnd}
      tabIndex={movable ? 0 : undefined}
      onKeyDown={onMoveKeyDown}
    >
      <div className="resizable-shell-body">{children}</div>
      {handlePosition === "static" && anchor && handleButton
        ? createPortal(handleButton, anchor)
        : handlePosition !== "static"
          ? handleButton
          : null}
    </div>
  );
}

export function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-title">
        {icon}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function StatusPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function KeyValue({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong>{value ?? "none"}</strong>
    </div>
  );
}

export function LiveSignalCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="live-signal-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}
