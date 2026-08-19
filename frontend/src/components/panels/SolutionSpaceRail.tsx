/**
 * Solution Space rail: generated candidates + directions (refactor plan P1a).
 * Click card to select/accept; drag card onto the version canvas to create a node.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Minus, Sparkles } from "lucide-react";
import type { AnalogyDirection, Candidate, JobRecord } from "../../types";
import { isActiveJobStatus } from "../../utils/format";
import { FLOWSTUDIO_CANDIDATE_MIME } from "../../utils/versionGraph";
import {
  candidateArtifactLevel,
  candidateStage,
  candidatePreviewUrl,
} from "../../utils/appHelpers";

const LOADING_SLOT_COUNT = 8;
const EXPANDED_LOADING_HEIGHT = 280;
const CLICK_COLLAPSE_PX = 8;

export function SolutionSpaceRail({
  candidates,
  directions,
  acceptedCandidateIds,
  job,
  loading,
  onCollapse,
  onPreview,
  onAcceptDirection,
  onCommit3D,
  onReject,
  onGenerate3D,
  selectedCandidateId,
  onSelectCandidate,
  onDropCandidate,
  progressLabel,
  errorMessage = null,
  height,
  onHeightChange,
  roundChips = [],
  displayIntentSeq = null,
  onSelectRound,
}: {
  candidates: Candidate[];
  directions: AnalogyDirection[];
  acceptedCandidateIds: string[];
  job: JobRecord | null;
  loading: boolean;
  hy3dCandidateIds: string[];
  onCollapse: () => void;
  onPreview: (candidate: Candidate) => void;
  onAcceptDirection: (candidate: Candidate) => void;
  onCommit3D: (candidate: Candidate) => void;
  onReject: (candidate: Candidate) => void;
  onGenerate3D: (candidate: Candidate) => void;
  selectedCandidateId: string | null;
  onSelectCandidate: (candidate: Candidate) => void;
  onDropCandidate: (candidate: Candidate) => void;
  progressLabel?: string | null;
  errorMessage?: string | null;
  height?: number;
  onHeightChange?: (height: number) => void;
  roundChips?: Array<{ intentSeq: number; count: number }>;
  displayIntentSeq?: number | null;
  onSelectRound?: (intentSeq: number) => void;
}) {
  const dragRef = useRef<{ startY: number; startH: number; moved: boolean } | null>(null);
  const [streamIndex, setStreamIndex] = useState(0);
  const expectedTotal = useMemo(() => {
    const match = String(progressLabel || "").match(/\/(\d+)/);
    const fromLabel = match ? Number(match[1]) : 0;
    return Math.max(LOADING_SLOT_COUNT, fromLabel || 0, candidates.length);
  }, [progressLabel, candidates.length]);

  const streamLines = useMemo(() => {
    const lines: string[] = [];
    if (errorMessage) {
      lines.push(`failed · ${errorMessage}`);
    }
    if (loading || (job && isActiveJobStatus(job.status))) {
      lines.push(`generating…${progressLabel ? ` ${progressLabel}` : " starting…"}`);
      if (candidates.length === 0) {
        lines.push("waiting for first image…");
      }
      for (const candidate of candidates.slice(-4)) {
        lines.push(`ready · ${candidate.label}`);
      }
      if (candidates.length > 0 && candidates.length < expectedTotal) {
        lines.push(`next · ${candidates.length + 1}/${expectedTotal}`);
      }
    } else if (candidates.length || directions.length) {
      lines.push(`${candidates.length || directions.length} items`);
    }
    return lines.length ? lines : ["idle"];
  }, [
    errorMessage,
    loading,
    job,
    progressLabel,
    candidates,
    expectedTotal,
    directions.length,
  ]);

  useEffect(() => {
    setStreamIndex(0);
  }, [streamLines.join("|")]);

  useEffect(() => {
    if (streamLines.length <= 1) return undefined;
    const timer = window.setInterval(() => {
      setStreamIndex((current) => (current + 1) % streamLines.length);
    }, 1400);
    return () => window.clearInterval(timer);
  }, [streamLines]);

  const pendingSlots = loading ? Math.max(0, expectedTotal - candidates.length) : 0;
  const streamText = streamLines[Math.min(streamIndex, streamLines.length - 1)] ?? "";
  // Keep the rail fully expanded while generating — never collapse to a strip.
  const railHeight = loading
    ? Math.max(height ?? EXPANDED_LOADING_HEIGHT, EXPANDED_LOADING_HEIGHT)
    : height;

  return (
    <section
      className={`solution-space-rail${loading ? " is-loading" : ""}${errorMessage ? " is-error" : ""}`}
      aria-label="Solution Space"
      style={railHeight ? { height: railHeight } : undefined}
    >
      <div className="solution-space-head">
        <div className="solution-space-head-title">
          <span>Solution Space</span>
          {roundChips.length ? (
            <div className="solution-space-round-pages" role="tablist" aria-label="Generation pages">
              {roundChips.map((chip) => {
                const selected = chip.intentSeq === displayIntentSeq;
                return (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    className={`solution-space-round-chip${selected ? " is-active" : ""}`}
                    key={chip.intentSeq}
                    title={`Gen${chip.intentSeq}${chip.count ? ` · ${chip.count}` : ""}`}
                    onClick={() => onSelectRound?.(chip.intentSeq)}
                  >
                    Gen{chip.intentSeq}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
        <div className="solution-space-head-actions">
          <div className="solution-space-status-stream" aria-live="polite" title={errorMessage ?? streamText}>
            <span key={`${streamIndex}:${streamText}`} className="solution-space-status-line">
              {streamText}
            </span>
          </div>
          <button type="button" className="solution-space-collapse" aria-label="Collapse Solution Space" title="收起 Solution Space" onClick={onCollapse}>
            <Minus size={13} />
            <span>收起</span>
          </button>
        </div>
      </div>
      {errorMessage && !candidates.length ? (
        <div className="solution-loading-strip is-error" role="alert">
          <span>生成失败：{errorMessage}</span>
        </div>
      ) : !candidates.length && !loading && !directions.length ? (
        <div className="solution-loading-strip" role="status">
          <span>waiting for new idea...</span>
        </div>
      ) : (
        <div className="solution-space-scroll">
          {candidates.map((candidate) => {
            const previewUrl = candidatePreviewUrl(candidate);
            const accepted = acceptedCandidateIds.includes(candidate.candidate_id);
            return (
              <article
                className={`solution-card ${accepted ? "accepted" : ""}`}
                key={candidate.candidate_id}
                draggable={Boolean(previewUrl)}
                title={previewUrl ? "点击选中；拖到画布创建版本" : candidate.label}
                onClick={() => {
                  if (accepted) {
                    onReject(candidate);
                    return;
                  }
                  onSelectCandidate(candidate);
                  onAcceptDirection(candidate);
                }}
                onDragStart={(event) => {
                  if (!previewUrl) return;
                  event.dataTransfer.effectAllowed = "copy";
                  event.dataTransfer.setData(FLOWSTUDIO_CANDIDATE_MIME, JSON.stringify({
                    candidateId: candidate.candidate_id,
                  }));
                  onSelectCandidate(candidate);
                }}
              >
                {accepted ? <span className="accepted-mark" aria-label="已选中">✓</span> : null}
                {previewUrl ? (
                  <img src={previewUrl} alt={candidate.label} width={220} height={150} loading="lazy" draggable={false} />
                ) : (
                  <div className="solution-card-placeholder">
                    <Sparkles size={18} />
                  </div>
                )}
                <div className="solution-card-body">
                  <strong>{candidate.label}</strong>
                  <span>{candidateStage(candidate)} · {candidateArtifactLevel(candidate)}</span>
                  <em>{accepted ? "accepted · 再点取消" : candidate.decision}</em>
                </div>
              </article>
            );
          })}
          {Array.from({ length: pendingSlots }, (_, index) => (
            <article
              className="solution-card is-skeleton"
              key={`pending_${index}`}
              aria-label={`Generating variant ${candidates.length + index + 1}`}
            >
              <div className="solution-card-skeleton" aria-hidden="true">
                <i />
                <span>{candidates.length + index + 1}/{expectedTotal}</span>
              </div>
            </article>
          ))}
          {!candidates.length && !loading
            ? directions.slice(0, 8).map((direction) => (
                <article className="solution-card direction" key={direction.direction_id}>
                  <div className="solution-card-placeholder">
                    <Sparkles size={18} />
                  </div>
                  <div className="solution-card-body">
                    <strong>{direction.label}</strong>
                    <span>{direction.dimension} · prompt direction</span>
                    <em>{direction.source_domain} → {direction.target_domain}</em>
                  </div>
                </article>
              ))
            : null}
        </div>
      )}
      {onHeightChange ? (
        <button
          type="button"
          className="solution-space-resize"
          aria-label="调整或收起 Solution Space"
          title="点击收起 · 拖动调整高度"
          onPointerDown={(event) => {
            event.preventDefault();
            dragRef.current = { startY: event.clientY, startH: railHeight ?? 168, moved: false };
            (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const drag = dragRef.current;
            if (!drag) return;
            const delta = event.clientY - drag.startY;
            if (Math.abs(delta) >= CLICK_COLLAPSE_PX) drag.moved = true;
            if (!drag.moved) return;
            const next = Math.max(120, Math.min(420, drag.startH + delta));
            onHeightChange(next);
          }}
          onPointerUp={(event) => {
            const drag = dragRef.current;
            dragRef.current = null;
            try {
              (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
            } catch {
              // ignore
            }
            if (drag && !drag.moved) {
              onCollapse();
            }
          }}
        />
      ) : null}
    </section>
  );
}
