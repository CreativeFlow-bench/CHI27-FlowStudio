import React, { useEffect, useImperativeHandle, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Box,
  Check,
  ChevronDown,
  Download,
  Focus,
  GripVertical,
  Maximize2,
  Minus,
  MousePointer2,
  Paintbrush,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Send,
  SmilePlus,
  Sparkles,
  Upload,
  Wand2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MTLLoader } from "three/examples/jsm/loaders/MTLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { EditorScene } from "./editorScene";
import { buildPrimitiveObject, addStudioPreviewLighting, loadObjWithOptionalMtl, applyDisplayMaterial, standardizeMeshMaterial } from "./components/viewport/scene";
import { sculptFalloff, sculptWorldPositions, sculptApplyOffset, grabDisplace, smoothDisplace } from "./components/viewport/sculptEngine";
import { ResizableShell, Panel, StatusPill, KeyValue, LiveSignalCard, EmptyState } from "./components/ui/primitives";
import { PlannerClarificationOverlay } from "./components/overlays/PlannerClarificationOverlay";
import { SolutionSpaceRail } from "./components/panels/SolutionSpaceRail";
import { reduceSolutionSpaceVisibility } from "./utils/solutionSpaceVisibility";
import { AIBehaviorPanel } from "./components/panels/AIBehaviorPanel";
import { selectActiveDecision } from "./utils/uiBrief";
import { buildAiBehaviorPresentation } from "./utils/workspacePresentation";
import { IntentComposer } from "./components/panels/IntentComposer";
import { PrimitiveControlsPanel, SculptControlsPanel, VersionCanvas } from "./components/StudioCanvas";
import { ThreeViewport } from "./components/ThreeViewport";
import { StudioMenu } from "./components/menu/StudioMenu";
import { PerceptionPanel } from "./components/panels/PerceptionPanel";
import { AnnotationCanvasOverlay } from "./components/overlays/AnnotationCanvasOverlay";
import { clamp01, formatScore, confidenceTone, stringValue, isActiveJobStatus } from "./utils/format";
import { readCandidateMemory } from "./utils/session";
import {
  isSilentObservationInterpretation,
  partSegmentationUrl,
  livePerceptionSummary,
  livePerceptionEvidence,
  CREATIVE_STATES,
  observeCreativeState,
  interactionHistoryItems,
  formatClock,
  behaviorContextDescription,
  buildPlannerNarration,
  perceptionHeadline,
  perceptionEvidenceLine,
  predictorStatusLabel,
  designStateMatches,
  evidenceSummaryItems,
  evidenceValueLabel,
  formatIRScore,
  irRouteLabel,
  irStateLabel,
  rankCandidates,
  candidatePreviewUrl,
  candidateStage,
  candidateFidelity,
  socketCompatibilityScore,
  artifactStatus,
  pipelineEvidence,
  pipelineEvidenceValue,
  remoteJobLabel,
  directionLabel,
  fitEvidenceLabel,
  socketEvidenceLabel,
  seamEvidenceLabel,
  socketScoreLabel,
  partDiscoveryAdapter,
  partDiscoveryDisplayAdapter,
  partDiscoveryRemoteValue,
  isRenderableBenchmarkAsset,
  findPartByViewportName,
  benchmarkAssetGroupLabel,
  compareBenchmarkAssets,
  benchmarkAssetGroups,
  selectedPartFaceCount,
  partSocketSummary,
  stageShortLabel,
  caseCreativeStage,
  isCreativeStage,
  commitPolicyForStage,
  divergenceAxesForStage,
  defaultFidelityForStage,
  upsertIntentDraft,
  upsertArtifact,
  referenceImagesPayload,
  referenceModelsPayload,
  artifactRecordsFromDraftRefs,
  hashString,
  buildAnnotationPayload,
  annotationBoundingBox,
  inferAnnotationShape,
  buildBrushMaskPayload,
  buildSmoothOperationPayload,
  buildPrimitiveAdditionPayload,
  buildDragOperationPayload,
  buildFocusObservationPayload,
  analogyPromptTokens,
  coercePromptToken,
  promptTokenDimension,
  promptTokenKey,
  composePromptWithTokens,
  buildAnalogyPromptPackage,
  inferObjectType,
  isDiscoverableMeshFile,
  signalSummary
} from "./utils/appHelpers";

