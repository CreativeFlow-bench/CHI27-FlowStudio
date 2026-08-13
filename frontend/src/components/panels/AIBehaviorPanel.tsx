/** AI Behavior narrative and divergence controls. */
import { useEffect, useMemo, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import type {
  AssetRecord,
  Interpretation,
  IntentBubbleUiState,
  PromptToken,
  SemanticCandidateGroup,
  SemanticDivergenceResponse,
  SessionRecord,
} from "../../types";
import { promptTokenKey } from "../../utils/appHelpers";
import {
  formatPerGroupCount,
  type AiBehaviorPresentation,
} from "../../utils/workspacePresentation";

const GROUP_LABELS: Record<SemanticCandidateGroup, string> = {
  shape: "SHAPE",
  connection: "CONNECTION",
  surface: "SURFACE",
  semantic_transfer: "TRANSFER",
};

function divergenceKeywordGroups(keywords: PromptToken[]) {
  const groups = new Map<SemanticCandidateGroup, PromptToken[]>(
    (Object.keys(GROUP_LABELS) as SemanticCandidateGroup[]).map((group) => [group, []]),
  );
  for (const token of keywords) {
    const group = token.group_key as SemanticCandidateGroup;
    if (!groups.has(group)) continue;
    const list = groups.get(group) ?? [];
    list.push(token);
    groups.set(group, list);
  }
  return Array.from(groups.entries()).map(([group, tokens]) => ({ group, tokens }));
}

export function AIBehaviorPanel({
  presentation,
  projectNotice,
  onDismissNotice,
  intentBubble,
  divergenceKeywords,
  selectedPromptTokens,
  interpretation,
  session,
  asset,
  generationBusy,
  solutionSpaceGenerating,
  onTogglePromptToken,
  onGenerate,
  divergenceTemperature,
  onDivergenceTemperatureChange,
  divergencePerGroupCount,
  onDivergencePerGroupCountChange,
  onDivergenceParametersCommit,
  semanticDivergence,
  semanticDivergenceLoading,
  semanticDivergenceError,
  divergencePhaseMessage,
  selectionPersistenceError,
  inheritedKeywords,
  drawerOpen = false,
  onMenuToggle,
}: {
  presentation: AiBehaviorPresentation;
  projectNotice: string | null;
  onDismissNotice: () => void;
  intentBubble: IntentBubbleUiState;
  divergenceKeywords: PromptToken[];
  selectedPromptTokens: PromptToken[];
  interpretation: Interpretation | null;
  session: SessionRecord | null;
  asset: AssetRecord | null;
  generationBusy: boolean;
  solutionSpaceGenerating: boolean;
  onTogglePromptToken: (token: PromptToken) => void;
  onGenerate: () => void;
  divergenceTemperature: number;
  onDivergenceTemperatureChange: (value: number) => void;
  divergencePerGroupCount: number;
  onDivergencePerGroupCountChange: (value: number) => void;
  onDivergenceParametersCommit: () => void;
  semanticDivergence: SemanticDivergenceResponse | null;
  semanticDivergenceLoading: boolean;
  semanticDivergenceError: string | null;
  divergencePhaseMessage: string | null;
  selectionPersistenceError: string | null;
  inheritedKeywords?: string[];
  drawerOpen?: boolean;
  onMenuToggle?: () => void;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [revealedKeywordCount, setRevealedKeywordCount] = useState(0);
  const [typedNarrative, setTypedNarrative] = useState(presentation.narrative);
  useEffect(() => {
    if (semanticDivergenceLoading) setMobileOpen(true);
  }, [semanticDivergenceLoading]);
  useEffect(() => {
    const full = presentation.narrative || "";
    let index = 0;
    setTypedNarrative("");
    if (!full) return undefined;
    const timer = window.setInterval(() => {
      index += 1;
      setTypedNarrative(full.slice(0, index));
      if (index >= full.length) window.clearInterval(timer);
    }, 28);
    return () => window.clearInterval(timer);
  }, [presentation.narrative]);
  useEffect(() => {
    const total = divergenceKeywords.length;
    if (total <= 0) {
      setRevealedKeywordCount(0);
      return;
    }
    setRevealedKeywordCount((current) => Math.min(current, total));
    const timer = window.setInterval(() => {
      setRevealedKeywordCount((current) => (current >= total ? current : current + 1));
    }, 48);
    return () => window.clearInterval(timer);
  }, [divergenceKeywords.length]);
  const visibleKeywords = useMemo(
    () => divergenceKeywords.slice(0, revealedKeywordCount),
    [divergenceKeywords, revealedKeywordCount],
  );
  const knowledgePartial = Object.values(semanticDivergence?.knowledge_route.source_statuses ?? {})
    .some((status) => status === "partial");
  const noCurrentCandidate = selectedPromptTokens.length === 0;
  const generateDisabledReason = selectionPersistenceError
    ? "关键词保存失败，请重新选择后再生成"
    : noCurrentCandidate
      ? "请先选择至少一个当前发散候选"
      : null;
  const generateDisabled = !session || !asset || generationBusy || solutionSpaceGenerating || Boolean(generateDisabledReason);
  const scopeReady = presentation.creativeState !== "locked";
  const scopeHint = intentBubble.scope
    ? `Change ${intentBubble.scope}`
    : interpretation?.features?.design_state_ir?.scope_hint
      ? `Change ${String(interpretation.features.design_state_ir.scope_hint)}`
      : null;
  const phaseText = divergencePhaseMessage ?? "Connecting to model…";
  return (
    <aside className={`ai-behavior-float float-panel${mobileOpen ? " is-mobile-open" : ""}`} aria-label="AI Behavior">
      <header className="ai-behavior-header">
        {onMenuToggle ? (
          <button
            type="button"
            className="drawer-toggle"
            aria-label={drawerOpen ? "Hide studio menu" : "Show studio menu"}
            aria-pressed={drawerOpen}
            aria-controls="studio-rail"
            title={drawerOpen ? "Hide studio menu" : "Show studio menu"}
            onClick={onMenuToggle}
          >
            {drawerOpen ? <PanelLeftClose size={15} aria-hidden="true" /> : <PanelLeftOpen size={15} aria-hidden="true" />}
          </button>
        ) : null}
        <strong>AI BEHAVIOR</strong>
        <span className="ai-behavior-status-dots" aria-hidden="true"><i /><i /><i /></span>
        <button
          type="button"
          className="mobile-panel-toggle"
          aria-label={mobileOpen ? "Close AI Behavior" : "Open AI Behavior"}
          aria-expanded={mobileOpen}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            setMobileOpen((current) => !current);
          }}
        >
          {mobileOpen ? "收起" : "展开"}
        </button>
      </header>
      <div className="ai-behavior-panel-body">
        <div className="ai-insight-stack">
          <section className="ai-insight-card ai-phenomenon-card" aria-labelledby="current-phenomenon-title">
            <span id="current-phenomenon-title">CURRENT PHENOMENON</span>
            <p aria-live="polite" className="ai-phenomenon-typewriter">{typedNarrative}<span className="ai-phenomenon-caret" aria-hidden="true" /></p>
          </section>
        </div>
        {projectNotice ? (
          <div className="project-notice">
            <span>{projectNotice}</span>
            <button type="button" onClick={onDismissNotice}>
              知道了
            </button>
          </div>
        ) : null}
        <h2 className="model-details-label">MODEL DETAILS</h2>
        <section className="more-creative-card">
          <header className="more-creative-header">
            <span>
              <strong className="more-creative-title">More Creative?</strong>
              <small className="more-creative-scope">
                {scopeReady && scopeHint ? scopeHint : "Confirm scope to start divergence"}
              </small>
            </span>
          </header>
          <section className={`mc-pane mc-keywords-pane${scopeReady ? "" : " is-locked"}`} aria-label="Divergence keywords" aria-disabled={!scopeReady}>
        <div className="mc-param-row" aria-label="发散参数">
          <label className="mc-param">
            <span className="mc-param-label">DIVERGENCE</span>
            <em>{divergenceTemperature.toFixed(1)}</em>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={divergenceTemperature}
              disabled={!scopeReady}
              onChange={(event) => onDivergenceTemperatureChange(Number(event.target.value))}
              onPointerUp={onDivergenceParametersCommit}
              onKeyUp={onDivergenceParametersCommit}
              onBlur={onDivergenceParametersCommit}
            />
          </label>
          <label className="mc-param mc-content-param">
            <span className="mc-param-label">CONTENT</span>
            <em>{divergencePerGroupCount}</em>
            <input
              className="mc-content-range"
              type="range"
              min="5"
              max="8"
              step="1"
              value={divergencePerGroupCount}
              disabled={!scopeReady}
              onChange={(event) => onDivergencePerGroupCountChange(Number(event.target.value))}
              onPointerUp={onDivergenceParametersCommit}
              onKeyUp={onDivergenceParametersCommit}
              onBlur={onDivergenceParametersCommit}
            />
            <span className="mc-content-segments" aria-hidden="true">
              {[5, 6, 7, 8].map((amount) => (
                <i className={amount <= divergencePerGroupCount ? "is-active" : ""} key={amount} />
              ))}
            </span>
            <span className="sr-only">{formatPerGroupCount(divergencePerGroupCount)}</span>
          </label>
        </div>
        {inheritedKeywords?.length ? (
          <div className="prompt-token-board grouped inherited-keywords" aria-label="已继承关键词">
            <span className="prompt-token-hint">继承自上一意图（不可点选）</span>
            {inheritedKeywords.map((keyword) => (
              <span className="prompt-token selected inherited" key={keyword}>{keyword}</span>
            ))}
          </div>
        ) : null}
        {semanticDivergenceLoading ? (
          <div className="semantic-keyword-skeleton" role="status" aria-live="polite" aria-busy="true">
            <p className="semantic-keyword-status is-phase-tick" key={phaseText}>
              {phaseText}
            </p>
            {!visibleKeywords.length ? (
              <div aria-hidden="true">
                <i /><i /><i /><i />
              </div>
            ) : (
              <p className="semantic-keyword-status is-phase-tick" key="streaming-hint">
                Streaming keywords — keep selecting.
              </p>
            )}
          </div>
        ) : null}
        {!semanticDivergenceLoading && semanticDivergence?.fallback_used ? (
          <p className="prompt-token-hint sr-only" role="status">Local VLM fallback</p>
        ) : null}
        {!semanticDivergenceLoading && knowledgePartial ? (
          <p className="prompt-token-hint sr-only" role="status">Knowledge augmentation partial — keep selecting.</p>
        ) : null}
        {!semanticDivergenceLoading && (semanticDivergenceError || semanticDivergence?.status === "failed") ? (
          <p className="prompt-token-hint" role="alert">
            {semanticDivergenceError || "Semantic divergence unavailable — retry or refine intent"}
          </p>
        ) : null}
        {visibleKeywords.length ? (
          <div className="dimension-direction-list">
              {divergenceKeywordGroups(visibleKeywords).map((group) => (
                <section className={`dimension-panel ${group.group}`} aria-labelledby={`dimension-${group.group}`} key={group.group}>
                  <div className="dimension-panel-head">
                    <strong id={`dimension-${group.group}`}>{GROUP_LABELS[group.group]}</strong>
                  </div>
                  {group.tokens.length ? (
                    <div className="prompt-token-board grouped">
                      {group.tokens.map((token, index) => {
                        const selected = selectedPromptTokens.some(
                          (item) => promptTokenKey(item) === promptTokenKey(token),
                        );
                        return (
                          <button
                            className={`prompt-token is-keyword-enter ${selected ? "selected" : ""}`}
                            key={promptTokenKey(token)}
                            type="button"
                            title={GROUP_LABELS[group.group]}
                            style={{ animationDelay: `${Math.min(index, 12) * 28}ms` }}
                            onClick={() => onTogglePromptToken(token)}
                            disabled={false}
                          >
                            <span>{token.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </section>
              ))}
            </div>
        ) : !semanticDivergenceLoading && !semanticDivergenceError && semanticDivergence?.status !== "failed" ? (
          <p className="prompt-token-hint sr-only">Divergence keywords will appear once a white model or intent is available.</p>
        ) : null}
          </section>
        </section>
        <button
          className="behavior-generate-button"
          type="button"
          disabled={generateDisabled}
          aria-describedby="semantic-generate-disabled-reason"
          onClick={onGenerate}
        >
          Generate
        </button>
        {generateDisabledReason ? (
          <p id="semantic-generate-disabled-reason" className="prompt-token-hint generate-disabled-reason" role={selectionPersistenceError ? "alert" : undefined}>
            {generateDisabledReason}
          </p>
        ) : null}
      </div>
    </aside>
  );
}
