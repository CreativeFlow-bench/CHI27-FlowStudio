import React, { useEffect, useMemo, useRef, useState } from "react";
import { EditorScene } from "../editorScene";
import { clamp01, formatScore, confidenceTone, stringValue, isActiveJobStatus } from "../utils/format";
import { readCandidateMemory } from "../utils/session";
import {
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
  partSegmentationUrl,
  remoteWorkerPathFromUrl,
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
  upsertArtifact,
  referenceImagesPayload,
  referenceModelsPayload,
  hashString,
  buildAnnotationPayload,
  annotationBoundingBox,
  inferAnnotationShape,
  buildBrushMaskPayload,
  buildSmoothOperationPayload,
  buildPrimitiveAdditionPayload,
  buildDragOperationPayload,
  buildFocusObservationPayload,
  coercePromptToken,
  promptTokenDimension,
  promptTokenKey,
  composePromptWithTokens,
  inferObjectType,
  isDiscoverableMeshFile,
  signalSummary
} from "../utils/appHelpers";

import { inferredChangeScope, inferChangeScopeFromText, explicitScopeFromText } from "../utils/scope";
import { API_BASE, WS_BASE, SESSION_STORAGE_KEY, api, sseFetch, timeoutAfter, absoluteUrl, inferMeshExtension, inferMtlUrl, assetExportUrl } from "../api";
import { captureAndUploadViewport, uploadViewportScreenshot } from "../utils/viewportCapture";
import {
  buildSolutionSpaceRoundChips,
  candidateIntentSeq,
  reduceSolutionSpaceVisibility,
} from "../utils/solutionSpaceVisibility";
import {
  fourStageCandidateFromArtifact,
  inheritedKeywordsFromRevisions,
  normalizeGenerationArtifacts,
  summarizeKeywords,
  visibleInheritedKeywords,
} from "./studioInteraction";
import { bindStudioHy3d } from "./studioHy3d";
import {
  centeredActiveCanvasPan,
  EMPTY_LIVE_SIGNALS,
  GATE_TIMEOUT_MS,
  isGenericMeshId,
  REVISION_GATED_INTERACTION,
} from "./studioStoreLayout";
import { mergeRealtimeRevisions } from "../utils/optimisticRevisions";
import { computeOverviewCanvasCamera, layoutVersionGraph } from "../utils/versionGraph";
import { createExperimentEventRecorder } from "../utils/experimentProject";
import {
  buildSemanticDivergenceParameters,
  deriveSemanticDivergenceUiState,
  EMPTY_CANVAS_CHATS,
  isEmptyCanvasChat,
  isMeshJargonLabel,
  isObjectStateNarrative,
} from "../utils/workspacePresentation";
import {
  describeDivergencePhase,
  streamSemanticDivergence,
} from "../utils/semanticDivergenceStream";
import {
  reconcileSelectedPromptTokens,
  resolveServerSelectedCandidateIds,
} from "../utils/selectionReconciliation";
import { createInteractionCoordinator } from "../interaction/coordinator.ts";
import { emptyInteractionState, type InteractionEvent, type InteractionState } from "../interaction/types.ts";
import type { StageState, SessionRecord, AssetRecord, PartRecord, Interpretation, EvidenceSummaryItem, CreativeState, BubbleScope, IntentBubbleUiState, JobRecord, Candidate, CandidateDecisionResponse, CaseRecord, ArtifactRecord, CaseIndexItem, CaseIndexResponse, CaseManifest, SessionSnapshotResponse, SolutionSpaceResponse, BenchmarkAsset, BenchmarkAssetListResponse, LogItem, PerceptionLogEntry, RemoteWorkerHealth, RemoteWorkerPreflight, BackendHealth, SystemServiceInfo, SystemServicesResponse, GeometryWorkerResponse, CanvasPrimitive, CanvasTool, CanvasDisplayMode, PartDiscoveryResponse, ActionAtom, PromptToken, LiveSignals, LivePerception, PerceptionLatestResponse, ViewportInteractionSignal, AnnotationPoint, AnnotationStroke, EditorSnapshot, PromptComposeResponse, SculptTool, ThreeViewportHandle, ThreeViewportProps, FourStageRun, FourStageUiState, FourStageWsEvent, FourStageGateAction, FourStageGateRequest, FourStageDecision, BehaviorSession, BehaviorViewSet, IntentRevision, LiveObservationState, RealtimeObservationSnapshot, SolutionBatch, VersionGraphNode, VersionGraphState, UiBrief, ExperimentProjectDetail, ExperimentEvent, ExperimentExportRecord } from "../types";

const ACTIVE_PROJECT_STORAGE_KEY = "flowstudio.active-project.v1";
function isObjectBehaviorAtom(atom: ActionAtom) {
  return atom.evidence?.source !== "more_creative_prompt_chip";
}

type SelectionPersistenceTracker = {
  sequence: number;
  chain: Promise<boolean>;
  latest: Promise<boolean>;
  pending: boolean;
  error: string | null;
  expectedVersion?: number;
  expectedSelectionVersion?: number;
};