import { inferredChangeScope, inferChangeScopeFromText, explicitScopeFromText, nextBubbleScope } from "./utils/scope";
import { API_BASE, WS_BASE, SESSION_STORAGE_KEY, api, timeoutAfter, absoluteUrl, inferMeshExtension, inferMtlUrl, assetExportUrl } from "./api";
import type { StageState, SessionRecord, AssetRecord, PartRecord, Hypothesis, Interpretation, SemanticTarget, EvidenceSummaryItem, PlannerDecisionResponse, DesignStateIRMatch, AssistanceSuggestion, PlannerClarificationBubble, CreativeState, BubbleScope, IntentBubbleUiState, JobRecord, Candidate, CandidateDecisionResponse, CaseRecord, ArtifactRecord, CaseIndexItem, CaseIndexResponse, CaseManifest, SessionSnapshotResponse, SolutionSpaceResponse, BenchmarkAsset, BenchmarkAssetListResponse, LogItem, PerceptionLogEntry, RemoteWorkerHealth, RemoteWorkerPreflight, BackendHealth, GeometryWorkerResponse, CanvasPrimitive, CanvasTool, CanvasDisplayMode, ChatMessage, PartDiscoveryResponse, ActionAtom, IntentDraft, IntentDraftListResponse, IntentEpisodeResponse, AnalogyDirection, PromptToken, ContextualFragment, LiveSignals, LivePerception, PerceptionLatestResponse, ViewportInteractionSignal, AnnotationPoint, AnnotationStroke, EditorSnapshot, CrossDomainDivergenceResponse, DirectionsSuggestResponse, PromptComposeResponse, SculptTool, ThreeViewportHandle, ThreeViewportProps } from "./types";
import "./styles.css";
import "./workspaceLayout.css";






































import { useStudioStore } from "./state/studioStore";

