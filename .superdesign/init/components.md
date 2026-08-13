# Shared UI Components

Framework: React 19 + TypeScript. UI library: custom components with lucide-react icons. Styling: one vanilla CSS stylesheet.

## primitives.tsx

- Path: `frontend/src/components/ui/primitives.tsx`
- Shared UI primitives: resizable shells, panels, status pills, key/value rows, live-signal cards, and empty states.

```tsx
/**
 * Generic UI primitives (refactor plan P1a).
 */
import { useEffect, useRef, useState } from "react";

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
  movable = false,
  style,
  children,
}: {
  className: string;
  ariaLabel?: string;
  defaultWidth: number;
  defaultHeight: number;
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  handleCorner?: "se" | "sw";
  movable?: boolean;
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  const [size, setSize] = useState({ w: defaultWidth, h: defaultHeight });
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
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
    setSize(clampSize({
      w: drag.startW + (handleCorner === "sw" ? -deltaX : deltaX),
      h: drag.startH + deltaY,
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

  return (
    <div
      className={`${className} resizable-shell`}
      aria-label={ariaLabel}
      style={{
        ...style,
        width: size.w,
        height: size.h,
        ...(position ? { left: position.x, top: position.y, right: "auto", transform: "none" } : {}),
      }}
      onPointerDown={onMoveStart}
      onPointerMove={onMove}
      onPointerUp={onMoveEnd}
      onPointerCancel={onMoveEnd}
      tabIndex={movable ? 0 : undefined}
      onKeyDown={onMoveKeyDown}
    >
      <div className="resizable-shell-body">{children}</div>
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

```

## ProjectSection.tsx

- Path: `frontend/src/components/project/ProjectSection.tsx`
- Experiment-file summary and recording-state entry point.

```tsx
import { Clock3, FilePlus2, FolderOpen } from "lucide-react";
import type { ExperimentProjectDetail } from "../../types";
import { projectPresentation } from "./projectPresentation";

export function ProjectSection({
  project,
  recordingError,
  onNew,
  onOpen,
  onTimeline,
}: {
  project: ExperimentProjectDetail | null;
  recordingError: string | null;
  onNew: () => void;
  onOpen: () => void;
  onTimeline: () => void;
}) {
  const view = projectPresentation(project);
  return (
    <section className={`project-section tone-${view.tone}`} aria-label="Experiment file">
      <div className="project-section-kicker">Experiment file</div>
      <div className="project-section-title-row">
        <div>
          <strong>{view.title}</strong>
          <span className="project-recording-status" aria-live="polite">
            <i aria-hidden="true" /> {recordingError ? "记录已暂停" : view.status}
          </span>
        </div>
      </div>
      {recordingError ? <p className="project-recording-error">{recordingError}</p> : null}
      <div className="project-section-actions">
        <button type="button" className="project-primary" onClick={project ? onTimeline : onNew}>
          {project ? <Clock3 size={14} /> : <FilePlus2 size={14} />} {view.primaryAction}
        </button>
        <button type="button" className="ghost compact" onClick={onOpen}>
          <FolderOpen size={14} /> 打开
        </button>
        {project ? <button type="button" className="ghost compact" onClick={onNew}><FilePlus2 size={14} /> 新建</button> : null}
      </div>
    </section>
  );
}

```

## ProjectDialog.tsx

- Path: `frontend/src/components/project/ProjectDialog.tsx`
- Create/open experiment file dialog.