export function useStudioStore() {
  const [session, setSession] = useState<SessionRecord | null>(null);
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [parts, setParts] = useState<PartRecord[]>([]);
  const [stage, setStage] = useState<StageState | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [job, setJob] = useState<JobRecord | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [previewCandidate, setPreviewCandidate] = useState<Candidate | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [activeVersionId, setActiveVersionId] = useState<string>("source");
  const [versionViewMode, setVersionViewMode] = useState<"active" | "overview">("active");
  const [versionGraph, setVersionGraph] = useState<VersionGraphState>({ active_node_id: null, nodes: [] });
  const [versionGraphHydrated, setVersionGraphHydrated] = useState(false);
  const [canvasPreview, setCanvasPreview] = useState<{ url: string; label: string } | null>(null);
  const [acceptedCandidateIds, setAcceptedCandidateIds] = useState<string[]>([]);
  const [caseTitle, setCaseTitle] = useState("Design DB exploration case");
  const [caseNotes, setCaseNotes] = useState("");
  const [savedCase, setSavedCase] = useState<CaseRecord | null>(null);
  const [caseLibrary, setCaseLibrary] = useState<CaseIndexItem[]>([]);
  const [savingCase, setSavingCase] = useState(false);
  const [loadingCaseIds, setLoadingCaseIds] = useState<string[]>([]);
  const [benchmarkAssets, setBenchmarkAssets] = useState<BenchmarkAsset[]>([]);
  const [selectedBenchmarkId, setSelectedBenchmarkId] = useState("");
  const [loadingBenchmark, setLoadingBenchmark] = useState(false);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [remoteHealth, setRemoteHealth] = useState<RemoteWorkerHealth | null>(null);
  const [remotePreflight, setRemotePreflight] = useState<RemoteWorkerPreflight | null>(null);
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(null);
  const [systemServices, setSystemServices] = useState<SystemServiceInfo[]>([]);
  const [systemServicesLoading, setSystemServicesLoading] = useState(false);
  const [startingServiceIds, setStartingServiceIds] = useState<string[]>([]);
  const [bootstrapRunning, setBootstrapRunning] = useState(false);
  const [partDiscovery, setPartDiscovery] = useState<PartDiscoveryResponse | null>(null);
  const [discoveringParts, setDiscoveringParts] = useState(false);
  const [hy3dCandidateIds, setHy3dCandidateIds] = useState<string[]>([]);
  const [hy3dProgress, setHy3dProgress] = useState<{ message: string; progress: number } | null>(null);
  const [fittingCandidateIds, setFittingCandidateIds] = useState<string[]>([]);
  const [autoDiscoverParts, setAutoDiscoverParts] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [intentText, setIntentText] = useState("");
  const [selectedPart, setSelectedPart] = useState("");
  const [partLabelDraft, setPartLabelDraft] = useState("");
  const [creativeStage, setCreativeStage] = useState("silhouette");
  const [creativeFidelity, setCreativeFidelity] = useState("low");
  const [canvasPrimitive, setCanvasPrimitive] = useState<CanvasPrimitive>(null);
  const [primitiveLocked, setPrimitiveLocked] = useState(false);
  const [canvasTool, setCanvasTool] = useState<CanvasTool>("select");
  const [sculptTool, setSculptTool] = useState<SculptTool | null>(null);
  const [sculptRadius, setSculptRadius] = useState(0.28);
  const [sculptStrength, setSculptStrength] = useState(0.28);
  const [sculptedMeshObjUrl, setSculptedMeshObjUrl] = useState<string | null>(null);
  const [projectNotice, setProjectNotice] = useState<string | null>(null);
  const [canvasDisplayMode, setCanvasDisplayMode] = useState<CanvasDisplayMode>("textured");
  const [fourStage, setFourStage] = useState<FourStageUiState>({
    runId: null,
    stage: null,
    decision: null,
    gateOpen: false,
    gateBusy: false,
    gateTimeoutAt: null,
    gateQuestion: null,
    scopeAccepted: false,
    divergenceSelection: null,
    generationArtifacts: [],
    generationCompleted: 0,
    generationTotal: 0,
    error: null,
    creatingRun: false,
  });
  const [liveObservation, setLiveObservation] = useState<LiveObservationState | null>(null);
  const [behaviorSessions, setBehaviorSessions] = useState<BehaviorSession[]>([]);
  const [intentRevisions, setIntentRevisions] = useState<IntentRevision[]>([]);
  const [solutionBatches, setSolutionBatches] = useState<SolutionBatch[]>([]);
  const [uiBrief, setUiBrief] = useState<UiBrief | null>(null);
  const [project, setProject] = useState<ExperimentProjectDetail | null>(null);
  const [projectList, setProjectList] = useState<ExperimentProjectDetail[]>([]);
  const [projectEvents, setProjectEvents] = useState<ExperimentEvent[]>([]);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [projectTimelineOpen, setProjectTimelineOpen] = useState(false);
  const [projectBusy, setProjectBusy] = useState(false);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [activeRevisionId, setActiveRevisionId] = useState<string | null>(null);
  const threeViewportRef = useRef<ThreeViewportHandle | null>(null);
  const sculptBehaviorRef = useRef<{
    tool: SculptTool | "annotation";
    startedAt: string;
    startViews: BehaviorViewSet;
    strokeCount: number;
    evidence: Record<string, unknown>;
    reservation: Promise<BehaviorSession | null>;
    localBehaviorId: string;
  } | null>(null);
  const primitiveBehaviorRef = useRef<{ localBehaviorId: string; primitive: Exclude<CanvasPrimitive, null>; behavior_seq: number; } | null>(null);
  const pendingBehaviorCommitsRef = useRef<Set<Promise<BehaviorSession | null>>>(new Set());
  const latestCommittedBehaviorSeqRef = useRef(0);
  const intentSendQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const latestIntentSeqRef = useRef(0);
  const handleUndoRedoRef = useRef<{ undo(): void; redo(): void }>({ undo: () => {}, redo: () => {} });
  const [actionAtoms, setActionAtoms] = useState<ActionAtom[]>([]);
  const [referenceImages, setReferenceImages] = useState<ArtifactRecord[]>([]);
  const [referenceModels, setReferenceModels] = useState<ArtifactRecord[]>([]);
  const [divergenceTemperature, setDivergenceTemperatureState] = useState(0.2);
  const [divergencePerGroupCount, setDivergencePerGroupCountState] = useState(5);
  const divergenceTemperatureRef = useRef(0.2);
  const divergencePerGroupCountRef = useRef(5);
  const setDivergenceTemperature = (value: number) => {
    divergenceTemperatureRef.current = value;
    setDivergenceTemperatureState(value);
  };
  const setDivergencePerGroupCount = (value: number) => {
    divergencePerGroupCountRef.current = value;
    setDivergencePerGroupCountState(value);
  };
  // 四阶段发散关键词：由 retrieval 先验 / decision divergence_seeds 派生，
  // 是关键词面板的唯一数据源（替代旧 directions/suggest 输出）。
  const [divergenceKeywords, setDivergenceKeywords] = useState<PromptToken[]>([]);
  const [selectedPromptTokens, setSelectedPromptTokens] = useState<PromptToken[]>([]);
  const [excludedInheritedKeywords, setExcludedInheritedKeywords] = useState<string[]>([]);
  const excludedInheritedKeywordsRef = useRef<string[]>([]);
  excludedInheritedKeywordsRef.current = excludedInheritedKeywords;
  const divergenceHydrateRetryRef = useRef<string | null>(null);
  const [semanticDivergence, setSemanticDivergence] = useState<NonNullable<FourStageRun["semantic_divergence"]> | null>(null);
  const [semanticDivergenceLoading, setSemanticDivergenceLoading] = useState(false);
  const [semanticDivergenceError, setSemanticDivergenceError] = useState<string | null>(null);
  const [divergencePhaseMessage, setDivergencePhaseMessage] = useState<string | null>(null);
  const gateResolutionInvocationRef = useRef(0);
  const divergenceCommitInvocationRef = useRef(0);
  const semanticDivergenceInFlightRef = useRef(new Map<string, Promise<NonNullable<FourStageRun["semantic_divergence"]>>>());
  const semanticDivergenceAttachingRevisionRef = useRef<string | null>(null);
  const semanticDivergenceLastSettledKeyRef = useRef<string | null>(null);
  const semanticDivergenceLastSettledResponseRef = useRef<NonNullable<FourStageRun["semantic_divergence"]> | null>(null);
  const semanticDivergenceLatestRequestedKeyRef = useRef<string | null>(null);
  const semanticDivergenceLiveParamsRef = useRef<{
    temperature: number;
    perGroupCount: number;
    revisionId: string | null;
  } | null>(null);
  const semanticDivergenceLiveRequestRef = useRef<Promise<NonNullable<FourStageRun["semantic_divergence"]>> | null>(null);
  const divergenceCommitTimerRef = useRef(0);
  const preflightDivergenceStartedRef = useRef<Set<string>>(new Set());
  const intentRevisionsRef = useRef(intentRevisions);
  intentRevisionsRef.current = intentRevisions;
  const activeRevisionIdRef = useRef(activeRevisionId);
  activeRevisionIdRef.current = activeRevisionId;
  const selectedPromptTokensRef = useRef(selectedPromptTokens);
  selectedPromptTokensRef.current = selectedPromptTokens;
  const [selectionPersistenceErrors, setSelectionPersistenceErrors] = useState<Record<string, string>>({});
  const selectionPersistenceByRevisionRef = useRef(new Map<string, SelectionPersistenceTracker>());
  const selectionPersistenceError = selectionPersistenceErrors[activeRevisionId ?? ""] ?? null;
  const [annotationMode, setAnnotationMode] = useState(false);
  const [hoverMode, setHoverMode] = useState(false);
  const [hoverLabel, setHoverLabel] = useState<string | null>(null);
  const [hoverSamBusy, setHoverSamBusy] = useState(false);
  const [hoverMaskDataUrl, setHoverMaskDataUrl] = useState<string | null>(null);
  const [studioDrawerOpen, setStudioDrawerOpen] = useState(false);
  const [menuWidth, setMenuWidth] = useState(360);
  const menuDragRef = useRef<{
    pointerId: number;
    startX: number;
    startWidth: number;
    wasOpen: boolean;
    moved: boolean;
  } | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [canvasPan, setCanvasPan] = useState(centeredActiveCanvasPan);
  const [canvasZoom, setCanvasZoom] = useState(1);
  const canvasZoomRef = useRef(canvasZoom);
  canvasZoomRef.current = canvasZoom;
  const versionCanvasShellRef = useRef<HTMLDivElement | null>(null);
  const [activeEditorExtent, setActiveEditorExtent] = useState(() => ({
    width: typeof window === "undefined" ? 1440 : window.innerWidth,
    height: typeof window === "undefined" ? 900 : window.innerHeight,
  }));
  const [spacePanArmed, setSpacePanArmed] = useState(false);
  const [creativeState, setCreativeState] = useState<CreativeState>("idle");
  const [creativeStateConfidence, setCreativeStateConfidence] = useState(1);
  const [intentBubble, setIntentBubble] = useState<IntentBubbleUiState>({
    visible: false,
    scope: null,
    status: null,
    shownAt: null,
  });
  const bubbleCooldownUntilRef = useRef(0);
  const composedInterpretKeyRef = useRef("");
  const lastFourStageDecisionIdRef = useRef<string | null>(null);
  const lastMeaningfulActionAtRef = useRef<number | null>(null);
  const fixationEnteredAtRef = useRef<number | null>(null);
  const [typedIntentStable, setTypedIntentStable] = useState(false);
  const [plannerNarration, setPlannerNarration] = useState("I'm watching the canvas quietly — take a move whenever you're ready.");

  useEffect(() => {
    const revision = intentRevisions.find((item) => item.revision_id === activeRevisionId);
    if (!revision?.semantic_divergence_status) return;
    const projected = deriveSemanticDivergenceUiState({
      revisionStatus: revision.semantic_divergence_status,
      revisionError: revision.semantic_divergence_error,
      resultStatus: semanticDivergence?.status ?? null,
      hasCandidates: divergenceKeywords.length > 0,
    });
    if (projected.loading) {
      setSemanticDivergenceLoading(true);
      setSemanticDivergenceError(null);
      setDivergencePhaseMessage((current) => current ?? "Connecting to model…");
      return;
    }
    setSemanticDivergenceLoading(false);
    setSemanticDivergenceError(projected.error);
    if (!projected.error) setDivergencePhaseMessage(null);
  }, [
    activeRevisionId,
    divergenceKeywords.length,
    intentRevisions,
    semanticDivergence?.status,
  ]);
  useEffect(() => {
    setExcludedInheritedKeywords([]);
    excludedInheritedKeywordsRef.current = [];
    divergenceHydrateRetryRef.current = null;
  }, [activeRevisionId]);
  const [plannerTypedText, setPlannerTypedText] = useState("");
  const [liveObserveNarrative, setLiveObserveNarrative] = useState<string | null>(null);
  const plannerNarrationTimerRef = useRef<number | null>(null);
  const plannerNarrationLastAtRef = useRef(0);
  const plannerNarrationIntentRef = useRef("");
  const liveObserveAbortRef = useRef<AbortController | null>(null);
  const liveObserveTimerRef = useRef<number | null>(null);
  const liveObserveSignatureRef = useRef("");
  const [perceptionHistoryOpen, setPerceptionHistoryOpen] = useState(false);
  const [workspaceChromeReady, setWorkspaceChromeReady] = useState(false);
  const [workspaceStartedAt, setWorkspaceStartedAt] = useState<string | null>(null);
  const [solutionSpaceReleased, setSolutionSpaceReleased] = useState(true);
  const [solutionSpaceReadyPulse, setSolutionSpaceReadyPulse] = useState(false);
  const wasSolutionSpaceGeneratingRef = useRef(false);
  const [solutionSpaceGenerating, setSolutionSpaceGenerating] = useState(false);
  const [solutionSpaceHeight, setSolutionSpaceHeight] = useState(168);
  /** Which intent round the rail body shows; null = follow live intent. */
  const [solutionSpaceViewIntentSeq, setSolutionSpaceViewIntentSeq] = useState<number | null>(null);
  const versionCanvasDragRef = useRef<{
    active: boolean;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const hoverLabelRef = useRef<string | null>(null);
  const hoverModeRef = useRef(false);
  const hoverCommittedRef = useRef<string | null>(null);
  const hoverDwellTimerRef = useRef<number | null>(null);
  const partFocusKeyRef = useRef<string | null>(null);
  const partFocusStartedAtRef = useRef<number | null>(null);
  const currentPartDwellMs = () => {
    const started = partFocusStartedAtRef.current;
    if (started == null) return 0;
    return Math.min(12_000, Math.max(0, Date.now() - started));
  };
  const notePartFocus = (key: string | null) => {
    const next = String(key || "").trim() || null;
    if (next !== partFocusKeyRef.current) {
      partFocusKeyRef.current = next;
      partFocusStartedAtRef.current = next ? Date.now() : null;
    }
    return currentPartDwellMs();
  };
  const [liveSignals, setLiveSignals] = useState<LiveSignals>(EMPTY_LIVE_SIGNALS);
  const [livePerception, setLivePerception] = useState<LivePerception>({
    summary: "Waiting for your first move.",
    evidence: [],
    confidence: null,
    source: "local",
    updatedAt: new Date().toISOString(),
  });
  const editorScene = useMemo(() => new EditorScene(), []);
  const [, setSceneVersion] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const interactionCursorRef = useRef(0);
  const [interactionState, setInteractionState] = useState<InteractionState>(() => emptyInteractionState());
  const interactionCoordinator = useMemo(() => {
    if (!session?.session_id) return null;
    return createInteractionCoordinator({
      api,
      sessionId: session.session_id,
      onState: setInteractionState,
    });
  }, [session?.session_id]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const referenceImageInputRef = useRef<HTMLInputElement | null>(null);
  const referenceModelInputRef = useRef<HTMLInputElement | null>(null);
  const textEditBaselineRef = useRef<EditorSnapshot | null>(null);
  const sourceSwitchSeqRef = useRef(0);
  const jobSourceSeqRef = useRef<Record<string, number>>({});
  const versionGraphRef = useRef<VersionGraphState>({ active_node_id: null, nodes: [] });
  const hy3dWatchRef = useRef(new Map<string, Promise<void>>());
  const hy3dAdoptedRef = useRef(new Set<string>());
  const versionViewModeRef = useRef<"active" | "overview">(versionViewMode);
  versionViewModeRef.current = versionViewMode;
  const sourceVersionCreationRef = useRef<Promise<VersionGraphState> | null>(null);
  const projectRef = useRef<ExperimentProjectDetail | null>(project);
  projectRef.current = project;
  const projectRecorder = useMemo(
    () => createExperimentEventRecorder({
      isActive: () => Boolean(projectRef.current?.active_run),
      postBatch: (events) => {
        const current = projectRef.current;
        if (!current?.active_run) return Promise.resolve([]);
        return api<ExperimentEvent[]>(
          `/api/v1/projects/${current.project.project_id}/runs/${current.active_run.run_id}/events:batch`,
          { method: "POST", body: JSON.stringify({ events }) },
        );
      },
      onHealthChange: (health, error) => {
        setRecordingError(health === "healthy" ? null : error ?? "记录暂时不可用");
      },
    }),
    [],
  );
  useEffect(() => {
    if (!project?.active_run || !intentText.trim()) return undefined;
    const text = intentText;
    const timer = window.setTimeout(() => {
      void projectRecorder.record(
        "input.text_snapshot",
        { text, trigger: "idle" },
        `text-idle:${hashString(text)}`,
      );
    }, 500);
    return () => window.clearTimeout(timer);
  }, [intentText, project?.active_run?.run_id, projectRecorder]);

  const applyVersionGraph = (next: VersionGraphState) => {
    versionGraphRef.current = next;
    setVersionGraph(next);
    if (next.active_node_id) setActiveVersionId(next.active_node_id);
  };

  const mergeVersionGraphNode = (node: VersionGraphNode, makeActive = false) => {
    const current = versionGraphRef.current;
    const next = {
      active_node_id: makeActive ? node.node_id : current.active_node_id,
      nodes: [...current.nodes.filter((item) => item.node_id !== node.node_id), node]
        .sort((left, right) => left.version_number - right.version_number),
    };
    applyVersionGraph(next);
    return next;
  };

  const addLog = (label: string, detail: string) => {
    setLogs((items) => [{ id: crypto.randomUUID(), label, detail, at: Date.now() }, ...items].slice(0, 18));
  };

  const resetSourceDependentState = (summary = "Waiting for your first move.") => {
    const seq = ++sourceSwitchSeqRef.current;
    if (hoverDwellTimerRef.current) window.clearTimeout(hoverDwellTimerRef.current);
    if (plannerNarrationTimerRef.current) window.clearTimeout(plannerNarrationTimerRef.current);
    hoverDwellTimerRef.current = null;
    plannerNarrationTimerRef.current = null;
    hoverLabelRef.current = null;
    hoverCommittedRef.current = null;
    partFocusKeyRef.current = null;
    partFocusStartedAtRef.current = null;
    lastMeaningfulActionAtRef.current = null;
    fixationEnteredAtRef.current = null;
    setCandidates([]);
    setPreviewCandidate(null);
    setCanvasPreview(null);
    setAcceptedCandidateIds([]);
    setSculptedMeshObjUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    setSculptTool(null);
    editorScene.reset();
    setSelectedPromptTokens([]);
    setExcludedInheritedKeywords([]);
    excludedInheritedKeywordsRef.current = [];
    divergenceHydrateRetryRef.current = null;
    setInterpretation(null);
    setSolutionSpaceReleased((current) =>
      reduceSolutionSpaceVisibility(current, { type: "source_changed" }),
    );
    setSolutionSpaceViewIntentSeq(null);
    setSolutionSpaceGenerating(false);
    setJob(null);
    setPartDiscovery(null);
    setStage((current) =>
      current
        ? {
            ...current,
            active_asset_id: null,
            active_part_id: null,
            current_goal: null,
            suggested_action: null,
            evidence: [],
          }
        : current,
    );
    setAsset(null);
    setParts([]);
    setSelectedPart("");
    setPartLabelDraft("");
    setActionAtoms([]);
    setIntentText("");
    setDivergenceKeywords([]);
    setSemanticDivergence(null);
    setSemanticDivergenceLoading(false);
    setSemanticDivergenceError(null);
    divergenceCommitInvocationRef.current += 1;
    semanticDivergenceInFlightRef.current.clear();
    semanticDivergenceLastSettledKeyRef.current = null;
    semanticDivergenceLastSettledResponseRef.current = null;
    semanticDivergenceLatestRequestedKeyRef.current = null;
    selectionPersistenceByRevisionRef.current.clear();
    setSelectionPersistenceErrors({});
    lastFourStageDecisionIdRef.current = null;
    setSelectedPromptTokens([]);
    // 历史内容：用户不下载即删除（参考图/模型、案例、四阶段产物、hy3d 等）。
    setVersionGraph({ active_node_id: null, nodes: [] });
    setVersionGraphHydrated(false);
    setCanvasPan(centeredActiveCanvasPan());
    setCanvasZoom(1);
    setReferenceImages([]);
    setReferenceModels([]);
    setSavedCase(null);
    setCaseTitle("Design DB exploration case");
    setCaseNotes("");
    setCaseLibrary([]);
    setHy3dCandidateIds([]);
    setFittingCandidateIds([]);
    setSelectedBenchmarkId("");
    sculptBehaviorRef.current = null;
    primitiveBehaviorRef.current = null;
    pendingBehaviorCommitsRef.current.clear();
    latestCommittedBehaviorSeqRef.current = 0;
    latestIntentSeqRef.current = 0;
    interactionCursorRef.current = 0;
    setDiscoveringParts(false);
    setAutoDiscoverParts(true);
    setUploading(false);
    setFourStage({
      runId: null,
      stage: null,
      decision: null,
      gateOpen: false,
      gateBusy: false,
      gateTimeoutAt: null,
      gateQuestion: null,
      scopeAccepted: false,
      divergenceSelection: null,
      generationArtifacts: [],
      generationCompleted: 0,
      generationTotal: 0,
      error: null,
      creatingRun: false,
    });
    setLiveObservation(null);
    setBehaviorSessions([]);
    setIntentRevisions([]);
    preflightDivergenceStartedRef.current.clear();
    setSolutionBatches([]);
    setActiveRevisionId(null);
    setSelectedCandidateId(null);
    setActiveVersionId("source");
    setVersionViewMode("active");
    versionGraphRef.current = { active_node_id: null, nodes: [] };
    setVersionGraph({ active_node_id: null, nodes: [] });
    setVersionGraphHydrated(false);
    sourceVersionCreationRef.current = null;
    setTypedIntentStable(false);
    setIntentBubble({ visible: false, scope: null, status: null, shownAt: null });
    setHoverLabel(null);
    setHoverMode(false);
    setHoverSamBusy(false);
    setAnnotationMode(false);
    setAddMenuOpen(false);
    setCanvasPrimitive(null);
    setCanvasTool("select");
    setCanvasDisplayMode("textured");
    setLiveSignals(EMPTY_LIVE_SIGNALS);
    setLivePerception({
      summary,
      evidence: [],
      confidence: null,
      source: "local",
      updatedAt: new Date().toISOString(),
    });
    setPlannerNarration("I'm watching the canvas quietly — take a move whenever you're ready.");
    setPlannerTypedText("");
    setCanvasPan(centeredActiveCanvasPan());
    setCanvasZoom(1);
    return seq;
  };

  const updateLiveSignals = (patch: Partial<LiveSignals> | ((current: LiveSignals) => Partial<LiveSignals>)) => {
    setLiveSignals((current) => ({ ...current, ...(typeof patch === "function" ? patch(current) : patch) }));
  };

  const applyServerLiveSignals = (signals?: Partial<LiveSignals> | null) => {
    if (!signals) return;
    setLiveSignals((current) => ({ ...current, ...signals }));
  };

  const incrementLiveSignal = (key: keyof LiveSignals, amount = 1) => {
    setLiveSignals((current) => {
      const value = current[key];
      return typeof value === "number" ? { ...current, [key]: value + amount } : current;
    });
  };

  const handleDisplayModeChange = (mode: CanvasDisplayMode) => {
    if (mode !== canvasDisplayMode) {
      updateLiveSignals((current) => ({
        viewport_orbit_count: current.viewport_orbit_count + 1,
        viewport_zoom_count:
          mode === "heatmap" || mode === "parts" ? current.viewport_zoom_count + 1 : current.viewport_zoom_count,
        local_zoom_count:
          mode === "heatmap" || mode === "parts" ? current.local_zoom_count + 1 : current.local_zoom_count,
      }));
    }
    setCanvasDisplayMode(mode);
  };

  const handleViewportInteraction = (signal: ViewportInteractionSignal) => {
    if (!signal.initial) {
      // Orbit / pan / zoom count as activity so idle Gate waits until the user stops.
      lastMeaningfulActionAtRef.current = Date.now();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("flowstudio:user-activity"));
      }
    }
    updateLiveSignals((current) => ({
      viewport_orbit_count:
        !signal.initial && (signal.type === "orbit" || signal.type === "pan")
          ? current.viewport_orbit_count + 1
          : current.viewport_orbit_count,
      viewport_zoom_count:
        !signal.initial && signal.type === "zoom" ? current.viewport_zoom_count + 1 : current.viewport_zoom_count,
      dwell_ms: signal.dwell_ms ? Math.max(current.dwell_ms, signal.dwell_ms) : current.dwell_ms,
      view_mode: signal.view_mode ?? current.view_mode,
    }));
  };

  const applyLocalPerception = (signals: LiveSignals = liveSignals) => {
    const topTarget = interpretation?.semantic_targets?.[0];
    const targetLabel = String(
      topTarget?.semantic?.label_en
        ?? topTarget?.level
        ?? "",
    ).trim();
    const targetPrefix = targetLabel ? `Target: ${targetLabel} · ` : "";
    setLivePerception({
      summary: `${targetPrefix}${livePerceptionSummary(
        signals,
        Boolean(asset?.mesh_url || asset?.obj_url),
        canvasPrimitive,
        activeSelectedPart?.label ?? null,
        interpretation,
      )}`,
      evidence: livePerceptionEvidence(signals, activeSelectedPart?.label ?? null, interpretation),
      confidence: null,
      source: "local",
      updatedAt: new Date().toISOString(),
    });
  };

  useEffect(() => {
    hoverLabelRef.current = hoverLabel;
  }, [hoverLabel]);

  useEffect(() => {
    hoverModeRef.current = hoverMode;
  }, [hoverMode]);

  const putLiveSignals = async (signals: LiveSignals) => {
    if (!session) return;
    try {
      await api(`/api/v1/sessions/${session.session_id}/live-signals`, {
        method: "PUT",
        body: JSON.stringify({ live_signals: signals }),
      });
    } catch (error) {
      addLog("live-signals", String(error).slice(0, 120));
    }
  };

  const syncLivePerceptionToBackend = async (signals: LiveSignals) => {
    if (!session || (!asset && !canvasPrimitive)) return;
    try {
      await putLiveSignals(signals);
    } catch (error) {
      applyLocalPerception(signals);
      addLog("live perception", String(error).slice(0, 160));
    }
  };

  const trackBehaviorCommit = (promise: Promise<BehaviorSession>): Promise<BehaviorSession | null> => {
    const epoch = sourceSwitchSeqRef.current;
    const tracked = promise
      .then((behavior) => {
        if (sourceSwitchSeqRef.current !== epoch) return null;
        latestCommittedBehaviorSeqRef.current = Math.max(
          latestCommittedBehaviorSeqRef.current,
          behavior.behavior_seq,
        );
        setBehaviorSessions((current) => [
          ...current.filter((item) => item.behavior_id !== behavior.behavior_id),
          behavior,
        ].sort((a, b) => a.behavior_seq - b.behavior_seq));
        return behavior;
      })
      .catch((error) => {
        addLog("observation", String(error).slice(0, 120));
        return null;
      });
    pendingBehaviorCommitsRef.current.add(tracked);
    void tracked.finally(() => pendingBehaviorCommitsRef.current.delete(tracked));
    return tracked;
  };

  const recordActionAtom = (
    tool: ActionAtom["tool"],
    target: Record<string, unknown> = {},
    evidence: Record<string, unknown> = {},
  ): string | null => {
    pushEditorHistory(`add ${tool}`);
    const atomId = `atom_${crypto.randomUUID().slice(0, 8)}`;
    const createdAt = new Date().toISOString();
    setActionAtoms((current) => {
      const atom = {
        atom_id: atomId,
        tool,
        target,
        evidence: { ...evidence, live_signals: evidence.live_signals ?? liveSignals },
        order: current.length,
        created_at: createdAt,
      };
      void syncActionAtom(atom);
      // Observation 常驻：行为提交后立即进入会话级编码/检索，不会打开 Gate。
      if (session) {
        const optimisticSeq =
          Math.max(
            0,
            latestCommittedBehaviorSeqRef.current,
            ...behaviorSessions.map((item) => item.behavior_seq),
          ) + 1;
        const optimisticBehavior: BehaviorSession = {
          behavior_id: atom.atom_id,
          session_id: session.session_id,
          behavior_seq: optimisticSeq,
          tool: atom.tool,
          target: {
            asset_id: typeof atom.target.asset_id === "string" ? atom.target.asset_id : null,
            part_id: typeof atom.target.part_id === "string" ? atom.target.part_id : null,
            label:
              typeof atom.target.label === "string"
                ? atom.target.label
                  : (activeSelectedPart?.label ?? (selectedPart || atom.tool)),
          },
          status: "committed",
          started_at: atom.created_at,
          ended_at: atom.created_at,
          stroke_count: Number((atom.evidence as any).stroke_count ?? 1) || 1,
          operation_summary: atom.evidence,
          start_views: {},
          end_views: {},
          evidence_refs: [],
        };
        setBehaviorSessions((currentBehaviors) => [
          ...currentBehaviors.filter((item) => item.behavior_id !== atom.atom_id),
          optimisticBehavior,
        ].sort((a, b) => a.behavior_seq - b.behavior_seq));
        void trackBehaviorCommit(api<BehaviorSession>(`/api/v1/sessions/${session.session_id}/behaviors`, {
          method: "POST",
          body: JSON.stringify({
            behavior_id: atom.atom_id,
            tool: atom.tool,
            target: atom.target,
            started_at: atom.created_at,
            ended_at: atom.created_at,
            stroke_count: optimisticBehavior.stroke_count,
            operation_summary: atom.evidence,
          }),
        }));
      }
      // Reset the idle bubble timer for any non-stroke action atom too.
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("flowstudio:user-activity"));
      }
      return [...current, atom];
    });
    return session ? atomId : null;
  };

  const handleSculptAction = (tool: SculptTool, evidence: Record<string, unknown>) => {
    const label =
      tool === "drag" ? "drag sculpt" : tool === "brush" ? "brush sculpt" : "smooth sculpt";
    const positionsBefore = evidence.positions as Float32Array | undefined;
    const positionsAfter = threeViewportRef.current?.capturePositions?.() ?? null;
    const { positions: _positions, ...compactEvidence } = evidence;
    const activeBehavior = sculptBehaviorRef.current;
    if (activeBehavior && activeBehavior.tool === tool) {
      activeBehavior.strokeCount += 1;
      activeBehavior.evidence = { ...activeBehavior.evidence, ...compactEvidence };
    }
    // Reset the idle bubble timer on every meaningful stroke / drag / smooth.
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("flowstudio:user-activity"));
    }
    updateLiveSignals({
      tool_switch_count: liveSignals.tool_switch_count + 1,
      semantic_distance: Math.min(1, liveSignals.semantic_distance + 0.05),
    });
    if (positionsBefore && positionsAfter) {
      editorScene.pushGeometryEdit(label, tool, positionsBefore, positionsAfter, compactEvidence);
    }
    // P5: geometry editing feeds the perception evidence chain immediately.
    applyLocalPerception({
      ...liveSignals,
      tool_switch_count: liveSignals.tool_switch_count + 1,
      semantic_distance: Math.min(1, liveSignals.semantic_distance + 0.05),
    });
  };

  
  const beginPrimitiveBehavior = (primitive: Exclude<CanvasPrimitive, null>) => {
    const id = `local_beh_${crypto.randomUUID().slice(0, 8)}`;
    const seq =
      Math.max(
        0,
        latestCommittedBehaviorSeqRef.current,
        ...behaviorSessions.map((item) => item.behavior_seq),
      ) + 1;
    const behavior: BehaviorSession = {
      behavior_id: id,
      session_id: session?.session_id ?? "",
      behavior_seq: seq,
      tool: "add",
      target: {
        asset_id: asset?.asset_id ?? null,
        part_id: selectedPart || null,
        label: activeSelectedPart?.label ?? (selectedPart || "add"),
      },
      status: "active",
      started_at: new Date().toISOString(),
      ended_at: null,
      stroke_count: 0,
      operation_summary: { primitive },
      start_views: {},
      end_views: {},
      evidence_refs: [],
    };
    setBehaviorSessions((current) => [...current, behavior]);
    return { ...behavior, localBehaviorId: id, primitive };
  };

  const cancelPrimitiveBehavior = () => {
    const behavior = primitiveBehaviorRef.current;
    primitiveBehaviorRef.current = null;
    if (behavior) {
      setBehaviorSessions((current) => current.filter((item) => item.behavior_id !== behavior.localBehaviorId));
    }
    setCanvasPrimitive(null);
    setPrimitiveLocked(false);
  };

  const finalizePrimitiveBehavior = async (): Promise<{
    behavior: BehaviorSession | null;
    endViews: BehaviorViewSet;
  }> => {
    const empty = { behavior: null as BehaviorSession | null, endViews: {} as BehaviorViewSet };
    const pending = primitiveBehaviorRef.current;
    if (!pending || !session) return empty;
    primitiveBehaviorRef.current = null;
    setPrimitiveLocked(true);
    await new Promise<void>((resolve) => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()));
    });
    const captured = threeViewportRef.current?.captureThreeViews?.(960, 0.82) ?? {};
    const fallback = threeViewportRef.current?.captureJpeg?.(960, 0.82) ?? null;
    const endViews = {
      front: captured.front ?? fallback,
      side: captured.side ?? fallback,
      top: captured.top ?? fallback,
    };
    setBehaviorSessions((current) =>
      current.filter((item) => item.behavior_id !== pending.localBehaviorId),
    );
    const endViewRefs = await uploadBehaviorViews(endViews, "end", "add");
    const screenshot = await captureAndUploadViewport(threeViewportRef.current, {
      sessionId: session.session_id,
      assetId: asset?.asset_id ?? null,
      partId: selectedPart || null,
      metadata: { trigger: "primitive_add_done", primitive: pending.primitive },
    });
    const screenshotUrl = screenshot?.url ?? endViewRefs.front ?? endViews.front ?? null;
    await recordAddPrimitive(pending.primitive, null, {
      viewport_screenshot_url: screenshotUrl,
      viewport_screenshot_artifact_id: screenshot?.artifact_id ?? null,
      end_views: endViewRefs,
    });
    addLog("add", screenshotUrl ? "primitive saved · screenshot" : "primitive saved");
    return {
      behavior: {
        behavior_id: pending.localBehaviorId,
        session_id: session.session_id,
        behavior_seq: pending.behavior_seq,
        tool: "add",
        target: { asset_id: asset?.asset_id ?? null, part_id: selectedPart || null, label: pending.primitive },
        status: "committed",
        started_at: new Date().toISOString(),
        ended_at: new Date().toISOString(),
        stroke_count: 1,
        operation_summary: { primitive: pending.primitive, viewport_screenshot_url: screenshotUrl },
        start_views: {},
        end_views: endViewRefs,
        evidence_refs: screenshotUrl ? [screenshotUrl] : [],
      },
      endViews,
    };
  };

  const beginSculptBehavior = (tool: SculptTool | "annotation", startViews: BehaviorViewSet) => {
    const epoch = sourceSwitchSeqRef.current;
    const startedAt = new Date().toISOString();
    const optimisticId = `local_beh_${crypto.randomUUID().slice(0, 8)}`;
    const nextSeq =
      Math.max(
        0,
        ...behaviorSessions.map((item) => item.behavior_seq),
        latestCommittedBehaviorSeqRef.current,
      ) + 1;
    const optimistic: BehaviorSession = {
      behavior_id: optimisticId,
      session_id: session?.session_id ?? "",
      behavior_seq: nextSeq,
      tool,
      target: {
        asset_id: asset?.asset_id ?? null,
        part_id: selectedPart || null,
        label: activeSelectedPart?.label ?? (selectedPart || tool),
      },
      status: "active",
      started_at: startedAt,
      ended_at: null,
      stroke_count: 0,
      operation_summary: {},
      start_views: {},
      end_views: {},
      evidence_refs: [],
    };
    if (session) {
      setBehaviorSessions((current) =>
        [...current.filter((item) => item.behavior_id !== optimisticId), optimistic].sort(
          (a, b) => a.behavior_seq - b.behavior_seq,
        ),
      );
    }
    const reservation = session
      ? api<BehaviorSession>(`/api/v1/sessions/${session.session_id}/behaviors/start`, {
          method: "POST",
          body: JSON.stringify({
            tool,
            started_at: startedAt,
            target: {
              asset_id: asset?.asset_id ?? null,
              part_id: selectedPart || null,
              label: activeSelectedPart?.label ?? (selectedPart || tool),
            },
          }),
        }).then((behavior) => {
          if (sourceSwitchSeqRef.current !== epoch) return null;
          setBehaviorSessions((current) => [
            ...current.filter(
              (item) => item.behavior_id !== behavior.behavior_id && item.behavior_id !== optimisticId,
            ),
            behavior,
          ].sort((a, b) => a.behavior_seq - b.behavior_seq));
          return behavior;
        }).catch((error) => {
          setBehaviorSessions((current) => current.filter((item) => item.behavior_id !== optimisticId));
          addLog("observation", String(error).slice(0, 120));
          return null;
        })
      : Promise.resolve(null);
    return {
      tool,
      startedAt,
      startViews,
      strokeCount: 0,
      evidence: {},
      reservation,
      localBehaviorId: optimisticId,
    };
  };

  const uploadBehaviorViews = async (
    views: BehaviorViewSet,
    phase: "start" | "end",
    tool: string,
  ): Promise<BehaviorViewSet> => {
    if (!session) return {};
    const entries = await Promise.all(
      (["front", "side", "top"] as const).map(async (view) => {
        const dataUrl = views[view];
        if (!dataUrl) return [view, null] as const;
        const artifact = await uploadViewportScreenshot(dataUrl, {
          sessionId: session.session_id,
          assetId: asset?.asset_id ?? null,
          partId: selectedPart || null,
          metadata: { trigger: "behavior_view", phase, view, tool },
        });
        return [view, artifact?.url ?? null] as const;
      }),
    );
    return Object.fromEntries(entries);
  };

  const deleteBehavior = async (behaviorId: string) => {
    if (!session || !behaviorId) return false;
    const deletingActive = behaviorSessions.some(
      (item) => item.behavior_id === behaviorId && item.status === "active",
    );
    if (deletingActive) {
      sculptBehaviorRef.current = null;
      setSculptTool(null);
    }
    setBehaviorSessions((current) => current.filter((item) => item.behavior_id !== behaviorId));
    setActionAtoms((current) => current.filter((item) => item.atom_id !== behaviorId));
    try {
      if (!behaviorId.startsWith("local_beh_")) {
        await api(`/api/v1/sessions/${session.session_id}/behaviors/${behaviorId}`, {
          method: "DELETE",
        });
      }
      addLog("observation", `deleted behavior ${behaviorId}`);
      return true;
    } catch (error) {
      addLog("observation", String(error).slice(0, 120));
      if (session.session_id) void refreshRealtimeObservation(session.session_id);
      return false;
    }
  };

  /** Exit / toggle-off: drop the active sculpt reservation without committing. */
  const cancelSculptBehavior = async (): Promise<void> => {
    await finalizeSculptBehavior(false);
  };

  const finalizeSculptBehavior = async (
    continueTool = false,
  ): Promise<{ behavior: BehaviorSession | null; endViews: BehaviorViewSet }> => {
    const empty = { behavior: null as BehaviorSession | null, endViews: {} as BehaviorViewSet };
    const behavior = sculptBehaviorRef.current;
    if (!behavior || !session) return empty;
    const endViews = threeViewportRef.current?.captureThreeViews?.(960, 0.82) ?? {};
    if (sculptBehaviorRef.current === behavior) {
      sculptBehaviorRef.current = continueTool
        ? beginSculptBehavior(behavior.tool, endViews)
        : null;
    }
    if (behavior.strokeCount === 0) {
      if (behavior.localBehaviorId) {
        setBehaviorSessions((current) =>
          current.filter((item) => item.behavior_id !== behavior.localBehaviorId),
        );
      }
      return empty;
    }
    const reserved = await behavior.reservation;
    if (behavior.localBehaviorId) {
      setBehaviorSessions((current) =>
        current.filter((item) => item.behavior_id !== behavior.localBehaviorId),
      );
    }
    const [startViewRefs, endViewRefs] = await Promise.all([
      uploadBehaviorViews(behavior.startViews, "start", behavior.tool),
      uploadBehaviorViews(endViews, "end", behavior.tool),
    ]);
    const atom: ActionAtom = {
      atom_id: `atom_${crypto.randomUUID().slice(0, 8)}`,
      tool: behavior.tool,
      target: {
        asset_id: asset?.asset_id ?? null,
        part_id: selectedPart || null,
        label: activeSelectedPart?.label ?? (selectedPart || behavior.tool),
      },
      evidence: {
        ...behavior.evidence,
        intent_text: intentText,
        live_signals: liveSignals,
        end_views: endViewRefs,
        start_views: startViewRefs,
      },
      order: actionAtoms.length,
      created_at: behavior.startedAt,
    };
    setActionAtoms((current) => [...current, { ...atom, order: current.length }]);
    void syncActionAtom(atom);
    const committed = await trackBehaviorCommit(api<BehaviorSession>(`/api/v1/sessions/${session.session_id}/behaviors`, {
      method: "POST",
      body: JSON.stringify({
        behavior_id: reserved?.behavior_id ?? atom.atom_id,
        tool: behavior.tool,
        target: atom.target,
        started_at: behavior.startedAt,
        ended_at: new Date().toISOString(),
        stroke_count: behavior.strokeCount,
        operation_summary: atom.evidence,
        start_views: startViewRefs,
        end_views: endViewRefs,
        evidence_refs: Object.values({ ...startViewRefs, ...endViewRefs }).filter(
          (value): value is string => typeof value === "string" && Boolean(value),
        ),
      }),
    }));
    addLog("observation", `sculpt behavior · ${behavior.tool} · ${behavior.strokeCount} strokes`);
    return { behavior: committed, endViews };
  };

  const snapshotSculptBehavior = async (): Promise<{
    behavior: BehaviorSession | null;
    endViews: BehaviorViewSet;
  }> => {
    const empty = { behavior: null as BehaviorSession | null, endViews: {} as BehaviorViewSet };
    const pending = sculptBehaviorRef.current;
    if (!pending) return empty;
    const captured = threeViewportRef.current?.captureThreeViews?.(960, 0.82) ?? {};
    const fallback = threeViewportRef.current?.captureJpeg?.(960, 0.82) ?? null;
    const endViews = {
      front: captured.front ?? fallback,
      side: captured.side ?? fallback,
      top: captured.top ?? fallback,
    };
    pending.evidence = { ...pending.evidence, preview_end_views: endViews };
    const reserved = await pending.reservation.catch(() => null);
    return {
      behavior: {
        behavior_id: reserved?.behavior_id ?? pending.localBehaviorId,
        session_id: session?.session_id ?? "",
        behavior_seq: reserved?.behavior_seq ?? 0,
        tool: pending.tool,
        target: reserved?.target ?? {},
        status: "active",
        started_at: pending.startedAt,
        ended_at: null,
        stroke_count: pending.strokeCount,
        operation_summary: pending.evidence,
        start_views: pending.startViews,
        end_views: endViews,
        evidence_refs: [],
      },
      endViews,
    };
  };

  /** After Done → continue: keep the same tool session. */
  const resumeSculptBehavior = () => {
    if (sculptBehaviorRef.current || !sculptTool) return;
    sculptBehaviorRef.current = beginSculptBehavior(
      sculptTool,
      threeViewportRef.current?.captureThreeViews?.() ?? {},
    );
  };

  const toggleSculptTool = (next: SculptTool) => {
    if (sculptTool === next) {
      void cancelSculptBehavior();
      setSculptTool(null);
      return;
    }
    if (sculptBehaviorRef.current) void cancelSculptBehavior();
    setAnnotationMode(false);
    setAddMenuOpen(false);
    deactivateHoverMode();
    sculptBehaviorRef.current = beginSculptBehavior(
      next,
      threeViewportRef.current?.captureThreeViews?.() ?? {},
    );
    setSculptTool(next);
  };

  const commitSculptedMesh = async () => {
    if (!session) return;
    const obj = threeViewportRef.current?.exportMeshOBJ?.();
    if (!obj) {
      addLog("sculpt", "没有可保存的雕刻网格");
      return;
    }
    try {
      const form = new FormData();
      form.set("session_id", session.session_id);
      form.set("edit_ops", JSON.stringify(editorScene.editOps()));
      form.set("source", "sculpt_commit");
      form.set(
        "metadata",
        JSON.stringify({
          parent_asset_id: asset?.asset_id ?? null,
          sculpted_at: new Date().toISOString(),
        }),
      );
      form.set("file", new File([obj], "sculpted.obj", { type: "text/plain" }));
      const response = await fetch(`${API_BASE}/api/v1/assets/${asset?.asset_id}/versions`, {
        method: "POST",
        body: form,
      });
      const version = await response.json();
      if (!response.ok || !version?.version_id) throw new Error(version?.detail ?? "version upload failed");
      if (asset) {
        let versionCount = 1;
        try {
          const versions = await api<{ versions: Array<{ version_id: string }> }>(
            `/api/v1/assets/${asset.asset_id}/versions`,
          );
          versionCount = versions.versions.length;
        } catch {
          // version count is best-effort
        }
        const nextAsset: AssetRecord = {
          ...asset,
          obj_url: version.obj_url ?? asset.obj_url,
          mesh_url: version.mesh_url ?? asset.mesh_url,
          metadata: {
            ...(asset.metadata ?? {}),
            current_version_id: version.version_id,
            version_count: versionCount,
          },
        };
        setAsset(nextAsset);
      }
      setSculptedMeshObjUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return null;
      });
      setSculptTool(null);
      setStage((current) =>
        current
          ? {
              ...current,
              active_asset_id: asset?.asset_id ?? current.active_asset_id,
            }
          : current,
      );
      addLog("sculpt", `saved version ${version.version_id} (${editorScene.editOps().length} ops)`);
    } catch (error) {
      addLog("sculpt", String(error).slice(0, 160));
    }
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) handleUndoRedoRef.current.redo();
        else handleUndoRedoRef.current.undo();
      } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "y") {
        event.preventDefault();
        handleUndoRedoRef.current.redo();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const renumberActionAtoms = (items: ActionAtom[]) =>
    items.map((atom, index) => ({ ...atom, order: index }));

  const removeActionAtom = (atomId: string) => {
    pushEditorHistory("remove behavior");
    setActionAtoms((current) => renumberActionAtoms(current.filter((atom) => atom.atom_id !== atomId)));
  };

  const moveActionAtom = (atomId: string, direction: -1 | 1) => {
    pushEditorHistory(direction < 0 ? "move behavior up" : "move behavior down");
    setActionAtoms((current) => {
      const index = current.findIndex((atom) => atom.atom_id === atomId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return renumberActionAtoms(next);
    });
  };

  const editorSnapshot = (): EditorSnapshot => ({
    intentText,
    actionAtoms,
    imageRefs: referenceImages,
    modelRefs: referenceModels,
    selectedPromptTokens,
    previewCandidate,
    canvasPreview,
  });

  const restoreEditorSnapshot = (snapshot: EditorSnapshot) => {
    setIntentText(snapshot.intentText);
    setActionAtoms(snapshot.actionAtoms);
    setReferenceImages(snapshot.imageRefs);
    setReferenceModels(snapshot.modelRefs);
    setSelectedPromptTokens(snapshot.selectedPromptTokens);
    setPreviewCandidate(snapshot.previewCandidate);
    setCanvasPreview(snapshot.canvasPreview);
  };

  const pushEditorHistory = (label: string, snapshot: EditorSnapshot = editorSnapshot()) => {
    editorScene.pushEditorCommand(label, snapshot, restoreEditorSnapshot);
    setSceneVersion((version) => version + 1);
  };

  const undoEditor = () => {
    if (editorScene.undo()) {
      void projectRecorder.record("behavior.undo", { label: editorScene.lastLabel }, `undo:${crypto.randomUUID()}`);
      addLog("undo", editorScene.lastLabel ?? "edit");
    }
  };

  const redoEditor = () => {
    if (editorScene.redo()) {
      void projectRecorder.record("behavior.redo", { label: editorScene.lastLabel }, `redo:${crypto.randomUUID()}`);
      addLog("redo", editorScene.lastLabel ?? "edit");
    }
  };

  handleUndoRedoRef.current = { undo: undoEditor, redo: redoEditor };

  useEffect(() => {
    editorScene.onCommandChange = () => setSceneVersion((version) => version + 1);
    editorScene.onGeometryApply = (positions) => {
      threeViewportRef.current?.applySculptSnapshot(positions);
    };
    return () => {
      editorScene.onCommandChange = null;
      editorScene.onGeometryApply = null;
    };
  }, [editorScene]);

  useEffect(() => {
    // After an editor command's state change has rendered, capture the "after"
    // snapshot so redo can restore it.
    editorScene.captureEditorAfter(editorSnapshot(), restoreEditorSnapshot);
  });

  const syncActionAtom = async (atom: ActionAtom) => {
    if (!session) return;
    try {
      await api<ActionAtom>(`/api/v1/sessions/${session.session_id}/actions`, {
        method: "POST",
        body: JSON.stringify({
          atom_id: atom.atom_id,
          tool: atom.tool,
          target: atom.target,
          evidence: atom.evidence,
          order: atom.order,
          metadata: { synced_from: "intent_composer" },
        }),
      });
    } catch (error) {
      addLog("action sync", String(error).slice(0, 160));
    }
  };

  const hydrateSessionSnapshot = (snapshot: SessionSnapshotResponse) => {
    setSession(snapshot.session);
    setStage(snapshot.session.stage);
    setAsset(snapshot.active_asset);
    setParts(snapshot.active_parts ?? snapshot.active_asset?.parts ?? []);
    setSelectedPart(snapshot.session.stage.active_part_id ?? snapshot.active_parts?.[0]?.part_id ?? "");
    setJob(snapshot.active_job);
    const ranked = rankCandidates(snapshot.visible_candidates ?? []);
    setCandidates(ranked);
    setAcceptedCandidateIds(
      ranked.filter((candidate) => candidate.decision === "accepted").map((candidate) => candidate.candidate_id),
    );
    setPreviewCandidate(ranked.find((candidate) => candidate.mesh_url || candidate.obj_url) ?? null);
    setCanvasPrimitive(null);
    setCanvasDisplayMode("textured");
    setCanvasTool("select");
    applyServerLiveSignals(snapshot.live_signals);
    const latestInterpretation = snapshot.recent_interpretations?.at(-1);
    if (latestInterpretation) setInterpretation(latestInterpretation);
  };

  const bootstrap = async () => {
    let activeSession: SessionRecord | null = null;
    const storedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (storedSessionId) {
      try {
        const snapshot = await Promise.race([
          api<SessionSnapshotResponse>(`/api/v1/sessions/${storedSessionId}/snapshot`),
          timeoutAfter(900, "session snapshot"),
        ]);
        hydrateSessionSnapshot(snapshot);
        activeSession = snapshot.session;
        addLog("session", `restored ${storedSessionId}`);
      } catch (error) {
        if (!String(error).includes("timed out")) {
          window.localStorage.removeItem(SESSION_STORAGE_KEY);
        }
        addLog("session", String(error).slice(0, 120));
      }
    }
    if (!activeSession) {
      try {
        const created = await Promise.race([
          api<SessionRecord>("/api/v1/sessions", {
            method: "POST",
            body: JSON.stringify({ title: "Design DB exploration", user_id: "local-dev" }),
          }),
          timeoutAfter(8000, "create session"),
        ]);
        activeSession = created;
        window.localStorage.setItem(SESSION_STORAGE_KEY, created.session_id);
        setSession(created);
        setStage(created.stage);
        setCanvasPrimitive(null);
        setCanvasDisplayMode("textured");
        setCanvasTool("select");
        setAsset(null);
        setParts([]);
        setSelectedPart("");
        setSelectedBenchmarkId("");
        addLog("session", "blank start; choose a Design DB model or upload refs");
      } catch (error) {
        addLog("session", String(error).slice(0, 160));
      }
    }
    setWorkspaceStartedAt(new Date().toISOString());
    // Session snapshot already contains the active white model. Mount the 3D
    // workspace now; health, service, case and library data can hydrate without
    // delaying the renderer or blocking observation.
    setWorkspaceChromeReady(true);
    if (!activeSession) return;
    void Promise.allSettled([
      refreshRemoteHealth(),
      refreshSystemServices(),
      loadCaseLibrary(),
      loadSolutionSpace(activeSession.session_id),
      loadBenchmarkAssets(),
    ]);

    attachSessionSocket(activeSession.session_id);
  };

  const activeCaseAssetId = useMemo(
    () => stage?.active_asset_id ?? asset?.asset_id ?? null,
    [asset?.asset_id, stage?.active_asset_id],
  );

  const setCreativeStagePreset = (nextStage: string) => {
    setCreativeStage(nextStage);
    setCreativeFidelity(defaultFidelityForStage(nextStage));
  };

  const candidateMemory = useMemo(() => readCandidateMemory(session), [session]);
  const activeSelectedPart = useMemo(
    () => parts.find((part) => part.part_id === selectedPart) ?? null,
    [parts, selectedPart],
  );
  const visibleBehaviorAtoms = useMemo(
    () => renumberActionAtoms(actionAtoms.filter(isObjectBehaviorAtom)),
    [actionAtoms],
  );
  const hasMeaningfulIntentEvidence = Boolean(
    intentText.trim().length >= 3 ||
      visibleBehaviorAtoms.length ||
      selectedPromptTokens.length ||
      liveSignals.annotation_count > 0 ||
      liveSignals.brush_count > 0,
  );
  // Typed intent must settle ~2.2s before it can trigger a bubble (avoid mid-typing interrupts).
  useEffect(() => {
    const text = intentText.trim();
    if (text.length < 3) {
      setTypedIntentStable(false);
      return undefined;
    }
    setTypedIntentStable(false);
    const timer = window.setTimeout(() => setTypedIntentStable(true), 2200);
    return () => window.clearTimeout(timer);
  }, [intentText]);

  useEffect(() => {
    if (!typedIntentStable || !intentText.trim()) return;
    setLivePerception({
      summary: "User typed an intent.",
      evidence: [`typed intent · ${intentText.trim().slice(0, 80)}`],
      confidence: 0.72,
      source: "local",
      updatedAt: new Date().toISOString(),
    });
  }, [typedIntentStable, intentText]);

  const selectPartFromViewportHit = (hitName: string, source: "click" | "hover") => {
    const part = findPartByViewportName(parts, hitName);
    if (!part) {
      if (source === "hover") {
        if (!hitName.trim()) {
          setHoverLabel(null);
          hoverLabelRef.current = null;
          if (hoverDwellTimerRef.current) {
            window.clearTimeout(hoverDwellTimerRef.current);
            hoverDwellTimerRef.current = null;
          }
          notePartFocus(null);
          return;
        }
        // White models may have no registered parts yet: still surface the raw
        // mesh name for visible feedback, but the observation is about the
        // whole silhouette, not a semantic part (reference observation model).
        const fallback = hitName.trim();
        if (fallback && fallback !== hoverLabelRef.current) {
          setHoverLabel(fallback);
          hoverLabelRef.current = fallback;
          const dwellMs = notePartFocus(fallback);
          setLiveSignals((current) => ({
            ...current,
            hover_count: current.hover_count + 1,
            dwell_ms: dwellMs,
          }));
          setLivePerception({
            summary: `User is inspecting the silhouette of ${fallback}.`,
            evidence: ["3D raycast hover · no registered part — silhouette observation"],
            confidence: 0.45,
            source: "local",
            updatedAt: new Date().toISOString(),
          });
        }
      }
      return;
    }
    if (part.part_id !== selectedPart) setSelectedPart(part.part_id);
    if (source === "hover") {
      const switched = hoverLabelRef.current !== part.label;
      setHoverLabel(part.label);
      hoverLabelRef.current = part.label;
      const dwellMs = notePartFocus(part.part_id || part.label);
      setLiveSignals((current) => ({
        ...current,
        hover_count: current.hover_count + (switched ? 1 : 0),
        dwell_ms: dwellMs,
      }));
      setLivePerception({
        summary:
          (liveSignals.view_mode ?? "empty") === "detail"
            ? `User is focusing on ${part.label}.`
            : `User is inspecting the silhouette near ${part.label}.`,
        evidence: [
          `${part.metadata?.source === "obj_group_fallback" ? "tentative OBJ-group label" : "3D raycast hover"} · ${part.label}`,
        ],
        confidence: typeof part.metadata?.confidence === "number" ? part.metadata.confidence : 0.68,
        source: "local",
        updatedAt: new Date().toISOString(),
      });
      if (hoverModeRef.current && switched) {
        if (hoverDwellTimerRef.current) window.clearTimeout(hoverDwellTimerRef.current);
        hoverDwellTimerRef.current = window.setTimeout(() => {
          if (
            hoverModeRef.current &&
            hoverLabelRef.current === part.label &&
            hoverCommittedRef.current !== part.label
          ) {
            void commitHoverFocus("dwell_end");
          }
        }, 1200);
      }
    }
  };

  const requestViewportSamForHover = async (part: PartRecord, point?: { x: number; y: number } | null) => {
    if (!session || !asset || hoverSamBusy) return;
    setHoverSamBusy(true);
    const hoverPoint = point ?? threeViewportRef.current?.getLastPointer?.() ?? { x: 0.5, y: 0.45 };
    const dataUrl = threeViewportRef.current?.captureJpeg?.(640, 0.7) ?? null;
    try {
      let response: {
        status: string;
        adapter?: string;
        mask_url?: string | null;
        overlay_url?: string | null;
        artifact_id?: string | null;
        result?: { mask_coverage?: number; note?: string };
      } | null = null;
      // Frontend MobileSAM first (fast, local); backend viewport-sam worker is
      // the fallback. Both are best-effort — Raycaster stays the floor.
      if (dataUrl) {
        const { segmentPoints } = await import("../utils/segmenter");
        const localMask = await segmentPoints(dataUrl, [{ x: hoverPoint.x, y: hoverPoint.y, label: 1 }]);
        if (localMask?.maskDataUrl) {
          setHoverMaskDataUrl(localMask.maskDataUrl);
          updateLiveSignals({ mask_coverage: localMask.coverage });
          addLog("viewport sam", `frontend mobile-sam mask ${part.label} (${Math.round(localMask.coverage * 100)}%)`);
          return;
        }
      }
      response = await api<{
        status: string;
        adapter?: string;
        mask_url?: string | null;
        overlay_url?: string | null;
        artifact_id?: string | null;
        result?: { mask_coverage?: number; note?: string };
      }>("/api/v1/viewport-segmentation", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset.asset_id,
          part_id: part.part_id,
          label: part.label,
          image_data_url: dataUrl ?? "",
          point: { x: hoverPoint.x, y: hoverPoint.y },
          viewport: { width: 1280, height: 720, camera: canvasDisplayMode },
          metadata: {
            source: "hover_tentative_label",
            frontend_segmenter: "mobile_sam_onnx",
            semantic_source:
              part.metadata?.source === "obj_group_fallback"
                ? "obj_group_projected_hover"
                : "projected_hover_tentative",
          },
        }),
      });
      if (typeof response?.result?.mask_coverage === "number") {
        updateLiveSignals({ mask_coverage: response.result.mask_coverage });
      }
      addLog(
        "viewport sam",
        response?.mask_url
          ? `${part.label} mask ready (${response.adapter ?? "viewport_sam"})`
          : response?.result?.note ?? response?.status ?? "unavailable",
      );
    } catch (error) {
      addLog("viewport sam", String(error).slice(0, 160));
    } finally {
      setHoverSamBusy(false);
    }
  };
  const generationBusy = Boolean(job && isActiveJobStatus(job.status));
  const hasRealModel = Boolean(asset?.mesh_url || asset?.obj_url);
  const remoteOnline = Boolean(backendHealth?.remote_worker_ok && remoteHealth?.ok);
  const creativeflowReady = Boolean(
    remoteOnline &&
      remotePreflight?.core_ready &&
      remoteHealth?.creativeflow_pipeline?.minimal_transfer_ready,
  );
  const segmentationReady = Boolean(
    remoteOnline &&
      (remoteHealth?.segmentation_worker_ready ||
        remoteHealth?.sam3d_ready ||
        (remoteHealth?.partfield_python_exists &&
          remoteHealth?.partfield_model_ready &&
          remoteHealth?.partfield_worker_script_exists)),
  );
  const editablePartsReady = segmentationReady || parts.length > 0;
  const renderReady = Boolean(
    backendHealth?.workers?.render_preview?.ok || remoteHealth?.render_preview_ready,
  );
  const geometryReady = Boolean(
    backendHealth?.workers?.geometry_processing?.ok || remoteHealth?.geometry_worker_ready,
  );
  const activeVersionNode = versionGraph.nodes.find((node) => node.node_id === versionGraph.active_node_id);
  const activeVersionMeshReady = activeVersionNode ? activeVersionNode.status === "mesh_ready" : hasRealModel;
  const canShowSolutionSpace = Boolean(hasRealModel);
  const canShowBrush = Boolean(hasRealModel && activeVersionMeshReady);
  const canShowDrag = Boolean(hasRealModel && activeVersionMeshReady);
  const canShowSculpt = Boolean(hasRealModel && activeVersionMeshReady);
  const hasRunnableAction = canShowSolutionSpace || canShowBrush || canShowDrag || canShowSculpt;
  const visibleCandidates = candidates.filter(
    (candidate) =>
      candidate.thumbnail_url ||
      candidate.mesh_url ||
      candidate.obj_url ||
      candidate.metadata.remote_image_url ||
      candidate.metadata.remote_result_path,
  );
  // 四阶段生成的 8 张候选图进入 Solution Space（点选不触发 hy3d；拖入画布才启动）。
  const appendedBatchArtifacts = solutionBatches.flatMap((batch) =>
    (batch.artifacts ?? []).map((artifact, promptIndex) => ({ batch, artifact, promptIndex })),
  );
  const fourStageCandidates: Candidate[] = appendedBatchArtifacts.map(
    ({ batch, artifact, promptIndex }) =>
      fourStageCandidateFromArtifact({
        runId: batch.run_id,
        index: promptIndex,
        artifact: {
          candidate_id: artifact.candidate_id,
          kind: String(artifact.kind ?? "png"),
          url: String(artifact.url ?? ""),
        },
        sessionId: session?.session_id ?? "",
        assetId: asset?.asset_id ?? "",
        partId: batch.source_context?.target_part_id ?? null,
        intentSeq: batch.intent_seq,
        revisionId: batch.revision_id,
        keywords: batch.delta_keywords?.length ? batch.delta_keywords : batch.cumulative_keywords,
        extraMetadata: {
          append_index: batch.append_index,
          parent_batch_id: batch.parent_batch_id,
          gate_id: batch.gate_id,
          base_keywords: batch.base_keywords,
          cumulative_keywords: batch.cumulative_keywords,
          source_context: batch.source_context,
        },
      }),
  );
  // 四阶段候选以 fourStage.generationArtifacts 派生为准；candidates 里若也
  // 放了一份（completed 时 setCandidates 写入），必须去重避免同一批图出现两次。
  // Prefer durable solutionBatches; keep in-flight four_stage candidates from
  // WS/poll until the observation snapshot mirrors the same artifacts.
  const streamedFourStageCandidates = visibleCandidates.filter(
    (item) =>
      item.metadata?.four_stage_artifact
      && !fourStageCandidates.some((batchItem) => batchItem.candidate_id === item.candidate_id),
  );
  const allCandidates = [
    ...fourStageCandidates,
    ...streamedFourStageCandidates,
    ...visibleCandidates.filter((item) => !item.metadata?.four_stage_artifact),
  ];
  const activeIntentRevision =
    (activeRevisionId
      ? intentRevisions.find((item) => item.revision_id === activeRevisionId)
      : null)
    ?? [...intentRevisions].reverse().find((item) =>
      ["planning", "awaiting_gate", "accepted", "generating"].includes(item.status),
    )
    ?? null;
  const liveIntentSeq =
    activeIntentRevision?.intent_seq
    ?? Math.max(0, ...intentRevisions.map((item) => item.intent_seq), ...solutionBatches.map((item) => item.intent_seq));
  const intentSeqLookup = {
    batches: solutionBatches,
    revisions: intentRevisions,
    activeRunId: fourStage.runId,
    activeIntentSeq: activeIntentRevision?.intent_seq ?? (liveIntentSeq || null),
  };
  const candidateRoundSeq = (item: Candidate) => candidateIntentSeq(item, intentSeqLookup);
  const roundCounts = new Map<number, number>();
  for (const item of allCandidates) {
    const seq = candidateRoundSeq(item);
    if (seq == null) continue;
    roundCounts.set(seq, (roundCounts.get(seq) ?? 0) + 1);
  }
  const displayIntentSeq = solutionSpaceViewIntentSeq ?? (liveIntentSeq || null);
  const solutionSpaceCandidates = displayIntentSeq == null
    ? allCandidates
    : allCandidates.filter((item) => {
        const seq = candidateRoundSeq(item);
        // In-flight WS artifacts often lack intent_seq — keep them on the live round.
        if (seq == null) return displayIntentSeq === liveIntentSeq;
        return seq === displayIntentSeq;
      });
  const solutionSpaceRoundChips = buildSolutionSpaceRoundChips(roundCounts, liveIntentSeq || null).map((chip) => {
    const batch = [...solutionBatches].reverse().find((item) => item.intent_seq === chip.intentSeq);
    const revision = intentRevisions.find((item) => item.intent_seq === chip.intentSeq);
    const keywords = batch?.delta_keywords?.length
      ? batch.delta_keywords
      : batch?.cumulative_keywords?.length
        ? batch.cumulative_keywords
        : revision?.delta_keywords ?? revision?.effective_keywords ?? [];
    return {
      ...chip,
      summary: summarizeKeywords(keywords),
      live: chip.intentSeq === liveIntentSeq && solutionSpaceGenerating,
    };
  });
  const inheritedKeywords = visibleInheritedKeywords(
    activeIntentRevision?.base_keywords?.length
      ? activeIntentRevision.base_keywords
      : inheritedKeywordsFromRevisions(intentRevisions, activeIntentRevision?.intent_seq ?? null),
    excludedInheritedKeywords,
  );
  const liveSolutionSpaceVisible = !solutionSpaceReleased;
  const solutionSpaceComparing = Boolean(
    liveSolutionSpaceVisible && !solutionSpaceGenerating && solutionSpaceCandidates.length > 0,
  );
  const plannerBubbleInterpretation =
    intentBubble.visible && intentBubble.status === "pending" ? interpretation : null;

  // Track last meaningful object/canvas action for fixation timing.
  useEffect(() => {
    if (
      visibleBehaviorAtoms.length ||
      liveSignals.brush_count > 0 ||
      liveSignals.annotation_count > 0 ||
      liveSignals.hover_count > 0
    ) {
      lastMeaningfulActionAtRef.current = Date.now();
    }
  }, [
    visibleBehaviorAtoms.length,
    liveSignals.brush_count,
    liveSignals.annotation_count,
    liveSignals.hover_count,
  ]);

  // ── Idle bubble watcher ──────────────────────────────────
  // After the user stops interacting (including orbit), wait 30s of stillness
  // before auto-sending an idle Gate. Manual Send is unchanged.
  const IDLE_BUBBLE_MS = 30_000;
  useEffect(() => {
    if (!session || !asset) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        if (cancelled) return;
        const lastAt = lastMeaningfulActionAtRef.current;
        // No prior activity → do not invent an idle Gate.
        if (lastAt == null) return;
        const idleMs = Date.now() - lastAt;
        if (idleMs >= IDLE_BUBBLE_MS) {
          void sendIntentRevision({ trigger: "idle" });
        }
      }, IDLE_BUBBLE_MS);
    };
    schedule();
    const onActivity = () => {
      lastMeaningfulActionAtRef.current = Date.now();
      schedule();
    };
    window.addEventListener("flowstudio:user-activity", onActivity);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener("flowstudio:user-activity", onActivity);
    };
    // We intentionally don't depend on the latest closures — the ref-based
    // `sendIntentRevision` + `lastMeaningfulActionAtRef` cover freshness.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.session_id, asset?.asset_id, behaviorSessions.length, intentText]);

  // Creative State Observer (frontend rule edition).
  useEffect(() => {
    const tick = () => {
      const now = Date.now();
      const observed = observeCreativeState({
        hasModel: Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive),
        signals: liveSignals,
        behaviorCount: visibleBehaviorAtoms.length,
        hasIntentText: intentText.trim().length >= 2,
        hasSelectedPart: Boolean(activeSelectedPart || selectedPart),
        comparing: solutionSpaceComparing,
        generating: solutionSpaceGenerating || generationBusy,
        lastActionAt: lastMeaningfulActionAtRef.current,
        now,
      });
      if (observed.state === "possible_fixation" || observed.state === "ready_for_help") {
        fixationEnteredAtRef.current = fixationEnteredAtRef.current ?? now;
      } else {
        fixationEnteredAtRef.current = null;
      }
      let nextState = observed.state;
      let nextConfidence = observed.confidence;
      if (
        observed.state === "possible_fixation" &&
        fixationEnteredAtRef.current &&
        now - fixationEnteredAtRef.current >= 2000
      ) {
        nextState = "ready_for_help";
        nextConfidence = Math.max(nextConfidence, 0.72);
      }
      const backendState = interpretation?.features?.creative_state;
      const backendConfidence = interpretation?.features?.creative_state_confidence;
      if (typeof backendState === "string" && CREATIVE_STATES.has(backendState)) {
        // Keep local ready_for_help promotion unless backend already agrees or is further.
        if (!(nextState === "ready_for_help" && backendState === "possible_fixation")) {
          nextState = backendState as CreativeState;
          if (typeof backendConfidence === "number") nextConfidence = backendConfidence;
        }
      }
      setCreativeState(nextState);
      setCreativeStateConfidence(nextConfidence);
    };
    tick();
    const timer = window.setInterval(tick, 500);
    return () => window.clearInterval(timer);
  }, [
    asset?.mesh_url,
    asset?.obj_url,
    canvasPrimitive,
    liveSignals,
    visibleBehaviorAtoms.length,
    intentText,
    activeSelectedPart,
    selectedPart,
    solutionSpaceComparing,
    solutionSpaceGenerating,
    generationBusy,
    interpretation,
  ]);

  // Intent bubble: only ready_for_help (or stable typed intent), with cooldown.
  useEffect(() => {
    if (REVISION_GATED_INTERACTION) return undefined;
    const now = Date.now();
    const blockedByCooldown = now < bubbleCooldownUntilRef.current;
    const blockedByGeneration = solutionSpaceGenerating || generationBusy;
    const blockedByCompare = solutionSpaceComparing;
    const onlyOrbiting =
      !hasMeaningfulIntentEvidence &&
      (liveSignals.viewport_orbit_count > 0 || liveSignals.viewport_zoom_count > 0) &&
      liveSignals.hover_count === 0 &&
      liveSignals.brush_count === 0 &&
      liveSignals.annotation_count === 0;
    const textScope = inferChangeScopeFromText(intentText);
    const irConfidence = designStateMatches(interpretation)[0]?.confidence ?? 0;
    const typedScopeAmbiguous = typedIntentStable && Boolean(intentText.trim()) && !explicitScopeFromText(intentText);
    const hasTargets = Boolean(interpretation?.semantic_targets?.length);
    const needsClarification =
      interpretation?.semantic_targets?.some((target) => target.requires_clarification) ?? false;
    const composedIntent =
      visibleBehaviorAtoms.length >= 2 ||
      (typedIntentStable && intentText.trim().length >= 3 && visibleBehaviorAtoms.length > 0);
    const shouldOffer =
      !blockedByCooldown &&
      !blockedByGeneration &&
      !blockedByCompare &&
      !onlyOrbiting &&
      intentBubble.status !== "accepted" &&
      intentBubble.status !== "rejected" &&
      (creativeState === "ready_for_help" ||
        (hasMeaningfulIntentEvidence && hasTargets) ||
        (composedIntent && (hasTargets || needsClarification || typedIntentStable)) ||
        (typedScopeAmbiguous && irConfidence >= 0.7));

    if (!shouldOffer) {
      if (intentBubble.visible && intentBubble.status === "pending" && (blockedByGeneration || blockedByCompare)) {
        setIntentBubble((current) => ({ ...current, visible: false }));
      }
      return;
    }
    if (intentBubble.visible || intentBubble.status === "accepted") return;
    const scope = intentText.trim()
      ? textScope
      : interpretation
        ? inferredChangeScope(interpretation, activeSelectedPart?.label ?? selectedPart)
        : "contour";
    setIntentBubble({
      visible: true,
      scope,
      status: "pending",
      shownAt: now,
    });
  }, [
    creativeState,
    hasMeaningfulIntentEvidence,
    typedIntentStable,
    solutionSpaceGenerating,
    generationBusy,
    solutionSpaceComparing,
    liveSignals.viewport_orbit_count,
    liveSignals.viewport_zoom_count,
    liveSignals.hover_count,
    liveSignals.brush_count,
    liveSignals.annotation_count,
    visibleBehaviorAtoms.length,
    intentText,
    interpretation,
    activeSelectedPart,
    selectedPart,
    intentBubble.visible,
    intentBubble.status,
  ]);

  // Bubble auto-ignore after 10s.
  useEffect(() => {
    if (REVISION_GATED_INTERACTION) return undefined;
    if (!intentBubble.visible || intentBubble.status !== "pending" || !intentBubble.shownAt) return undefined;
    const remain = Math.max(0, 15_000 - (Date.now() - intentBubble.shownAt));
    const timer = window.setTimeout(() => {
      bubbleCooldownUntilRef.current = Date.now() + 15_000;
      setIntentBubble({
        visible: false,
        scope: intentBubble.scope,
        status: "ignored",
        shownAt: null,
      });
      addLog("intent bubble", `ignored ${intentBubble.scope ?? "scope"}`);
    }, remain);
    return () => window.clearTimeout(timer);
  }, [intentBubble.visible, intentBubble.status, intentBubble.shownAt, intentBubble.scope]);

  // Right-panel planner line: show the latest bounded summary as soon as it
  // arrives. Model latency is represented by an explicit loading state rather
  // than an artificial debounce/typewriter delay.
  useEffect(() => {
    const intentKey = intentText.trim();
    const intentChanged = plannerNarrationIntentRef.current !== intentKey;
    if (intentChanged) plannerNarrationIntentRef.current = intentKey;
    const next = buildPlannerNarration({
      perceptionSummary: livePerception.summary,
      creativeState,
      hasModel: Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive),
      partLabel: inferChangeScopeFromText(intentText) === "part" ? activeSelectedPart?.label ?? null : null,
      intentText,
      bubbleScope: intentBubble.scope,
      bubbleStatus: intentBubble.status,
      signals: liveSignals,
      generating: solutionSpaceGenerating || generationBusy,
    });
    if (next === plannerNarration) return undefined;
    if (plannerNarrationTimerRef.current) window.clearTimeout(plannerNarrationTimerRef.current);
    plannerNarrationLastAtRef.current = Date.now();
    setPlannerNarration(next);
    return () => {
      if (plannerNarrationTimerRef.current) window.clearTimeout(plannerNarrationTimerRef.current);
    };
  }, [
    livePerception.summary,
    creativeState,
    asset?.mesh_url,
    asset?.obj_url,
    canvasPrimitive,
    activeSelectedPart?.label,
    intentText,
    intentBubble.scope,
    intentBubble.status,
    liveSignals,
    solutionSpaceGenerating,
    generationBusy,
    plannerNarration,
  ]);

  useEffect(() => {
    setPlannerTypedText(plannerNarration);
    return undefined;
  }, [plannerNarration]);

  // UI-only LLM 3D-context narrator: look at the viewport screenshot, then describe it.
  useEffect(() => {
    if (!session?.session_id) return undefined;
    const hasObject = Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive || sculptedMeshObjUrl);
    if (!hasObject) {
      liveObserveAbortRef.current?.abort();
      if (liveObserveTimerRef.current) window.clearTimeout(liveObserveTimerRef.current);
      liveObserveSignatureRef.current = "empty";
      setLiveObserveNarrative(EMPTY_CANVAS_CHATS[0]);
      let index = 0;
      liveObserveTimerRef.current = window.setInterval(() => {
        index = (index + 1) % EMPTY_CANVAS_CHATS.length;
        setLiveObserveNarrative(EMPTY_CANVAS_CHATS[index]);
      }, 9000);
      return () => {
        if (liveObserveTimerRef.current) window.clearInterval(liveObserveTimerRef.current);
      };
    }
    const objectName = [asset?.label, asset?.object_type]
      .map((item) => String(item || "").trim())
      .find((item) => item && !isMeshJargonLabel(item)) || "3D model";
    const fallback = objectName === "3D model" ? EMPTY_CANVAS_CHATS[0] : `This is a ${objectName}.`;
    const signature = [
      objectName,
      asset?.asset_id ?? "",
      asset?.mesh_url ?? "",
      asset?.obj_url ?? "",
      sculptedMeshObjUrl ?? "",
      String(liveSignals.viewport_orbit_count),
      String(liveSignals.viewport_zoom_count),
    ].join("::");
    if (!isObjectStateNarrative(liveObserveNarrative) && !isEmptyCanvasChat(liveObserveNarrative)) {
      setLiveObserveNarrative(fallback);
    }
    if (signature === liveObserveSignatureRef.current) return undefined;
    if (liveObserveTimerRef.current) window.clearTimeout(liveObserveTimerRef.current);
    liveObserveTimerRef.current = window.setTimeout(() => {
      liveObserveSignatureRef.current = signature;
      liveObserveAbortRef.current?.abort();
      const controller = new AbortController();
      liveObserveAbortRef.current = controller;
      void (async () => {
        try {
          let preview: string | null = null;
          for (let attempt = 0; attempt < 6; attempt += 1) {
            const captured = threeViewportRef.current?.captureJpeg?.(360, 0.48) ?? null;
            if (captured?.startsWith("data:image/") && captured.length <= 380_000) {
              preview = captured;
              break;
            }
            await new Promise((resolve) => window.setTimeout(resolve, 450));
            if (controller.signal.aborted) return;
          }
          if (!preview) {
            setLiveObserveNarrative(fallback);
            return;
          }
          const response = await fetch(`${API_BASE}/api/v1/sandbox/observe-narrative`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            body: JSON.stringify({
              object_type: objectName,
              parts: [],
              part_label: null,
              part_id: null,
              preview_image: preview,
            }),
          });
          if (!response.ok) return;
          const data = (await response.json()) as { narrative?: string };
          const narrative = String(data.narrative || "").trim();
          if (isObjectStateNarrative(narrative)) setLiveObserveNarrative(narrative);
        } catch (error) {
          if ((error as { name?: string })?.name === "AbortError") return;
        }
      })();
    }, 1800);
    return () => {
      if (liveObserveTimerRef.current) window.clearTimeout(liveObserveTimerRef.current);
    };
  }, [
    session?.session_id,
    asset?.asset_id,
    asset?.label,
    asset?.object_type,
    asset?.mesh_url,
    asset?.obj_url,
    sculptedMeshObjUrl,
    canvasPrimitive,
    liveSignals.viewport_orbit_count,
    liveSignals.viewport_zoom_count,
  ]);

  const solutionSpaceSignature = [job?.job_id ?? "", ...solutionBatches.map((batch) => batch.batch_id)].join("|");
  const segmentationPreviewUrl = partSegmentationUrl(parts);
  const analysisPreviewUrl =
    (canvasDisplayMode === "parts" || canvasDisplayMode === "heatmap") && segmentationPreviewUrl
      ? segmentationPreviewUrl
      : null;
  const activePreviewUrl = analysisPreviewUrl ?? sculptedMeshObjUrl ?? canvasPreview?.url ?? previewCandidate?.mesh_url ?? previewCandidate?.obj_url ?? null;
  const activePreviewLabel = analysisPreviewUrl
    ? canvasDisplayMode === "heatmap"
      ? "Part weight heatmap"
      : "Part segmentation"
    : canvasPreview?.label ?? previewCandidate?.label ?? null;

  useEffect(() => {
    setPartLabelDraft(activeSelectedPart?.label ?? selectedPart);
  }, [activeSelectedPart?.label, selectedPart]);

  useEffect(() => {
    void bootstrap();
    return () => socketRef.current?.close();
  }, []);

  useEffect(() => {
    applyLocalPerception(liveSignals);
  }, [liveSignals, asset?.asset_id, canvasPrimitive]);

  useEffect(() => {
    if (!session || (!asset && !canvasPrimitive)) return;
    const timer = window.setTimeout(() => {
      void syncLivePerceptionToBackend(liveSignals);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [
    session?.session_id,
    asset?.asset_id,
    canvasPrimitive,
    liveSignals.dwell_ms,
    liveSignals.compare_dwell_ms,
    liveSignals.viewport_orbit_count,
    liveSignals.viewport_zoom_count,
    liveSignals.local_zoom_count,
    liveSignals.hover_count,
    liveSignals.brush_count,
    liveSignals.annotation_count,
    liveSignals.drawing_content,
    liveSignals.mask_coverage,
    liveSignals.tool_switch_count,
    liveSignals.reference_match_count,
  ]);

  useEffect(() => {
    const finished = wasSolutionSpaceGeneratingRef.current && !solutionSpaceGenerating;
    wasSolutionSpaceGeneratingRef.current = solutionSpaceGenerating;
    if (!finished || !solutionSpaceReleased) return;
    setSolutionSpaceReadyPulse(true);
    const timer = window.setTimeout(() => setSolutionSpaceReadyPulse(false), 2800);
    return () => window.clearTimeout(timer);
  }, [solutionSpaceGenerating, solutionSpaceReleased]);

  useEffect(() => {
    if (!job?.job_id || job.job_id.startsWith("local_pending_") || !isActiveJobStatus(job.status)) return;
    const sourceSeq = jobSourceSeqRef.current[job.job_id] ?? sourceSwitchSeqRef.current;
    const timer = window.setInterval(() => {
      void refreshJob(job.job_id, sourceSeq);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  const gateTimeoutTimerRef = useRef<number | null>(null);

  const clearGateTimeout = () => {
    if (gateTimeoutTimerRef.current !== null) {
      window.clearTimeout(gateTimeoutTimerRef.current);
      gateTimeoutTimerRef.current = null;
    }
  };

  const mapRunArtifactsToCandidates = (
    runId: string,
    artifacts: Array<{ candidate_id?: unknown; kind?: string | null; url?: string | null }>,
  ) => {
    const revisionForRun =
      intentRevisionsRef.current.find((item) => item.run_id === runId)
      ?? intentRevisionsRef.current.find((item) => item.revision_id === activeRevisionIdRef.current)
      ?? null;
    const keywords = revisionForRun?.delta_keywords?.length
      ? revisionForRun.delta_keywords
      : revisionForRun?.effective_keywords ?? [];
    return artifacts.map((artifact, index) =>
      fourStageCandidateFromArtifact({
        runId,
        index,
        artifact,
        sessionId: session?.session_id ?? "",
        assetId: asset?.asset_id ?? "",
          partId: revisionForRun?.source_context?.target_part_id ?? (selectedPart || null),
        intentSeq: revisionForRun?.intent_seq,
        revisionId: revisionForRun?.revision_id,
        keywords,
      }),
    );
  };

  const applyFourStageWsEvent = (message: FourStageWsEvent) => {
    const { payload } = message;
    const runId = payload?.run_id ?? null;
    const stage = (payload?.stage as FourStageUiState["stage"]) ?? null;
    if (
      (message.type === "four_stage.retrieval_completed" ||
        message.type === "four_stage.decision_completed" ||
        message.type === "four_stage.awaiting_gate") &&
      runId
    ) {
      void refreshFourStageRun(String(runId));
    }
    if (message.type === "four_stage.awaiting_gate") {
      armGateDismissal(String(runId ?? ""));
    }
    setFourStage((current) => {
      const next: FourStageUiState = { ...current, runId: runId ?? current.runId, stage: stage ?? current.stage };
      if (message.type === "four_stage.encoding_started") {
        next.error = null;
      }
      if (message.type === "four_stage.awaiting_gate") {
        next.gateOpen = true;
        next.gateTimeoutAt = Date.now() + GATE_TIMEOUT_MS;
        if (typeof payload?.gate_question === "string") next.gateQuestion = payload.gate_question;
      }
      if (message.type === "four_stage.gate_resolved") {
        next.gateOpen = false;
        next.gateTimeoutAt = null;
        next.scopeAccepted = payload?.action === "accept_option";
        clearGateTimeout();
      }
      if (message.type === "four_stage.generation_queued") {
        next.stage = "generation";
        setSolutionSpaceGenerating(true);
      }
      if (message.type === "four_stage.generation_progress") {
        // 8 张串行生成：每完成一张就实时进 Solution Space，前端能立刻看到图。
        next.stage = "generation";
        setSolutionSpaceGenerating(true);
        next.generationArtifacts = extractGenerationArtifacts(payload);
        next.generationCompleted = Number(payload?.completed_count ?? next.generationArtifacts.length);
        next.generationTotal = Number(payload?.total_count ?? next.generationArtifacts.length);
        const runCandidates = mapRunArtifactsToCandidates(next.runId ?? "run", next.generationArtifacts);
        if (runCandidates.length) {
          setCandidates((current) =>
            rankCandidates([
              ...runCandidates,
              ...current.filter((item) => !item.metadata?.four_stage_artifact),
            ]),
          );
        }
      }
      if (message.type === "four_stage.completed") {
        next.gateOpen = false;
        next.gateTimeoutAt = null;
        clearGateTimeout();
        setSolutionSpaceGenerating(false);
        next.generationArtifacts = extractGenerationArtifacts(payload);
        next.generationCompleted = next.generationArtifacts.length;
        next.generationTotal = next.generationArtifacts.length;
        // 四阶段产物进入 Solution Space 候选（点选不触发 hy3d；拖入才启动）。
        const runCandidates = mapRunArtifactsToCandidates(next.runId ?? "run", next.generationArtifacts);
        if (runCandidates.length) {
          setCandidates((current) =>
            rankCandidates([
              ...runCandidates,
              ...current.filter((item) => !item.metadata?.four_stage_artifact),
            ]),
          );
        }
      }
      if (message.type === "four_stage.failed") {
        next.gateOpen = false;
        next.gateTimeoutAt = null;
        clearGateTimeout();
        next.stage = "failed";
        setSolutionSpaceGenerating(false);
        next.error = {
          code: String(payload?.error_code ?? "stage_failed"),
          message: String(payload?.message ?? `four-stage failed at ${stage ?? "unknown"}`),
          retryable: true,
        };
      }
      if (message.type === "four_stage.cancelled") {
        next.gateOpen = false;
        next.gateTimeoutAt = null;
        clearGateTimeout();
        next.stage = "cancelled";
        setSolutionSpaceGenerating(false);
      }
      if (message.type === "four_stage.completed") {
        next.stage = "completed";
      }
      return next;
    });
  };

  const extractGenerationArtifacts = (payload: Record<string, unknown>) => {
    const artifacts = Array.isArray(payload?.artifacts)
      ? (payload.artifacts as Array<Record<string, unknown>>)
      : [];
    const items = normalizeGenerationArtifacts(artifacts);
    if (typeof payload?.preview_url === "string" && payload.preview_url.trim()) {
      items.push({ url: payload.preview_url.trim(), kind: "png" });
    }
    return items;
  };

  const armGateDismissal = (runId: string) => {
    clearGateTimeout();
    gateTimeoutTimerRef.current = window.setTimeout(() => {
      gateTimeoutTimerRef.current = null;
      const currentRunId = fourStageRef.current.runId ?? runId;
      if (!currentRunId) return;
      addLog("gate", "scope question ignored after 10s — waiting for explicit user confirmation");
      setFourStage((current) => ({
        ...current,
        gateOpen: current.runId === currentRunId ? false : current.gateOpen,
        gateTimeoutAt: null,
      }));
    }, GATE_TIMEOUT_MS);
  };

  const fourStageRef = useRef(fourStage);
  fourStageRef.current = fourStage;

  const recommendedOption = (decision: FourStageUiState["decision"]) => {
    if (!decision || !decision.options.length) return null;
    return [...decision.options].sort((a, b) => b.confidence - a.confidence)[0];
  };

  const refreshFourStageDecision = async (runId: string) => {
    if (!runId) return;
    try {
      const decision = await api<FourStageDecision>(`/api/v1/four-stage/runs/${runId}/decision`);
      setFourStage((current) => ({ ...current, decision }));
    } catch (error) {
      addLog("four-stage", `decision fetch failed: ${String(error).slice(0, 120)}`);
    }
  };

  const syncFourStageGenerationArtifacts = (
    run: FourStageRun,
    next: FourStageUiState,
  ) => {
    const fromRun = normalizeGenerationArtifacts(run.generation_artifacts as Array<Record<string, unknown>> | undefined);
    // While generating, WS may be ahead of persisted run artifacts — never
    // clobber a richer local progress snapshot with an empty poll.
    const keepLocal =
      run.stage === "generation"
      && (next.generationArtifacts?.length ?? 0) > fromRun.length;
    if (!keepLocal) {
      next.generationArtifacts = fromRun;
    }
    const totalHint = Number(
      (run.generation_spec as { candidate_count?: number } | null | undefined)?.candidate_count ?? 0,
    );
    next.generationCompleted = next.generationArtifacts.length;
    next.generationTotal = Math.max(next.generationArtifacts.length, totalHint, next.generationTotal);
    const sourceArtifacts = keepLocal
      ? next.generationArtifacts
      : fromRun;
    const runCandidates = mapRunArtifactsToCandidates(run.run_id, sourceArtifacts);
    if (runCandidates.length) {
      setCandidates((current) =>
        rankCandidates([
          ...runCandidates,
          ...current.filter((item) => !item.metadata?.four_stage_artifact),
        ]),
      );
    }
  };

  const refreshFourStageRun = async (runId: string) => {
    try {
      const run = await api<FourStageRun>(`/api/v1/four-stage/runs/${runId}`);
      if (run.stage === "awaiting_gate") {
        armGateDismissal(run.run_id);
      }
      refreshFourStageUiFromRun(run);
      setFourStage((current) => {
        const next: FourStageUiState = { ...current, runId: run.run_id, stage: run.stage };
        if (run.decision) next.decision = run.decision;
        next.gateQuestion = run.scope_gate?.question ?? run.decision?.gate_question ?? null;
        next.scopeAccepted = run.scope_gate?.status === "accepted";
        next.divergenceSelection = run.divergence_selection ?? null;
        if (run.stage === "awaiting_gate" && !next.gateOpen) {
          next.gateOpen = true;
          next.gateTimeoutAt = Date.now() + GATE_TIMEOUT_MS;
        }
        if (run.stage === "generation" || run.stage === "completed") {
          syncFourStageGenerationArtifacts(run, next);
        }
        if (run.stage === "completed" || run.stage === "failed" || run.stage === "cancelled") {
          setSolutionSpaceGenerating(false);
        } else if (run.stage === "generation") {
          setSolutionSpaceGenerating(true);
        }
        if (run.error) next.error = run.error;
        return next;
      });
      return run;
    } catch (error) {
      addLog("four-stage", `run refresh failed: ${String(error).slice(0, 120)}`);
      return null;
    }
  };

  useEffect(() => {
    if (!solutionSpaceGenerating) return undefined;
    const runId =
      fourStage.runId
      ?? intentRevisions.find((item) => item.revision_id === activeRevisionId)?.run_id
      ?? null;
    if (!runId) return undefined;
    const timer = window.setInterval(() => {
      void refreshFourStageRun(runId);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [solutionSpaceGenerating, fourStage.runId, activeRevisionId, intentRevisions]);

  const attachSessionSocket = (targetSessionId: string) => {
    if (socketRef.current) socketRef.current.close();
    const ws = new WebSocket(`${WS_BASE}/ws/sessions/${targetSessionId}`);
    socketRef.current = ws;
    ws.onmessage = (event) => {
      if (socketRef.current !== ws) return;
      const message = JSON.parse(event.data);
      addLog(message.type, message.payload?.primary_intent ?? message.payload?.message ?? "received");
      if (message.type?.startsWith("four_stage.")) {
        // Revision-gated mode owns gate/decision UX, but generation progress /
        // terminal events must still stream into Solution Space.
        const generationEvent =
          message.type.startsWith("four_stage.generation")
          || message.type === "four_stage.completed"
          || message.type === "four_stage.failed"
          || message.type === "four_stage.cancelled";
        if (!REVISION_GATED_INTERACTION || generationEvent) {
          applyFourStageWsEvent(message as FourStageWsEvent);
        }
      }
      if (message.type?.startsWith("observation.") || message.type?.startsWith("intent.revision_")) {
        void refreshRealtimeObservation(targetSessionId);
      }
      if (message.type === "interaction.event") {
        // Durable interaction events are the primary completion signal. The
        // projection pull is intentionally a narrow merge, so a task for
        // revision A cannot clear revision B's local error or selection.
        addLog("interaction", message.event_type ?? message.payload?.event_type ?? "event");
        interactionCursorRef.current = Math.max(
          interactionCursorRef.current,
          Number(message.event_cursor ?? 0),
        );
        interactionCoordinator?.receiveEvent(message as InteractionEvent);
        void refreshRealtimeObservation(targetSessionId);
      }
      if (message.type === "stage_update") setStage(message.payload);
      if (message.type === "live_signals_updated") {
        applyServerLiveSignals(message.payload?.live_signals as Partial<LiveSignals> | undefined);
      }
      if (message.type === "perception_updated" || message.type === "perception_snapshot") {
        const payload = message.payload ?? {};
        const summary = String(payload.summary ?? payload.behavior_label ?? "").trim();
        if (summary && summary.toLowerCase() !== "unknown") {
          setLivePerception({
            summary,
            evidence: Array.isArray(payload.evidence)
              ? payload.evidence.map((item: unknown) =>
                  typeof item === "string" ? item : String((item as { value?: string }).value ?? ""),
                ).filter(Boolean)
              : [],
            confidence: typeof payload.confidence === "number" ? payload.confidence : null,
            source: "server",
            updatedAt: new Date().toISOString(),
          });
        }
      }
      if (message.type === "action_atom_created") {
        addLog("action atom", message.payload?.action_atom_id ?? message.payload?.atom_id ?? "created");
      }
      if (message.type === "case_saved") addLog("case", message.payload?.case_id ?? "saved");
      if (message.type === "reference_image_attached") {
        const artifact = message.payload?.artifact as ArtifactRecord | undefined;
        if (artifact?.artifact_id) {
          setReferenceImages((current) => upsertArtifact(current, artifact));
        }
      }
      if (message.type === "hy3d_progress") {
        const payload = message.payload ?? {};
        setHy3dProgress({
          message: String(payload.message ?? "").trim() || "Hunyuan3D 运行中",
          progress: Number(payload.progress ?? 0),
        });
      }
      if (message.type === "job_update") {
        setJob((current) => ({ ...(current ?? {}), ...message.payload }) as JobRecord);
        if (!isActiveJobStatus(message.payload?.status)) setSolutionSpaceGenerating(false);
      }
      if (message.type === "candidate_ready") {
        setSolutionSpaceGenerating(false);
        const sourceSeq = jobSourceSeqRef.current[String(message.payload.job_id ?? "")] ?? sourceSwitchSeqRef.current;
        void loadCandidates(message.payload.candidate_ids, message.payload.job_id, sourceSeq);
        void refreshJob(message.payload.job_id, sourceSeq);
      }
    };
    ws.onopen = () => {
      addLog("websocket", `connected ${targetSessionId.slice(0, 10)}`);
      interactionCoordinator?.setConnected(true);
      ws.send(JSON.stringify({
        type: "interaction.replay",
        event_id: `replay_${crypto.randomUUID()}`,
        session_id: targetSessionId,
        payload: { last_event_cursor: interactionCursorRef.current },
      }));
    };
    ws.onclose = () => interactionCoordinator?.setConnected(false);
    ws.onerror = () => addLog("websocket", "connection error");
    return ws;
  };

  const ensureSourceVersionNode = async (
    targetSession = session,
    targetAsset = asset,
  ): Promise<VersionGraphState> => {
    if (!targetSession || !targetAsset) return versionGraphRef.current;
    const current = versionGraphRef.current;
    if (current.nodes.some((node) => node.parent_node_id === null)) return current;
    if (sourceVersionCreationRef.current) return sourceVersionCreationRef.current;
    sourceVersionCreationRef.current = (async () => {
      const node = await api<VersionGraphNode>(
        `/api/v1/sessions/${targetSession.session_id}/version-nodes`,
        {
          method: "POST",
          body: JSON.stringify({
            parent_node_id: null,
            candidate_id: `source:${targetAsset.asset_id}`,
            label: targetAsset.label || "Source model",
            preview_url: targetAsset.thumbnail_url ?? null,
            mesh_url: targetAsset.mesh_url ?? null,
            obj_url: targetAsset.obj_url ?? null,
            status: "mesh_ready",
          }),
        },
      );
      mergeVersionGraphNode(node, true);
      const graph = await api<VersionGraphState>(
        `/api/v1/sessions/${targetSession.session_id}/active-version/${node.node_id}`,
        { method: "PUT" },
      );
      applyVersionGraph(graph);
      return graph;
    })();
    try {
      return await sourceVersionCreationRef.current;
    } finally {
      sourceVersionCreationRef.current = null;
    }
  };

  const refreshRealtimeObservation = async (sessionId = session?.session_id) => {
    if (!sessionId) return null;
    const epoch = sourceSwitchSeqRef.current;
    try {
      const snapshot = await api<RealtimeObservationSnapshot>(
        `/api/v1/sessions/${sessionId}/realtime-observation`,
      );
      if (sourceSwitchSeqRef.current !== epoch) return null;
      setLiveObservation(snapshot.observation);
      const cutoff = Math.max(
        0,
        ...(snapshot.revisions ?? []).map((item) => item.cutoff_seq ?? 0),
      );
      setBehaviorSessions((current) => {
        const serverVisible = (snapshot.behaviors ?? []).filter(
          (item) => item.behavior_seq > cutoff,
        );
        // Keep in-flight local / active dots that polling would otherwise wipe.
        const localPending = current.filter((item) => {
          if (serverVisible.some((server) => server.behavior_id === item.behavior_id)) {
            return false;
          }
          return item.status === "active" || String(item.behavior_id).startsWith("local_beh_")
            || String(item.behavior_id).startsWith("atom_");
        });
        return [...serverVisible, ...localPending].sort(
          (a, b) => a.behavior_seq - b.behavior_seq,
        );
      });
      const serverRevisions = snapshot.revisions ?? [];
      latestIntentSeqRef.current = Math.max(
        latestIntentSeqRef.current,
        ...serverRevisions.map((item) => item.intent_seq),
      );
      setIntentRevisions((current) => mergeRealtimeRevisions(serverRevisions, current));
      setSolutionBatches(snapshot.solution_batches ?? []);
      setUiBrief(snapshot.ui_brief ?? null);
      applyVersionGraph(snapshot.version_graph ?? { active_node_id: null, nodes: [] });
      setVersionGraphHydrated(true);
      return snapshot;
    } catch (error) {
      addLog("observation", String(error).slice(0, 120));
      return null;
    }
  };

  useEffect(() => {
    if (!session?.session_id) return undefined;
    void refreshRealtimeObservation(session.session_id);
    const timer = window.setInterval(() => {
      void refreshRealtimeObservation(session.session_id);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [session?.session_id]);

  useEffect(() => {
    if (!interactionCoordinator) {
      setInteractionState(emptyInteractionState());
      return undefined;
    }
    void interactionCoordinator.recover().catch(() => undefined);
    return () => {
      interactionCoordinator.setConnected(false);
    };
  }, [interactionCoordinator]);

  useEffect(() => {
    if (!session || !asset) return;
    if (!versionGraphHydrated) return;
    if (versionGraph.nodes.some((node) => node.parent_node_id === null)) return;
    void ensureSourceVersionNode(session, asset).catch((error) => {
      addLog("version", `Version 1 创建失败：${String(error).slice(0, 120)}`);
    });
  }, [session?.session_id, asset?.asset_id, versionGraph.nodes.length, versionGraphHydrated]);

  const sendIntentRevision = (options?: { trigger?: "manual" | "idle" }) => {
    const trigger = options?.trigger ?? "manual";
    if (!session || !asset) return null;
    if (trigger === "idle") {
      // Idle hint: only fire when there is something new since the last sent
      // revision AND no other revision is currently waiting for gate/planning.
      const stillInFlight = intentRevisions.some((item) =>
        item.status === "planning" || item.status === "awaiting_gate",
      );
      let lastAcceptedCutoff = 0;
      for (let i = intentRevisions.length - 1; i >= 0; i -= 1) {
        if (intentRevisions[i].status === "accepted") {
          lastAcceptedCutoff = intentRevisions[i].cutoff_seq;
          break;
        }
      }
      // Require a real committed behavior past the last cutoff. Orbit / dwell
      // alone must never invent a Gate (even on the first revision).
      const cutoffFloor = Math.max(
        latestCommittedBehaviorSeqRef.current - 1,
        lastAcceptedCutoff,
        0,
      );
      const behaviorAdvanced =
        (liveObservation?.latest_behavior_seq ?? 0) > cutoffFloor
        || behaviorSessions.some(
          (item) => item.status === "committed" && item.behavior_seq > cutoffFloor,
        );
      if (stillInFlight || !behaviorAdvanced) return null;
    }
    // Send 是唯一的截止点：先封口当前工具会话，后续行为归入下一 revision。
    const baselineSeqAtClick = Math.max(
      latestCommittedBehaviorSeqRef.current,
      liveObservation?.latest_behavior_seq ?? 0,
    );
    const pendingAtClick = [...pendingBehaviorCommitsRef.current];
    const sourceDataUrl = trigger === "idle"
      ? null
      : (() => {
          const views = threeViewportRef.current?.captureThreeViews?.(960, 0.82) ?? {};
          return views.front ?? threeViewportRef.current?.captureJpeg?.(960, 0.82) ?? null;
        })();
    const currentToolCommit = finalizeSculptBehavior(Boolean(sculptTool)).then((result) => result.behavior);
    const primitiveCommit = finalizePrimitiveBehavior().then((result) => result.behavior);
    // Register the whole tool-finalization promise immediately. A second rapid
    // Send can therefore include this first cutoff even while view uploads run.
    pendingBehaviorCommitsRef.current.add(currentToolCommit);
    pendingBehaviorCommitsRef.current.add(primitiveCommit);
    void currentToolCommit.finally(() => pendingBehaviorCommitsRef.current.delete(currentToolCommit));
    void primitiveCommit.finally(() => pendingBehaviorCommitsRef.current.delete(primitiveCommit));
    const intentTextAtClick = trigger === "idle" ? "" : intentText.trim();
    const annotationEvidenceAtClick = (() => {
      if (trigger === "idle") return null;
      const fromBehavior = [...behaviorSessions].reverse().find((item) => item.tool === "annotation");
      if (fromBehavior) {
        const summary = fromBehavior.operation_summary ?? {};
        const kinds = Array.isArray(summary.brush_kinds)
          ? summary.brush_kinds.map((item) => String(item))
          : [];
        return {
          stroke_count: Number(summary.stroke_count ?? fromBehavior.stroke_count ?? 0),
          brush_kinds: kinds,
          brush_summary: summary.brush_summary ? String(summary.brush_summary) : null,
        };
      }
      const fromAtom = [...actionAtoms].reverse().find((item) => item.tool === "annotation");
      if (fromAtom) {
        const kinds = Array.isArray(fromAtom.evidence.brush_kinds)
          ? fromAtom.evidence.brush_kinds.map((item) => String(item))
          : [];
        return {
          stroke_count: Number(fromAtom.evidence.stroke_count ?? 0),
          brush_kinds: kinds,
          brush_summary: fromAtom.evidence.brush_summary
            ? String(fromAtom.evidence.brush_summary)
            : null,
        };
      }
      if (liveSignals.annotation_count > 0) {
        return {
          stroke_count: liveSignals.annotation_count,
          brush_kinds: [] as string[],
          brush_summary: liveSignals.drawing_content || null,
        };
      }
      return null;
    })();
    const selectedPartAtClick = selectedPart || null;
    const namedPartAtClick = isGenericMeshId(selectedPartAtClick) ? null : selectedPartAtClick;
    const liveSignalsAtClick = {
      ...liveSignals,
      dwell_ms: Math.max(liveSignals.dwell_ms, currentPartDwellMs()),
    };
    const assetAtClick = asset;
    const versionAtClick = activeVersionId;
    const sourceModelAtClick = sculptedMeshObjUrl ?? asset.mesh_url ?? asset.obj_url;
    const genericTypes = new Set(["", "object", "unknown", "item", "thing", "model", "asset"]);
    const objectTypeAtClick = genericTypes.has(String(assetAtClick.object_type ?? "").trim().toLowerCase())
      ? String(assetAtClick.label || "design subject")
      : assetAtClick.object_type;
    const optimisticId = `local_${crypto.randomUUID().slice(0, 10)}`;
    // Idle hint: keep the same intent_seq so a later manual Send cleanly
    // supersedes it. Manual: increment by 1 (monotonic per session).
    const optimisticIntentSeq = trigger === "idle"
      ? Math.max(latestIntentSeqRef.current, ...intentRevisions.map((item) => item.intent_seq))
      : Math.max(
          latestIntentSeqRef.current,
          ...intentRevisions.map((item) => item.intent_seq),
        ) + 1;
    if (trigger !== "idle") {
      latestIntentSeqRef.current = optimisticIntentSeq;
    }
    const optimisticCreatedAt = new Date().toISOString();
    const optimisticRevision: IntentRevision = {
      revision_id: optimisticId,
      session_id: session.session_id,
      intent_seq: optimisticIntentSeq,
      parent_revision_id: null,
      window_start_seq: baselineSeqAtClick + 1,
      cutoff_seq: baselineSeqAtClick,
      behavior_ids: [],
      user_text: intentTextAtClick,
      source_context: {
        asset_id: assetAtClick.asset_id,
        object_type: objectTypeAtClick,
        version_id: versionAtClick,
        source_image_ref: null,
        source_model_ref: sourceModelAtClick,
        target_part_id: namedPartAtClick,
      },
      status: "planning",
      version: 1,
      selection_version: 0,
      run_id: null,
      gate_id: null,
      gate_question: trigger === "idle"
        ? "正在判断修改范围（系统推断）…"
        : "正在判断修改范围…",
      gate_target: namedPartAtClick,
      gate_scope: null,
      gate_provisional: true,
      base_keywords: [],
      delta_keywords: [],
      effective_keywords: [],
      divergence_selection: null,
      semantic_divergence_status: null,
      semantic_divergence_error: null,
      error: null,
      created_at: optimisticCreatedAt,
      updated_at: optimisticCreatedAt,
      trigger,
    };
    setIntentRevisions((current) => [...current, optimisticRevision].sort((a, b) => a.intent_seq - b.intent_seq));
    if (trigger !== "idle") {
      setIntentText((current) => current.trim() === intentTextAtClick ? "" : current);
      // Stow prior Solution Space into round chips; body follows the new intent.
      setSolutionSpaceViewIntentSeq(optimisticIntentSeq);
    }
    const queued = intentSendQueueRef.current.then(async () => {
      if (trigger === "idle") {
        // Idle hint: skip text-snapshot + screenshot upload (the user didn't
        // explicitly send anything). Send a synthetic cutoff so the planner
        // still has a fresh "latest behavior seq" anchor.
        try {
          const revision = await api<IntentRevision>(
            `/api/v1/sessions/${session.session_id}/intent-revisions`,
            {
              method: "POST",
              body: JSON.stringify({
                user_text: "",
                cutoff_seq: baselineSeqAtClick,
                run_hy3d: false,
                source_context: {
                  asset_id: assetAtClick.asset_id,
                  object_type: objectTypeAtClick,
                  version_id: versionAtClick,
                  source_image_ref: null,
                  source_model_ref: sourceModelAtClick,
                  target_part_id: namedPartAtClick,
                },
                live_signals: liveSignalsAtClick,
              }),
            },
          );
          const idleRevision: IntentRevision = { ...revision, trigger: "idle" };
          setIntentRevisions((current) => [
            ...current.filter((item) =>
              item.revision_id !== revision.revision_id &&
              item.revision_id !== optimisticId &&
              !(item.status === "planning" && item.intent_seq === revision.intent_seq),
            ),
            idleRevision,
          ].sort((a, b) => a.intent_seq - b.intent_seq));
          addLog("intent", `idle hint · revision ${revision.intent_seq} sent for inference`);
          return revision;
        } catch (error) {
          addLog("intent", `idle hint failed: ${String(error).slice(0, 120)}`);
          setIntentRevisions((current) => current.filter((item) => item.revision_id !== optimisticId));
          return null;
        }
      }
      try {
        await projectRecorder.record(
          "input.text_snapshot",
          { text: intentTextAtClick, trigger: "submit" },
          `text-submit:${optimisticId}`,
          { critical: true },
        );
      } catch {
        setIntentRevisions((current) => current.filter((item) => item.revision_id !== optimisticId));
        setIntentText((current) => current.trim() ? current : intentTextAtClick);
        return null;
      }
            const allCommits = await Promise.all([...pendingAtClick, currentToolCommit, primitiveCommit]);
      const cutoffSeq = allCommits.reduce(
        (latest, behavior: any) => Math.max(latest, behavior?.behavior_seq ?? 0),
        baselineSeqAtClick,
      );
      // Clear consumed behaviors from the rail after cutoff is known.
      setBehaviorSessions((current) =>
        current.filter((item) => item.behavior_seq > cutoffSeq),
      );
      // Prefer screenshots already uploaded with the behavior — no re-capture on Send.
      const reusedShot = [...behaviorSessions]
        .reverse()
        .map((item) => {
          const summary = item.operation_summary ?? {};
          const url = summary.viewport_screenshot_url ?? summary.stroke_url;
          return typeof url === "string" && url ? url : null;
        })
        .find(Boolean) ?? null;
      const sourceImagePromise = reusedShot
        ? Promise.resolve({ url: reusedShot } as { url: string })
        : sourceDataUrl
          ? uploadViewportScreenshot(sourceDataUrl, {
              sessionId: session.session_id,
              assetId: assetAtClick.asset_id,
              partId: selectedPartAtClick,
              metadata: { trigger: "intent_revision_cutoff", cutoff_seq: cutoffSeq },
            }).catch(() => null)
          : Promise.resolve(null);
      const sourceImage = await Promise.race([
        sourceImagePromise,
        new Promise<null>((resolve) => {
          window.setTimeout(() => resolve(null), 2500);
        }),
      ]);
      if (!reusedShot) void sourceImagePromise;
      let resolvedUserText = intentTextAtClick;
      // Drawing/sculpt provide LOCATION via committed behaviors — do not invent
      // fake user_text that pollutes the semantic channel for Gate.
      if (!resolvedUserText) {
        const hasDrawing = Boolean(annotationEvidenceAtClick);
        if (hasDrawing) {
          addLog("intent", "drawing location evidence only · leave semantic empty for Gate");
        }
      }
      try {
        const revision = await api<IntentRevision>(
          `/api/v1/sessions/${session.session_id}/intent-revisions`,
          {
            method: "POST",
            body: JSON.stringify({
              user_text: resolvedUserText,
              cutoff_seq: cutoffSeq,
              run_hy3d: hy3dCandidateIds.length > 0,
              source_context: {
                asset_id: assetAtClick.asset_id,
                object_type: objectTypeAtClick,
                version_id: versionAtClick,
                source_image_ref: sourceImage?.url ?? null,
                source_model_ref: sourceModelAtClick,
                target_part_id: namedPartAtClick,
              },
              live_signals: liveSignalsAtClick,
            }),
          },
        );
        latestIntentSeqRef.current = Math.max(latestIntentSeqRef.current, revision.intent_seq);
        const manualRevision: IntentRevision = { ...revision, trigger: "manual" };
        setIntentRevisions((current) => [
          ...current.filter((item) =>
            item.revision_id !== revision.revision_id &&
            item.revision_id !== optimisticId &&
            !(item.status === "planning" && item.intent_seq === revision.intent_seq)
          ),
          manualRevision,
        ].sort((a, b) => a.intent_seq - b.intent_seq));
        setBehaviorSessions((current) =>
          current.filter((item) => item.behavior_seq > revision.cutoff_seq),
        );
        setSelectedPromptTokens([]);
        addLog("intent", `revision ${revision.intent_seq} locked at behavior ${revision.cutoff_seq}`);
        return revision;
      } catch (error) {
        addLog("intent", String(error).slice(0, 160));
        setIntentRevisions((current) => current.filter((item) => item.revision_id !== optimisticId));
        setIntentText((current) => current.trim() ? current : intentTextAtClick);
        setProjectNotice("意图提交失败，已保留原始文字，请重新发送。");
        return null;
      }
    });
    intentSendQueueRef.current = queued.then(() => undefined, () => undefined);
    return queued;
  };

  const selectIntentRevision = async (revisionId: string) => {
    const revision = intentRevisions.find((item) => item.revision_id === revisionId);
    if (!revision || !["accepted", "generating", "completed"].includes(revision.status)) return null;
    divergenceCommitInvocationRef.current += 1;
    semanticDivergenceLatestRequestedKeyRef.current = null;
    activeRevisionIdRef.current = revisionId;
    setActiveRevisionId(revisionId);
    setSemanticDivergenceLoading(false);
    setSemanticDivergenceError(null);
    setSemanticDivergence(null);
    setDivergenceKeywords([]);
    setSelectedPromptTokens([]);
    if (!revision.run_id) return revision;
    try {
      const run = await api<FourStageRun>(`/api/v1/four-stage/runs/${revision.run_id}`);
      if (activeRevisionIdRef.current !== revisionId) return revision;
      refreshFourStageUiFromRun(run);
      setFourStage((current) => ({
        ...current,
        runId: run.run_id,
        stage: run.stage,
        decision: run.decision,
        gateOpen: false,
        scopeAccepted: true,
      }));
      return revision;
    } catch (error) {
      addLog("intent", String(error).slice(0, 160));
      return null;
    }
  };

  const resolveIntentRevisionGate = async (revisionId: string, accepted: boolean) => {
    const capturedRevisionId = revisionId;
    const invocationToken = accepted ? ++gateResolutionInvocationRef.current : null;
    const revisionForCommand = intentRevisionsRef.current.find((item) => item.revision_id === revisionId);
    const commandId = `gate_${revisionId}_${crypto.randomUUID()}`;
    const idempotencyKey = commandId;
    // The authoritative interaction transaction is now server-side. Recording
    // the experiment projection must never delay Gate feedback or invalidate a
    // valid command when the projection store is temporarily degraded.
    void projectRecorder.record(
      "gate.answered",
      { revision_id: revisionId, accepted },
      `gate:${revisionId}:${commandId}`,
    );
    let capturedRunId: string | null = null;
    const isLatestGateResolution = (runId?: string | null) =>
      invocationToken !== null &&
      gateResolutionInvocationRef.current === invocationToken &&
      activeRevisionIdRef.current === capturedRevisionId &&
      (!runId || capturedRunId === runId);
    const revisionToResolve = intentRevisions.find((item) => item.revision_id === capturedRevisionId) ?? null;
    const inheritedRevisionKeywords = revisionToResolve
      ? [...intentRevisions]
          .filter((item) => item.intent_seq < revisionToResolve.intent_seq && ["accepted", "generating", "completed"].includes(item.status))
          .reverse()
          .find((item) => item.effective_keywords.length)?.effective_keywords ?? []
      : [];
    if (accepted) {
      activeRevisionIdRef.current = capturedRevisionId;
      setActiveRevisionId(capturedRevisionId);
      if (revisionToResolve?.run_id) {
        fourStageRef.current = {
          ...fourStageRef.current,
          runId: revisionToResolve.run_id,
          stage: "awaiting_gate",
        };
        setFourStage((current) => ({
          ...current,
          runId: revisionToResolve.run_id,
          stage: "awaiting_gate",
        }));
      }
      setSemanticDivergenceLoading(true);
      setSemanticDivergenceError(null);
      setDivergencePhaseMessage("Connecting to model…");
      setIntentRevisions((current) =>
        current.map((item) =>
          item.revision_id === capturedRevisionId
            ? {
                ...item,
                semantic_divergence_status:
                  item.semantic_divergence_status === "completed" ? "completed" : "running",
                semantic_divergence_error: null,
              }
            : item,
        ),
      );
      // Start SSE first so the worker joins this progress-capable task.
      void commitDivergenceParameters({
        preflight: true,
        revisionId: capturedRevisionId,
      });
    }
    try {
      if (!revisionForCommand || !interactionCoordinator) {
        throw new Error("interaction coordinator unavailable");
      }
      const revision = accepted
        ? await interactionCoordinator.acceptGate(
            revisionForCommand,
            {
              divergence_params: {
                ...buildSemanticDivergenceParameters({
                  temperature: divergenceTemperatureRef.current,
                  perGroupCount: divergencePerGroupCountRef.current,
                }),
                inherited_keywords: inheritedRevisionKeywords,
              },
            },
            { command_id: commandId, idempotency_key: idempotencyKey },
          )
        : await interactionCoordinator.rejectGate(
            revisionForCommand,
            undefined,
            { command_id: commandId, idempotency_key: idempotencyKey },
          );
      capturedRunId = revision.run_id;
      setIntentRevisions((current) => current.map((item) => item.revision_id === capturedRevisionId ? revision : item));
      if (accepted) {
        if (!isLatestGateResolution()) return revision;
        // Accept bumps revision.version — reset selection OCC so later keyword saves don't 409.
        selectionPersistenceByRevisionRef.current.set(capturedRevisionId, {
          sequence: 0,
          chain: Promise.resolve(true),
          latest: Promise.resolve(true),
          pending: false,
          error: null,
          expectedVersion: revision.version,
          expectedSelectionVersion: revision.selection_version,
        });
        setSelectionPersistenceErrors((current) => {
          const nextErrors = { ...current };
          delete nextErrors[capturedRevisionId];
          return nextErrors;
        });
        const run = revision.run_id ? await api<FourStageRun>(`/api/v1/four-stage/runs/${revision.run_id}`) : null;
        if (run && isLatestGateResolution(run.run_id)) {
          refreshFourStageUiFromRun(run);
          setFourStage((current) => ({
            ...current,
            runId: run.run_id,
            stage: run.stage,
            decision: run.decision,
            gateOpen: false,
            scopeAccepted: true,
          }));
        }
      }
      return revision;
    } catch (error) {
      if (accepted && isLatestGateResolution()) {
        setSemanticDivergenceLoading(false);
        setSemanticDivergenceError(String(error).slice(0, 160));
      }
      addLog("gate", String(error).slice(0, 160));
      return null;
    }
  };

  const commitDivergenceParameters = async (options?: {
    preflight?: boolean;
    revisionId?: string;
    force?: boolean;
    temperature?: number;
    perGroupCount?: number;
  }) => {
    const preflight = Boolean(options?.preflight);
    const capturedRevisionId = options?.revisionId ?? activeRevisionIdRef.current;
    const temperature = options?.temperature ?? divergenceTemperatureRef.current;
    const perGroupCount = options?.perGroupCount ?? divergencePerGroupCountRef.current;
    const liveParams = semanticDivergenceLiveParamsRef.current;
    const liveRequest = semanticDivergenceLiveRequestRef.current;
    if (
      !options?.force &&
      liveRequest &&
      liveParams?.temperature === temperature &&
      liveParams?.perGroupCount === perGroupCount &&
      liveParams?.revisionId === capturedRevisionId
    ) {
      return liveRequest;
    }
    const invocationToken = ++divergenceCommitInvocationRef.current;
    if (capturedRevisionId) {
      semanticDivergenceAttachingRevisionRef.current = capturedRevisionId;
    }
    let revision = intentRevisionsRef.current.find((item) => item.revision_id === capturedRevisionId) ?? null;
    const allowedStatuses = preflight
      ? new Set(["awaiting_gate", "accepted"])
      : new Set(["accepted"]);
    const sessionId = session?.session_id;
    if (revision && allowedStatuses.has(revision.status) && !revision.run_id && sessionId) {
      setDivergencePhaseMessage("Waiting for planner…");
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        if (activeRevisionIdRef.current !== capturedRevisionId) {
          if (
            divergenceCommitInvocationRef.current === invocationToken &&
            semanticDivergenceAttachingRevisionRef.current === capturedRevisionId
          ) {
            semanticDivergenceAttachingRevisionRef.current = null;
          }
          return null;
        }
        const snapshot = await refreshRealtimeObservation(sessionId);
        revision =
          (snapshot?.revisions ?? []).find((item) => item.revision_id === capturedRevisionId)
          ?? intentRevisionsRef.current.find((item) => item.revision_id === capturedRevisionId)
          ?? null;
        if (revision?.run_id) break;
      }
    }
    if (!revision || !allowedStatuses.has(revision.status) || !revision.run_id) {
      if (
        divergenceCommitInvocationRef.current === invocationToken &&
        semanticDivergenceAttachingRevisionRef.current === capturedRevisionId
      ) {
        semanticDivergenceAttachingRevisionRef.current = null;
      }
      setDivergencePhaseMessage(
        !revision
          ? "No active revision to diverge"
          : !revision.run_id
            ? "Waiting for planner…"
            : `Revision status ${revision.status} cannot diverge`,
      );
      return null;
    }
    const capturedRunId = revision.run_id;
    const capturedParameters = {
      ...buildSemanticDivergenceParameters({
        temperature,
        perGroupCount,
      }),
      preflight,
    };
    void projectRecorder.record(
      "divergence.parameters_changed",
      { revision_id: capturedRevisionId, ...capturedParameters },
      `divergence-params:${capturedRevisionId}:${capturedParameters.temperature}:${capturedParameters.per_group_count}:${preflight ? "pre" : "post"}`,
    );
    const capturedInheritedKeywords = visibleInheritedKeywords(
      inheritedKeywordsFromRevisions(intentRevisionsRef.current, revision.intent_seq),
      excludedInheritedKeywordsRef.current,
    );
    const capturedRequestBaseKey = JSON.stringify([
      capturedRunId,
      capturedParameters.temperature,
      capturedParameters.strictness,
      capturedParameters.per_group_count,
      [...capturedInheritedKeywords].sort(),
      preflight ? "preflight" : "accepted",
    ]);
    semanticDivergenceLatestRequestedKeyRef.current = capturedRequestBaseKey;
    const isCurrentDivergenceInvocation = () =>
      divergenceCommitInvocationRef.current === invocationToken &&
      activeRevisionIdRef.current === capturedRevisionId &&
      Boolean(capturedRunId);

    try {
      if (!isCurrentDivergenceInvocation()) return null;
      let run = await api<FourStageRun>(`/api/v1/four-stage/runs/${capturedRunId}`);
      if (!isCurrentDivergenceInvocation()) return null;
      for (let attempt = 0; attempt < 90 && run.stage !== "awaiting_gate"; attempt += 1) {
        if (run.stage === "failed" || run.stage === "cancelled") {
          setDivergencePhaseMessage(run.error?.message ?? `Planner ${run.stage}`);
          return null;
        }
        setDivergencePhaseMessage(`Planner ${run.stage}…`);
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        if (!isCurrentDivergenceInvocation()) return null;
        run = await api<FourStageRun>(`/api/v1/four-stage/runs/${capturedRunId}`);
      }
      if (run.stage !== "awaiting_gate") {
        setDivergencePhaseMessage(`等待 run 进入 awaiting_gate（当前 ${run.stage}）`);
        return null;
      }
      if (!preflight && run.scope_gate?.status !== "accepted") {
        // Accept may still be in flight; keep listening with preflight-capable params.
        setDivergencePhaseMessage("Gate 尚未接受，改用 preflight 发散…");
      }
      const canStream =
        preflight ||
        run.scope_gate?.status === "accepted" ||
        run.scope_gate?.status === "pending" ||
        run.scope_gate?.status == null;
      if (!canStream) {
        setDivergencePhaseMessage(`无法发散：gate=${run.scope_gate?.status ?? "none"}`);
        return null;
      }
      const streamParams = {
        ...capturedParameters,
        // Prefer preflight whenever Gate is not yet accepted so SSE can start during Accept.
        preflight: Boolean(preflight || run.scope_gate?.status !== "accepted"),
        inherited_keywords: capturedInheritedKeywords,
      };
      const authoritativeDecisionId = run.decision?.decision_id ?? "";
      const commitKey = JSON.stringify([
        capturedRunId,
        authoritativeDecisionId,
        streamParams.temperature,
        streamParams.strictness,
        streamParams.per_group_count,
        [...capturedInheritedKeywords].sort(),
        streamParams.preflight ? "pre" : "post",
      ]);
      semanticDivergenceLatestRequestedKeyRef.current = commitKey;
      const applyCurrentResponse = (response: NonNullable<FourStageRun["semantic_divergence"]>) => {
        if (!isCurrentDivergenceInvocation()) return response;
        setSemanticDivergence(response);
        setDivergenceKeywords(semanticCandidateTokens({ ...run, semantic_divergence: response }));
        // Keep user selection while divergence settles — do not wipe tokens here.
        setSemanticDivergenceLoading(false);
        setDivergencePhaseMessage(null);
        setIntentRevisions((current) => current.map((item) => item.revision_id === capturedRevisionId
          ? {
              ...item,
              semantic_divergence_status:
                response.status === "completed"
                  ? "completed"
                  : response.status === "failed"
                    ? "failed"
                    : item.semantic_divergence_status,
              semantic_divergence_error: response.status === "failed" ? "semantic divergence unavailable" : null,
            }
          : item));
        return response;
      };
      if (
        !options?.force &&
        semanticDivergenceLastSettledKeyRef.current === commitKey &&
        semanticDivergenceLastSettledResponseRef.current
      ) {
        return applyCurrentResponse(semanticDivergenceLastSettledResponseRef.current);
      }
      if (!isCurrentDivergenceInvocation()) return null;
      setSemanticDivergenceLoading(true);
      setDivergenceKeywords([]);
      setSemanticDivergenceError(null);
      setDivergencePhaseMessage(
        streamParams.preflight ? "Preflight divergence…" : "Connecting to model…",
      );
      let request = semanticDivergenceInFlightRef.current.get(commitKey);
      if (!request) {
        request = (async () => {
          const response = await streamSemanticDivergence(
            capturedRunId,
            streamParams,
            {
              onPhase: (event) => {
                if (!isCurrentDivergenceInvocation()) return;
                const message = describeDivergencePhase(event);
                if (message) setDivergencePhaseMessage(message);
              },
              onPartial: (partial) => {
                if (!isCurrentDivergenceInvocation()) return;
                setSemanticDivergence(partial);
                setDivergenceKeywords(
                  semanticCandidateTokens({ ...run, semantic_divergence: partial }),
                );
              },
            },
          );
          return response;
        })();
        semanticDivergenceInFlightRef.current.set(commitKey, request);
        void request.then(
          () => {
            if (semanticDivergenceInFlightRef.current.get(commitKey) === request) {
              semanticDivergenceInFlightRef.current.delete(commitKey);
            }
            if (semanticDivergenceLiveRequestRef.current === request) {
              semanticDivergenceLiveRequestRef.current = null;
            }
          },
          () => {
            if (semanticDivergenceInFlightRef.current.get(commitKey) === request) {
              semanticDivergenceInFlightRef.current.delete(commitKey);
            }
            if (semanticDivergenceLiveRequestRef.current === request) {
              semanticDivergenceLiveRequestRef.current = null;
            }
          },
        );
      }
      semanticDivergenceLiveParamsRef.current = {
        temperature,
        perGroupCount,
        revisionId: capturedRevisionId,
      };
      semanticDivergenceLiveRequestRef.current = request;
      const response = await request;
      if (semanticDivergenceLatestRequestedKeyRef.current === commitKey) {
        semanticDivergenceLastSettledKeyRef.current = commitKey;
        semanticDivergenceLastSettledResponseRef.current = response;
      }
      if (!isCurrentDivergenceInvocation()) return response;
      return applyCurrentResponse(response);
    } catch (error) {
      if (isCurrentDivergenceInvocation()) {
        setSemanticDivergenceLoading(false);
        setDivergencePhaseMessage(null);
        setSemanticDivergenceError(String(error).slice(0, 160));
        setIntentRevisions((current) =>
          current.map((item) =>
            item.revision_id === capturedRevisionId
              ? {
                  ...item,
                  semantic_divergence_status: "failed",
                  semantic_divergence_error: String(error).slice(0, 160),
                }
              : item,
          ),
        );
        addLog("semantic divergence", String(error).slice(0, 160));
      }
      return null;
    } finally {
      if (
        divergenceCommitInvocationRef.current === invocationToken &&
        semanticDivergenceAttachingRevisionRef.current === capturedRevisionId
      ) {
        semanticDivergenceAttachingRevisionRef.current = null;
      }
    }
  };

  const scheduleDivergenceParametersCommit = () => {
    window.clearTimeout(divergenceCommitTimerRef.current);
    divergenceCommitTimerRef.current = window.setTimeout(() => {
      void commitDivergenceParameters({
        force: true,
        temperature: divergenceTemperatureRef.current,
        perGroupCount: divergencePerGroupCountRef.current,
      });
    }, 2000);
  };

  // Composer Mana: one-click whole-silhouette keyword diverge. Do not write
  // Action History / Gate — those force a second click before keywords appear.
  const triggerPostGateDivergence = async () => {
    if (!session || semanticDivergenceLoading) return null;
    const invocationToken = ++divergenceCommitInvocationRef.current;
    const genericObjectNames = new Set([
      "",
      "object",
      "unknown",
      "item",
      "thing",
      "model",
      "asset",
      "design subject",
    ]);
    const isGenericName = (value: string) => {
      const text = value.trim();
      if (!text) return true;
      if (genericObjectNames.has(text.toLowerCase())) return true;
      return /^(cube\.|obj_group_|mesh_|mesh\.)/i.test(text);
    };
    const objectName = (() => {
      const meta = asset?.metadata ?? {};
      const candidates = [
        asset?.label,
        asset?.object_type,
        typeof meta.title === "string" ? meta.title : null,
        typeof meta.object_type === "string" ? meta.object_type : null,
        typeof meta.label === "string" ? meta.label : null,
      ]
        .map((item) => String(item || "").trim())
        .filter(Boolean);
      return candidates.find((item) => !isGenericName(item)) || candidates[0] || "design subject";
    })();
    const intentHint = intentText.trim();
    const userSemanticIntent = [
      intentHint || null,
      `主体是${objectName}`,
      `当前关注整体轮廓：${objectName}`,
      `围绕${objectName}的整体外形、比例与风格提出具体可执行方向`,
    ]
      .filter(Boolean)
      .join("。");
    const body = {
      object_type: objectName,
      asset_id: asset?.asset_id ?? null,
      scope: "whole",
      part_id: null,
      part_label: null,
      user_semantic_intent: userSemanticIntent,
      behavior_summary: `mana whole-silhouette diverge on ${objectName}`,
      gate_question: `你想改变这个 ${objectName} 的整体轮廓吗？`,
      hard_constraints: [
        `preserve_object_identity:${objectName}`,
        `all candidates must remain about ${objectName}`,
        `prefer_scope_whole:${objectName}`,
        "prefer_scope_silhouette",
      ],
      temperature: divergenceTemperature,
      strictness: 0.6,
      per_group_count: divergencePerGroupCount,
      model_choice: "primary_then_fallback" as const,
      knowledge_mode: "auto" as const,
    };
    const tokensFromCandidates = (candidates: Array<Record<string, unknown>>): PromptToken[] =>
      candidates.map((candidate, index) => {
        const candidateId = String(candidate.candidate_id ?? `sandbox_${index + 1}`);
        const group = String(candidate.group ?? "shape");
        const attributeDelta = (candidate.attribute_delta ?? {}) as Record<string, unknown>;
        const provenance = (candidate.provenance ?? {}) as Record<string, unknown>;
        return {
          token_id: candidateId,
          candidate_id: candidateId,
          label: String(candidate.display_label_zh ?? candidate.label_en ?? candidateId),
          dimension:
            group === "surface"
              ? "Aesthetic"
              : group === "semantic_transfer"
                ? "Cross-domain"
                : "Structural",
          group_key: group,
          role: "semantic_divergence",
          full_prompt_phrase: typeof candidate.prompt_phrase === "string" ? candidate.prompt_phrase : undefined,
          operation: typeof candidate.operation === "string" ? candidate.operation : undefined,
          attribute_delta: {
            [String(attributeDelta.attribute ?? "direction")]: String(attributeDelta.change ?? ""),
          },
          provenance_path: {
            source: String(provenance.generator ?? "sandbox"),
            mode: String(provenance.mode ?? "direct"),
          },
          target_ref: candidate.target_ref as PromptToken["target_ref"],
        };
      });
    const isCurrent = () => divergenceCommitInvocationRef.current === invocationToken;
    setSemanticDivergenceLoading(true);
    setSemanticDivergenceError(null);
    setDivergencePhaseMessage("Connecting to model…");
    setSelectedPromptTokens([]);
    try {
      let sawDone = false;
      for await (const event of sseFetch("/api/v1/sandbox/diverge/stream", {
        method: "POST",
        body: JSON.stringify(body),
      })) {
        if (!isCurrent()) return null;
        if (event.event === "phase") {
          const phase = (event.data ?? {}) as Record<string, unknown>;
          const message = describeDivergencePhase(phase);
          if (message) setDivergencePhaseMessage(message);
          const candidates = Array.isArray(phase.candidates)
            ? (phase.candidates as Array<Record<string, unknown>>)
            : [];
          if (candidates.length) {
            setDivergenceKeywords(tokensFromCandidates(candidates));
          }
          continue;
        }
        if (event.event === "done") {
          sawDone = true;
          const payload = (event.data ?? {}) as Record<string, unknown>;
          const candidates = Array.isArray(payload.candidates)
            ? (payload.candidates as Array<Record<string, unknown>>)
            : [];
          setDivergenceKeywords(tokensFromCandidates(candidates));
          setSemanticDivergence({
            schema_version: "flowstudio.semantic-divergence.v1",
            divergence_id: `sandbox_${Date.now().toString(36)}`,
            run_id: "",
            decision_id: "",
            request_key: `sandbox:${objectName}:whole`,
            status: "completed",
            generator_model: String(payload.model ?? "sandbox"),
            fallback_used: Boolean(payload.fallback_used),
            fallback_reason: null,
            knowledge_route: {
              mode: "model_only",
              use_wikidata: false,
              use_getty_aat: false,
              use_asknature: false,
              reasons: ["composer_mana_direct"],
              source_statuses: {},
            },
            validation_counts: {},
            latency_ms: Number(payload.latency_ms ?? 0),
            prompt_version: "semantic-divergence-v1",
            candidates: candidates as NonNullable<FourStageRun["semantic_divergence"]>["candidates"],
          });
          addLog("divergence", `sandbox keywords ${candidates.length}`);
          continue;
        }
        if (event.event === "error") {
          const detail =
            (event.data as { detail?: string } | null)?.detail ?? "sandbox diverge failed";
          throw new Error(detail);
        }
      }
      if (!sawDone) throw new Error("sandbox diverge stream ended without done");
      return true;
    } catch (error) {
      if (isCurrent()) {
        setSemanticDivergenceError(String(error).slice(0, 160));
        setDivergencePhaseMessage(null);
        addLog("divergence", String(error).slice(0, 160));
      }
      return null;
    } finally {
      if (isCurrent()) {
        setSemanticDivergenceLoading(false);
        setDivergencePhaseMessage(null);
      }
    }
  };

  // If server marks divergence running (Accept path) but SSE wasn't attached, attach it.
  // Also re-fetch once if the worker already marked completed but keywords never hydrated.
  useEffect(() => {
    const revision =
      (activeRevisionId
        ? intentRevisions.find((item) => item.revision_id === activeRevisionId)
        : null) ??
      [...intentRevisions].reverse().find((item) => item.semantic_divergence_status === "running") ??
      null;
    if (!revision?.run_id) return;
    if (semanticDivergence?.status === "failed") return;
    const needsHydrate =
      revision.semantic_divergence_status === "completed"
      && divergenceKeywords.length === 0
      && semanticDivergence?.status !== "completed";
    const needsAttach = revision.semantic_divergence_status === "running";
    if (!needsAttach && !needsHydrate) return;
    if (solutionSpaceGenerating && needsAttach) return;
    const hydrateAttempts = Number(divergenceHydrateRetryRef.current?.split(":")[1] || 0);
    if (needsHydrate && divergenceHydrateRetryRef.current?.startsWith(`${revision.revision_id}:`) && hydrateAttempts >= 3) {
      setSemanticDivergence((current) => current ?? {
        schema_version: "semantic-divergence-v1",
        divergence_id: "hydrate-timeout",
        run_id: revision.run_id ?? "",
        decision_id: "",
        request_key: "",
        status: "failed",
        generator_model: "",
        fallback_used: false,
        fallback_reason: "no keywords returned",
        knowledge_route: {
          mode: "model_only",
          use_wikidata: false,
          use_getty_aat: false,
          use_asknature: false,
          reasons: [],
          source_statuses: {},
        },
        validation_counts: {},
        latency_ms: 0,
        prompt_version: "semantic-divergence-v1",
        candidates: [],
      });
      return;
    }
    if (needsHydrate && divergenceHydrateRetryRef.current === `${revision.revision_id}:${hydrateAttempts}` && semanticDivergenceAttachingRevisionRef.current === revision.revision_id) return;
    if (semanticDivergenceAttachingRevisionRef.current === revision.revision_id && !needsHydrate) return;
    if (semanticDivergenceInFlightRef.current.size > 0 && !needsHydrate) return;
    if (semanticDivergence?.status === "completed" && divergenceKeywords.length > 0) return;
    if (needsHydrate) {
      divergenceHydrateRetryRef.current = `${revision.revision_id}:${hydrateAttempts + 1}`;
    }
    void commitDivergenceParameters({
      preflight: true,
      revisionId: revision.revision_id,
      force: needsHydrate,
    });
  }, [activeRevisionId, intentRevisions, semanticDivergence?.status, divergenceKeywords.length, solutionSpaceGenerating]);

  // While SSE is mid-flight, also poll the run so keywords appear even if a phase
  // event was missed (Accept worker join / proxy buffering).
  useEffect(() => {
    if (!semanticDivergenceLoading) return;
    const runId =
      fourStageRef.current.runId ??
      intentRevisions.find((item) => item.revision_id === activeRevisionId)?.run_id ??
      null;
    if (!runId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const run = await api<FourStageRun>(`/api/v1/four-stage/runs/${runId}`);
        if (cancelled) return;
        const response = run.semantic_divergence;
        if (!response) return;
        if (response.status === "failed") {
          setSemanticDivergence(response);
          setSemanticDivergenceLoading(false);
          setDivergencePhaseMessage(null);
          setSemanticDivergenceError(
            response.fallback_reason || "semantic divergence unavailable",
          );
          return;
        }
        if (!response.candidates?.length) return;
        setSemanticDivergence(response);
        setDivergenceKeywords(semanticCandidateTokens(run));
        if (response.status === "completed") {
          setSemanticDivergenceLoading(false);
          setDivergencePhaseMessage(null);
          setSemanticDivergenceError(null);
        } else {
          setDivergencePhaseMessage((current) => current ?? "Receiving candidates…");
        }
      } catch {
        // Ignore transient poll errors; SSE remains authoritative.
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [semanticDivergenceLoading, activeRevisionId, intentRevisions]);

  const startActiveRevisionGeneration = async () => {
    const revisionId = activeRevisionIdRef.current ?? [...intentRevisionsRef.current].reverse().find((item) => item.status === "accepted")?.revision_id;
    if (!revisionId) {
      setProjectNotice("请先确认改变范围，再点 Generate");
      return null;
    }
    setSolutionSpaceReadyPulse(false);
    setSolutionSpaceGenerating(true);
    setSolutionSpaceReleased((current) =>
      reduceSolutionSpaceVisibility(current, { type: "expand" }),
    );
    setSolutionSpaceHeight((current) => Math.max(current, 280));
    const focusRevision = intentRevisionsRef.current.find((item) => item.revision_id === revisionId);
    if (focusRevision) setSolutionSpaceViewIntentSeq(focusRevision.intent_seq);
    void projectRecorder.record(
      "generation.requested",
      { revision_id: revisionId },
      `generation:${revisionId}:${crypto.randomUUID()}`,
    );
    const selectionTracker = selectionPersistenceByRevisionRef.current.get(revisionId);
    if (selectionTracker) {
      let awaitedSelectionPersistence = selectionTracker.latest;
      let persistenceOk = await selectionTracker.latest;
      while (awaitedSelectionPersistence !== selectionTracker.latest) {
        awaitedSelectionPersistence = selectionTracker.latest;
        persistenceOk = await awaitedSelectionPersistence;
      }
      if (
        activeRevisionIdRef.current !== revisionId ||
        !persistenceOk ||
        selectionTracker.error
      ) {
        const message = selectionTracker.error ?? "关键词保存失败，请重新选择后再生成";
        selectionTracker.error = message;
        setSelectionPersistenceErrors((current) => ({ ...current, [revisionId]: message }));
        addLog("generation", message);
        setProjectNotice(message);
        setSolutionSpaceGenerating(false);
        return null;
      }
    }
    try {
      let revision = intentRevisionsRef.current.find((item) => item.revision_id === revisionId);
      if (!revision || !interactionCoordinator) {
        throw new Error("interaction coordinator unavailable");
      }
      // Refresh viewport identity image right before Generate so Qwen has a real source.
      if (session?.session_id && threeViewportRef.current) {
        const shot = await captureAndUploadViewport(threeViewportRef.current, {
          sessionId: session.session_id,
          assetId: revision.source_context.asset_id,
          partId: revision.source_context.target_part_id ?? (selectedPart || null),
          metadata: { trigger: "generate", tool_surface: "3d" },
        });
        if (shot?.url) {
          revision = await api<IntentRevision>(
            `/api/v1/intent-revisions/${revisionId}/source-image`,
            {
              method: "POST",
              body: JSON.stringify({ source_image_ref: shot.url }),
            },
          );
          setIntentRevisions((current) =>
            current.map((item) => (item.revision_id === revisionId ? revision! : item)),
          );
        }
      }
      const commandId = `generation_${revisionId}_${crypto.randomUUID()}`;
      const response = await interactionCoordinator.startGeneration(revision, {
        command_id: commandId,
        idempotency_key: `generation-command:${revisionId}:${commandId}`,
      });
      setIntentRevisions((current) => current.map((item) => item.revision_id === revisionId ? response.revision : item));
      // The task acknowledgement is the user-visible success boundary. The
      // SolutionBatch appears through the event/projection stream later.
      if (session?.session_id) void refreshRealtimeObservation(session.session_id);
      return response.task;
    } catch (error) {
      const message = String(error).slice(0, 160);
      addLog("generation", message);
      setProjectNotice(`生成失败：${message}`);
      setSolutionSpaceGenerating(false);
      return null;
    }
  };

  const createFourStageRun = async (behaviorOverride?: ActionAtom[]) => {
    if (!session) return null;
    if (fourStage.creatingRun) return null;
    setFourStage((current) => ({ ...current, creatingRun: true, error: null }));
    try {
      const CANONICAL_EVENT_TYPES: Record<string, string> = {
        brush: "brush_end",
        drag: "drag_end",
        smooth: "smooth_end",
        annotation: "annotation_commit",
        hover: "hover_focus",
        add: "primitive_added",
        text: "text_committed",
        image: "image_ref",
        model: "model_ref",
      };
      const boundedPayload = (atom: ActionAtom): Record<string, unknown> => {
        const payload: Record<string, unknown> = { ...atom.target, ...atom.evidence };
        for (const key of Object.keys(payload)) {
          const value = payload[key];
          if (typeof value === "string" && value.startsWith("data:") && value.length > 8_000) {
            payload[key] = null;
          }
        }
        return payload;
      };
      const behaviorEvents: Array<{
        type: string;
        event_id: string;
        session_id: string;
        timestamp: string;
        payload: Record<string, unknown>;
      }> = (behaviorOverride ?? visibleBehaviorAtoms).slice(-8).map((atom, index) => ({
        type: CANONICAL_EVENT_TYPES[atom.tool] ?? "behavior_observation",
        event_id: atom.atom_id,
        session_id: session.session_id,
        timestamp: atom.created_at ?? new Date().toISOString(),
        payload: {
          ...boundedPayload(atom),
          behavior_atoms: (behaviorOverride ?? visibleBehaviorAtoms).slice(0, index + 1).map((item, order) => ({
            atom_id: item.atom_id,
            tool: item.tool,
            target: item.target,
            evidence: boundedPayload(item),
            order,
          })),
          behavior_count: (behaviorOverride ?? visibleBehaviorAtoms).length,
          order: index,
        },
      }));
      if (intentText.trim()) {
        behaviorEvents.push({
          type: "intent_text_changed",
          event_id: `evt_${crypto.randomUUID().slice(0, 8)}`,
          session_id: session.session_id,
          timestamp: new Date().toISOString(),
          payload: { text: intentText, intent_text: intentText },
        });
      }
      if (!behaviorEvents.length) {
        addLog("four-stage", "no behavior evidence yet — draw/type something first");
        setFourStage((current) => ({ ...current, creatingRun: false }));
        return null;
      }
      const run = await api<FourStageRun>("/api/v1/four-stage/runs", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          idempotency_key: `run_${session.session_id}_${Date.now()}`,
          run_hy3d: hy3dCandidateIds.length > 0,
          auto_advance: false,
          events: behaviorEvents,
        }),
      });
      setFourStage((current) => ({
        ...current,
        runId: run.run_id,
        stage: run.stage,
        gateOpen: run.stage === "awaiting_gate",
        gateTimeoutAt: run.stage === "awaiting_gate" ? Date.now() + GATE_TIMEOUT_MS : null,
        creatingRun: false,
        error: null,
      }));
      lastFourStageDecisionIdRef.current = null;
      setDivergenceKeywords([]);
      addLog("four-stage", `run ${run.run_id} created (${run.stage})`);
      return run;
    } catch (error) {
      addLog("four-stage", `run creation failed: ${String(error).slice(0, 160)}`);
      setFourStage((current) => ({
        ...current,
        creatingRun: false,
        error: { code: "create_failed", message: String(error).slice(0, 160), retryable: true },
      }));
      return null;
    }
  };

  /** 交互中持续把新行为事件追加进当前 run（四阶段流式编码）。 */
  const appendFourStageEvents = async (
    atoms: ActionAtom[],
    opts: { advance?: boolean } = {},
  ) => {
    const runId = fourStageRef.current.runId;
    const terminal = fourStageRef.current.stage === "completed" || fourStageRef.current.stage === "failed";
    if (!session || terminal) return null;
    if (!runId) {
      // 交互即编码：首个行为事件直接创建 run（auto_advance=false 停在 raw_events，
      // 事件追加后后端自动执行 encoding 并停在 encoding）。
      return createFourStageRun(atoms);
    }
    const CANONICAL_EVENT_TYPES: Record<string, string> = {
      brush: "brush_end",
      drag: "drag_end",
      smooth: "smooth_end",
      annotation: "annotation_commit",
      hover: "hover_focus",
      add: "primitive_added",
      text: "text_committed",
      image: "image_ref",
      model: "model_ref",
    };
    const events = atoms.slice(-8).map((atom) => ({
      type: CANONICAL_EVENT_TYPES[atom.tool] ?? "behavior_observation",
      event_id: atom.atom_id,
      session_id: session.session_id,
      timestamp: atom.created_at ?? new Date().toISOString(),
      payload: { ...atom.target, ...atom.evidence },
    }));
    if (!events.length) return null;
    try {
      const run = await api<FourStageRun>(
        `/api/v1/four-stage/runs/${runId}/events?auto_advance=${opts.advance ? "true" : "false"}`,
        {
          method: "POST",
          body: JSON.stringify({
            session_id: session.session_id,
            events,
          }),
        },
      );
      setFourStage((current) => ({
        ...current,
        runId: run.run_id,
        stage: run.stage,
        error: run.error ?? current.error,
      }));
      return run;
    } catch (error) {
      addLog("four-stage", `append events failed: ${String(error).slice(0, 120)}`);
      return null;
    }
  };

  /** 流式推进：意图判断→检索；点关键词→决策→awaiting_gate。 */
  const advanceFourStageRun = async (target?: string) => {
    const runId = fourStageRef.current.runId;
    if (!runId) return null;
    try {
      const run = await api<FourStageRun>(`/api/v1/four-stage/runs/${runId}/advance`, {
        method: "POST",
        body: JSON.stringify({ target: target ?? null }),
      });
      setFourStage((current) => ({
        ...current,
        runId: run.run_id,
        stage: run.stage,
        decision: run.decision ?? current.decision,
        gateOpen: run.stage === "awaiting_gate",
        gateTimeoutAt: run.stage === "awaiting_gate" ? Date.now() + GATE_TIMEOUT_MS : null,
        error: run.error ?? current.error,
      }));
      refreshFourStageUiFromRun(run);
      if (run.stage === "awaiting_gate") {
        armGateDismissal(run.run_id);
      }
      return run;
    } catch (error) {
      addLog("four-stage", `advance failed: ${String(error).slice(0, 120)}`);
      return null;
    }
  };

  const gateFourStage = async (
    runId: string,
    decisionId: string,
    action: FourStageGateAction,
    opts: { selected_option_id?: string | null; user_revision?: string | null; reason?: string | null; auto_generate?: boolean } = {},
  ) => {
    if (!session) return;
    setFourStage((current) => ({ ...current, gateBusy: true }));
    try {
      const body: FourStageGateRequest = { run_id: runId, action, ...opts };
      const run = await api<FourStageRun>(`/api/v1/four-stage/decisions/${decisionId}/gate`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setFourStage((current) => {
        const next: FourStageUiState = {
          ...current,
          runId: run.run_id,
          stage: run.stage,
          gateBusy: false,
          error: run.error ?? null,
        };
        if (run.decision) next.decision = run.decision;
        next.gateQuestion = run.scope_gate?.question ?? run.decision?.gate_question ?? next.gateQuestion;
        next.scopeAccepted = run.scope_gate?.status === "accepted";
        next.divergenceSelection = run.divergence_selection ?? next.divergenceSelection;
        if (action === "request_revision") {
          next.gateOpen = true;
          next.gateTimeoutAt = Date.now() + GATE_TIMEOUT_MS;
        armGateDismissal(run.run_id);
        } else {
          next.gateOpen = false;
          next.gateTimeoutAt = null;
          clearGateTimeout();
        }
        return next;
      });
      refreshFourStageUiFromRun(run);
      addLog("four-stage", `gate ${action} -> ${run.stage}`);
      return run;
    } catch (error) {
      addLog("four-stage", `gate ${action} failed: ${String(error).slice(0, 160)}`);
      setFourStage((current) => ({ ...current, gateBusy: false }));
      return null;
    }
  };

  const saveFourStageDivergenceSelection = async (selection: NonNullable<FourStageRun["divergence_selection"]>) => {
    const runId = fourStageRef.current.runId;
    if (!runId) return null;
    try {
      const run = await api<FourStageRun>(`/api/v1/four-stage/runs/${runId}/divergence-selection`, {
        method: "PUT",
        body: JSON.stringify(selection),
      });
      refreshFourStageUiFromRun(run);
      setFourStage((current) => ({
        ...current,
        divergenceSelection: run.divergence_selection ?? selection,
        stage: run.stage,
      }));
      return run;
    } catch (error) {
      addLog("four-stage", `keyword selection failed: ${String(error).slice(0, 160)}`);
      return null;
    }
  };

  const startFourStageGeneration = async () => {
    const runId = fourStageRef.current.runId;
    if (!runId) return null;
    try {
      const run = await api<FourStageRun>(`/api/v1/four-stage/runs/${runId}/generation`, {
        method: "POST",
      });
      refreshFourStageUiFromRun(run);
      setFourStage((current) => ({ ...current, runId: run.run_id, stage: run.stage, scopeAccepted: true }));
      return run;
    } catch (error) {
      addLog("four-stage", `generation start failed: ${String(error).slice(0, 160)}`);
      return null;
    }
  };

  const semanticCandidateTokens = (run: FourStageRun): PromptToken[] =>
    (run.semantic_divergence?.candidates ?? []).map((candidate) => ({
      token_id: candidate.candidate_id,
      candidate_id: candidate.candidate_id,
      label: candidate.display_label_zh,
      dimension: candidate.group === "surface"
        ? "Aesthetic"
        : candidate.group === "semantic_transfer"
          ? "Cross-domain"
          : "Structural",
      group_key: candidate.group,
      role: "semantic_divergence",
      full_prompt_phrase: candidate.prompt_phrase,
      operation: candidate.operation,
      attribute_delta: {
        [candidate.attribute_delta.attribute]: candidate.attribute_delta.change,
      },
      provenance_path: {
        source: candidate.provenance.generator,
        mode: candidate.provenance.mode,
      },
      target_ref: candidate.target_ref,
    }));

  type FourStageRetrievalView = {
    retrieval_id?: string;
    matches?: Array<{
      prior_ir_id: string;
      case_id?: string | null;
      final_score?: number;
      sparse_score?: number;
      prior_judgement?: {
        design_state?: string;
        route?: string;
        target_level?: string;
        recommended_axes?: string[];
        evidence_strength?: string;
      };
      evidence?: Array<{
        signal_overlap?: string[];
        term_overlap?: string[];
        scope_match?: boolean;
      }>;
    }>;
  };

  const deriveFourStageInterpretation = (run: FourStageRun): Interpretation | null => {
    if (!run) return null;
    const decision = run.decision;
    const retrieval = run.retrieval as FourStageRetrievalView | null;
    if (!decision && !retrieval) return null;
    const topMatch = retrieval?.matches?.[0];
    const level = decision?.recommended_scope ?? topMatch?.prior_judgement?.target_level ?? "whole";
    const semanticTarget = decision?.semantic_target ?? activeSelectedPart?.label ?? "部件";
    const isMaterialScope = level === "material" || level === "material_region";
    const scopeZh =
      level === "part"
        ? semanticTarget
        : isMaterialScope
          ? "材质区域"
          : "整体轮廓";
    const confidence = decision?.confidence ?? topMatch?.final_score ?? 0.5;
    return {
      interpretation_id: decision?.decision_id ?? retrieval?.retrieval_id ?? `ir_${run.run_id}`,
      primary_intent: decision?.summary ?? (intentText.trim() || "composed intent"),
      predictor: decision?.model ?? "four-stage",
      predictor_version: decision?.prompt_version ?? "v1",
      confidence,
      ambiguity: 0,
      hypotheses: [],
      assistance_policy: "four_stage",
      evidence: [],
      semantic_targets: [
        {
          target_id: decision?.decision_id ?? retrieval?.retrieval_id ?? `tgt_${run.run_id}`,
          level: isMaterialScope ? "material_region" : level === "part" ? "part" : "silhouette",
          semantic: { label_zh: scopeZh },
          operation_hint: "deform",
          confidence,
          evidence: [],
        },
      ],
      features: {
        creative_state: "ready_for_help",
        creative_state_confidence: confidence,
        design_state_ir: {
          ready: true,
          scope_hint: scopeZh,
          change_scope_hint: scopeZh,
          recommended_axes: topMatch?.prior_judgement?.recommended_axes ?? [],
          matches: (retrieval?.matches ?? []).map((match) => ({
            ir_id: match.prior_ir_id,
            case_id: match.case_id ?? "",
            score: match.final_score,
            confidence: match.final_score,
            vector_score: match.sparse_score,
            design_state: String(match.prior_judgement?.design_state ?? ""),
            route: String(match.prior_judgement?.route ?? ""),
            signals: [],
            signal_overlap: (match.evidence?.[0]?.signal_overlap ?? []) as string[],
            term_overlap: (match.evidence?.[0]?.term_overlap ?? []) as string[],
            scope_match: Boolean(match.evidence?.[0]?.scope_match ?? true),
            scope_hint: scopeZh,
            change_scope_hint: scopeZh,
            recommended_axes: (match.prior_judgement?.recommended_axes ?? []) as string[],
          })),
        },
      },
    };
  };

  /** 四阶段 -> UI 的唯一桥：interpretation/意图泡泡/发散关键词全部由 run 派生。 */
  const refreshFourStageUiFromRun = (run: FourStageRun | null) => {
    if (!run) return;
    const interpreted = deriveFourStageInterpretation(run);
    if (interpreted) setInterpretation(interpreted);
    const retrievalView = run.retrieval as FourStageRetrievalView | null;
    const decisionId = run.decision?.decision_id ?? null;
    const availableTokens = semanticCandidateTokens(run);
    if (decisionId) lastFourStageDecisionIdRef.current = decisionId;
    setSemanticDivergence(run.semantic_divergence ?? null);
    if (run.semantic_divergence?.status === "completed") {
      setDivergenceKeywords(availableTokens);
      setSemanticDivergenceLoading(false);
      setSemanticDivergenceError(null);
    } else if (run.semantic_divergence?.status === "failed") {
      setDivergenceKeywords([]);
      setSemanticDivergenceLoading(false);
      setSemanticDivergenceError(run.error?.message ?? "semantic divergence unavailable");
    }
    const level = run.decision?.recommended_scope ?? retrievalView?.matches?.[0]?.prior_judgement?.target_level;
    const bubbleScope: BubbleScope =
      level === "part" ? "part" : level === "material" || level === "material_region" ? "material" : "contour";
    const revisionForRun = intentRevisionsRef.current.find((item) => item.run_id === run.run_id);
    const selectionTracker = revisionForRun
      ? selectionPersistenceByRevisionRef.current.get(revisionForRun.revision_id)
      : undefined;
    const reconciledSelection = reconcileSelectedPromptTokens({
      availableTokens,
      serverSelectedCandidateIds: resolveServerSelectedCandidateIds({
        revisionSelectedCandidateIds: revisionForRun?.divergence_selection?.selected_candidate_ids,
        runSelectedCandidateIds: run.divergence_selection?.selected_candidate_ids,
      }),
      optimisticTokens: selectedPromptTokensRef.current,
      persistencePending: Boolean(selectionTracker?.pending || selectionTracker?.error),
    });
    selectedPromptTokensRef.current = reconciledSelection;
    setSelectedPromptTokens(reconciledSelection);
    if (run.stage === "awaiting_gate" && run.scope_gate?.status !== "accepted") {
      setIntentBubble({
        visible: true,
        scope: bubbleScope,
        status: "pending",
        shownAt: Date.now(),
      });
    } else if (run.stage === "awaiting_gate" && run.scope_gate?.status === "accepted") {
      setIntentBubble((current) => ({ ...current, visible: false, status: "accepted" }));
    }
  };

  /** 意图文本进入四阶段：追加 intent_text_changed 事件并推进到检索（阶段2）。 */
  const submitIntentTextToFourStage = async (text: string, target: "retrieval" | "re_representation" = "retrieval") => {
    if (!session || !asset) return;
    let runId = fourStageRef.current.runId;
    const terminal =
      runId !== null &&
      (fourStageRef.current.stage === "completed" || fourStageRef.current.stage === "failed");
    if (!runId || terminal) {
      const run = await createFourStageRun();
      if (!run) return;
      runId = run.run_id;
    }
    try {
      await api<FourStageRun>(
        `/api/v1/four-stage/runs/${runId}/events?auto_advance=false`,
        {
          method: "POST",
          body: JSON.stringify({
            session_id: session.session_id,
            events: [
              {
                type: "intent_text_changed",
                event_id: `evt_${crypto.randomUUID().slice(0, 8)}`,
                session_id: session.session_id,
                timestamp: new Date().toISOString(),
                payload: { text, intent_text: text, asset_id: asset.asset_id },
              },
            ],
          }),
        },
      );
    } catch (error) {
      addLog("four-stage", `intent text append failed: ${String(error).slice(0, 120)}`);
      return;
    }
    void advanceFourStageRun(target);
  };

  // 意图文本稳定后自动进入四阶段检索（阶段2），替代旧 interaction/interpret。
  useEffect(() => {
    if (REVISION_GATED_INTERACTION) return undefined;
    const text = intentText.trim();
    if (!typedIntentStable || !session || !asset || text.length < 3) return;
    const key = `${asset.asset_id}:${text}:${visibleBehaviorAtoms.length}`;
    if (composedInterpretKeyRef.current === key) return;
    const timer = window.setTimeout(() => {
      if (composedInterpretKeyRef.current === key) return;
      composedInterpretKeyRef.current = key;
      void submitIntentTextToFourStage(text);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [
    typedIntentStable,
    intentText,
    asset?.asset_id,
    visibleBehaviorAtoms.length,
    session,
    asset,
  ]);

  useEffect(() => {
    const runId = fourStage.runId;
    if (!runId) return;
    // completed 也要至少再拉一次（WS 事件可能不带 artifacts，需从 run 补拿）。
    if (fourStage.stage === "completed") {
      void refreshFourStageRun(runId);
      return;
    }
    const terminal = fourStage.stage === "failed" || fourStage.stage === "cancelled";
    if (terminal) return;
    const timer = window.setInterval(() => {
      void refreshFourStageRun(runId);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [fourStage.runId, fourStage.stage]);

  const sendEvent = (type: string, payload: Record<string, unknown>) => {
    if (!session || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
    socketRef.current.send(
      JSON.stringify({
        type,
        event_id: `evt_${crypto.randomUUID().slice(0, 8)}`,
        session_id: session.session_id,
        timestamp: new Date().toISOString(),
        payload,
      }),
    );
  };

  const refreshRemoteHealth = async () => {
    try {
      const [backend, health, preflight] = await Promise.all([
        api<BackendHealth>("/health"),
        api<RemoteWorkerHealth>("/api/v1/remote-worker/health"),
        api<RemoteWorkerPreflight>("/api/v1/remote-worker/preflight"),
      ]);
      setBackendHealth(backend);
      setRemoteHealth(health);
      setRemotePreflight(preflight);
      addLog(
        "remote",
        health.ok ? `worker online / preflight ${preflight.ok ? "ready" : "warning"}` : "worker unavailable",
      );
    } catch (error) {
      setBackendHealth({ status: "error", remote_worker_ok: false });
      setRemoteHealth({ ok: false, error: String(error) });
      setRemotePreflight({ ok: false, error: String(error) });
      addLog("remote", "health check failed");
    }
  };

  const refreshSystemServices = async () => {
    if (systemServicesLoading) return;
    setSystemServicesLoading(true);
    try {
      const response = await api<SystemServicesResponse>("/api/v1/system/services");
      setSystemServices(response.services ?? []);
      setBootstrapRunning(Boolean(response.bootstrap?.running?.length));
    } catch {
      // Registry endpoint may be absent on older backends; keep last snapshot.
    } finally {
      setSystemServicesLoading(false);
    }
  };

  const startSystemService = async (serviceId: string) => {
    if (startingServiceIds.includes(serviceId)) return;
    setStartingServiceIds((current) => [...current, serviceId]);
    try {
      await api<{ ok: boolean; error?: string }>(
        `/api/v1/system/services/${serviceId}/start`,
        { method: "POST" },
      );
      addLog("services", `starting ${serviceId}`);
    } catch (error) {
      addLog("services", String(error).slice(0, 160));
    } finally {
      setStartingServiceIds((current) => current.filter((id) => id !== serviceId));
      window.setTimeout(() => void refreshSystemServices(), 1500);
    }
  };

  const bootstrapSystemServices = async () => {
    if (bootstrapRunning) return;
    setBootstrapRunning(true);
    try {
      const response = await api<{ ok: boolean; bootstrap_id?: string; message?: string }>(
        "/api/v1/system/services/bootstrap",
        { method: "POST" },
      );
      addLog("services", response.message ?? "bootstrap started");
    } catch (error) {
      setBootstrapRunning(false);
      addLog("services", String(error).slice(0, 160));
    }
    const timer = window.setInterval(() => {
      void refreshSystemServices();
    }, 2500);
    window.setTimeout(() => window.clearInterval(timer), 240000);
  };

  const refreshSession = async () => {
    if (!session) return null;
    const updated = await api<SessionRecord>(`/api/v1/sessions/${session.session_id}`);
    setSession(updated);
    setStage(updated.stage);
    return updated;
  };

  const loadCaseLibrary = async () => {
    try {
      const response = await api<CaseIndexResponse>("/files/cases/index.json");
      setCaseLibrary(response.cases.slice(0, 5));
    } catch {
      setCaseLibrary([]);
    }
  };

  const loadSolutionSpace = async (sessionId = session?.session_id) => {
    if (!sessionId) return;
    const sourceSeq = sourceSwitchSeqRef.current;
    try {
      const response = await api<SolutionSpaceResponse>(`/api/v1/sessions/${sessionId}/solution-space`);
      if (sourceSeq !== sourceSwitchSeqRef.current) return;
      setStage(response.stage);
      const restoredCandidates = response.nodes
        .map((node) => node.candidate)
        .filter((candidate): candidate is Candidate => Boolean(candidate));
      const ranked = rankCandidates(restoredCandidates);
      setCandidates(ranked);
      setAcceptedCandidateIds(
        ranked.filter((candidate) => candidate.decision === "accepted").map((candidate) => candidate.candidate_id),
      );
      addLog("solution space", `${ranked.length} candidates / ${response.directions?.length ?? 0} directions`);
    } catch (error) {
      addLog("solution space", String(error).slice(0, 160));
    }
  };

  const loadBenchmarkAssets = async () => {
    try {
      const response = await api<BenchmarkAssetListResponse>("/api/v1/benchmark-assets");
      const renderableAssets = response.assets.filter(isRenderableBenchmarkAsset).sort(compareBenchmarkAssets);
      setBenchmarkAssets(renderableAssets);
      const snowman = renderableAssets.find((item) => /snowman|雪人/i.test(`${item.label} ${item.object_type}`));
      if (snowman?.obj_url) void fetch(absoluteUrl(snowman.obj_url));
      return renderableAssets;
    } catch (error) {
      addLog("benchmark", String(error));
      setBenchmarkAssets([]);
      return [];
    }
  };

  const loadBenchmarkAsset = async (sessionId: string, benchmarkId: string) => {
    return api<AssetRecord>(`/api/v1/benchmark-assets/${benchmarkId}/load`, {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    });
  };

  const confirmProjectSwitch = (): boolean => {
    const unsaved =
      visibleBehaviorAtoms.length > 0 ||
      Boolean(sculptedMeshObjUrl) ||
      selectedPromptTokens.length > 0;
    if (!unsaved) return true;
    const confirmed = window.confirm(
      "当前项目有未保存的雕刻、行为或意图草稿。切换后当前项目将结束并保留在会话历史中，是否继续？",
    );
    if (confirmed) {
      setProjectNotice(
        `上一个项目已结束并保留在历史中（${visibleBehaviorAtoms.length} 条行为）`,
      );
      addLog("project", "ended with unsaved edits kept in history");
    }
    return confirmed;
  };

  const switchBenchmarkAsset = async (benchmarkId: string) => {
    if (!session || !benchmarkId || loadingBenchmark) return;
    if (!confirmProjectSwitch()) return;
    const sourceSeq = resetSourceDependentState("Loading selected white model…");
    setSelectedBenchmarkId(benchmarkId);
    incrementLiveSignal("new_case_attempt_rate");
    setLoadingBenchmark(true);
    try {
      const nextAsset = await loadBenchmarkAsset(session.session_id, benchmarkId);
      if (sourceSeq !== sourceSwitchSeqRef.current) return;
      setAsset(nextAsset);
      setParts(nextAsset.parts);
      setSelectedPart(nextAsset.parts[0]?.part_id ?? "");
      setStage((current) =>
        current
          ? {
              ...current,
              active_asset_id: nextAsset.asset_id,
              active_part_id: nextAsset.parts[0]?.part_id ?? null,
              current_goal: null,
              suggested_action: null,
              evidence: [],
            }
          : current,
      );
      setLivePerception({
        summary: `Loaded ${nextAsset.label}.`,
        evidence: ["source switched from Design DB"],
        confidence: null,
        source: "local",
        updatedAt: new Date().toISOString(),
      });
      addLog("benchmark", nextAsset.label);
      if (autoDiscoverParts && nextAsset.obj_url) {
        void discoverPartsForAsset(nextAsset, "upload");
      }
      // Semantic keywords are created only after an accepted Gate. A white
      // model is context for the divergence service, not a client-side seed.
      setDivergenceKeywords([]);
    } catch (error) {
      addLog("benchmark", String(error));
    } finally {
      setLoadingBenchmark(false);
    }
  };

  const startBlankWorkspace = async () => {
    if (!confirmProjectSwitch()) return null;
    pushEditorHistory("start blank workspace");
    resetSourceDependentState("Blank workspace. Load a model, add a primitive, or type an intent.");
    try {
      // 直接创建全新 session：历史（旧 session 的资产/行为/草稿/记忆）彻底隔离，
      // 刷新后 bootstrap 恢复的是空白新会话，与旧历史完全无关。
      const fresh = await api<SessionRecord>("/api/v1/sessions", {
        method: "POST",
        body: JSON.stringify({ title: "Design DB exploration", user_id: "local-dev" }),
      });
      window.localStorage.setItem(SESSION_STORAGE_KEY, fresh.session_id);
      setSession(fresh);
      setStage(fresh.stage);
      // 切换 WebSocket 到新会话，四阶段/感知事件回到空白会话通道。
      attachSessionSocket(fresh.session_id);
      // 旧会话后端历史也一并清空（用户不下载即删除），避免占用存储。
      if (session) {
        void api<{ ok: boolean }>(`/api/v1/sessions/${session.session_id}/reset`, {
          method: "POST",
          body: JSON.stringify({}),
        }).catch(() => undefined);
      }
      addLog("blank", `新工作区 ${fresh.session_id.slice(0, 10)}`);
      return fresh;
    } catch (error) {
      addLog("blank", String(error).slice(0, 120));
      return null;
    }
  };

  const clearCurrentHistory = async () => {
    if (!session) return null;
    const confirmed = window.confirm("清除当前历史记录？意图、行为和发散会清空，白模会重新加载。");
    if (!confirmed) return null;
    const benchmarkId = selectedBenchmarkId;
    try {
      await api<{ ok: boolean }>(`/api/v1/sessions/${session.session_id}/reset`, {
        method: "POST",
        body: JSON.stringify({}),
      });
    } catch (error) {
      addLog("history", String(error).slice(0, 120));
    }
    resetSourceDependentState("History cleared. Load a model or type an intent.");
    attachSessionSocket(session.session_id);
    void refreshRealtimeObservation(session.session_id);
    if (!benchmarkId) return session;
    try {
      const nextAsset = await loadBenchmarkAsset(session.session_id, benchmarkId);
      setSelectedBenchmarkId(benchmarkId);
      setAsset(nextAsset);
      setParts(nextAsset.parts);
      setSelectedPart(nextAsset.parts[0]?.part_id ?? "");
      addLog("history", "cleared; white model reloaded");
    } catch (error) {
      addLog("history", String(error).slice(0, 120));
    }
    return session;
  };

  const loadCaseIntoStudio = async (item: CaseIndexItem) => {
    if (!item.case_url || !session || loadingCaseIds.includes(item.case_id)) return;
    setLoadingCaseIds((current) => [...current, item.case_id]);
    try {
      const manifest = await api<CaseManifest>(item.case_url);
      const importedAsset = await api<AssetRecord>("/api/v1/assets", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          object_type: manifest.asset.object_type,
          label: manifest.asset.label,
          mesh_url: manifest.asset.mesh_url,
          obj_url: manifest.asset.obj_url,
          thumbnail_url: manifest.asset.thumbnail_url,
          parts: manifest.asset.parts,
          metadata: {
            ...manifest.asset.metadata,
            imported_from_case_id: manifest.case.case_id,
            imported_from_asset_id: manifest.asset.asset_id,
          },
        }),
      });
      setSavedCase(manifest.case);
      setCanvasPrimitive(null);
      setCanvasDisplayMode("textured");
      setCanvasTool("select");
      setAsset(importedAsset);
      setParts(importedAsset.parts);
      setStage({
        ...manifest.stage,
        active_asset_id: importedAsset.asset_id,
      });
      setSelectedPart(manifest.stage.active_part_id ?? importedAsset.parts[0]?.part_id ?? selectedPart);
      setAcceptedCandidateIds(manifest.case.accepted_candidate_ids);
      setCandidates(rankCandidates(manifest.accepted_candidates ?? []));
      setPreviewCandidate(
        (manifest.accepted_candidates ?? []).find((candidate) => candidate.mesh_url || candidate.obj_url) ?? null,
      );
      setCanvasPreview(null);
      setJob(null);
      setCaseTitle(manifest.case.title);
      setCaseNotes(manifest.case.notes ?? "");
      setCreativeStagePreset(caseCreativeStage(manifest, creativeStage));
      addLog("case loaded", `${manifest.case.case_id} -> ${importedAsset.asset_id}`);
      void refreshSession();
    } catch (error) {
      addLog("case load", String(error));
    } finally {
      setLoadingCaseIds((current) => current.filter((id) => id !== item.case_id));
    }
  };

  const sendBrush = async (partOverride?: PartRecord) => {
    if (!asset) return null;
    const screenshotPromise = captureAndUploadViewport(threeViewportRef.current, {
      sessionId: session?.session_id ?? "",
      assetId: asset.asset_id,
      partId: selectedPart || null,
      metadata: { trigger: "brush_end", tool_surface: "3d" },
    });
    const brushPart = partOverride ?? activeSelectedPart;
    const brushPartId = brushPart?.part_id ?? selectedPart;
    const brushMaskPayload = buildBrushMaskPayload({
      sessionId: session?.session_id ?? "",
      asset,
      part: brushPart ?? undefined,
      partId: brushPartId || null,
      text: intentText,
      displayMode: canvasDisplayMode,
    });
    let brushMaskArtifact: ArtifactRecord | null = null;
    try {
      brushMaskArtifact = await api<ArtifactRecord>("/api/v1/brush-masks", {
        method: "POST",
        body: JSON.stringify(brushMaskPayload),
      });
    } catch (error) {
      addLog("brush mask artifact", String(error).slice(0, 160));
    }
    const screenshotArtifact = await screenshotPromise;
    const screenshotUrl = screenshotArtifact?.url ?? null;
    const brushMaskUrl = brushMaskArtifact?.url ?? "/files/uploads/debug_mask.png";
    const nextLiveSignals = {
      ...liveSignals,
      mask_coverage: brushMaskPayload.metrics.coverage,
      brush_count: liveSignals.brush_count + 1,
    };
    setLiveSignals(nextLiveSignals);
    sendEvent("brush_end", {
      asset_id: asset.asset_id,
      brush_mask_artifact_id: brushMaskArtifact?.artifact_id ?? null,
      brush_mask_url: brushMaskArtifact?.url ?? null,
      brush_coverage: brushMaskPayload.metrics.coverage,
      brush_projection: brushMaskPayload.projection,
      viewport_screenshot_url: screenshotUrl,
      viewport_screenshot_artifact_id: screenshotArtifact?.artifact_id ?? null,
      selection: {
        type: "brush",
        part_id: brushPartId,
        label: brushPart?.label ?? brushPartId,
        mask_url: brushMaskUrl,
        brush_mask_artifact_id: brushMaskArtifact?.artifact_id ?? null,
        brush_mask_url: brushMaskArtifact?.url ?? null,
        coverage: brushMaskPayload.metrics.coverage,
        projection: brushMaskPayload.projection,
        bbox: [120, 82, 360, 264],
        metadata: brushPart
          ? {
              part_record: brushPart,
              partfield: brushPart.metadata ?? {},
              brush_mask_artifact: brushMaskArtifact,
            }
          : {},
      },
      intent_text: intentText,
      live_signals: nextLiveSignals,
      viewport: {
        camera_position: [0, 1.5, 4],
        camera_target: [0, 0.8, 0],
      },
    });
    recordActionAtom(
      "brush",
      {
        asset_id: asset.asset_id,
        part_id: brushPartId,
        label: brushPart?.label ?? brushPartId,
        part_source: brushPart?.metadata?.source ?? null,
        source_part_id: brushPart?.metadata?.source_part_id ?? null,
        brush_mask_artifact_id: brushMaskArtifact?.artifact_id ?? null,
      },
      {
        intent_text: intentText,
        part_source: brushPart?.metadata?.source ?? null,
        source_part_id: brushPart?.metadata?.source_part_id ?? null,
        part_face_count: brushPart?.metadata?.face_count ?? null,
        mask_url: brushMaskUrl,
        brush_mask_url: brushMaskArtifact?.url ?? null,
        brush_mask_artifact_id: brushMaskArtifact?.artifact_id ?? null,
        brush_coverage: brushMaskPayload.metrics.coverage,
        brush_projection: brushMaskPayload.projection,
        viewport_screenshot_url: screenshotUrl,
        tool_surface: "3d",
        live_signals: nextLiveSignals,
      },
    );
    return brushMaskArtifact;
  };

  const sendDrag = async (response?: GeometryWorkerResponse | null) => {
    if (!asset) return null;
    const screenshotPromise = captureAndUploadViewport(threeViewportRef.current, {
      sessionId: session?.session_id ?? "",
      assetId: asset.asset_id,
      partId: selectedPart || null,
      metadata: { trigger: "drag_end", tool_surface: "3d" },
    });
    const dragOperationPayload = buildDragOperationPayload({
      sessionId: session?.session_id ?? "",
      asset,
      part: activeSelectedPart,
      partId: selectedPart || null,
      text: intentText,
      response,
    });
    let dragOperationArtifact: ArtifactRecord | null = null;
    try {
      dragOperationArtifact = await api<ArtifactRecord>("/api/v1/drag-operations", {
        method: "POST",
        body: JSON.stringify(dragOperationPayload),
      });
    } catch (error) {
      addLog("drag artifact", String(error).slice(0, 160));
    }
    const screenshotArtifact = await screenshotPromise;
    const screenshotUrl = screenshotArtifact?.url ?? null;
    sendEvent("drag_end", {
      asset_id: asset.asset_id,
      part_id: selectedPart,
      selected_part_label: activeSelectedPart?.label ?? null,
      intent_text: intentText,
      viewport_screenshot_url: screenshotUrl,
      viewport_screenshot_artifact_id: screenshotArtifact?.artifact_id ?? null,
      drag_operation_artifact_id: dragOperationArtifact?.artifact_id ?? null,
      drag_operation_url: dragOperationArtifact?.url ?? null,
      drag_preview_mesh_url: response?.preview_mesh_url ?? null,
      drag_geometry_job_id: response?.job_id ?? null,
      drag: dragOperationPayload.drag,
      region: dragOperationPayload.region,
    });
    recordActionAtom(
      "drag",
      {
        asset_id: asset.asset_id,
        part_id: selectedPart || null,
        label: activeSelectedPart?.label ?? null,
        drag_operation_artifact_id: dragOperationArtifact?.artifact_id ?? null,
      },
      {
        ...dragOperationPayload.drag,
        drag_operation_url: dragOperationArtifact?.url ?? null,
        drag_operation_artifact_id: dragOperationArtifact?.artifact_id ?? null,
        preview_mesh_url: response?.preview_mesh_url ?? null,
        geometry_job_id: response?.job_id ?? null,
        viewport_screenshot_url: screenshotUrl,
        viewport_screenshot_artifact_id: screenshotArtifact?.artifact_id ?? null,
        metrics: dragOperationPayload.metrics,
      },
    );
    return dragOperationArtifact;
  };

  const commitHoverFocus = async (reason: "toolbar_click" | "dwell_end" = "toolbar_click") => {
    if (!asset) return;
    const partLabel = hoverLabelRef.current ?? activeSelectedPart?.label ?? null;
    const partId = selectedPart || null;
    if (!partLabel && !partId) {
      addLog("hover", "no tentative part yet — keep hovering a mesh region");
      return;
    }
    if (hoverCommittedRef.current === partLabel && reason === "dwell_end") return;
    hoverCommittedRef.current = partLabel;

    const focusPayload = buildFocusObservationPayload({
      sessionId: session?.session_id ?? "",
      asset,
      partId,
      partLabel,
      displayMode: canvasDisplayMode,
      focusSource: reason === "dwell_end" ? "hover_dwell_end" : "toolbar_hover_commit",
    });
    let focusArtifact: ArtifactRecord | null = null;
    try {
      focusArtifact = await api<ArtifactRecord>("/api/v1/focus-observations", {
        method: "POST",
        body: JSON.stringify(focusPayload),
      });
    } catch (error) {
      addLog("focus artifact", String(error).slice(0, 160));
    }
    const nextLiveSignals = {
      ...liveSignals,
      dwell_ms: Math.max(liveSignals.dwell_ms, focusPayload.metrics.dwell_ms),
      hover_count: liveSignals.hover_count + (reason === "toolbar_click" ? 1 : 0),
    };
    setLiveSignals(nextLiveSignals);
    void putLiveSignals(nextLiveSignals);
    const partLifecycle =
      activeSelectedPart?.lifecycle ||
      (typeof activeSelectedPart?.metadata?.lifecycle === "string"
        ? activeSelectedPart.metadata.lifecycle
        : activeSelectedPart?.metadata?.source === "obj_group_fallback"
          ? "obj_group_fallback"
          : "tentative_raycast");
    recordActionAtom(
      "hover",
      {
        asset_id: asset.asset_id,
        part_id: partId,
        label: partLabel,
        lifecycle: partLifecycle,
        focus_observation_artifact_id: focusArtifact?.artifact_id ?? null,
      },
      {
        viewport: canvasDisplayMode,
        focus_source: focusPayload.observation.focus_source,
        part_lifecycle: partLifecycle,
        semantic_source:
          partLifecycle === "obj_group_fallback"
            ? "obj_group_projected_hover"
            : partLifecycle === "segmented_3d"
              ? "segmented_3d_hover"
              : "projected_hover_tentative",
        interaction_mode: "projected_semantic_hover",
        focus_observation_url: focusArtifact?.url ?? null,
        focus_observation_artifact_id: focusArtifact?.artifact_id ?? null,
        dwell_ms: focusPayload.metrics.dwell_ms,
        live_signals: nextLiveSignals,
      },
    );
    sendEvent("hover_focus", {
      asset_id: asset.asset_id,
      part_id: partId,
      selected_part_label: partLabel,
      focus_observation_artifact_id: focusArtifact?.artifact_id ?? null,
      focus_observation_url: focusArtifact?.url ?? null,
      focus_source: focusPayload.observation.focus_source,
      dwell_ms: focusPayload.metrics.dwell_ms,
      live_signals: nextLiveSignals,
    });
    setLivePerception({
      summary: `User focused on ${partLabel ?? "part"}.`,
      evidence: [`Hover committed · ${reason.replace("_", " ")}`],
      confidence: focusPayload.metrics.confidence,
      source: "local",
      updatedAt: new Date().toISOString(),
    });
    addLog("hover", focusArtifact?.artifact_id ?? partLabel ?? asset.label);
    if (activeSelectedPart) {
      void requestViewportSamForHover(activeSelectedPart, threeViewportRef.current?.getLastPointer?.() ?? null);
    }
  };

  const toggleAddMenu = () => {
    if (!addMenuOpen) {
      if (sculptBehaviorRef.current) void cancelSculptBehavior();
      setSculptTool(null);
      setAnnotationMode(false);
      deactivateHoverMode();
    }
    setAddMenuOpen((v) => !v);
  };

  const toggleAnnotationMode = () => {
    if (annotationMode) {
      if (sculptBehaviorRef.current?.tool === "annotation") {
        void cancelSculptBehavior();
      }
      setAnnotationMode(false);
      return;
    }
    if (sculptBehaviorRef.current) void cancelSculptBehavior();
    setSculptTool(null);
    setAddMenuOpen(false);
    deactivateHoverMode();
    sculptBehaviorRef.current = beginSculptBehavior("annotation", {});
    setAnnotationMode(true);
  };

  const deactivateHoverMode = () => {
    setHoverMode((currentHoverMode) => {
      if (!currentHoverMode) return currentHoverMode;
      setHoverMaskDataUrl(null);
      if (hoverLabelRef.current || activeSelectedPart) {
        void commitHoverFocus("toolbar_click");
      } else {
        setHoverLabel(null);
        hoverLabelRef.current = null;
        hoverCommittedRef.current = null;
        addLog("hover", "mode off");
      }
      return false;
    });
  };

  const toggleHoverMode = () => {
    if (!asset) return;
    if (!hoverMode) {
      if (sculptBehaviorRef.current) void cancelSculptBehavior();
      setSculptTool(null);
      setAnnotationMode(false);
      setAddMenuOpen(false);

      setHoverMode(true);
      setHoverMaskDataUrl(null);
      incrementLiveSignal("tool_switch_count");
      addLog("hover", "mode on — raycast tentative labels; click again or dwell to commit");
      return;
    }
    deactivateHoverMode();
  };

  const recordAnnotation = async (
    strokes?: AnnotationStroke[],
    brushStrokes?: Array<{ brush: string; points: AnnotationStroke }>,
  ) => {
    if (!asset) return;
    const annotationPayload = buildAnnotationPayload({
      sessionId: session?.session_id ?? "",
      asset,
      partId: selectedPart || null,
      partLabel: activeSelectedPart?.label ?? null,
      text: intentText,
      displayMode: canvasDisplayMode,
      strokes,
      brushStrokes,
    });
    const inferredShape = String(annotationPayload.metadata.inferred_shape || "freehand_contour");
    const nextLiveSignals = {
      ...liveSignals,
      drawing_content: intentText.trim() || inferredShape,
      annotation_count: liveSignals.annotation_count + 1,
    };
    setLiveSignals(nextLiveSignals);
    setLivePerception({
      summary: "User is drawing on the silhouette.",
      evidence: [
        `${annotationPayload.strokes.length} 2D pencil stroke${annotationPayload.strokes.length > 1 ? "s" : ""}`,
        String(annotationPayload.metadata.inferred_shape ?? inferredShape),
      ],
      confidence: 0.82,
      source: "local",
      updatedAt: new Date().toISOString(),
    });
    setCreativeStagePreset("silhouette");
    if (!sculptBehaviorRef.current || sculptBehaviorRef.current.tool !== "annotation") {
      sculptBehaviorRef.current = beginSculptBehavior("annotation", {});
    }
    const annotationSession = sculptBehaviorRef.current;
    annotationSession.strokeCount += annotationPayload.strokes.length;
    annotationSession.evidence = {
      ...annotationSession.evidence,
      annotation_mode: brushStrokes?.length ? "2d_brush" : "2d_pencil",
      text: intentText,
      annotation_shape: inferredShape,
      inferred_shape: inferredShape,
      brush_count: (Number(annotationSession.evidence.brush_count) || 0) + (brushStrokes?.length ?? 0),
      brush_kinds: [...new Set([
        ...((annotationSession.evidence.brush_kinds as string[] | undefined) ?? []),
        ...(brushStrokes?.map((stroke) => stroke.brush) ?? []),
      ])],
      brush_summary: annotationPayload.metadata.brush_summary ?? annotationSession.evidence.brush_summary ?? null,
      stroke_count: annotationSession.strokeCount,
      projection: annotationPayload.projection,
      live_signals: nextLiveSignals,
    };
    const reserved = await annotationSession.reservation.catch(() => null);
    const behaviorId = reserved?.behavior_id ?? annotationSession.localBehaviorId;
    setBehaviorSessions((current) =>
      current.map((item) =>
        item.behavior_id === annotationSession.localBehaviorId || item.behavior_id === behaviorId
          ? {
              ...item,
              stroke_count: annotationSession.strokeCount,
              operation_summary: annotationSession.evidence,
            }
          : item,
      ),
    );
    sendEvent("annotation_commit", {
      asset_id: asset.asset_id,
      part_id: selectedPart || null,
      annotation_text: intentText,
      annotation_shape: inferredShape,
      brush_count: brushStrokes?.length ?? 0,
      brush_kinds: [...new Set(brushStrokes?.map((stroke) => stroke.brush) ?? [])],
      stroke_count: annotationPayload.strokes.length,
      stroke_point_count: annotationPayload.strokes.reduce((sum, stroke) => sum + (stroke.points?.length ?? 0), 0),
      projection: annotationPayload.projection,
      live_signals: nextLiveSignals,
    });
    addLog("annotation", intentText || "2D mark");

    // Upload screenshot as soon as the behavior exists; persist on the behavior.
    // If the user deletes the behavior, backend cancels and purges these files.
    if (behaviorId && session) {
      void (async () => {
        try {
          const screenshotPromise = captureAndUploadViewport(threeViewportRef.current, {
            sessionId: session.session_id,
            assetId: asset.asset_id,
            partId: selectedPart || null,
            metadata: {
              trigger: "annotation_behavior",
              behavior_id: behaviorId,
              stroke_count: strokes?.length ?? 0,
              brush_count: brushStrokes?.length ?? 0,
            },
          });
          const scribbleMaskPromise = brushStrokes?.length
            ? (async () => {
                const dataUrl = threeViewportRef.current?.captureJpeg?.(640, 0.7) ?? null;
                if (!dataUrl) return null;
                const sampled = brushStrokes
                  .flatMap((stroke) => stroke.points)
                  .filter((point, index, all) => index % Math.max(1, Math.floor(all.length / 24)) === 0)
                  .slice(0, 8)
                  .map((point) => ({ x: point.x, y: point.y, label: 1 as const }));
                if (!sampled.length) return null;
                const { segmentPoints } = await import("../utils/segmenter");
                return segmentPoints(dataUrl, sampled);
              })().catch(() => null)
            : Promise.resolve(null);
          let annotationArtifact: ArtifactRecord | null = null;
          try {
            annotationArtifact = await api<ArtifactRecord>("/api/v1/annotations", {
              method: "POST",
              body: JSON.stringify(annotationPayload),
            });
          } catch (error) {
            addLog("annotation artifact", String(error).slice(0, 160));
          }
          const screenshotArtifact = await screenshotPromise.catch(() => null);
          const scribbleMask = await scribbleMaskPromise;
          if (!annotationArtifact && !screenshotArtifact && !scribbleMask) return;
          const operationSummary = {
            stroke_url: annotationArtifact?.url ?? null,
            annotation_artifact_id: annotationArtifact?.artifact_id ?? null,
            scribble_mask_data_url: scribbleMask?.maskDataUrl ?? null,
            scribble_mask_coverage: scribbleMask?.coverage ?? null,
            viewport_screenshot_url: screenshotArtifact?.url ?? null,
            viewport_screenshot_artifact_id: screenshotArtifact?.artifact_id ?? null,
          };
          setBehaviorSessions((current) => {
            if (!current.some((item) => item.behavior_id === behaviorId)) return current;
            return current.map((item) =>
              item.behavior_id === behaviorId
                ? {
                    ...item,
                    operation_summary: {
                      ...item.operation_summary,
                      ...operationSummary,
                    },
                    evidence_refs: [
                      ...item.evidence_refs,
                      ...(screenshotArtifact?.url ? [screenshotArtifact.url] : []),
                      ...(annotationArtifact?.url ? [annotationArtifact.url] : []),
                    ].filter((value, index, all) => all.indexOf(value) === index),
                  }
                : item,
            );
          });
          try {
            let patched: BehaviorSession | null = null;
            for (let attempt = 0; attempt < 6; attempt += 1) {
              try {
                patched = await api<BehaviorSession>(
                  `/api/v1/sessions/${session.session_id}/behaviors/${behaviorId}`,
                  {
                    method: "PATCH",
                    body: JSON.stringify({
                      operation_summary: operationSummary,
                      evidence_refs: [
                        ...(screenshotArtifact?.url ? [screenshotArtifact.url] : []),
                        ...(annotationArtifact?.url ? [annotationArtifact.url] : []),
                      ],
                    }),
                  },
                );
                break;
              } catch (error) {
                if (attempt >= 5) throw error;
                await new Promise((resolve) => window.setTimeout(resolve, 200));
              }
            }
            if (patched) {
              setBehaviorSessions((current) => {
                if (!current.some((item) => item.behavior_id === behaviorId)) return current;
                return current.map((item) =>
                  item.behavior_id === patched.behavior_id ? patched : item,
                );
              });
            }
          } catch (error) {
            // Gone / deleted while upload ran — leave local rail as-is.
            addLog("annotation patch", String(error).slice(0, 120));
          }
        } catch (error) {
          addLog("annotation enrich", String(error).slice(0, 120));
        }
      })();
    }
  };

  const recordAddPrimitive = async (
    primitiveOverride?: Exclude<CanvasPrimitive, null>,
    response?: GeometryWorkerResponse | null,
    screenshotEvidence: Record<string, unknown> = {},
  ) => {
    const primitive = primitiveOverride ?? canvasPrimitive ?? "sphere";
    if (!asset && !primitiveOverride && !canvasPrimitive) return;
    const transform = threeViewportRef.current?.getPrimitiveTransform?.() ?? null;
    const primitivePayload = buildPrimitiveAdditionPayload({
      sessionId: session?.session_id ?? "",
      asset,
      partId: selectedPart || null,
      partLabel: activeSelectedPart?.label ?? null,
      primitive,
      text: intentText,
      transform,
    });
    let primitiveArtifact: ArtifactRecord | null = null;
    try {
      primitiveArtifact = await api<ArtifactRecord>("/api/v1/primitive-additions", {
        method: "POST",
        body: JSON.stringify(primitivePayload),
      });
    } catch (error) {
      addLog("primitive artifact", String(error).slice(0, 160));
    }
    recordActionAtom(
      "add",
      {
        asset_id: asset?.asset_id ?? null,
        part_id: selectedPart || null,
        primitive,
        primitive_addition_artifact_id: primitiveArtifact?.artifact_id ?? null,
      },
      {
        primitive_addition_url: primitiveArtifact?.url ?? null,
        primitive_addition_artifact_id: primitiveArtifact?.artifact_id ?? null,
        geometry_job_id: response?.job_id ?? null,
        preview_mesh_url: response?.preview_mesh_url ?? null,
        result_mesh_url: response?.result_mesh_url ?? null,
        blender_script_url:
          response?.artifacts && typeof response.artifacts.blender_script_url === "string"
            ? response.artifacts.blender_script_url
            : null,
        transform: primitivePayload.transform,
        relation: primitivePayload.relation,
        constraints: primitivePayload.constraints,
        ...screenshotEvidence,
      },
    );
    sendEvent("primitive_add_intent", {
      asset_id: asset?.asset_id ?? null,
      part_id: selectedPart || null,
      primitive,
      primitive_addition_artifact_id: primitiveArtifact?.artifact_id ?? null,
      primitive_addition_url: primitiveArtifact?.url ?? null,
      primitive_preview_mesh_url: response?.preview_mesh_url ?? null,
      primitive_geometry_job_id: response?.job_id ?? null,
      primitive_transform: primitivePayload.transform,
      primitive_relation: primitivePayload.relation,
      primitive_constraints: primitivePayload.constraints,
      intent_text: intentText,
      viewport_screenshot_url: screenshotEvidence.viewport_screenshot_url ?? null,
      viewport_screenshot_artifact_id: screenshotEvidence.viewport_screenshot_artifact_id ?? null,
    });
    addLog("add", primitiveArtifact?.artifact_id ?? `${primitive} intent`);
  };

  const createPrimitive = async (primitive: Exclude<CanvasPrimitive, null>) => {
    incrementLiveSignal("new_case_attempt_rate");
    incrementLiveSignal("tool_switch_count");
    const graph = versionGraphRef.current;
    const targetId = graph.active_node_id;
    const target = targetId ? graph.nodes.find((item) => item.node_id === targetId) : undefined;
    const targetCandidate = target?.candidate_id
      ? allCandidates.find((item) => item.candidate_id === target.candidate_id) ?? null
      : null;
    const targetHasMesh = Boolean(
      target?.mesh_url || target?.obj_url || asset?.mesh_url || asset?.obj_url,
    );
    if (targetId && versionViewModeRef.current === "overview") {
      setActiveVersionId(targetId);
      setVersionViewMode("active");
      applyVersionGraph({ ...graph, active_node_id: targetId });
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          setCanvasPan(centeredActiveCanvasPan(versionCanvasShellRef.current));
        });
      });
      if (targetCandidate) {
        setSelectedCandidateId(targetCandidate.candidate_id);
      }
    }
    setCanvasPrimitive(primitive);
    setPrimitiveLocked(false);
    if (!targetHasMesh) {
      setAsset(null);
      setParts([]);
      setSelectedPart("");
      setCandidates([]);
      setPreviewCandidate(null);
      setCanvasPreview(null);
    }
    handleDisplayModeChange("clay");
    setCanvasTool("clay");
    if (primitiveBehaviorRef.current) {
       // if there is an existing one, clear it
       setBehaviorSessions((current) => current.filter(item => item.behavior_id !== primitiveBehaviorRef.current!.localBehaviorId));
    }
    primitiveBehaviorRef.current = beginPrimitiveBehavior(primitive);
    addLog("primitive", primitive);
  };

  const persistDivergenceSelection = (next: PromptToken[], excludedInherited: string[]) => {
    const revisionId = activeRevisionIdRef.current;
    const revision = intentRevisionsRef.current.find((item) => item.revision_id === revisionId);
    if (!revisionId || !revision) return;
    const tracker = selectionPersistenceByRevisionRef.current.get(revisionId) ?? {
      sequence: 0,
      chain: Promise.resolve(true),
      latest: Promise.resolve(true),
      pending: false,
      error: null,
      expectedVersion: revision.version,
      expectedSelectionVersion: revision.selection_version,
    };
    tracker.expectedVersion = revision.version;
    tracker.expectedSelectionVersion = revision.selection_version;
    selectionPersistenceByRevisionRef.current.set(revisionId, tracker);
    const selectionSequence = ++tracker.sequence;
    tracker.pending = true;
    tracker.error = null;
    setSelectionPersistenceErrors((current) => {
      const nextErrors = { ...current };
      delete nextErrors[revisionId];
      return nextErrors;
    });
    const payload = {
      scope: revision.gate_scope ?? "whole",
      target_part_id: revision.source_context.target_part_id ?? (selectedPart || null),
      selected_candidate_ids: next.flatMap((item) => item.candidate_id ? [item.candidate_id] : []),
      selected_keywords: next.map((item) => item.label),
      user_text: revision.user_text || null,
      system_keywords: revision.divergence_selection?.system_keywords ?? [],
      excluded_inherited_keywords: excludedInherited,
    };
    const isVersionConflict = (error: unknown) => {
      const text = String(error);
      return (
        text.includes("409") ||
        text.includes("expected revision version") ||
        text.includes("expected selection version")
      );
    };
    const persistence = tracker.chain
      .catch(() => false)
      .then(async () => {
        if (!interactionCoordinator) {
          throw new Error("interaction coordinator unavailable");
        }
        const latest =
          intentRevisionsRef.current.find((item) => item.revision_id === revisionId) ?? revision;
        tracker.expectedVersion = latest.version;
        tracker.expectedSelectionVersion = latest.selection_version;
        const commandId = `selection_${revisionId}_${selectionSequence}_${crypto.randomUUID()}`;
        const saveOnce = (rev: IntentRevision) =>
          interactionCoordinator.saveSelection(
            rev,
            {
              ...payload,
              expected_version: rev.version,
              expected_selection_version: rev.selection_version,
            },
            {
              command_id: commandId,
              idempotency_key: `selection:${revisionId}:${selectionSequence}`,
            },
          );
        let updated: IntentRevision;
        try {
          updated = await saveOnce(latest);
        } catch (error) {
          if (!isVersionConflict(error) || !session?.session_id) throw error;
          const projection = await api<{ revisions: IntentRevision[] }>(
            `/api/v1/sessions/${session.session_id}/interaction-projection`,
          );
          const fresh = projection.revisions.find((item) => item.revision_id === revisionId);
          if (!fresh) throw error;
          setIntentRevisions((current) =>
            current.map((item) => (item.revision_id === revisionId ? { ...item, ...fresh } : item)),
          );
          updated = await saveOnce(fresh);
        }
        tracker.expectedVersion = updated.version;
        tracker.expectedSelectionVersion = updated.selection_version;
        if (tracker.sequence === selectionSequence) {
          tracker.pending = false;
          setIntentRevisions((current) =>
            current.map((item) => (item.revision_id === revisionId ? updated : item)),
          );
          tracker.error = null;
          setSelectionPersistenceErrors((current) => {
            const nextErrors = { ...current };
            delete nextErrors[revisionId];
            return nextErrors;
          });
        }
        return true;
      })
      .catch((error) => {
        if (tracker.sequence === selectionSequence) {
          tracker.pending = false;
          const message = "关键词保存失败，请重新选择后再生成";
          tracker.error = message;
          setSelectionPersistenceErrors((current) => ({ ...current, [revisionId]: message }));
          addLog("keywords", `${message}: ${String(error).slice(0, 80)}`);
        }
        return false;
      });
    tracker.chain = persistence;
    tracker.latest = persistence;
  };

  const togglePromptToken = (token: PromptToken) => {
    pushEditorHistory(`toggle ${token.label}`);
    const key = promptTokenKey(token);
    const currentTokens = selectedPromptTokensRef.current;
    const exists = currentTokens.some((item) => promptTokenKey(item) === key);
    const next = exists
      ? currentTokens.filter((item) => promptTokenKey(item) !== key)
      : [...currentTokens, token];
    selectedPromptTokensRef.current = next;
    setSelectedPromptTokens(next);
    void projectRecorder.record(
      "divergence.selection_changed",
      { token_id: token.token_id, selected: !exists, selected_token_ids: next.map((item) => item.token_id) },
      `divergence-selection:${activeRevisionIdRef.current ?? "none"}:${crypto.randomUUID()}`,
    );
    updateLiveSignals({ semantic_distance: Math.min(1, next.length / 6) });
    persistDivergenceSelection(next, excludedInheritedKeywordsRef.current);
  };

  const dismissInheritedKeyword = (keyword: string) => {
    const nextExcluded = [...new Set([...excludedInheritedKeywordsRef.current, keyword])];
    excludedInheritedKeywordsRef.current = nextExcluded;
    setExcludedInheritedKeywords(nextExcluded);
    persistDivergenceSelection(selectedPromptTokensRef.current, nextExcluded);
  };

  const discoverPartsForAsset = async (
    targetAsset: AssetRecord,
    trigger: "manual" | "upload" | "brush" | "hy3d",
  ): Promise<PartDiscoveryResponse | null> => {
    if (!session) return null;
    const sourceSeq = sourceSwitchSeqRef.current;
    setDiscoveringParts(true);
    try {
      const response = await api<PartDiscoveryResponse>("/api/v1/parts/discover", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: targetAsset.asset_id,
          mode: "mesh",
          prompt: "discover editable semantic parts for interactive design",
          metadata: {
            partfield_real: true,
            granularity: "medium",
            max_parts: 8,
            ...(trigger === "hy3d"
              ? { sam3d_real: true, segmentation_real: true, wait_timeout_sec: 120 }
              : {}),
          },
        }),
      });
      if (sourceSeq !== sourceSwitchSeqRef.current) return null;
      setPartDiscovery(response);
      setParts(response.parts);
      setAsset((current) => (current && current.asset_id === targetAsset.asset_id
        ? { ...current, parts: response.parts }
        : current));
      if (response.parts.length) setSelectedPart(response.parts[0].part_id);
      addLog(
        "parts",
        `${trigger !== "manual" ? "auto " : ""}${response.parts.length} parts via ${partDiscoveryAdapter(response)}`,
      );
      if (trigger !== "manual" && response.parts.length) setCreativeStagePreset("part");
      return response;
    } catch (error) {
      addLog("parts", String(error));
      return null;
    } finally {
      if (sourceSeq === sourceSwitchSeqRef.current) setDiscoveringParts(false);
    }
  };

  const discoverParts = async () => {
    if (!asset) return;
    await discoverPartsForAsset(asset, "manual");
  };

  const renameSelectedPart = async () => {
    if (!asset || !activeSelectedPart) return;
    const nextLabel = partLabelDraft.trim();
    if (!nextLabel || nextLabel === activeSelectedPart.label) return;
    const updated = await api<PartRecord>(
      `/api/v1/assets/${asset.asset_id}/parts/${activeSelectedPart.part_id}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          label: nextLabel,
          metadata: {
            user_labeled: true,
            previous_label: activeSelectedPart.label,
          },
        }),
      },
    );
    setParts((current) =>
      current.map((part) => (part.part_id === updated.part_id ? updated : part)),
    );
    setAsset((current) =>
      current
        ? {
            ...current,
            parts: current.parts.map((part) => (part.part_id === updated.part_id ? updated : part)),
          }
        : current,
    );
    addLog("part label", `${updated.part_id}: ${updated.label}`);
  };

  const uploadAsset = async (file: File | undefined) => {
    if (!session || !file) return;
    if (!confirmProjectSwitch()) return;
    const sourceSeq = resetSourceDependentState("Uploading selected model…");
    setSelectedBenchmarkId("");
    setUploading(true);
    try {
      const form = new FormData();
      form.set("session_id", session.session_id);
      form.set("object_type", inferObjectType(file.name));
      form.set("label", file.name.replace(/\.[^.]+$/, ""));
      form.set("metadata", JSON.stringify({ source: "local_upload" }));
      form.set("file", file);
      const response = await fetch(`${API_BASE}/api/v1/assets/upload`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(await response.text());
      const uploaded = (await response.json()) as AssetRecord;
      void projectRecorder.record(
        "input.asset_uploaded",
        { asset_id: uploaded.asset_id, filename: file.name },
        `asset-upload:${uploaded.asset_id}`,
      );
      if (sourceSeq !== sourceSwitchSeqRef.current) return;
      setAsset(uploaded);
      setParts(uploaded.parts);
      setSelectedPart(uploaded.parts[0]?.part_id ?? "");
      setLivePerception({
        summary: `Loaded ${uploaded.label}.`,
        evidence: ["source uploaded from local file"],
        confidence: null,
        source: "local",
        updatedAt: new Date().toISOString(),
      });
      addLog("upload", uploaded.asset_id);
      if (autoDiscoverParts && isDiscoverableMeshFile(file.name)) {
        void discoverPartsForAsset(uploaded, "upload");
      }
    } catch (error) {
      addLog("upload", String(error));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const uploadReferenceImage = async (file: File | undefined) => {
    if (!session || !file) return;
    pushEditorHistory("attach reference image");
    setUploading(true);
    try {
      const form = new FormData();
      form.set("session_id", session.session_id);
      if (asset?.asset_id) form.set("asset_id", asset.asset_id);
      form.set("role", "shape_reference");
      form.set(
        "metadata",
        JSON.stringify({
          source: "intent_composer",
          object_type: asset?.object_type ?? null,
        }),
      );
      form.set("file", file);
      const response = await fetch(`${API_BASE}/api/v1/reference-images/upload`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(await response.text());
      const artifact = (await response.json()) as ArtifactRecord;
      void projectRecorder.record(
        "input.reference_added",
        { artifact_id: artifact.artifact_id, kind: "image", filename: file.name },
        `reference:${artifact.artifact_id}`,
      );
      setReferenceImages((current) => upsertArtifact(current, artifact));
      incrementLiveSignal("reference_match_count");
      recordActionAtom(
        "image",
        { asset_id: asset?.asset_id ?? null, artifact_id: artifact.artifact_id, role: "shape_reference" },
        { image_url: artifact.url, filename: file.name, source: "reference_image_upload" },
      );
      addLog("reference image", artifact.artifact_id);
    } catch (error) {
      addLog("reference image", String(error));
    } finally {
      setUploading(false);
      if (referenceImageInputRef.current) referenceImageInputRef.current.value = "";
    }
  };

  const uploadReferenceModel = async (file: File | undefined) => {
    if (!session || !file) return;
    pushEditorHistory("attach reference model");
    setUploading(true);
    try {
      const form = new FormData();
      form.set("session_id", session.session_id);
      if (asset?.asset_id) form.set("asset_id", asset.asset_id);
      form.set("role", "model_reference");
      form.set(
        "metadata",
        JSON.stringify({
          source: "intent_composer",
          object_type: asset?.object_type ?? null,
          intent_role: "reference_model_not_active_asset",
        }),
      );
      form.set("file", file);
      const response = await fetch(`${API_BASE}/api/v1/reference-models/upload`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) throw new Error(await response.text());
      const artifact = (await response.json()) as ArtifactRecord;
      void projectRecorder.record(
        "input.reference_added",
        { artifact_id: artifact.artifact_id, kind: "model", filename: file.name },
        `reference:${artifact.artifact_id}`,
      );
      setReferenceModels((current) => upsertArtifact(current, artifact));
      incrementLiveSignal("reference_match_count");
      recordActionAtom(
        "model",
        { asset_id: asset?.asset_id ?? null, artifact_id: artifact.artifact_id, role: "model_reference" },
        { model_url: artifact.url, filename: file.name, source: "reference_model_upload" },
      );
      addLog("reference model", artifact.artifact_id);
    } catch (error) {
      addLog("reference model", String(error));
    } finally {
      setUploading(false);
      if (referenceModelInputRef.current) referenceModelInputRef.current.value = "";
    }
  };

  const refreshJob = async (jobId = job?.job_id, sourceSeq = sourceSwitchSeqRef.current) => {
    if (!jobId) return;
    try {
      const nextJob = await api<JobRecord>(`/api/v1/jobs/${jobId}`);
      if (sourceSeq !== sourceSwitchSeqRef.current) return;
      setJob(nextJob);
      if (nextJob.candidate_ids?.length) {
        setSolutionSpaceGenerating(false);
        await loadCandidates(nextJob.candidate_ids, nextJob.job_id, sourceSeq);
      }
    } catch (error) {
      addLog("job refresh", String(error));
    }
  };

  const cancelJob = async () => {
    if (!job?.job_id || !isActiveJobStatus(job.status)) return;
    try {
      const nextJob = await api<JobRecord>(`/api/v1/jobs/${job.job_id}/cancel`, {
        method: "POST",
      });
      setJob(nextJob);
      addLog("job cancel", nextJob.job_id);
    } catch (error) {
      addLog("job cancel", String(error));
    }
  };

  const loadCandidates = async (ids: string[], jobId = job?.job_id, sourceSeq = sourceSwitchSeqRef.current) => {
    const loaded = await loadJobCandidates(ids, jobId);
    if (sourceSeq !== sourceSwitchSeqRef.current) return;
    const ranked = rankCandidates(loaded);
    setCandidates(ranked);
    const accepted = loaded
      .filter((candidate) => candidate.decision === "accepted")
      .map((candidate) => candidate.candidate_id);
    if (accepted.length) {
      setAcceptedCandidateIds((current) => Array.from(new Set([...current, ...accepted])));
    }
    setPreviewCandidate((current) => {
      if (current && ranked.some((candidate) => candidate.candidate_id === current.candidate_id)) {
        return ranked.find((candidate) => candidate.candidate_id === current.candidate_id) ?? current;
      }
      return ranked.find((candidate) => candidate.mesh_url || candidate.obj_url) ?? null;
    });
  };

  const loadJobCandidates = async (ids: string[], jobId?: string) => {
    if (jobId) {
      try {
        const loaded = await api<Candidate[]>(`/api/v1/jobs/${jobId}/candidates`);
        if (loaded.length) return loaded;
      } catch {
        addLog("candidates", "job candidate list unavailable");
      }
    }
    return Promise.all(ids.map((id) => api<Candidate>(`/api/v1/candidates/${id}`)));
  };

  const previewCandidateForComparison = async (candidate: Candidate) => {
    pushEditorHistory(`preview ${candidate.label}`);
    updateLiveSignals((current) => ({
      compare_dwell_ms: Math.max(current.compare_dwell_ms, 2000),
      semantic_distance: Math.min(1, Math.max(current.semantic_distance, 0.45)),
    }));
    setPreviewCandidate(candidate);
    setCanvasPreview(null);
    if (session) {
      try {
        await api<Candidate>(`/api/v1/candidates/${candidate.candidate_id}/preview`, {
          method: "POST",
          body: JSON.stringify({
            session_id: session.session_id,
            reason: "temporary comparison preview",
            make_active_asset: false,
          }),
        });
      } catch (error) {
        addLog("candidate preview", String(error).slice(0, 160));
      }
    }
    sendEvent("candidate_compared", {
      asset_id: candidate.source_asset_id,
      candidate_id: candidate.candidate_id,
      candidate_label: candidate.label,
      candidate_thumbnail_url: candidatePreviewUrl(candidate),
      mesh_url: candidate.mesh_url,
      obj_url: candidate.obj_url,
      scores: candidate.scores,
      creative_stage: candidateStage(candidate),
      fidelity: candidateFidelity(candidate),
      pipeline_evidence: pipelineEvidence(candidate),
      selection: {
        type: candidate.metadata.stage === "part" ? "part" : "none",
        part_id: candidate.source_part_id ?? selectedPart,
        label: activeSelectedPart?.label ?? candidate.source_part_id ?? selectedPart,
      },
    });
    if (session) {
      void trackBehaviorCommit(api<BehaviorSession>(`/api/v1/sessions/${session.session_id}/behaviors`, {
        method: "POST",
        body: JSON.stringify({
          tool: "compare",
          target: {
            asset_id: candidate.source_asset_id,
            part_id: (candidate.source_part_id ?? selectedPart) || null,
          },
          stroke_count: 0,
          operation_summary: {
            event_type: "candidate_compared",
            candidate_id: candidate.candidate_id,
            live_signals: {
              ...liveSignals,
              compare_dwell_ms: Math.max(liveSignals.compare_dwell_ms, 2000),
            },
          },
        }),
      }));
    }
  };

  const decideCandidate = async (
    candidate: Candidate,
    decision: "accept" | "reject",
    makeActiveAsset = false,
  ) => {
    if (!session) return;
    // Four-stage Solution Space cards are observation artifacts, not
    // /api/v1/candidates records — accept locally and let drag create versions.
    if (candidate.metadata?.four_stage_artifact) {
      if (decision === "reject") {
        setAcceptedCandidateIds((current) =>
          current.filter((id) => id !== candidate.candidate_id),
        );
        setSelectedCandidateId((current) =>
          current === candidate.candidate_id ? null : current,
        );
        return;
      }
      setSelectedCandidateId(candidate.candidate_id);
      setAcceptedCandidateIds((current) => Array.from(new Set([...current, candidate.candidate_id])));
      return;
    }
    try {
      await projectRecorder.record(
        decision === "accept" ? "candidate.accepted" : "candidate.rejected",
        { candidate_id: candidate.candidate_id, make_active_asset: makeActiveAsset },
        `candidate-decision:${candidate.candidate_id}:${decision}`,
        { critical: true },
      );
    } catch {
      // Recording is best-effort; don't block the candidate decision click.
    }
    const commitAsAsset = decision === "accept" && makeActiveAsset && Boolean(candidate.mesh_url || candidate.obj_url);
    const body = {
      session_id: session.session_id,
      reason: commitAsAsset
        ? "commit selected 3D candidate as the next active asset"
        : decision === "accept"
          ? "accept direction as creative memory"
          : "not aligned enough",
      make_active_asset: commitAsAsset,
    };
    const endpoint = commitAsAsset ? "commit" : decision;
    const response = await api<CandidateDecisionResponse>(`/api/v1/candidates/${candidate.candidate_id}/${endpoint}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setStage(response.updated_stage);
    if (decision === "accept") {
      setAcceptedCandidateIds((current) => Array.from(new Set([...current, candidate.candidate_id])));
    }
    void refreshSession();
    if (decision === "accept" && response.active_asset_id) {
      const nextAsset = await api<AssetRecord>(`/api/v1/assets/${response.active_asset_id}`);
      setCanvasPrimitive(null);
      setCanvasDisplayMode("textured");
      setCanvasTool("select");
      setAsset(nextAsset);
      setParts(nextAsset.parts);
      if (nextAsset.parts.length) setSelectedPart(nextAsset.parts[0].part_id);
      setPreviewCandidate(null);
      setCandidates([]);
      setJob(null);
      addLog("active asset", response.active_asset_id);
      return;
    }
    if (job?.candidate_ids) await loadCandidates(job.candidate_ids);
  };

  const patchVersionNode = async (
    nodeId: string,
    update: Partial<Pick<VersionGraphNode, "status" | "preview_url" | "mesh_url" | "obj_url" | "hy3d_job_id" | "error">>,
  ) => {
    if (!session) throw new Error("session is required for version update");
    const node = await api<VersionGraphNode>(
      `/api/v1/sessions/${session.session_id}/version-nodes/${nodeId}`,
      { method: "PATCH", body: JSON.stringify(update) },
    );
    mergeVersionGraphNode(node, versionGraphRef.current.active_node_id === nodeId);
    if (update.status === "mesh_ready" || update.status === "mesh_failed") {
      setHy3dProgress(null);
    }
    return node;
  };

  const {
    adoptHy3dMeshAsActiveAsset,
    dropCandidateIntoVersionGraph,
    watchFourStageHy3dJob,
    runFourStageHy3d,
    retryVersionNode,
  } = bindStudioHy3d({
    session,
    asset,
    hy3dCandidateIds,
    hy3dAdoptedRef,
    hy3dWatchRef,
    versionGraphRef,
    versionViewModeRef,
    versionCanvasShellRef,
    fourStageRef,
    allCandidates,
    projectRecorder,
    setAsset,
    setParts,
    setCandidates,
    setPreviewCandidate,
    setCanvasPreview,
    setHy3dCandidateIds,
    setHy3dProgress,
    setVersionViewMode,
    setSolutionSpaceReleased,
    setCanvasZoom,
    setCanvasPan,
    setSelectedCandidateId,
    setAcceptedCandidateIds,
    addLog,
    patchVersionNode,
    mergeVersionGraphNode,
    applyVersionGraph,
    ensureSourceVersionNode,
    discoverPartsForAsset,
  });

  const highlightVersionNode = async (nodeId: string, candidate: Candidate | null) => {
    setActiveVersionId(nodeId);
    applyVersionGraph({ ...versionGraphRef.current, active_node_id: nodeId });
    if (candidate) {
      setSelectedCandidateId(candidate.candidate_id);
    }
    if (!session) return;
    try {
      const graph = await api<VersionGraphState>(
        `/api/v1/sessions/${session.session_id}/active-version/${nodeId}`,
        { method: "PUT" },
      );
      applyVersionGraph({ ...graph, active_node_id: nodeId });
    } catch (error) {
      addLog("version", `高亮版本保存失败：${String(error).slice(0, 120)}`);
    }
  };

  /** 激活持久化版本；先本地切换，再把活动节点写回服务器。 */
  const activateVersionNode = async (nodeId: string, candidate: Candidate | null) => {
    setActiveVersionId(nodeId);
    setVersionViewMode("active");
    setCanvasZoom(1);
    applyVersionGraph({ ...versionGraphRef.current, active_node_id: nodeId });
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        setCanvasPan(centeredActiveCanvasPan(versionCanvasShellRef.current));
      });
    });
    if (candidate) {
      setSelectedCandidateId(candidate.candidate_id);
      if (candidate.mesh_url || candidate.obj_url || candidatePreviewUrl(candidate)) {
        setPreviewCandidate(candidate);
        setCanvasPreview(
          candidate.mesh_url || candidate.obj_url ? null : { url: candidatePreviewUrl(candidate) ?? "", label: candidate.label },
        );
      }
    } else {
      setSelectedCandidateId(null);
      setPreviewCandidate(null);
      setCanvasPreview(null);
    }
    if (session) {
      try {
        const graph = await api<VersionGraphState>(
          `/api/v1/sessions/${session.session_id}/active-version/${nodeId}`,
          { method: "PUT" },
        );
        applyVersionGraph(graph);
      } catch (error) {
        addLog("version", `活动版本保存失败：${String(error).slice(0, 120)}`);
      }
    }
    addLog("version", `活动版本切换为 ${candidate?.label ?? nodeId}`);
  };

  const deleteVersionNode = async (nodeId: string) => {
    if (!session) return;
    if (versionGraphRef.current.nodes.length <= 1) {
      addLog("version", "至少保留一个版本");
      return;
    }
    try {
      const graph = await api<VersionGraphState>(
        `/api/v1/sessions/${session.session_id}/version-nodes/${nodeId}`,
        { method: "DELETE" },
      );
      applyVersionGraph(graph);
      setPreviewCandidate(null);
      setCanvasPreview(null);
      setSelectedCandidateId(null);
      addLog("version", `已删除版本 ${nodeId}`);
    } catch (error) {
      addLog("version", `删除版本失败：${String(error).slice(0, 120)}`);
    }
  };

  useEffect(() => {
    if (!versionGraphHydrated) return;
    for (const node of versionGraph.nodes) {
      if (
        node.status === "mesh_ready"
        && node.parent_node_id
        && node.hy3d_job_id
        && (node.mesh_url || node.obj_url)
      ) {
        const live = node.candidate_id
          ? allCandidates.find((item) => item.candidate_id === node.candidate_id)
          : undefined;
        void adoptHy3dMeshAsActiveAsset(
          live ?? {
            candidate_id: node.candidate_id ?? `version_${node.node_id}`,
            job_id: node.hy3d_job_id,
            session_id: session?.session_id ?? node.session_id,
            source_asset_id: asset?.asset_id ?? "",
            source_part_id: null,
            label: node.label,
            decision: "accepted",
            mesh_url: node.mesh_url,
            obj_url: node.obj_url,
            thumbnail_url: node.preview_url,
            scores: {},
            metadata: { four_stage_artifact: true },
          },
          node.mesh_url,
          node.obj_url,
          node.preview_url,
          remoteWorkerPathFromUrl(node.obj_url) || remoteWorkerPathFromUrl(node.mesh_url),
          node.node_id,
        );
        continue;
      }
      const jobId = String(node.hy3d_job_id || "").trim();
      if (node.status !== "generating_3d" || !jobId || hy3dWatchRef.current.has(jobId)) continue;
      const live = node.candidate_id
        ? allCandidates.find((item) => item.candidate_id === node.candidate_id)
        : undefined;
      const fourStageMatch = node.candidate_id ? /^fourstage_(.+)_(\d+)$/.exec(node.candidate_id) : null;
      const runId = String(
        live?.metadata?.run_id
          ?? fourStageMatch?.[1]
          ?? fourStageRef.current.runId
          ?? "",
      );
      const candidate: Candidate = live ?? {
        candidate_id: node.candidate_id ?? `version_${node.node_id}`,
        job_id: runId,
        session_id: session?.session_id ?? node.session_id,
        source_asset_id: asset?.asset_id ?? "",
        source_part_id: null,
        label: node.label,
        decision: "accepted",
        mesh_url: node.mesh_url,
        obj_url: node.obj_url,
        thumbnail_url: node.preview_url,
        scores: {},
        metadata: {
          four_stage_artifact: true,
          run_id: runId || undefined,
        },
      };
      setHy3dCandidateIds((current) => (
        current.includes(candidate.candidate_id) ? current : [...current, candidate.candidate_id]
      ));
      void watchFourStageHy3dJob(jobId, candidate, node.node_id);
    }
  }, [versionGraphHydrated, versionGraph.nodes]);

  const fitCandidateToPart = async (candidate: Candidate) => {
    if (!session || fittingCandidateIds.includes(candidate.candidate_id)) return;
    setFittingCandidateIds((current) => [...current, candidate.candidate_id]);
    addLog("fit", `started ${candidate.candidate_id}`);
    try {
      const updated = await api<Candidate>(`/api/v1/candidates/${candidate.candidate_id}/fit`, {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          target_part_id: candidate.source_part_id,
          policy: "bbox_uniform",
        }),
      });
      setCandidates((current) =>
        current.map((item) => (item.candidate_id === updated.candidate_id ? updated : item)),
      );
      setPreviewCandidate(updated);
      addLog("fit", fitEvidenceLabel(updated));
    } catch (error) {
      addLog("fit", String(error));
    } finally {
      setFittingCandidateIds((current) => current.filter((id) => id !== candidate.candidate_id));
      if (job?.candidate_ids) void loadCandidates(job.candidate_ids);
    }
  };

  const versionLayout = useMemo(
    () => layoutVersionGraph(
      versionGraph.nodes,
      versionGraph.active_node_id,
      versionViewMode === "active",
      versionViewMode === "active" ? activeEditorExtent : undefined,
    ),
    [versionGraph, versionViewMode, activeEditorExtent],
  );

  const versionNodes = useMemo(
    () => versionLayout.nodes.map((layoutNode) => {
      const graphNode = layoutNode.graphNode;
      const candidate = graphNode.candidate_id
        ? allCandidates.find((item) => item.candidate_id === graphNode.candidate_id) ?? null
        : null;
      const isSource = graphNode.parent_node_id === null;
      const previewUrl = absoluteUrl(
        graphNode.preview_url
          ?? (candidate ? candidatePreviewUrl(candidate) : null)
          ?? (isSource ? asset?.thumbnail_url ?? null : null)
          ?? "",
      ) || null;
      return {
        id: graphNode.node_id,
        kind: isSource ? "source" as const : "branch" as const,
        versionNumber: graphNode.version_number,
        label: graphNode.label,
        x: layoutNode.x,
        y: layoutNode.y,
        width: layoutNode.width,
        height: layoutNode.height,
        previewUrl,
        meshUrl: graphNode.mesh_url || candidate?.mesh_url || null,
        objUrl: graphNode.obj_url || candidate?.obj_url || (
          previewUrl && /\.preview\.png(?:\?|$)/i.test(previewUrl)
            ? previewUrl.replace(/\.preview\.png/i, ".obj")
            : null
        ),
        status: graphNode.status,
        error: graphNode.error,
        isActivePath: layoutNode.isActivePath,
        candidate,
      };
    }),
    [versionLayout.nodes, allCandidates],
  );

  const versionLinks = useMemo(
    () => versionLayout.links.map((link) => ({
      id: link.id,
      x1: link.x1,
      y1: link.y1,
      x2: link.x2,
      y2: link.y2,
      controlX1: link.controlX1,
      controlX2: link.controlX2,
      isActivePath: link.isActivePath,
    })),
    [versionLayout.links],
  );
  const focusVersionCanvas = (mode: "all" | "active") => {
    if (mode === "active") {
      setVersionViewMode("active");
      setCanvasPan(centeredActiveCanvasPan(versionCanvasShellRef.current));
      setCanvasZoom(1);
      return;
    }
    setVersionViewMode("overview");
    const overviewNodes = layoutVersionGraph(versionGraph.nodes, versionGraph.active_node_id, false).nodes;
    const camera = computeOverviewCanvasCamera(overviewNodes, freeCanvasBand(versionCanvasShellRef.current));
    setCanvasZoom(camera.zoom);
    setCanvasPan(camera.pan);
  };

  // 3D is the bottom layer: only recenter on window / canvas shell size, not chrome overlay resize.
  useEffect(() => {
    if (versionViewMode !== "active") return undefined;
    const shell = versionCanvasShellRef.current;
    if (!shell) return undefined;
    let frame = 0;
    const recenter = () => {
      cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const currentShell = versionCanvasShellRef.current;
        setCanvasPan(centeredActiveCanvasPan(currentShell));
        const activeNode = currentShell?.querySelector<HTMLElement>(".version-node.active");
        const width = Math.round(activeNode?.offsetWidth || window.innerWidth);
        const height = Math.round(activeNode?.offsetHeight || window.innerHeight);
        setActiveEditorExtent((prev) => (
          prev.width === width && prev.height === height ? prev : { width, height }
        ));
      });
    };
    recenter();
    const observer = new ResizeObserver(() => recenter());
    observer.observe(shell);
    window.addEventListener("resize", recenter);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("resize", recenter);
    };
  }, [versionViewMode, studioDrawerOpen, menuWidth, activeVersionId, versionGraph.nodes.length]);

  const zoomCanvasBy = (factor: number) => {
    const current = canvasZoomRef.current;
    const next = Math.max(0.4, Math.min(1.8, Number((current * factor).toFixed(3))));
    if (next === current) return;
    const shell = versionCanvasShellRef.current;
    const width = shell?.clientWidth ?? window.innerWidth;
    const height = shell?.clientHeight ?? window.innerHeight;
    const centerX = width / 2;
    const centerY = height / 2;
    const ratio = next / current;
    setCanvasPan((pan) => ({
      x: centerX - (centerX - pan.x) * ratio,
      y: centerY - (centerY - pan.y) * ratio,
    }));
    setCanvasZoom(next);
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code === "Space" && !event.repeat && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        setSpacePanArmed(true);
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") setSpacePanArmed(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const saveCase = async () => {
    if (!session || !activeCaseAssetId) return;
    setSavingCase(true);
    try {
      const response = await api<CaseRecord>("/api/v1/cases", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          title: caseTitle.trim() || `${asset?.label ?? "FlowStudio"} case`,
          asset_id: activeCaseAssetId,
          accepted_candidate_ids: acceptedCandidateIds,
          notes: caseNotes,
          metadata: {
            creative_stage: creativeStage,
            fidelity: creativeFidelity,
            intent_text: intentText,
            last_job_id: job?.job_id ?? null,
            active_phase: stage?.phase ?? null,
            candidate_decisions: candidates.map((candidate) => ({
              candidate_id: candidate.candidate_id,
              decision: candidate.decision,
              mesh_url: candidate.mesh_url,
              thumbnail_url: candidate.thumbnail_url,
            })),
          },
        }),
      });
      setSavedCase(response);
      setStage((current) =>
        current
          ? {
              ...current,
              phase: "finalizing",
              current_goal: `Saved case: ${response.title}`,
            }
          : current,
      );
      addLog("case saved", response.case_id);
      void loadCaseLibrary();
    } catch (error) {
      addLog("case error", String(error));
    } finally {
      setSavingCase(false);
    }
  };

  const refreshProjectList = async () => {
    const items = await api<ExperimentProjectDetail[]>("/api/v1/projects");
    setProjectList(items);
    return items;
  };

  const refreshProjectTimeline = async (target = projectRef.current) => {
    if (!target) return [];
    const page = await api<{ items: ExperimentEvent[]; next_cursor: number | null }>(
      `/api/v1/projects/${target.project.project_id}/events?limit=500`,
    );
    setProjectEvents(page.items);
    return page.items;
  };

  const openExperimentProject = async (projectId: string) => {
    setProjectBusy(true);
    try {
      const detail = await api<ExperimentProjectDetail>(`/api/v1/projects/${projectId}`);
      if (detail.active_run && detail.active_run.session_id !== session?.session_id) {
        const snapshot = await api<SessionSnapshotResponse>(
          `/api/v1/sessions/${detail.active_run.session_id}/snapshot`,
        );
        hydrateSessionSnapshot(snapshot);
        window.localStorage.setItem(SESSION_STORAGE_KEY, detail.active_run.session_id);
        attachSessionSocket(detail.active_run.session_id);
      }
      setProject(detail);
      projectRef.current = detail;
      window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, detail.project.project_id);
      await refreshProjectTimeline(detail);
      setProjectDialogOpen(false);
      return detail;
    } finally {
      setProjectBusy(false);
    }
  };

  const createExperimentProject = async ({
    title,
    participantCode,
    conditionLabel,
    baselineMode,
  }: {
    title: string;
    participantCode?: string;
    conditionLabel?: string;
    baselineMode: "blank" | "current_state";
  }) => {
    setProjectBusy(true);
    setRecordingError(null);
    try {
      const targetSession = baselineMode === "blank" ? await startBlankWorkspace() : session;
      if (!targetSession) throw new Error("无法创建实验会话");
      const detail = await api<ExperimentProjectDetail>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim() || "Untitled experiment",
          participant_code: participantCode?.trim() || null,
          condition_label: conditionLabel?.trim() || null,
          session_id: targetSession.session_id,
          baseline_mode: baselineMode,
          baseline_snapshot: baselineMode === "current_state" ? {
            active_asset_id: asset?.asset_id ?? null,
            action_atoms: actionAtoms,
            divergence_parameters: buildSemanticDivergenceParameters({
              temperature: divergenceTemperature,
              perGroupCount: divergencePerGroupCount,
            }),
            selected_candidate_ids: [selectedCandidateId, ...acceptedCandidateIds].filter(Boolean),
            version_graph: versionGraphRef.current,
          } : {},
        }),
      });
      setProject(detail);
      projectRef.current = detail;
      await refreshProjectTimeline(detail);
      window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, detail.project.project_id);
      setProjectDialogOpen(false);
      void refreshProjectList();
      return detail;
    } catch (error) {
      setRecordingError(String(error));
      throw error;
    } finally {
      setProjectBusy(false);
    }
  };

  const endExperimentRun = async () => {
    const current = projectRef.current;
    if (!current?.active_run) return null;
    const run = await api<ExperimentProjectDetail["active_run"]>(
      `/api/v1/projects/${current.project.project_id}/runs/${current.active_run.run_id}/end`,
      { method: "POST" },
    );
    const next = { ...current, active_run: null, project: { ...current.project, active_run_id: null } };
    setProject(next);
    projectRef.current = next;
    await refreshProjectTimeline(next);
    return run;
  };

  const exportExperimentProject = async () => {
    const current = projectRef.current;
    if (!current) return null;
    return api<ExperimentExportRecord>(`/api/v1/projects/${current.project.project_id}/export`, {
      method: "POST",
    });
  };

  const recordExperimentEvent = (
    eventType: string,
    payload: Record<string, unknown>,
    idempotencyKey = `${eventType}:${crypto.randomUUID()}`,
    critical = false,
  ) => projectRecorder.record(eventType, payload, idempotencyKey, { critical });

  useEffect(() => {
    const storedProjectId = window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
    void refreshProjectList().catch(() => undefined);
    if (storedProjectId) {
      void openExperimentProject(storedProjectId).catch(() => {
        window.localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
      });
    }
  }, []);

  const onMenuHandlePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    menuDragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: studioDrawerOpen ? menuWidth : 0,
      wasOpen: studioDrawerOpen,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onMenuHandlePointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = menuDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const delta = event.clientX - drag.startX;
    if (Math.abs(delta) > 4) drag.moved = true;
    if (!drag.moved) return;
    const nextWidth = Math.max(0, Math.min(640, drag.startWidth + delta));
    if (nextWidth < 48) {
      setStudioDrawerOpen(false);
      return;
    }
    setStudioDrawerOpen(true);
    setMenuWidth(Math.max(280, nextWidth));
  };

  const onMenuHandlePointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = menuDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    menuDragRef.current = null;
    if (menuWidth < 48) {
      setStudioDrawerOpen(false);
    }
  };

  return {
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
    setSystemServices,
    systemServicesLoading,
    setSystemServicesLoading,
    startingServiceIds,
    setStartingServiceIds,
    bootstrapRunning,
    setBootstrapRunning,
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
    divergenceTemperature,
    setDivergenceTemperature,
    divergencePerGroupCount,
    setDivergencePerGroupCount,
    divergenceKeywords,
    setDivergenceKeywords,
    semanticDivergence,
    semanticDivergenceLoading,
    semanticDivergenceError,
    divergencePhaseMessage,
    selectionPersistenceError,
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
    setLiveObserveNarrative,
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
    solutionSpaceViewIntentSeq,
    setSolutionSpaceViewIntentSeq,
    solutionSpaceCandidates,
    solutionSpaceRoundChips,
    displayIntentSeq,
    liveIntentSeq,
    solutionSpaceGenerating,
    setSolutionSpaceGenerating,
    solutionSpaceHeight,
    setSolutionSpaceHeight,
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
    allCandidates,
    selectedCandidateId,
    setSelectedCandidateId,
    activeVersionId,
    setActiveVersionId,
    versionViewMode,
    versionGraph,
    dropCandidateIntoVersionGraph,
    highlightVersionNode,
    activateVersionNode,
    deleteVersionNode,
    retryVersionNode,
    activeVersionMeshReady,
    liveSolutionSpaceVisible,
    solutionSpaceComparing,
    plannerBubbleInterpretation,
    solutionSpaceSignature,
    segmentationPreviewUrl,
    analysisPreviewUrl,
    activePreviewUrl,
    activePreviewLabel,
    sendEvent,
    fourStage,
    liveObservation,
    behaviorSessions,
    intentRevisions,
    interactionState,
    solutionBatches,
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
    refreshProjectList,
    createExperimentProject,
    openExperimentProject,
    endExperimentRun,
    exportExperimentProject,
    recordExperimentEvent,
    refreshProjectTimeline,
    activeRevisionId,
    setActiveRevisionId,
    refreshRealtimeObservation,
    sendIntentRevision,
    selectIntentRevision,
    resolveIntentRevisionGate,
    commitDivergenceParameters,
    scheduleDivergenceParametersCommit,
    triggerPostGateDivergence,
    startActiveRevisionGeneration,
    finalizeSculptBehavior,
    snapshotSculptBehavior,
    cancelSculptBehavior,
    resumeSculptBehavior,
    finalizePrimitiveBehavior,
    cancelPrimitiveBehavior,
    deleteBehavior,
    createFourStageRun,
    appendFourStageEvents,
    advanceFourStageRun,
    gateFourStage,
    startFourStageGeneration,
    saveFourStageDivergenceSelection,
    submitIntentTextToFourStage,
    refreshFourStageRun,
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
    dismissInheritedKeyword,
    inheritedKeywords,
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
    fitCandidateToPart,
    versionNodes,
    versionLinks,
    focusVersionCanvas,
    zoomCanvasBy,
    saveCase,
    onMenuHandlePointerDown,
    onMenuHandlePointerMove,
    onMenuHandlePointerUp,
  };
}