function App() {
  const {
    session,
    setSession,
    asset,
    setAsset,
    parts,
    setParts,
    stage,
    setStage,
    interpretation,
    setInterpretation,
    job,
    setJob,
    candidates,
    setCandidates,
    previewCandidate,
    setPreviewCandidate,
    canvasPreview,
    setCanvasPreview,
    acceptedCandidateIds,
    setAcceptedCandidateIds,
    caseTitle,
    setCaseTitle,
    caseNotes,
    setCaseNotes,
    savedCase,
    setSavedCase,
    caseLibrary,
    setCaseLibrary,
    savingCase,
    setSavingCase,
    loadingCaseIds,
    setLoadingCaseIds,
    benchmarkAssets,
    setBenchmarkAssets,
    selectedBenchmarkId,
    setSelectedBenchmarkId,
    loadingBenchmark,
    setLoadingBenchmark,
    logs,
    setLogs,
    remoteHealth,
    setRemoteHealth,
    remotePreflight,
    setRemotePreflight,
    systemServices,
    systemServicesLoading,
    startingServiceIds,
    bootstrapRunning,
    backendHealth,
    setBackendHealth,
    partDiscovery,
    setPartDiscovery,
    discoveringParts,
    setDiscoveringParts,
    hy3dCandidateIds,
    hy3dProgress,
    setHy3dCandidateIds,
    fittingCandidateIds,
    setFittingCandidateIds,
    autoDiscoverParts,
    setAutoDiscoverParts,
    uploading,
    setUploading,
    intentText,
    setIntentText,
    selectedPart,
    setSelectedPart,
    partLabelDraft,
    setPartLabelDraft,
    creativeStage,
    setCreativeStage,
    creativeFidelity,
    setCreativeFidelity,
    canvasPrimitive,
    primitiveLocked,
    setCanvasPrimitive,
    canvasTool,
    setCanvasTool,
    sculptTool,
    setSculptTool,
    sculptRadius,
    setSculptRadius,
    sculptStrength,
    setSculptStrength,
    sculptedMeshObjUrl,
    setSculptedMeshObjUrl,
    projectNotice,
    setProjectNotice,
    canvasDisplayMode,
    setCanvasDisplayMode,
    threeViewportRef,
    actionAtoms,
    setActionAtoms,
    referenceImages,
    setReferenceImages,
    referenceModels,
    setReferenceModels,
    selectedPromptTokens,
    setSelectedPromptTokens,
    annotationMode,
    setAnnotationMode, toggleAnnotationMode,
    hoverMode,
    setHoverMode,
    hoverLabel,
    hoverMaskDataUrl,
    setHoverLabel,
    hoverSamBusy,
    setHoverSamBusy,
    studioDrawerOpen,
    setStudioDrawerOpen,
    menuWidth,
    setMenuWidth,
    menuDragRef,
    addMenuOpen,
    setAddMenuOpen, toggleAddMenu,
    canvasPan,
    setCanvasPan,
    canvasZoom,
    setCanvasZoom,
    canvasZoomRef,
    versionCanvasShellRef,
    spacePanArmed,
    setSpacePanArmed,
    creativeState,
    setCreativeState,
    creativeStateConfidence,
    setCreativeStateConfidence,
    intentBubble,
    setIntentBubble,
    bubbleCooldownUntilRef,
    lastMeaningfulActionAtRef,
    fixationEnteredAtRef,
    typedIntentStable,
    setTypedIntentStable,
    plannerNarration,
    setPlannerNarration,
    plannerTypedText,
    setPlannerTypedText,
    liveObserveNarrative,
    plannerNarrationTimerRef,
    plannerNarrationLastAtRef,
    plannerNarrationIntentRef,
    perceptionHistoryOpen,
    setPerceptionHistoryOpen,
    workspaceChromeReady,
    setWorkspaceChromeReady,
    workspaceStartedAt,
    setWorkspaceStartedAt,
    solutionSpaceReleased,
    setSolutionSpaceReleased,
    solutionSpaceReadyPulse,
    setSolutionSpaceReadyPulse,
    solutionSpaceHeight,
    setSolutionSpaceHeight,
    solutionSpaceGenerating,
    setSolutionSpaceGenerating,
    solutionSpaceCandidates,
    solutionSpaceRoundChips,
    displayIntentSeq,
    liveIntentSeq,
    setSolutionSpaceViewIntentSeq,
    versionCanvasDragRef,
    hoverLabelRef,
    hoverModeRef,
    hoverCommittedRef,
    hoverDwellTimerRef,
    liveSignals,
    setLiveSignals,
    livePerception,
    setLivePerception,
    editorScene,
    setSceneVersion,
    socketRef,
    fileInputRef,
    referenceImageInputRef,
    referenceModelInputRef,
    textEditBaselineRef,
    sourceSwitchSeqRef,
    jobSourceSeqRef,
    addLog,
    resetSourceDependentState,
    updateLiveSignals,
    applyServerLiveSignals,
    incrementLiveSignal,
    handleDisplayModeChange,
    handleViewportInteraction,
    applyLocalPerception,
    putLiveSignals,
    syncLivePerceptionToBackend,
    recordActionAtom,
    handleSculptAction,
    toggleSculptTool,
    commitSculptedMesh,
    handleUndoRedoRef,
    renumberActionAtoms,
    removeActionAtom,
    moveActionAtom,
    editorSnapshot,
    restoreEditorSnapshot,
    pushEditorHistory,
    undoEditor,
    redoEditor,
    syncActionAtom,
    hydrateSessionSnapshot,
    bootstrap,
    activeCaseAssetId,
    setCreativeStagePreset,
    candidateMemory,
    activeSelectedPart,
    visibleBehaviorAtoms,
    hasMeaningfulIntentEvidence,
    selectPartFromViewportHit,
    requestViewportSamForHover,
    generationBusy,
    hasRealModel,
    remoteOnline,
    creativeflowReady,
    segmentationReady,
    editablePartsReady,
    renderReady,
    geometryReady,
    canShowSolutionSpace,
    canShowBrush,
    canShowDrag,
    canShowSculpt,
    hasRunnableAction,
    visibleCandidates,
    liveSolutionSpaceVisible,
    solutionSpaceComparing,
    plannerBubbleInterpretation,
    solutionSpaceSignature,
    segmentationPreviewUrl,
    analysisPreviewUrl,
    activePreviewUrl,
    activePreviewLabel,
    sendEvent,
    refreshRemoteHealth,
    refreshSystemServices,
    startSystemService,
    bootstrapSystemServices,
    refreshSession,
    loadCaseLibrary,
    loadSolutionSpace,
    loadBenchmarkAssets,
    loadBenchmarkAsset,
    confirmProjectSwitch,
    switchBenchmarkAsset,
    startBlankWorkspace,
    clearCurrentHistory,
    loadCaseIntoStudio,
    sendBrush,
    sendDrag,
    commitHoverFocus,
    toggleHoverMode,
    recordAnnotation,
    recordAddPrimitive,
    createPrimitive,
    togglePromptToken,
    discoverPartsForAsset,
    discoverParts,
    renameSelectedPart,
    uploadAsset,
    uploadReferenceImage,
    uploadReferenceModel,
    refreshJob,
    cancelJob,
    loadCandidates,
    loadJobCandidates,
    previewCandidateForComparison,
    decideCandidate,
    generateCandidateHy3d,
    fitCandidateToPart,
    versionNodes,
    versionLinks,
    focusVersionCanvas,
    zoomCanvasBy,
    saveCase,
    onMenuHandlePointerDown,
    onMenuHandlePointerMove,
    onMenuHandlePointerUp,
    fourStage,
    liveObservation,
    behaviorSessions,
    intentRevisions,
    uiBrief,
    project,
    projectList,
    projectEvents,
    projectDialogOpen,
    setProjectDialogOpen,
    projectTimelineOpen,
    setProjectTimelineOpen,
    projectBusy,
    recordingError,
    createExperimentProject,
    openExperimentProject,
    endExperimentRun,
    exportExperimentProject,
    activeRevisionId,
    sendIntentRevision,
    selectIntentRevision,
    resolveIntentRevisionGate,
    startActiveRevisionGeneration,
    finalizeSculptBehavior,
    snapshotSculptBehavior,
    cancelSculptBehavior,
    resumeSculptBehavior,
    finalizePrimitiveBehavior,
    cancelPrimitiveBehavior,
    deleteBehavior,
    createFourStageRun,
    advanceFourStageRun,
    gateFourStage,
    startFourStageGeneration,
    saveFourStageDivergenceSelection,
    submitIntentTextToFourStage,
    divergenceTemperature,
    setDivergenceTemperature,
    divergencePerGroupCount,
    setDivergencePerGroupCount,
    divergenceKeywords,
    semanticDivergence,
    semanticDivergenceLoading,
    semanticDivergenceError,
    divergencePhaseMessage,
    selectionPersistenceError,
    scheduleDivergenceParametersCommit,
    triggerPostGateDivergence,
    allCandidates,
    selectedCandidateId,
    setSelectedCandidateId,
    activeVersionId,
    versionViewMode,
    dropCandidateIntoVersionGraph,
    setActiveVersionId,
    highlightVersionNode,
    activateVersionNode,
    deleteVersionNode,
    retryVersionNode,
    activeVersionMeshReady,
  } = useStudioStore();

  const [perceptionWidth, setPerceptionWidth] = useState(320);
  const aiBehaviorWidth = 378;
  const [aiBehaviorCollapsed, setAiBehaviorCollapsed] = useState(false);
  const [perceptionCollapsed, setPerceptionCollapsed] = useState(false);

  const canvasDecisionRevision = selectActiveDecision(intentRevisions);
  const activeIntentRevision = intentRevisions.find((item) => item.revision_id === activeRevisionId) ?? null;
  const latestIntentCutoff = intentRevisions.reduce((latest, item) => Math.max(latest, item.cutoff_seq), 0);
  // Only the newest revision drives the canvas spinner — a stale leftover
  // `planning` row must not keep the blue ring spinning forever.
  const latestIntentRevision = intentRevisions.reduce<(typeof intentRevisions)[number] | null>(
    (latest, item) => (!latest || item.intent_seq >= latest.intent_seq ? item : latest),
    null,
  );
  // Spin for the whole planning window (optimistic + Fast-Gate draft still
  // count as waiting). Stop once status becomes awaiting_gate / failed.
  const gatePlanning = latestIntentRevision?.status === "planning";
  const canSendIntent = Boolean(
    intentText.trim() || sculptTool || behaviorSessions.some((item) => item.status === "committed" && item.behavior_seq > latestIntentCutoff),
  );
  const solutionProgressLabel = fourStage.error?.message
    ? null
    : fourStage.stage === "generation" && fourStage.generationTotal > 0
      ? `${fourStage.generationCompleted}/${fourStage.generationTotal}`
      : solutionSpaceGenerating
        ? fourStage.stage === "generation"
          ? fourStage.generationCompleted > 0
            ? `${fourStage.generationCompleted}${fourStage.generationTotal ? `/${fourStage.generationTotal}` : ""}`
            : "waiting for first image…"
          : "starting…"
        : null;
  const acceptedIntentMarkers = intentRevisions
    .filter((item) => ["accepted", "generating", "completed"].includes(item.status))
    .map((item) => ({
      id: item.revision_id,
      intentSeq: item.intent_seq,
      label: item.gate_question || item.user_text || `意图 ${item.intent_seq}`,
      detail: [
        item.gate_scope ? `范围：${item.gate_scope}` : null,
        item.gate_target ? `目标：${item.gate_target}` : null,
        item.user_text ? `意图：${item.user_text}` : null,
        item.phenomenon ? `现象：${item.phenomenon}` : null,
      ].filter(Boolean).join(" · "),
    }));
  const inheritedRevisionKeywords = activeIntentRevision
    ? [...intentRevisions]
        .filter((item) => item.intent_seq < activeIntentRevision.intent_seq && ["accepted", "generating", "completed"].includes(item.status))
        .reverse()
        .find((item) => item.effective_keywords.length)?.effective_keywords ?? []
    : [];
  const aiBehaviorPresentation = buildAiBehaviorPresentation({
    uiBrief,
    plannerTypedText,
    plannerNarration,
    phenomenon: canvasDecisionRevision?.phenomenon ?? null,
    liveObserveNarrative,
    semanticDivergenceLoading,
    semanticDivergenceError,
    hasDivergenceContent: Boolean(semanticDivergence || divergenceKeywords.length),
  });
  const canTriggerKeywordDivergence = Boolean(session) && !semanticDivergenceLoading;

  return (
    <main
      className={`studio-shell${studioDrawerOpen ? " menu-open" : ""}${liveSolutionSpaceVisible ? " has-solution-space" : ""}${aiBehaviorCollapsed ? " ai-behavior-collapsed" : ""}${perceptionCollapsed ? " perception-collapsed" : ""}`}
      style={{
        ["--solution-space-height" as string]: `${solutionSpaceHeight}px`,
        ["--perception-width" as string]: `${perceptionWidth}px`,
        ["--ai-behavior-width" as string]: `${aiBehaviorWidth}px`,
      }}
    >
      <VersionCanvas
            shellRef={versionCanvasShellRef}
            dragRef={versionCanvasDragRef}
            canvasPan={canvasPan}
            onPanChange={setCanvasPan}
            canvasZoom={canvasZoom}
            zoomCanvasBy={zoomCanvasBy}
            spacePanArmed={spacePanArmed}
            versionNodes={versionNodes}
            versionLinks={versionLinks}
            activeVersionId={activeVersionId}
            versionViewMode={versionViewMode}
            onHighlightVersion={(nodeId, candidate) => void highlightVersionNode(nodeId, candidate)}
            onActivateVersion={(nodeId, candidate) => void activateVersionNode(nodeId, candidate)}
            onShowOverview={() => focusVersionCanvas("all")}
            onDeleteVersion={(nodeId) => void deleteVersionNode(nodeId)}
            versionCandidates={allCandidates}
            onDropCandidate={(candidate) => dropCandidateIntoVersionGraph(candidate)}
            onRetryVersionNode={(nodeId) => retryVersionNode(nodeId)}
            hy3dProgress={hy3dProgress}
            threeViewportRef={threeViewportRef}
            asset={asset}
            activePreviewUrl={activePreviewUrl}
            activePreviewLabel={activePreviewLabel}
            onClearPreview={() => {
              pushEditorHistory("clear preview");
              setPreviewCandidate(null);
              setCanvasPreview(null);
            }}
            selectedPart={selectedPart}
            hoverLabel={hoverLabel}
            hoverMaskDataUrl={hoverMaskDataUrl}
            canvasPrimitive={canvasPrimitive}
            primitiveLocked={primitiveLocked}
            canvasTool={canvasTool}
            canvasDisplayMode={canvasDisplayMode}
            parts={parts}
            onSelectPart={selectPartFromViewportHit}
            onHoverPart={selectPartFromViewportHit}
            onViewportInteraction={handleViewportInteraction}
            sculptTool={sculptTool}
            onSculptAction={handleSculptAction}
            sculptRadius={sculptRadius}
            sculptStrength={sculptStrength}
            editorScene={editorScene}
            annotationMode={annotationMode}
            onCancelAnnotation={toggleAnnotationMode}
            onCommitAnnotation={(strokes, brushStrokes) => {
              // Keep the overlay open: it shows a completion card (2D snapshot +
              // saved state) until the user exits or continues drawing.
              void recordAnnotation(strokes, brushStrokes);
            }}
            onPreviewBranch={(candidate) => void previewCandidateForComparison(candidate)}
            gatePlanning={gatePlanning}
            acceptedIntentMarkers={acceptedIntentMarkers}
            gateOverlay={
              <PlannerClarificationOverlay
                visible={Boolean(canvasDecisionRevision)}
                scope={intentBubble.scope}
                interpretation={plannerBubbleInterpretation}
                selectedPartLabel={activeSelectedPart?.label ?? selectedPart}
                gateModes={(canvasDecisionRevision ? [canvasDecisionRevision] : []).map((revision) => ({
                  id: revision.revision_id,
                  intentSeq: revision.intent_seq,
                  status: revision.status === "planning" ? "planning" : revision.status === "awaiting_gate" ? "pending" : "accepted",
                  provisional: Boolean(revision.gate_provisional),
                  active: revision.revision_id === activeRevisionId,
                  onSelect: revision.status !== "awaiting_gate" ? () => void selectIntentRevision(revision.revision_id) : undefined,
                  question: revision.gate_question,
                  onAccept: revision.status === "awaiting_gate" && !String(revision.revision_id).startsWith("local_")
                    ? () => void resolveIntentRevisionGate(revision.revision_id, true)
                    : undefined,
                  onReject: revision.status === "awaiting_gate" && !String(revision.revision_id).startsWith("local_")
                    ? () => void resolveIntentRevisionGate(revision.revision_id, false)
                    : undefined,
                }))}
              />
            }
          />
      <div className="brand-mark" style={studioDrawerOpen ? { left: Math.max(22, menuWidth + 18) } : undefined}>
        <img className="brand-mark-logo" src="/logo.png?v=20260809b" alt="" width={72} height={34} aria-hidden="true" />
        <h1>Flow Studio</h1>
      </div>

<StudioMenu
      studioDrawerOpen={studioDrawerOpen}
      menuWidth={menuWidth}
      fileInputRef={fileInputRef}
      referenceImageInputRef={referenceImageInputRef}
      referenceModelInputRef={referenceModelInputRef}
      uploadAsset={uploadAsset}
      uploadReferenceImage={uploadReferenceImage}
      uploadReferenceModel={uploadReferenceModel}
      uploading={uploading}
      session={session}
      referenceImages={referenceImages}
      referenceModels={referenceModels}
      benchmarkAssets={benchmarkAssets}
      selectedBenchmarkId={selectedBenchmarkId}
      loadingBenchmark={loadingBenchmark}
      switchBenchmarkAsset={switchBenchmarkAsset}
      loadBenchmarkAssets={loadBenchmarkAssets}
      asset={asset}
      canvasPrimitive={canvasPrimitive}
      startBlankWorkspace={startBlankWorkspace}
      hasRealModel={hasRealModel}
      backendHealth={backendHealth}
      remoteOnline={remoteOnline}
      geometryReady={geometryReady}
      renderReady={renderReady}
      job={job}
      refreshRemoteHealth={refreshRemoteHealth}
      refreshSystemServices={refreshSystemServices}
      startSystemService={startSystemService}
      bootstrapSystemServices={bootstrapSystemServices}
      systemServices={systemServices}
      systemServicesLoading={systemServicesLoading}
      startingServiceIds={startingServiceIds}
      bootstrapRunning={bootstrapRunning}
      acceptedCandidateIds={acceptedCandidateIds}
      caseTitle={caseTitle}
      setCaseTitle={setCaseTitle}
      activeCaseAssetId={activeCaseAssetId}
      savingCase={savingCase}
      saveCase={saveCase}
      savedCase={savedCase}
      onMenuHandlePointerDown={onMenuHandlePointerDown}
      onMenuHandlePointerMove={onMenuHandlePointerMove}
      onMenuHandlePointerUp={onMenuHandlePointerUp}
      onMenuToggle={() => setStudioDrawerOpen((current) => !current)}
      menuDragRef={menuDragRef}
      project={project}
      projectList={projectList}
      projectEvents={projectEvents}
      projectDialogOpen={projectDialogOpen}
      setProjectDialogOpen={setProjectDialogOpen}
      projectTimelineOpen={projectTimelineOpen}
      setProjectTimelineOpen={setProjectTimelineOpen}
      projectBusy={projectBusy}
      recordingError={recordingError}
      createExperimentProject={createExperimentProject}
      openExperimentProject={openExperimentProject}
      endExperimentRun={endExperimentRun}
      exportExperimentProject={exportExperimentProject}
    />
      <section className="workspace">
        <section className="canvas-column">
          {!workspaceChromeReady ? (
            <div className="canvas-loading" role="status" aria-live="polite">
              <span className="canvas-loading-spinner" aria-hidden="true" />
              <span>正在初始化工作区…</span>
            </div>
          ) : null}
          {loadingBenchmark ? (
            <div className="canvas-loading" role="status" aria-live="polite">
              <span className="canvas-loading-spinner" aria-hidden="true" />
              <span>正在加载白模…</span>
            </div>
          ) : null}

          {liveSolutionSpaceVisible ? (
            <SolutionSpaceRail
              candidates={solutionSpaceCandidates}
              directions={[]}
              acceptedCandidateIds={acceptedCandidateIds}
              job={job}
              loading={(solutionSpaceGenerating || fourStage.stage === "generation") && !fourStage.error && displayIntentSeq === liveIntentSeq}
              progressLabel={solutionProgressLabel}
              errorMessage={fourStage.stage === "failed" ? fourStage.error?.message ?? null : null}
              hy3dCandidateIds={hy3dCandidateIds}
              selectedCandidateId={selectedCandidateId}
              height={solutionSpaceHeight}
              onHeightChange={setSolutionSpaceHeight}
              roundChips={solutionSpaceRoundChips}
              displayIntentSeq={displayIntentSeq}
              onSelectRound={(intentSeq) => setSolutionSpaceViewIntentSeq(intentSeq)}
              onSelectCandidate={(candidate) => setSelectedCandidateId(candidate.candidate_id)}
              onDropCandidate={(candidate) => void dropCandidateIntoVersionGraph(candidate)}
              onCollapse={() => {
                setSolutionSpaceReleased((current) =>
                  reduceSolutionSpaceVisibility(current, { type: "collapse" }),
                );
              }}
              onPreview={(candidate) => void previewCandidateForComparison(candidate)}
              onAcceptDirection={(candidate) => void decideCandidate(candidate, "accept", false)}
              onCommit3D={(candidate) => void decideCandidate(candidate, "accept", true)}
              onReject={(candidate) => void decideCandidate(candidate, "reject")}
              onGenerate3D={(candidate) => void generateCandidateHy3d(candidate)}
            />
          ) : null}
          {!liveSolutionSpaceVisible ? (
            <button
              type="button"
              className={`solution-space-launcher is-top-drawer${solutionSpaceReadyPulse ? " is-ready" : ""}`}
              aria-label="Open Solution Space"
              onClick={() => {
                setSolutionSpaceReadyPulse(false);
                setSolutionSpaceReleased((current) =>
                  reduceSolutionSpaceVisibility(current, { type: "expand" }),
                );
              }}
            >
              <span className="solution-space-launcher-grip" aria-hidden="true" />
              <Sparkles size={14} aria-hidden="true" />
              Solution Space · {solutionSpaceCandidates.length || solutionSpaceRoundChips.reduce((sum, chip) => sum + chip.count, 0)}
            </button>
          ) : null}

          {workspaceChromeReady && session ? (
          <div className={`workspace-chrome${sculptTool ? " sculpting" : ""}`} aria-hidden={false}>
          <ResizableShell
            className="perception-float-shell"
            ariaLabel="Perception panel"
            defaultWidth={320}
            minWidth={260}
            maxWidth={520}
            handleCorner="se"
            handlePosition="static"
            resizable
            onSizeChange={(size) => setPerceptionWidth(size.w)}
          >
            <PerceptionPanel
              perceptionHistoryOpen={perceptionHistoryOpen}
              onToggleHistory={() => setPerceptionHistoryOpen((value) => !value)}
              styleLeft={undefined}
              livePerception={livePerception}
              liveObservation={liveObservation}
              behaviorSessions={behaviorSessions}
              hasModel={Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive)}
              collapsed={perceptionCollapsed}
              onCollapsedChange={setPerceptionCollapsed}
            />
          </ResizableShell>
          <ResizableShell
            className="ai-behavior-float-shell"
            ariaLabel="AI Behavior panel"
            defaultWidth={378}
            minWidth={320}
            maxWidth={560}
            handleCorner="sw"
            handlePosition="static"
            resizable
          >
            <AIBehaviorPanel
              presentation={aiBehaviorPresentation}
              divergenceTemperature={divergenceTemperature}
              onDivergenceTemperatureChange={setDivergenceTemperature}
              divergencePerGroupCount={divergencePerGroupCount}
              onDivergencePerGroupCountChange={setDivergencePerGroupCount}
              onDivergenceParametersCommit={scheduleDivergenceParametersCommit}
              semanticDivergence={semanticDivergence}
              semanticDivergenceLoading={semanticDivergenceLoading}
              semanticDivergenceError={semanticDivergenceError}
              divergencePhaseMessage={divergencePhaseMessage}
              selectionPersistenceError={selectionPersistenceError}
              inheritedKeywords={inheritedRevisionKeywords}
              projectNotice={projectNotice}
              onDismissNotice={() => setProjectNotice(null)}
              intentBubble={intentBubble}
              divergenceKeywords={divergenceKeywords}
              selectedPromptTokens={selectedPromptTokens}
              interpretation={interpretation}
              session={session}
              asset={asset}
              generationBusy={generationBusy}
              solutionSpaceGenerating={solutionSpaceGenerating}
              onTogglePromptToken={togglePromptToken}
              onGenerate={() => void startActiveRevisionGeneration()}
              collapsed={aiBehaviorCollapsed}
              onCollapsedChange={setAiBehaviorCollapsed}
            />
          </ResizableShell>

          {(sculptTool && activeVersionMeshReady) || canvasPrimitive ? (
            <div className="canvas-tool-dock" aria-label="Canvas tools">
              {sculptTool && activeVersionMeshReady ? (
                <SculptControlsPanel
                  sculptTool={sculptTool}
                  onExit={() => {
                    void cancelSculptBehavior();
                    setSculptTool(null);
                  }}
                  onContinueSculpt={resumeSculptBehavior}
                  sculptRadius={sculptRadius}
                  onRadiusChange={setSculptRadius}
                  sculptStrength={sculptStrength}
                  onStrengthChange={setSculptStrength}
                  onCommitVersion={() => void commitSculptedMesh()}
                  onDoneBehavior={() => snapshotSculptBehavior()}
                  editorScene={editorScene}
                  asset={asset}
                />
              ) : null}
              {canvasPrimitive ? (
                <PrimitiveControlsPanel
                  primitive={canvasPrimitive}
                  locked={primitiveLocked}
                  onDone={() => finalizePrimitiveBehavior()}
                  onCancel={cancelPrimitiveBehavior}
                  onTransformMode={(mode) => threeViewportRef.current?.setPrimitiveTransformMode?.(mode)}
                />
              ) : null}
            </div>
          ) : null}

          <ResizableShell
            className="canvas-composer-shell-resizable"
            ariaLabel="Intent composer"
            defaultWidth={400}
            minWidth={320}
            maxWidth={480}
            handleCorner="ne"
            handlePosition="static"
            resizable
          >
            <IntentComposer
              intentText={intentText}
              onIntentChange={setIntentText}
              onIntentFocus={() => {
                textEditBaselineRef.current = editorSnapshot();
              }}
              onIntentBlur={() => {
                const baseline = textEditBaselineRef.current;
                if (baseline && baseline.intentText !== intentText) {
                  pushEditorHistory("edit prompt", baseline);
                }
                textEditBaselineRef.current = null;
              }}
              hoverMode={hoverMode}
              onToggleHoverMode={toggleHoverMode}
              sculptTool={sculptTool}
              onToggleSculptTool={toggleSculptTool}
              canShowBrush={canShowBrush}
              canShowDrag={canShowDrag}
              canShowSculpt={canShowSculpt}
              annotationMode={annotationMode}
              onToggleAnnotationMode={toggleAnnotationMode}
              addMenuOpen={addMenuOpen}
              onToggleAddMenu={toggleAddMenu}
              canvasPrimitive={canvasPrimitive}
              asset={asset}
              activeVersionMeshReady={activeVersionMeshReady}
              generationBusy={generationBusy}
              session={session}
              visibleBehaviorAtoms={visibleBehaviorAtoms}
              behaviorSessions={behaviorSessions}
              canSendIntent={canSendIntent}
              onSend={() => void sendIntentRevision()}
              onCreatePrimitive={(primitive) => void createPrimitive(primitive)}
              onDeleteBehavior={(behaviorId) => { void deleteBehavior(behaviorId); }}
              divergenceBusy={semanticDivergenceLoading}
              canTriggerDivergence={canTriggerKeywordDivergence}
              onTriggerDivergence={() => void triggerPostGateDivergence()}
            />
          </ResizableShell>
          </div>
          ) : null}

          {workspaceChromeReady ? (
            <nav className="canvas-nav" aria-label="Canvas navigation">
              <button type="button" title="Undo" aria-label="Undo" disabled={!editorScene.canUndo} onClick={undoEditor}>
                <RotateCcw size={14} aria-hidden="true" />
              </button>
              <button type="button" title="Redo" aria-label="Redo" disabled={!editorScene.canRedo} onClick={redoEditor}>
                <RefreshCw size={14} aria-hidden="true" />
              </button>
              <button type="button" title="Zoom out" aria-label="Zoom out" onClick={() => setCanvasZoom((value) => Math.max(0.4, Number((value - 0.1).toFixed(2))))}>
                <ZoomOut size={14} aria-hidden="true" />
              </button>
              <button type="button" title="Fit all" aria-label="Fit all versions" onClick={() => focusVersionCanvas("all")}>
                <Maximize2 size={14} aria-hidden="true" />
              </button>
              <button type="button" className="active" title="Focus active" aria-label="Focus active version" onClick={() => focusVersionCanvas("active")}>
                <Focus size={14} aria-hidden="true" />
              </button>
            </nav>
          ) : null}
          {workspaceChromeReady && session ? (
            <button
              type="button"
              className="clear-history-fab"
              aria-label="清除当前历史记录"
              onClick={() => void clearCurrentHistory()}
            >
              <RotateCcw size={16} aria-hidden="true" />
            </button>
          ) : null}

        </section>
      </section>
    </main>
  );
}










import { Component, type ReactNode } from "react";

class StudioErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    console.error("[studio-boundary]", error, info.componentStack ?? "");
  }

  render() {
    if (this.state.error) {
      return (
        <div className="studio-error-screen" role="alert">
          <h2>界面遇到问题</h2>
          <p>{String(this.state.error.message ?? this.state.error).slice(0, 240)}</p>
          <button
            type="button"
            onClick={() => {
              this.setState({ error: null });
              window.location.reload();
            }}
          >
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <StudioErrorBoundary>
    <App />
  </StudioErrorBoundary>,
);
