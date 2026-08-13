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