```tsx
import { X } from "lucide-react";
import { useState } from "react";
import type { ExperimentProjectDetail } from "../../types";

export function ProjectDialog({
  projects,
  busy,
  onClose,
  onCreate,
  onOpen,
}: {
  projects: ExperimentProjectDetail[];
  busy: boolean;
  onClose: () => void;
  onCreate: (input: { title: string; participantCode?: string; conditionLabel?: string; baselineMode: "blank" | "current_state" }) => Promise<unknown>;
  onOpen: (id: string) => Promise<unknown>;
}) {
  const [title, setTitle] = useState("");
  const [participantCode, setParticipantCode] = useState("");
  const [conditionLabel, setConditionLabel] = useState("");
  const [baselineMode, setBaselineMode] = useState<"blank" | "current_state">("blank");
  return (
    <div className="project-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="project-dialog" role="dialog" aria-modal="true" aria-labelledby="project-dialog-title">
        <header>
          <div><span>Experiment file</span><h2 id="project-dialog-title">新建或打开实验文件</h2></div>
          <button type="button" className="icon-button" aria-label="关闭实验文件对话框" onClick={onClose}><X size={16} /></button>
        </header>
        <div className="project-dialog-grid">
          <form onSubmit={(event) => { event.preventDefault(); void onCreate({ title, participantCode, conditionLabel, baselineMode }); }}>
            <label>文件名<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Participant P07" required /></label>
            <div className="project-field-row">
              <label>参与者<input value={participantCode} onChange={(event) => setParticipantCode(event.target.value)} placeholder="P07" /></label>
              <label>条件<input value={conditionLabel} onChange={(event) => setConditionLabel(event.target.value)} placeholder="A" /></label>
            </div>
            <fieldset>
              <legend>开始状态</legend>
              <label className="baseline-option"><input type="radio" name="baseline" checked={baselineMode === "blank"} onChange={() => setBaselineMode("blank")} /><span><strong>空白工作区</strong><em>建立全新 Session，从第一步开始记录</em></span></label>
              <label className="baseline-option"><input type="radio" name="baseline" checked={baselineMode === "current_state"} onChange={() => setBaselineMode("current_state")} /><span><strong>当前状态</strong><em>保留当前画布作为基线，不导入旧事件</em></span></label>
            </fieldset>
            <button className="project-submit" type="submit" disabled={busy}>{busy ? "正在创建…" : "新建实验文件"}</button>
          </form>
          <div className="project-open-list" aria-label="已有实验文件">
            <h3>最近文件</h3>
            {projects.length ? projects.map((item) => (
              <button type="button" key={item.project.project_id} onClick={() => void onOpen(item.project.project_id)} disabled={busy}>
                <strong>{item.project.title}</strong>
                <span>{item.project.participant_code || "未标记参与者"} · {item.active_run ? `Run ${String(item.active_run.run_number).padStart(2, "0")}` : "已结束"}</span>
              </button>
            )) : <p>还没有实验文件。</p>}
          </div>
        </div>
      </section>
    </div>
  );
}

```

## ProjectTimeline.tsx

- Path: `frontend/src/components/project/ProjectTimeline.tsx`
- Append-only experiment timeline drawer.

```tsx
import { Download, Square, X } from "lucide-react";
import type { ExperimentEvent, ExperimentProjectDetail } from "../../types";

export function ProjectTimeline({ project, events, onClose, onEnd, onExport }: {
  project: ExperimentProjectDetail;
  events: ExperimentEvent[];
  onClose: () => void;
  onEnd: () => Promise<unknown>;
  onExport: () => Promise<{ file_url: string | null } | null>;
}) {
  return (
    <aside className="project-timeline" aria-label="实验记录时间线">
      <header><div><span>Recording timeline</span><h2>{project.project.title}</h2></div><button className="icon-button" type="button" aria-label="关闭时间线" onClick={onClose}><X size={16} /></button></header>
      <div className="project-timeline-actions">
        {project.active_run ? <button type="button" className="ghost compact" onClick={() => void onEnd()}><Square size={13} /> 结束 Run</button> : null}
        <button type="button" className="ghost compact" onClick={async () => { const result = await onExport(); if (result?.file_url) window.open(result.file_url, "_blank", "noopener,noreferrer"); }}><Download size={13} /> 导出实验包</button>
      </div>
      <ol>
        {events.map((event) => <li key={event.event_id}><i aria-hidden="true" /><div><strong>{event.event_type}</strong><span>{event.actor} · {new Date(event.recorded_at).toLocaleString()}</span></div><em>#{event.seq}</em></li>)}
      </ol>
    </aside>
  );
}

```


