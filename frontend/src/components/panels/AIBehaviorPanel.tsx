/** AI Behavior narrative and divergence controls. */
import { useEffect, useMemo, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
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
  divergenceKeywords,
  selectedPromptTokens,
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
  onDismissInheritedKeyword,
  collapsed = false,
  onCollapsedChange,
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
  onDismissInheritedKeyword?: (keyword: string) => void;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
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
    : generationBusy || solutionSpaceGenerating
      ? "正在生成…"
      : noCurrentCandidate
        ? "先点选至少一个关键词，再 Generate"
        : null;
  const generateDisabled = !session || !asset || generationBusy || solutionSpaceGenerating || noCurrentCandidate || Boolean(selectionPersistenceError);
  const scopeReady = presentation.creativeState !== "locked";
  const phaseText = divergencePhaseMessage ?? "Connecting to model…";
  return (
    <aside className={`ai-behavior-float float-panel${mobileOpen ? " is-mobile-open" : ""}${collapsed ? " is-collapsed" : ""}`} aria-label="AI Behavior">
      <header className="float-panel-label observe-head">
        <span>AI Behavior</span>
        <div className="observe-head-actions">
          <span className="status-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <button
            type="button"
            className="drawer-toggle"
            aria-label={collapsed ? "Expand AI Behavior" : "Collapse AI Behavior"}
            aria-pressed={collapsed}
            aria-expanded={!collapsed}
            title={collapsed ? "Expand AI Behavior" : "Collapse AI Behavior"}
            onClick={() => onCollapsedChange?.(!collapsed)}
          >
            {collapsed ? <PanelRightOpen size={15} aria-hidden="true" /> : <PanelRightClose size={15} aria-hidden="true" />}
          </button>
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
        </div>
      </header>
      <div className="ai-behavior-panel-body">
        <div className="ai-insight-stack">
          <section className="ai-insight-card ai-phenomenon-card" aria-label="Current phenomenon">
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
        <section className="more-creative-card">
          <header className="more-creative-header">
            <span>
              <strong className="more-creative-title">More Creative?</strong>
              <p className="more-creative-scope">Waiting for your design. I'll give you more inspiration.</p>
            </span>
          </header>
          <section className={`mc-pane mc-keywords-pane${scopeReady ? "" : " is-locked"}`} aria-label="Divergence keywords" aria-disabled={!scopeReady}>
        <div className="mc-param-row" aria-label="Divergence parameters">
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
              onPointerUp={(event) => {
                onDivergenceTemperatureChange(Number(event.currentTarget.value));
                onDivergenceParametersCommit();
              }}
              onKeyUp={(event) => {
                onDivergenceTemperatureChange(Number(event.currentTarget.value));
                onDivergenceParametersCommit();
              }}
              onBlur={(event) => {
                onDivergenceTemperatureChange(Number(event.currentTarget.value));
                onDivergenceParametersCommit();
              }}
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
              onPointerUp={(event) => {
                onDivergencePerGroupCountChange(Number(event.currentTarget.value));
                onDivergenceParametersCommit();
              }}
              onKeyUp={(event) => {
                onDivergencePerGroupCountChange(Number(event.currentTarget.value));
                onDivergenceParametersCommit();
              }}
              onBlur={(event) => {
                onDivergencePerGroupCountChange(Number(event.currentTarget.value));
                onDivergenceParametersCommit();
              }}
            />
            <span className="mc-content-segments" aria-hidden="true">
              {[5, 6, 7, 8].map((amount) => (
                <i className={amount <= divergencePerGroupCount ? "is-active" : ""} key={amount} />
              ))}
            </span>
            <span className="sr-only">{formatPerGroupCount(divergencePerGroupCount)}</span>
          </label>
        </div>
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
        {!semanticDivergenceLoading && !generationBusy && !solutionSpaceGenerating && (semanticDivergenceError || semanticDivergence?.status === "failed") ? (
          <p className="prompt-token-hint" role="alert">
            {semanticDivergenceError || "Semantic divergence unavailable — retry or refine intent"}
          </p>
        ) : null}
        {inheritedKeywords?.length || visibleKeywords.length ? (
          <div className="dimension-direction-list">
              {inheritedKeywords?.length ? (
                <section className="dimension-panel inherited-keywords" aria-label="已继承关键词">
                  <div className="dimension-panel-head">
                    <strong>上一意图</strong>
                    <span className="sr-only">点击关键词可从本轮移除</span>
                  </div>
                  <div className="prompt-token-board grouped">
                    {inheritedKeywords.map((keyword, index) => (
                      <button
                        className="prompt-token is-keyword-enter is-inherited"
                        key={keyword}
                        type="button"
                        title="点击移除，不再带入本轮"
                        style={{ animationDelay: `${Math.min(index, 12) * 28}ms` }}
                        onClick={() => onDismissInheritedKeyword?.(keyword)}
                      >
                        <span>{keyword}</span>
                      </button>
                    ))}
                  </div>
                </section>
              ) : null}
              {visibleKeywords.length
                ? divergenceKeywordGroups(visibleKeywords).map((group) => (
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
              )) : null}
            </div>
        ) : null}
          </section>
        </section>
        <button
          className="behavior-generate-button"
          type="button"
          disabled={generateDisabled}
          onClick={onGenerate}
        >
          Generate
        </button>
        {generateDisabledReason ? (
          <p className="prompt-token-hint generate-disabled-reason" role="alert">
            {generateDisabledReason}
          </p>
        ) : null}
      </div>
    </aside>
  );
}
