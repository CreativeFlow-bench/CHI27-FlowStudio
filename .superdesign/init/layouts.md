# Shared Layouts

## frontend/src/main.tsx

Root Flow Studio application shell and single-page render tree.

```tsx
import React, { useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
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
import { IntentComposer } from "./components/panels/IntentComposer";
import { CanvasNav, SculptControlsPanel, VersionCanvas } from "./components/StudioCanvas";
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
  buildPerceptionLogEntries,
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
    setAnnotationMode,
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
    setAddMenuOpen,
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
    solutionSpaceGenerating,
    setSolutionSpaceGenerating,
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
    createFourStageRun,
    advanceFourStageRun,
    gateFourStage,
    startFourStageGeneration,
    saveFourStageDivergenceSelection,
    submitIntentTextToFourStage,
    divergenceTemperature,
    setDivergenceTemperature,
    divergenceStrictness,
    setDivergenceStrictness,
    divergenceKeywords,
    semanticDivergence,
    semanticDivergenceLoading,
    semanticDivergenceError,
    selectionPersistenceError,
    commitDivergenceParameters,
    allCandidates,
    selectedCandidateId,
    setSelectedCandidateId,
    activeVersionId,
    versionViewMode,
    dropCandidateIntoVersionGraph,
    setActiveVersionId,
    activateVersionNode,
    retryVersionNode,
    activeVersionMeshReady,
  } = useStudioStore();

  const pendingIntentRevisions = intentRevisions.filter((item) => ["planning", "awaiting_gate"].includes(item.status));
  const canvasDecisionRevision = selectActiveDecision(intentRevisions);
  const activeIntentRevision = intentRevisions.find((item) => item.revision_id === activeRevisionId) ?? null;
  const latestIntentCutoff = intentRevisions.reduce((latest, item) => Math.max(latest, item.cutoff_seq), 0);
  const canSendIntent = Boolean(
    sculptTool || behaviorSessions.some((item) => item.status === "committed" && item.behavior_seq > latestIntentCutoff),
  );
  const inheritedRevisionKeywords = activeIntentRevision
    ? [...intentRevisions]
        .filter((item) => item.intent_seq < activeIntentRevision.intent_seq && ["accepted", "generating", "completed"].includes(item.status))
        .reverse()
        .find((item) => item.effective_keywords.length)?.effective_keywords ?? []
    : [];

  return (
    <main className={`studio-shell ${studioDrawerOpen ? "menu-open" : ""}`}>
      <div className="brand-mark" style={studioDrawerOpen ? { left: Math.max(22, menuWidth + 18) } : undefined}>
        <div className="brand-mark-logo" aria-hidden="true" />
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
            onActivateVersion={(nodeId, candidate) => void activateVersionNode(nodeId, candidate)}
            onShowOverview={() => focusVersionCanvas("all")}
            versionCandidates={allCandidates}
            onDropCandidate={(candidate) => dropCandidateIntoVersionGraph(candidate)}
            onRetryVersionNode={(nodeId) => retryVersionNode(nodeId)}
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
            onCancelAnnotation={() => setAnnotationMode(false)}
            onCommitAnnotation={(strokes, brushStrokes) => {
              // Keep the overlay open: it shows a completion card (2D snapshot +
              // saved state) until the user exits or continues drawing.
              void recordAnnotation(strokes, brushStrokes);
            }}
            onPreviewBranch={(candidate) => void previewCandidateForComparison(candidate)}
          />

          {sculptTool && activeVersionMeshReady ? (
            <SculptControlsPanel
              sculptTool={sculptTool}
              onExit={() => {
                void finalizeSculptBehavior();
                setSculptTool(null);
              }}
              sculptRadius={sculptRadius}
              onRadiusChange={setSculptRadius}
              sculptStrength={sculptStrength}
              onStrengthChange={setSculptStrength}
              onCommit={() => void commitSculptedMesh()}
              editorScene={editorScene}
              asset={asset}
            />
          ) : null}

          <PlannerClarificationOverlay
            visible={Boolean(canvasDecisionRevision)}
            scope={intentBubble.scope}
            interpretation={plannerBubbleInterpretation}
            selectedPartLabel={activeSelectedPart?.label ?? selectedPart}
            gateModes={(canvasDecisionRevision ? [canvasDecisionRevision] : []).map((revision) => ({
              id: revision.revision_id,
              intentSeq: revision.intent_seq,
              status: revision.status === "planning" ? "planning" : revision.status === "awaiting_gate" ? "pending" : "accepted",
              active: revision.revision_id === activeRevisionId,
              onSelect: revision.status !== "awaiting_gate" ? () => void selectIntentRevision(revision.revision_id) : undefined,
              question: revision.gate_question,
              onAccept: revision.status === "awaiting_gate" ? () => void resolveIntentRevisionGate(revision.revision_id, true) : undefined,
              onReject: revision.status === "awaiting_gate" ? () => void resolveIntentRevisionGate(revision.revision_id, false) : undefined,
            }))}
          />
          {liveSolutionSpaceVisible ? (
            <SolutionSpaceRail
              candidates={allCandidates}
              directions={[]}
              acceptedCandidateIds={acceptedCandidateIds}
              job={job}
              loading={solutionSpaceGenerating}
              progressLabel={
                fourStage.stage === "generation" && fourStage.generationTotal > 0
                  ? `${fourStage.generationCompleted}/${fourStage.generationTotal}`
                  : null
              }
              hy3dCandidateIds={hy3dCandidateIds}
              selectedCandidateId={selectedCandidateId}
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
          {solutionSpaceReleased && (allCandidates.length > 0 || solutionSpaceGenerating) ? (
            <button
              type="button"
              className="solution-space-launcher"
              aria-label="Open Solution Space"
              onClick={() => setSolutionSpaceReleased((current) =>
                reduceSolutionSpaceVisibility(current, { type: "expand" })
              )}
            >
              <Sparkles size={14} aria-hidden="true" />
              展开 Solution Space · {allCandidates.length}
            </button>
          ) : null}

          {workspaceChromeReady && session ? (
          <div className={`workspace-chrome${sculptTool ? " sculpting" : ""}`} aria-hidden={false}>
          <PerceptionPanel
            perceptionHistoryOpen={perceptionHistoryOpen}
            onToggleHistory={() => setPerceptionHistoryOpen((value) => !value)}
            styleLeft={studioDrawerOpen ? menuWidth + 18 : undefined}
            livePerception={livePerception}
            liveObservation={liveObservation}
            hoverLabel={hoverLabel}
            hoverMode={hoverMode}
            hoverSamBusy={hoverSamBusy}
            sessionStartedAt={workspaceStartedAt}
            session={session}
            hasModel={Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive)}
            actionAtoms={actionAtoms}
          />
          <AIBehaviorPanel
            fourStage={fourStage}
            divergenceTemperature={divergenceTemperature}
            onDivergenceTemperatureChange={setDivergenceTemperature}
            divergenceStrictness={divergenceStrictness}
            onDivergenceStrictnessChange={setDivergenceStrictness}
            onDivergenceParametersCommit={commitDivergenceParameters}
            semanticDivergence={semanticDivergence}
            semanticDivergenceLoading={semanticDivergenceLoading}
            semanticDivergenceError={semanticDivergenceError}
            selectionPersistenceError={selectionPersistenceError}
            pendingRevisionCount={pendingIntentRevisions.length}
            inheritedKeywords={inheritedRevisionKeywords}
            uiBrief={uiBrief}
            projectNotice={projectNotice}
            onDismissNotice={() => setProjectNotice(null)}
            plannerTypedText={plannerTypedText}
            plannerNarration={plannerNarration}
            intentBubble={intentBubble}
            divergenceKeywords={activeRevisionId ? divergenceKeywords : []}
            selectedPromptTokens={selectedPromptTokens}
            interpretation={interpretation}
            session={session}
            asset={asset}
            generationBusy={generationBusy}
            solutionSpaceGenerating={solutionSpaceGenerating}
            onTogglePromptToken={togglePromptToken}
            onGenerate={() => void startActiveRevisionGeneration()}
          />

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
            onToggleAnnotationMode={() => setAnnotationMode((value) => !value)}
            addMenuOpen={addMenuOpen}
            onToggleAddMenu={() => setAddMenuOpen((value) => !value)}
            canvasPrimitive={canvasPrimitive}
            asset={asset}
            generationBusy={generationBusy}
            session={session}
            visibleBehaviorAtoms={visibleBehaviorAtoms}
            behaviorSessions={behaviorSessions}
            canSendIntent={canSendIntent}
            onSend={() => void sendIntentRevision()}
            onCreatePrimitive={(primitive) => void createPrimitive(primitive)}
          />
          </div>
          ) : null}

          {workspaceChromeReady ? (
          <CanvasNav
            canUndo={editorScene.canUndo}
            canRedo={editorScene.canRedo}
            onUndo={undoEditor}
            onRedo={redoEditor}
            onZoomOut={() => zoomCanvasBy(0.9)}
            onFitAll={() => focusVersionCanvas("all")}
            onFocusActive={() => focusVersionCanvas("active")}
          />
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

```

