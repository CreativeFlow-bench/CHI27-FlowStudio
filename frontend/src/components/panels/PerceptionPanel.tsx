/**
 * Privacy-safe summary of the user's current interaction and recent operations.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Eye, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type { BehaviorSession, LiveObservationState, LivePerception } from "../../types";
import {
  buildPerceptionDisplay,
  type PerceptionDisplayEvent,
  type PerceptionDisplayOperation,
} from "../../utils/perceptionDisplay";

const MIN_STATUS_DURATION_MS = 800;

const operationLabels: Record<PerceptionDisplayOperation, string> = {
  add: "ADDING",
  draw: "DRAWING",
  sculpt: "SCULPTING",
  reshape: "RESHAPING",
  smooth: "SMOOTHING",
  focus: "FOCUSING",
  inspect: "INSPECTING",
  survey: "SURVEYING",
  compare: "COMPARING",
  describe_intent: "DESCRIBING",
  review: "REVIEWING",
  idle: "WAITING",
};

function formatHistoryTime(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(timestamp);
}

export function PerceptionPanel({
  perceptionHistoryOpen,
  onToggleHistory,
  styleLeft,
  livePerception,
  liveObservation,
  behaviorSessions,
  hasModel,
  collapsed = false,
  onCollapsedChange,
}: {
  perceptionHistoryOpen: boolean;
  onToggleHistory: () => void;
  styleLeft: number | undefined;
  livePerception: LivePerception;
  liveObservation?: LiveObservationState | null;
  behaviorSessions: BehaviorSession[];
  hasModel: boolean;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(false);
  const display = useMemo(() => buildPerceptionDisplay({
    livePerception,
    liveObservation,
    behaviors: behaviorSessions,
    hasModel,
    now,
  }), [behaviorSessions, hasModel, liveObservation, livePerception, now]);
  const [current, setCurrent] = useState<PerceptionDisplayEvent>(() => display.current);
  const displayedAtRef = useRef(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (display.current.id === current.id) return;

    const commit = () => {
      setCurrent(display.current);
      displayedAtRef.current = Date.now();
    };
    if (display.current.explicit) {
      commit();
      return;
    }

    const remaining = MIN_STATUS_DURATION_MS - (Date.now() - displayedAtRef.current);
    if (remaining <= 0) {
      commit();
      return;
    }
    const timer = window.setTimeout(commit, remaining);
    return () => window.clearTimeout(timer);
  }, [current.id, display.current]);

  return (
    <section
      className={`perception-float float-panel observe-float${perceptionHistoryOpen ? " is-open" : ""}${expanded ? " is-expanded" : ""}${collapsed ? " is-collapsed" : ""}`}
      aria-label="Perception"
      style={{ left: styleLeft }}
    >
      <header className="float-panel-label observe-head">
        <button
          type="button"
          className="perception-eye"
          aria-label={expanded ? "Collapse Perception" : "Expand Perception"}
          onClick={() => setExpanded((current) => !current)}
        >
          <Eye size={16} aria-hidden="true" />
        </button>
        <span>Perception</span>
        <div className="observe-head-actions">
          <span className="status-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <button
            type="button"
            className={`observe-toggle${perceptionHistoryOpen ? " is-open" : ""}`}
            aria-expanded={perceptionHistoryOpen}
            aria-controls="perception-operation-history"
            aria-label={perceptionHistoryOpen ? "Collapse operation history" : "Expand operation history"}
            onClick={onToggleHistory}
          >
            <ChevronDown size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="drawer-toggle"
            aria-label={collapsed ? "Expand Perception" : "Collapse Perception"}
            aria-pressed={collapsed}
            aria-expanded={!collapsed}
            title={collapsed ? "Expand Perception" : "Collapse Perception"}
            onClick={() => onCollapsedChange?.(!collapsed)}
          >
            {collapsed ? <PanelLeftOpen size={15} aria-hidden="true" /> : <PanelLeftClose size={15} aria-hidden="true" />}
          </button>
        </div>
      </header>

      <div className="observe-current" aria-live="polite" aria-atomic="true">
        <p className="observe-sentence">{current.sentence}</p>
      </div>

      {perceptionHistoryOpen ? (
        <div
          id="perception-operation-history"
          className="observe-log"
          role="region"
          aria-label="Operation history"
        >
          {display.history.length ? display.history.map((entry) => (
            <div className="observe-log-row" key={entry.id}>
              <time dateTime={new Date(entry.timestamp).toISOString()}>{formatHistoryTime(entry.timestamp)}</time>
              <em>{operationLabels[entry.operation]}{entry.count > 1 ? ` ×${entry.count}` : ""}</em>
              <span>{entry.sentence}</span>
            </div>
          )) : (
            <p className="observe-log-empty">No operations recorded yet.</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
