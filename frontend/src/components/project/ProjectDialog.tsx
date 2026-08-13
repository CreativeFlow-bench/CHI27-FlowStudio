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
