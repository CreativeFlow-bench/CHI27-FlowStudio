/**
 * Four-stage pipeline progress + Gate overlay (P5).
 *
 * Only the awaiting_gate stage is interactive (scheduler is the single
 * switch); every other stage renders as a progress rail. Gate timeout (90s)
 * auto-accepts the recommended option; reject maps to request_revision.
 */
import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, RefreshCw, Send, X } from "lucide-react";
import type { FourStageDecision, FourStageGateAction, FourStageUiState } from "../../types";

const STAGE_ORDER: Array<{ key: string; label: string }> = [
  { key: "encoding", label: "编码" },
  { key: "retrieval", label: "检索" },
  { key: "re_representation", label: "方向决策" },
  { key: "generation", label: "生成" },
];

function stageIndex(stage: string | null): number {
  if (!stage) return -1;
  if (stage === "awaiting_gate") return 2;
  const idx = STAGE_ORDER.findIndex((item) => item.key === stage);
  return idx >= 0 ? idx : -1;
}

function recommendedOption(decision: FourStageDecision | null) {
  if (!decision || !decision.options.length) return null;
  return [...decision.options].sort((a, b) => b.confidence - a.confidence)[0];
}

export function FourStageGateOverlay({
  fourStage,
  onCreateRun,
  onGate,
  onRetry,
}: {
  fourStage: FourStageUiState;
  onCreateRun: () => void;
  onGate: (decisionId: string, action: FourStageGateAction, opts?: Record<string, unknown>) => void;
  onRetry: () => void;
}) {
  const [revisionText, setRevisionText] = useState("");
  const activeStage = stageIndex(fourStage.stage);
  const recommended = useMemo(() => recommendedOption(fourStage.decision), [fourStage.decision]);
  const gateVisible = fourStage.gateOpen && fourStage.decision !== null;

  useEffect(() => {
    if (!gateVisible) setRevisionText("");
  }, [gateVisible]);

  if (fourStage.runId === null && fourStage.stage === null && !fourStage.error) {
    return (
      <div className="four-stage-overlay">
        <div className="four-stage-panel">
          <div className="four-stage-title">四阶段意图管线</div>
          <p className="four-stage-hint">
            先绘制 / 输入意图（画笔、标注、拖拽、雕刻），再把行为证据提交给编码 → 检索 → 方向决策 → 生成。
          </p>
          <button className="primary" disabled={fourStage.creatingRun} onClick={onCreateRun}>
            {fourStage.creatingRun ? <Loader2 className="spin" size={16} /> : <Send size={16} />}
            提交行为并启动管线
          </button>
        </div>
      </div>
    );
  }

  const timeoutSeconds =
    fourStage.gateTimeoutAt && gateVisible
      ? Math.max(0, Math.ceil((fourStage.gateTimeoutAt - Date.now()) / 1000))
      : null;

  return (
    <div className="four-stage-overlay">
      <div className="four-stage-panel">
        <div className="four-stage-title">
          四阶段意图管线
          {fourStage.runId ? <span className="four-stage-run-id">{fourStage.runId.slice(0, 12)}</span> : null}
        </div>

        <div className="four-stage-rail">
          {STAGE_ORDER.map((item, index) => {
            const done = activeStage > index || fourStage.stage === "completed";
            const current = activeStage === index || (fourStage.stage === "awaiting_gate" && index === 2);
            return (
              <div key={item.key} className={`four-stage-step${done ? " is-done" : ""}${current ? " is-current" : ""}`}>
                {done ? <Check size={13} /> : current ? <Loader2 className="spin" size={13} /> : <span className="four-stage-step-dot" />}
                <span>{item.label}</span>
              </div>
            );
          })}
        </div>

        {fourStage.error ? (
          <div className="four-stage-error">
            <span>{fourStage.error.message}</span>
            {fourStage.error.retryable ? (
              <button className="ghost compact" onClick={onRetry}>
                <RefreshCw size={13} /> 重试
              </button>
            ) : null}
          </div>
        ) : null}

        {gateVisible && fourStage.decision ? (
          <div className="four-stage-gate">
            <div className="four-stage-gate-head">
              <span>方向决策待确认</span>
              {timeoutSeconds !== null ? (
                <span className="four-stage-gate-timeout">{timeoutSeconds}s 后自动采用推荐项</span>
              ) : null}
            </div>
            {fourStage.decision.summary ? <p className="four-stage-gate-summary">{fourStage.decision.summary}</p> : null}
            {fourStage.decision.clarification_question ? (
              <p className="four-stage-gate-clarify">需要澄清：{fourStage.decision.clarification_question}</p>
            ) : null}
            <div className="four-stage-options">
              {fourStage.decision.options.map((option) => {
                const isRecommended = recommended?.option_id === option.option_id;
                return (
                  <button
                    key={option.option_id}
                    className={`four-stage-option${isRecommended ? " is-recommended" : ""}`}
                    disabled={fourStage.gateBusy}
                    onClick={() =>
                      onGate(fourStage.decision!.decision_id, "accept_option", {
                        selected_option_id: option.option_id,
                        reason: isRecommended ? "user_accepted_recommended" : "user_accepted_option",
                      })
                    }
                  >
                    <span className="four-stage-option-label">
                      {isRecommended ? <Check size={13} /> : null}
                      {option.label}
                    </span>
                    <span className="four-stage-option-conf">{Math.round(option.confidence * 100)}%</span>
                    {option.rationale ? <span className="four-stage-option-rationale">{option.rationale}</span> : null}
                  </button>
                );
              })}
            </div>
            <div className="four-stage-gate-actions">
              <input
                className="four-stage-revision"
                placeholder="都不满意？写下修改意见（将重新决策并再次弹出方向）"
                value={revisionText}
                disabled={fourStage.gateBusy}
                onChange={(event) => setRevisionText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && revisionText.trim()) {
                    onGate(fourStage.decision!.decision_id, "request_revision", { user_revision: revisionText.trim() });
                  }
                }}
              />
              <button
                className="ghost"
                disabled={fourStage.gateBusy || !revisionText.trim()}
                onClick={() =>
                  onGate(fourStage.decision!.decision_id, "request_revision", { user_revision: revisionText.trim() })
                }
              >
                <Send size={14} /> 修改后重新决策
              </button>
              <button
                className="ghost"
                disabled={fourStage.gateBusy}
                onClick={() =>
                  onGate(fourStage.decision!.decision_id, "request_revision", {
                    reason: "reject_all_directions",
                  })
                }
              >
                <X size={14} /> 全部不满意
              </button>
            </div>
          </div>
        ) : fourStage.stage === "completed" ? (
          <div className="four-stage-completed">
            <Check size={15} /> 管线完成 · {fourStage.generationArtifacts.length} 个产物
          </div>
        ) : fourStage.stage ? (
          <div className="four-stage-status">当前阶段：{fourStage.stage}</div>
        ) : null}
      </div>
    </div>
  );
}