## frontend/src/components/menu/StudioMenu.tsx

Resizable left rail shared across the workspace.

```tsx
/**
 * Left studio menu: source uploads, runtime status, export, case (refactor P1a).
 */
import { Activity, Box, Download, GripVertical, Play, RefreshCw, Rocket, Save, Upload } from "lucide-react";
import type {
  ArtifactRecord,
  AssetRecord,
  BackendHealth,
  BenchmarkAsset,
  CanvasPrimitive,
  CaseRecord,
  JobRecord,
  SessionRecord,
  SystemServiceInfo,
  ExperimentProjectDetail,
  ExperimentEvent,
  ExperimentExportRecord,
} from "../../types";
import { API_BASE, absoluteUrl, assetExportUrl, inferMeshExtension } from "../../api";
import { benchmarkAssetGroups } from "../../utils/appHelpers";
import { EmptyState, KeyValue, Panel } from "../ui/primitives";
import { ProjectSection } from "../project/ProjectSection";
import { ProjectDialog } from "../project/ProjectDialog";
import { ProjectTimeline } from "../project/ProjectTimeline";

export function StudioMenu({
  studioDrawerOpen,
  menuWidth,
  fileInputRef,
  referenceImageInputRef,
  referenceModelInputRef,
  uploadAsset,
  uploadReferenceImage,
  uploadReferenceModel,
  uploading,
  session,
  referenceImages,
  referenceModels,
  benchmarkAssets,
  selectedBenchmarkId,
  loadingBenchmark,
  switchBenchmarkAsset,
  asset,
  canvasPrimitive,
  startBlankWorkspace,
  hasRealModel,
  backendHealth,
  remoteOnline,
  geometryReady,
  renderReady,
  job,
  refreshRemoteHealth,
  refreshSystemServices,
  startSystemService,
  bootstrapSystemServices,
  systemServices,
  systemServicesLoading,
  startingServiceIds,
  bootstrapRunning,
  acceptedCandidateIds,
  caseTitle,
  setCaseTitle,
  activeCaseAssetId,
  savingCase,
  saveCase,
  savedCase,
  onMenuHandlePointerDown,
  onMenuHandlePointerMove,
  onMenuHandlePointerUp,
  onMenuToggle,
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
}: {
  studioDrawerOpen: boolean,
  menuWidth: number,
  fileInputRef: React.RefObject<HTMLInputElement | null>,
  referenceImageInputRef: React.RefObject<HTMLInputElement | null>,
  referenceModelInputRef: React.RefObject<HTMLInputElement | null>,
  uploadAsset: (file: File | undefined) => void,
  uploadReferenceImage: (file: File | undefined) => void,
  uploadReferenceModel: (file: File | undefined) => void,
  uploading: boolean,
  session: SessionRecord | null,
  referenceImages: ArtifactRecord[],
  referenceModels: ArtifactRecord[],
  benchmarkAssets: BenchmarkAsset[],
  selectedBenchmarkId: string,
  loadingBenchmark: boolean,
  switchBenchmarkAsset: (id: string) => void,
  asset: AssetRecord | null,
  canvasPrimitive: CanvasPrimitive,
  startBlankWorkspace: () => void,
  hasRealModel: boolean,
  backendHealth: BackendHealth | null,
  remoteOnline: boolean,
  geometryReady: boolean,
  renderReady: boolean,
  job: JobRecord | null,
  refreshRemoteHealth: () => void,
  refreshSystemServices: () => void,
  startSystemService: (id: string) => void,
  bootstrapSystemServices: () => void,
  systemServices: SystemServiceInfo[],
  systemServicesLoading: boolean,
  startingServiceIds: string[],
  bootstrapRunning: boolean,
  acceptedCandidateIds: string[],
  caseTitle: string,
  setCaseTitle: (v: string) => void,
  activeCaseAssetId: string | null,
  savingCase: boolean,
  saveCase: () => void,
  savedCase: CaseRecord | null,
  onMenuHandlePointerDown: (event: React.PointerEvent<HTMLButtonElement>) => void,
  onMenuHandlePointerMove: (event: React.PointerEvent<HTMLButtonElement>) => void,
  onMenuHandlePointerUp: (event: React.PointerEvent<HTMLButtonElement>) => void,
  onMenuToggle: () => void,
  project: ExperimentProjectDetail | null,
  projectList: ExperimentProjectDetail[],
  projectEvents: ExperimentEvent[],
  projectDialogOpen: boolean,
  setProjectDialogOpen: (open: boolean) => void,
  projectTimelineOpen: boolean,
  setProjectTimelineOpen: (open: boolean) => void,
  projectBusy: boolean,
  recordingError: string | null,
  createExperimentProject: (input: { title: string; participantCode?: string; conditionLabel?: string; baselineMode: "blank" | "current_state" }) => Promise<unknown>,
  openExperimentProject: (id: string) => Promise<unknown>,
  endExperimentRun: () => Promise<unknown>,
  exportExperimentProject: () => Promise<ExperimentExportRecord | null>,
}) {
  const onMenuHandleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onMenuToggle();
    }
  };

  return (
    <>
      <aside
        className={`studio-rail ${studioDrawerOpen ? "is-open" : ""}`}
        style={{ width: studioDrawerOpen ? menuWidth : 0 }}
        aria-label="Studio menu"
        aria-hidden={!studioDrawerOpen}
        inert={!studioDrawerOpen}
      >
        <div className="studio-rail-scroll">
            <ProjectSection
              project={project}
              recordingError={recordingError}
              onNew={() => setProjectDialogOpen(true)}
              onOpen={() => setProjectDialogOpen(true)}
              onTimeline={() => setProjectTimelineOpen(true)}
            />
            <Panel title="Source" icon={<Upload size={16} />}>
              <div className="upload-row">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".glb,.obj,.zip"
                  onChange={(event) => void uploadAsset(event.target.files?.[0])}
                />
                <input
                  ref={referenceImageInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(event) => void uploadReferenceImage(event.target.files?.[0])}
                />
                <input
                  ref={referenceModelInputRef}
                  type="file"
                  accept=".glb,.obj,.zip"
                  onChange={(event) => void uploadReferenceModel(event.target.files?.[0])}
                />
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading || !session}>
                  <Upload size={16} /> {uploading ? "Uploading" : "Upload OBJ/GLB"}
                </button>
                <button onClick={() => referenceImageInputRef.current?.click()} disabled={uploading || !session}>
                  <Upload size={16} /> Ref Image
                </button>
                <button onClick={() => referenceModelInputRef.current?.click()} disabled={uploading || !session}>
                  <Upload size={16} /> Ref Model
                </button>
              </div>
              {referenceImages.length ? (
                <div className="reference-image-strip">
                  {referenceImages.slice(0, 4).map((item) => (
                    <div className="reference-image-chip" key={item.artifact_id}>
                      <img src={absoluteUrl(item.url)} alt="reference" width={72} height={52} loading="lazy" />
                      <span>{String(item.metadata?.role ?? "reference")}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {referenceModels.length ? (
                <div className="reference-model-strip">
                  {referenceModels.slice(0, 4).map((item) => (
                    <div className="reference-model-chip" key={item.artifact_id}>
                      <Box size={13} />
                      <span>{String(item.metadata?.uploaded_filename ?? item.metadata?.role ?? "model ref")}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {benchmarkAssets.length ? (
                <label>
                  Design DB
                  <select
                    value={selectedBenchmarkId}
                    disabled={loadingBenchmark}
                    onChange={(event) => void switchBenchmarkAsset(event.target.value)}
                  >
                    <option value="">Choose a white model...</option>
                    {benchmarkAssetGroups(benchmarkAssets).map((group) => (
                      <optgroup key={group.label} label={group.label}>
                        {group.assets.map((item) => (
                          <option key={item.benchmark_id} value={item.benchmark_id}>
                            {item.label}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
              ) : (
                <div className="benchmark-loading">白模库加载中…</div>
              )}
              <button className="ghost compact" disabled={!session || (!asset && !canvasPrimitive)} onClick={startBlankWorkspace}>
                Start Blank
              </button>
              {hasRealModel ? <KeyValue label="model" value={asset?.label} /> : <EmptyState text="Blank workspace: compose text, refs, or choose/upload a model" />}
            </Panel>

            <Panel title="Runtime" icon={<Activity size={16} />}>
              <div className="runtime-chip-row">
                <span>backend {backendHealth?.status === "ok" ? "online" : "offline"}</span>
                {remoteOnline ? <span>worker online</span> : <span>worker offline</span>}
                {geometryReady ? <span>geometry</span> : null}
                {renderReady ? <span>render</span> : null}
                {session ? <span>{session.session_id.slice(0, 10)}</span> : null}
                {job ? <span>{job.status}</span> : null}
              </div>
              <button className="ghost compact" onClick={refreshRemoteHealth}>
                <RefreshCw size={16} /> Check runtime
              </button>
            </Panel>

            {asset && hasRealModel ? (
              <Panel title="Export 3D" icon={<Download size={16} />}>
                <p className="export-note">Download only real mesh outputs from the active asset.</p>
                <div className="case-link-row">
                  {asset.mesh_url && inferMeshExtension(asset.mesh_url) !== "obj" ? (
                    <a href={assetExportUrl(asset.asset_id, "glb")} target="_blank" rel="noreferrer">
                      Export GLB
                    </a>
                  ) : null}
                  {asset.obj_url || inferMeshExtension(asset.mesh_url ?? "") === "obj" ? (
                    <a href={assetExportUrl(asset.asset_id, "obj")} target="_blank" rel="noreferrer">
                      Export OBJ
                    </a>
                  ) : null}
                </div>
              </Panel>
            ) : null}

            {acceptedCandidateIds.length ? (
              <Panel title="Case" icon={<Save size={16} />}>
                <label>
                  Title
                  <input value={caseTitle} onChange={(event) => setCaseTitle(event.target.value)} />
                </label>
                <button className="ghost" disabled={!activeCaseAssetId || savingCase} onClick={saveCase}>
                  <Save size={16} /> {savingCase ? "Saving" : "Save case"}
                </button>
                {savedCase?.report_url ? (
                  <div className="case-link-row">
                    <a href={`${API_BASE}${savedCase.report_url}`} target="_blank" rel="noreferrer">
                      Report
                    </a>
                  </div>
                ) : null}
              </Panel>
            ) : null}

            <Panel title="Services" icon={<Activity size={16} />}>
              <div className="service-toolbar">
                <button
                  className="ghost compact"
                  onClick={() => void refreshSystemServices()}
                  disabled={systemServicesLoading}
                >
                  <RefreshCw size={14} /> Refresh
                </button>
                <button
                  className="ghost compact"
                  onClick={() => void bootstrapSystemServices()}
                  disabled={bootstrapRunning || systemServicesLoading}
                >
                  <Rocket size={14} /> {bootstrapRunning ? "Starting…" : "Start missing"}
                </button>
              </div>
              {systemServices.length === 0 ? (
                <EmptyState text={systemServicesLoading ? "probing services…" : "no service info"} />
              ) : (
                <ul className="service-list">
                  {systemServices.map((service) => {
                    const starting = Boolean(
                      service.starting || startingServiceIds.includes(service.id),
                    );
                    const up = service.state === "up";
                    return (
                      <li className={`service-item state-${service.state}`} key={service.id}>
                        <span className="service-dot" title={service.detail ?? service.state} />
                        <span className="service-name">
                          {service.name_zh ?? service.name ?? service.id}
                          <em>
                            :{service.port} · {service.state}
                            {service.required ? " · required" : ""}
                          </em>
                        </span>
                        {!up && service.startable && !starting ? (
                          <button
                            className="ghost compact service-start"
                            onClick={() => startSystemService(service.id)}
                            title={`Start ${service.name ?? service.id}`}
                          >
                            <Play size={13} /> Start
                          </button>
                        ) : starting ? (
                          <span className="service-starting">starting…</span>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="service-note">
                初始化自动拉起全部必需服务（Qwen-Image 常驻、planner、worker、前端、KG 代理、CreativeFlow API）。
                可选服务（intent_vlm）未安装；点击 Start 逐个启动缺失服务。
              </p>
            </Panel>
        </div>
      </aside>
      {projectDialogOpen ? (
        <ProjectDialog
          projects={projectList}
          busy={projectBusy}
          onClose={() => setProjectDialogOpen(false)}
          onCreate={createExperimentProject}
          onOpen={openExperimentProject}
        />
      ) : null}
      {projectTimelineOpen && project ? (
        <ProjectTimeline
          project={project}
          events={projectEvents}
          onClose={() => setProjectTimelineOpen(false)}
          onEnd={endExperimentRun}
          onExport={exportExperimentProject}
        />
      ) : null}
      <button
        className={`studio-rail-handle ${studioDrawerOpen ? "is-open" : ""}`}
        type="button"
        style={{ left: studioDrawerOpen ? Math.max(8, menuWidth - 14) : 10 }}
        title={studioDrawerOpen ? "Drag to resize · click to close" : "Open menu"}
        aria-label={studioDrawerOpen ? "Resize or close studio menu" : "Open studio menu"}
        aria-expanded={studioDrawerOpen}
        onPointerDown={onMenuHandlePointerDown}
        onPointerMove={onMenuHandlePointerMove}
        onPointerUp={onMenuHandlePointerUp}
        onPointerCancel={onMenuHandlePointerUp}
        onKeyDown={onMenuHandleKeyDown}
      >
        <GripVertical size={16} />
      </button>


    </>
  );
}

```

