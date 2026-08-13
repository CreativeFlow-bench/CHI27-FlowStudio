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