## frontend/src/components/StudioCanvas.tsx

Canvas shell, navigation, version graph, and sculpt controls.

```tsx
/**
 * Version canvas shell: pannable/zoomable canvas with ThreeViewport,
 * branch thumbnails, sculpt controls panel and canvas navigation
 * (refactor plan P1a).
 */
import { useState } from "react";
import { Box, Focus, Maximize2, RefreshCw, RotateCcw, X, ZoomOut } from "lucide-react";
import type {
  AnnotationStroke,
  AssetRecord,
  CanvasDisplayMode,
  Candidate,
  CanvasPrimitive,
  CanvasTool,
  PartRecord,
  SculptTool,
  VersionNodeStatus,
  ViewportInteractionSignal,
} from "../types";
import type { ThreeViewportHandle } from "../types";
import { ThreeViewport } from "./ThreeViewport";
import { AnnotationCanvasOverlay } from "./overlays/AnnotationCanvasOverlay";
import { FLOWSTUDIO_CANDIDATE_MIME } from "../utils/versionGraph";

// Native drag payload: application/x-flowstudio-candidate.

export type VersionCanvasNode = {
  id: string;
  kind: "source" | "branch";
  versionNumber: number;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  previewUrl: string | null;
  meshUrl: string | null;
  objUrl: string | null;
  status: VersionNodeStatus;
  error: string | null;
  isActivePath: boolean;
  candidate: Candidate | null;
};

export type VersionCanvasLink = {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  controlX1: number;
  controlX2: number;
  isActivePath: boolean;
};

export type CanvasPanState = { x: number; y: number };

export type EditorSceneLike = {
  setGeometry(geometry: unknown): void;
  canUndo: boolean;
  canRedo: boolean;
  editOps(): unknown[];
};

export type CanvasDragRef = {
  active: boolean;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
};

export function VersionCanvas({
  shellRef,
  dragRef,
  canvasPan,
  onPanChange,
  canvasZoom,
  zoomCanvasBy,
  spacePanArmed,
  versionNodes,
  versionLinks,
  threeViewportRef,
  asset,
  activePreviewUrl,
  activePreviewLabel,
  onClearPreview,
  selectedPart,
  hoverLabel,
  hoverMaskDataUrl,
  canvasPrimitive,
  canvasTool,
  canvasDisplayMode,
  parts,
  onSelectPart,
  onHoverPart,
  onViewportInteraction,
  sculptTool,
  onSculptAction,
  sculptRadius,
  sculptStrength,
  editorScene,
  annotationMode,
  onCancelAnnotation,
  onCommitAnnotation,
  onPreviewBranch,
  activeVersionId,
  versionViewMode,
  onActivateVersion,
  onShowOverview,
  versionCandidates,
  onDropCandidate,
  onRetryVersionNode,
}: {
  shellRef: React.RefObject<HTMLDivElement | null>;
  dragRef: React.MutableRefObject<CanvasDragRef | null>;
  canvasPan: CanvasPanState;
  onPanChange: (pan: CanvasPanState) => void;
  canvasZoom: number;
  zoomCanvasBy: (factor: number) => void;
  spacePanArmed: boolean;
  versionNodes: VersionCanvasNode[];
  versionLinks: VersionCanvasLink[];
  threeViewportRef: React.RefObject<ThreeViewportHandle | null>;
  asset: AssetRecord | null;
  activePreviewUrl: string | null;
  activePreviewLabel: string | null;
  onClearPreview: () => void;
  selectedPart: string;
  hoverLabel: string | null;
  hoverMaskDataUrl?: string | null;
  canvasPrimitive: CanvasPrimitive;
  canvasTool: CanvasTool;
  canvasDisplayMode: CanvasDisplayMode;
  parts: PartRecord[];
  onSelectPart: (part: string, source: "click" | "hover") => void;
  onHoverPart: (part: string, source: "click" | "hover") => void;
  onViewportInteraction: (signal: ViewportInteractionSignal) => void;
  sculptTool: SculptTool | null;
  onSculptAction: (tool: SculptTool, evidence: Record<string, unknown>) => void;
  sculptRadius: number;
  sculptStrength: number;
  editorScene: EditorSceneLike;
  annotationMode: boolean;
  onCancelAnnotation: () => void;
  onCommitAnnotation: (strokes: AnnotationStroke[], brushStrokes?: Array<{ brush: string; points: AnnotationStroke }>) => void;
  onPreviewBranch: (candidate: Candidate) => void;
  activeVersionId: string;
  versionViewMode: "active" | "overview";
  onActivateVersion: (nodeId: string, candidate: Candidate | null) => void;
  onShowOverview: () => void;
  versionCandidates: Candidate[];
  onDropCandidate: (candidate: Candidate) => void | Promise<void>;
  onRetryVersionNode: (nodeId: string) => void | Promise<void>;
}) {
  const [dropTargetActive, setDropTargetActive] = useState(false);
  const statusLabel = (status: VersionNodeStatus) => {
    if (status === "generating_3d") return "正在生成 3D";
    if (status === "mesh_ready") return "可编辑 3D";
    if (status === "mesh_failed") return "3D 失败";
    return "图片已就绪";
  };
  return (
    <div
      className={`version-canvas-shell${dropTargetActive ? " is-drop-target" : ""}`}
      aria-label="Version history canvas drop target"
      ref={shellRef}
      onDragEnter={(event) => {
        if (!event.dataTransfer.types.includes(FLOWSTUDIO_CANDIDATE_MIME)) return;
        event.preventDefault();
        setDropTargetActive(true);
      }}
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes(FLOWSTUDIO_CANDIDATE_MIME)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDropTargetActive(true);
      }}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDropTargetActive(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setDropTargetActive(false);
        const raw = event.dataTransfer.getData(FLOWSTUDIO_CANDIDATE_MIME);
        if (!raw) return;
        try {
          const payload = JSON.parse(raw) as { candidateId?: string };
          const candidate = versionCandidates.find((item) => item.candidate_id === payload.candidateId);
          if (candidate) void onDropCandidate(candidate);
        } catch {
          // Ignore malformed payloads from outside FlowStudio.
        }
      }}
      onWheel={(event) => {
        if (event.ctrlKey || event.metaKey) {
          // Trackpad pinch over the 3D viewport must zoom the camera only;
          // the 2D canvas zoom is reserved for the empty canvas area and the
          // explicit CanvasNav buttons.
          const target = event.target as HTMLElement | null;
          if (target && !target.closest(".version-node-frame")) {
            event.preventDefault();
            zoomCanvasBy(event.deltaY > 0 ? 0.9 : 1.1);
          }
        }
      }}
      onPointerDown={(event) => {
        if (!(spacePanArmed || event.button === 1 || event.altKey)) return;
        dragRef.current = {
          active: true,
          startX: event.clientX,
          startY: event.clientY,
          originX: canvasPan.x,
          originY: canvasPan.y,
        };
        (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag?.active) return;
        onPanChange({
          x: drag.originX + (event.clientX - drag.startX),
          y: drag.originY + (event.clientY - drag.startY),
        });
      }}
      onPointerUp={() => {
        if (dragRef.current) dragRef.current.active = false;
      }}
    >
      {dropTargetActive ? <div className="version-drop-hint">释放以创建下一版本</div> : null}
      <div
        className="version-canvas-world"
        style={{ transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${canvasZoom})` }}
      >
        <svg className="version-canvas-links" aria-hidden="true">
          {versionLinks.map((link) => (
            <path
              key={link.id}
              className={`version-link${link.isActivePath ? " is-active-path" : ""}`}
              d={`M ${link.x1} ${link.y1} C ${link.controlX1} ${link.y1}, ${link.controlX2} ${link.y2}, ${link.x2} ${link.y2}`}
            />
          ))}
        </svg>

        {versionNodes.map((node) =>
          node.id === activeVersionId && versionViewMode === "active" ? (
            <div
              className={`version-node active status-${node.status}${node.isActivePath ? " is-active-path" : ""}`}
              key={node.id}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
            >
              <div className="version-node-meta">
                <strong>Version {node.versionNumber}</strong>
                <span>{node.label}</span>
                <em>{statusLabel(node.status)}</em>
                <button type="button" aria-label="查看全部版本" onClick={onShowOverview}>全部版本</button>
              </div>
              <div className="version-node-frame">
                {node.status === "mesh_ready" ? <ThreeViewport
                  ref={threeViewportRef}
                  asset={asset}
                  previewMeshUrl={node.meshUrl ?? node.objUrl ?? activePreviewUrl}
                  previewLabel={activePreviewLabel}
                  onClearPreview={onClearPreview}
                  selectedPart={selectedPart}
                  hoverLabel={hoverLabel}
                  hoverMaskDataUrl={hoverMaskDataUrl}
                  primitive={canvasPrimitive}
                  tool={canvasTool}
                  displayMode={canvasDisplayMode}
                  parts={parts}
                  onSelectPart={(part) => onSelectPart(part, "click")}
                  onHoverPart={(part) => onHoverPart(part, "hover")}
                  onViewportInteraction={onViewportInteraction}
                  sculptTool={sculptTool}
                  onSculptAction={onSculptAction}
                  sculptRadius={sculptRadius}
                  sculptStrength={sculptStrength}
                  canvasZoom={canvasZoom}
                  onGeometryReady={(geometry) => editorScene.setGeometry(geometry)}
                /> : node.previewUrl ? <img className="version-active-image" src={node.previewUrl} alt={node.label} width={520} height={520} /> : <div className="version-thumb-fallback"><Box size={32} /></div>}
                {node.status === "mesh_ready" ? <AnnotationCanvasOverlay
                  active={annotationMode}
                  onCancel={onCancelAnnotation}
                  onCommit={onCommitAnnotation}
                /> : null}
              </div>
              {node.status === "mesh_failed" ? <button type="button" className="version-retry" aria-label={`重试 Version ${node.versionNumber} 的 3D 生成`} onClick={() => void onRetryVersionNode(node.id)}>重试 3D</button> : null}
            </div>
          ) : (
            <button
              type="button"
              className={`version-node thumbnail status-${node.status}${node.isActivePath ? " is-active-path" : ""}${node.id === activeVersionId ? " is-active-version" : ""}`}
              key={node.id}
              style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
              onClick={() => {
                onActivateVersion(node.id, node.candidate);
              }}
              title={node.id === activeVersionId ? "重新进入当前版本" : "进入该版本"}
            >
              {node.previewUrl ? (
                <img src={node.previewUrl} alt={node.label} width={200} height={150} loading="lazy" />
              ) : (
                <div className="version-thumb-fallback">
                  <Box size={22} />
                </div>
              )}
              <strong>Version {node.versionNumber}</strong>
              <span>{node.label}</span>
              <em>{statusLabel(node.status)}</em>
              {node.status === "mesh_failed" ? <span className="version-retry-inline" role="button" tabIndex={0} aria-label={`重试 Version ${node.versionNumber} 的 3D 生成`} onClick={(event) => { event.stopPropagation(); void onRetryVersionNode(node.id); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); void onRetryVersionNode(node.id); } }}>重试</span> : null}
            </button>
          ),
        )}
      </div>
    </div>
  );
}

export function SculptControlsPanel({
  sculptTool,
  onExit,
  sculptRadius,
  onRadiusChange,
  sculptStrength,
  onStrengthChange,
  onCommit,
  editorScene,
  asset,
}: {
  sculptTool: SculptTool;
  onExit: () => void;
  sculptRadius: number;
  onRadiusChange: (value: number) => void;
  sculptStrength: number;
  onStrengthChange: (value: number) => void;
  onCommit: () => void;
  editorScene: EditorSceneLike;
  asset: AssetRecord | null;
}) {
  return (
    <div className="sculpt-float-panel float-panel" aria-label="Sculpt controls">
      <div className="float-panel-label">
        <span>
          雕刻 ·{" "}
          {sculptTool === "drag"
            ? "Drag 抓取"
            : sculptTool === "brush"
              ? "Brush 凹凸"
              : "Smooth 平滑"}
        </span>
        <button
          className="sculpt-exit"
          type="button"
          title="退出雕刻"
          onClick={onExit}
        >
          <X size={13} />
        </button>
      </div>
      <div className="sculpt-sliders">
        <label>
          笔刷大小
          <input
            type="range"
            min="0.05"
            max="0.8"
            step="0.05"
            value={sculptRadius}
            onChange={(event) => onRadiusChange(Number(event.target.value))}
          />
          <span>{sculptRadius.toFixed(2)}</span>
        </label>
        <label>
          力度
          <input
            type="range"
            min="0.05"
            max="0.6"
            step="0.05"
            value={sculptStrength}
            onChange={(event) => onStrengthChange(Number(event.target.value))}
          />
          <span>{sculptStrength.toFixed(2)}</span>
        </label>
      </div>
      <div className="sculpt-actions">
        <button className="sculpt-save" type="button" onClick={onCommit}>
          保存为资产版本
        </button>
        <em>
          {sculptTool === "drag"
            ? "在模型上按住向外拖动"
            : sculptTool === "brush"
              ? "按住雕刻，Shift 凹陷"
              : "按住平滑"} · Cmd/Ctrl+Z 撤销
        </em>
      </div>
      <div className="sculpt-state-line">
        已编辑 {editorScene.editOps().length} 笔
        {editorScene.canUndo ? " · 可撤销" : ""}
        {asset?.metadata?.current_version_id ? " · 当前版本已提交" : ""}
      </div>
    </div>
  );
}

export function CanvasNav({
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onZoomOut,
  onFitAll,
  onFocusActive,
}: {
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onZoomOut: () => void;
  onFitAll: () => void;
  onFocusActive: () => void;
}) {
  return (
    <div className="canvas-nav" aria-label="Canvas navigation">
      <button type="button" aria-label="Undo" title="Undo" disabled={!canUndo} onClick={onUndo}>
        <RotateCcw size={14} />
      </button>
      <button type="button" aria-label="Redo" title="Redo" disabled={!canRedo} onClick={onRedo}>
        <RefreshCw size={14} />
      </button>
      <button type="button" aria-label="Zoom out" title="Zoom out" onClick={onZoomOut}>
        <ZoomOut size={14} />
      </button>
      <button type="button" aria-label="Fit all" title="Fit all" onClick={onFitAll}>
        <Maximize2 size={14} />
      </button>
      <button type="button" aria-label="Focus active" className="active" title="Focus active" onClick={onFocusActive}>
        <Focus size={14} />
      </button>
    </div>
  );
}

```


