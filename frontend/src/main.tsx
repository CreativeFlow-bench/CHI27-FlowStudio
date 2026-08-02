import React, { useEffect, useMemo, useRef, useState } from "react";
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
import "./styles.css";

const API_BASE =
  import.meta.env.VITE_API_BASE ?? `${window.location.protocol}//${window.location.hostname}:8000`;
const WS_BASE =
  import.meta.env.VITE_WS_BASE ??
  `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`;
const SESSION_STORAGE_KEY = "flowstudio:last-session-id";

type StageState = {
  phase: string;
  confidence: number;
  current_goal: string | null;
  active_asset_id: string | null;
  active_part_id: string | null;
  suggested_action: string | null;
  evidence?: string[];
};

type SessionRecord = {
  session_id: string;
  title: string;
  stage: StageState;
  metadata: Record<string, unknown>;
  created_at?: string;
};

type AssetRecord = {
  asset_id: string;
  object_type: string;
  label: string;
  mesh_url: string | null;
  obj_url: string | null;
  parts: PartRecord[];
};

type PartRecord = {
  part_id: string;
  label: string;
  type?: string;
  lifecycle?: "tentative_raycast" | "obj_group_fallback" | "viewport_2d_mask" | "segmented_3d" | string;
  metadata?: Record<string, unknown>;
};

type Hypothesis = {
  intent: string;
  confidence: number;
  evidence?: string[];
};

type Interpretation = {
  interpretation_id: string;
  primary_intent: string;
  predictor?: string;
  predictor_version?: string;
  predictor_metadata?: Record<string, unknown>;
  confidence: number;
  ambiguity: number;
  hypotheses: Hypothesis[];
  assistance_policy: string;
  suggested_assistance?: AssistanceSuggestion[];
  evidence: string[];
  features?: {
    signals?: Record<string, Record<string, unknown>>;
    creative_state?: string;
    creative_state_confidence?: number;
    change_scope_hint?: string;
    recommended_axes?: string[];
    design_state_ir?: {
      ready?: boolean;
      matches?: DesignStateIRMatch[];
      source?: string;
      recommended_axes?: string[];
      axis_scores?: Array<{ axis: string; score: number }>;
      query_signals?: string[];
      query_terms?: string[];
      retrieval_mode?: string;
      policy?: string;
    };
  };
};

type EvidenceSummaryItem = {
  label: string;
  value: unknown;
  source: string;
  confidence?: number;
  score?: unknown;
};

type PlannerDecisionResponse = {
  interpretation_id: string;
  session_id: string;
  decision: "accepted" | "rejected";
  event_id: string;
  memory_id: string;
  updated_stage: StageState;
};

type DesignStateIRMatch = {
  ir_id?: string;
  case_id?: string;
  score?: number;
  confidence?: number;
  vector_score?: number;
  design_state?: string;
  route?: string;
  signals?: string[];
  signal_overlap?: string[];
  term_overlap?: string[];
  scope_match?: boolean;
  scope_hint?: string;
  recommended_axes?: string[];
  evidence_strength?: string;
  text?: string;
};

type AssistanceSuggestion = {
  type: "generate" | "ask" | "notify" | "highlight";
  mode?: "replace" | "drag_regenerate" | "diverge" | "refine" | null;
  label?: string | null;
  question?: string | null;
  metadata?: Record<string, unknown>;
};

type PlannerClarificationBubble = {
  id: string;
  label: string;
  detail: string;
  kind: "target" | "axis" | "action";
  position: "left" | "right" | "top";
};

type CreativeState =
  | "idle"
  | "exploring"
  | "focused_editing"
  | "refining"
  | "comparing"
  | "possible_fixation"
  | "ready_for_help";

type BubbleScope = "contour" | "part" | "material";

type IntentBubbleUiState = {
  visible: boolean;
  scope: BubbleScope | null;
  status: "pending" | "accepted" | "rejected" | "ignored" | null;
  shownAt: number | null;
};

type JobRecord = {
  job_id: string;
  status: string;
  stage: string;
  progress: number;
  message: string | null;
  candidate_ids: string[];
};

type Candidate = {
  candidate_id: string;
  job_id: string;
  session_id: string;
  source_asset_id: string;
  source_part_id: string | null;
  label: string;
  decision: string;
  mesh_url: string | null;
  obj_url: string | null;
  thumbnail_url: string | null;
  scores: Record<string, number>;
  metadata: Record<string, unknown>;
};

type CandidateDecisionResponse = {
  candidate_id: string;
  decision: string;
  active_asset_id: string | null;
  updated_stage: StageState;
};

type CaseRecord = {
  case_id: string;
  session_id: string;
  title: string;
  asset_id: string;
  accepted_candidate_ids: string[];
  notes: string | null;
  report_url: string | null;
  metadata: Record<string, unknown>;
};

type ArtifactRecord = {
  artifact_id: string;
  type: string;
  url: string;
  session_id: string | null;
  asset_id: string | null;
  worker: string;
  operation: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

type CaseIndexItem = {
  case_id: string;
  session_id: string;
  title: string;
  asset_id: string;
  report_url: string | null;
  case_url: string | null;
  accepted_candidate_ids: string[];
  created_at: string;
};

type CaseIndexResponse = {
  schema_version: string;
  cases: CaseIndexItem[];
};

type CaseManifest = {
  schema_version: string;
  case: CaseRecord;
  stage: StageState;
  asset: AssetRecord;
  accepted_candidates: Candidate[];
};

type SessionSnapshotResponse = {
  session: SessionRecord;
  active_asset: AssetRecord | null;
  active_parts: PartRecord[];
  active_job: JobRecord | null;
  live_signals?: Partial<LiveSignals>;
  visible_candidates: Candidate[];
  recent_interpretations: Interpretation[];
};

type SolutionSpaceResponse = {
  session_id: string;
  stage: StageState;
  active_asset: AssetRecord | null;
  nodes: Array<{
    candidate_id?: string;
    decision?: string;
    candidate?: Candidate;
  }>;
  directions: AnalogyDirection[];
  memory?: Record<string, unknown>;
};

type BenchmarkAsset = {
  benchmark_id: string;
  label: string;
  object_type: string;
  mesh_url: string | null;
  obj_url: string | null;
  model_available?: boolean;
  file_size_bytes: number;
  vertex_count: number | null;
  face_count: number | null;
  metadata: Record<string, unknown>;
};

type BenchmarkAssetListResponse = {
  assets: BenchmarkAsset[];
};

type LogItem = {
  id: string;
  label: string;
  detail: string;
  at?: number;
};

type PerceptionLogEntry = {
  id: string;
  time: string;
  tag: "SYS" | "INIT" | "PERCEPTION" | "ACTION";
  text: string;
};

type RemoteWorkerHealth = {
  ok: boolean;
  configured?: boolean;
  pipeline_root?: string;
  python_bin_exists?: boolean;
  original_pipeline_exists?: boolean;
  transfer_script_exists?: boolean;
  transfer_minimal_script_exists?: boolean;
  hy3d_script_exists?: boolean;
  mesh_worker_exists?: boolean;
  creativeflow_pipeline?: {
    structured_transfer_ready?: boolean;
    minimal_transfer_ready?: boolean;
    legacy_pipeline_ready?: boolean;
    hy3d_ready?: boolean;
    staged_endpoints?: string[];
  };
  partfield_root_exists?: boolean;
  partfield_python_exists?: boolean;
  partfield_model_exists?: boolean;
  partfield_model_ready?: boolean;
  partfield_model_size?: number;
  partfield_worker_script_exists?: boolean;
  sam3d_root_exists?: boolean;
  sam3d_python_exists?: boolean;
  sam3d_model_exists?: boolean;
  sam3d_worker_script_exists?: boolean;
  sam3d_ready?: boolean;
  segmentation_adapter?: string;
  segmentation_worker_ready?: boolean;
  partfield_setup_running?: boolean;
  partfield_setup_processes?: Array<{
    pid?: string;
    ppid?: string;
    elapsed?: string;
    cpu?: string;
    mem?: string;
    command?: string;
  }>;
  partfield_setup_log_tail?: string | null;
  geometry_worker_ready?: boolean;
  render_preview_ready?: boolean;
  blender_exists?: boolean;
  blender_bin?: string;
  jobs?: number;
  error?: string;
};

type RemoteWorkerPreflight = {
  ok: boolean;
  core_ready?: boolean;
  long_run_ready?: boolean;
  qwen_image?: {
    probe?: {
      reachable?: boolean;
      status?: number | null;
      elapsed_sec?: number;
      error?: string | null;
    };
  };
  kb_network?: Record<
    string,
    {
      reachable?: boolean;
      status?: number | null;
      elapsed_sec?: number;
      error?: string | null;
    }
  >;
  oss?: {
    env_file_exists?: boolean;
    configured_keys?: Record<string, boolean>;
  };
  warnings?: string[];
  error?: string;
};

type BackendHealth = {
  status: string;
  remote_worker_configured?: boolean;
  remote_worker_ok?: boolean;
  interaction_understanding?: {
    predictor?: string;
    predictor_version?: string;
    vlm_configured?: boolean;
  };
  workers?: {
    geometry_processing?: {
      ok?: boolean;
      mode?: string;
    };
    render_preview?: {
      ok?: boolean;
      mode?: string;
      remote_blender_bin?: string | null;
    };
  };
};

type GeometryWorkerResponse = {
  ok: boolean;
  job_id: string;
  status: string;
  operation: string;
  result_mesh_url: string | null;
  preview_mesh_url: string | null;
  metrics?: Record<string, unknown>;
  artifacts?: Record<string, unknown>;
  error?: {
    message?: string;
  } | null;
};

type CanvasPrimitive =
  | "plane"
  | "cube"
  | "circle"
  | "sphere"
  | "ico_sphere"
  | "cylinder"
  | "cone"
  | "torus"
  | null;
type CanvasTool = "select" | "clay" | "move";
type CanvasDisplayMode = "textured" | "parts" | "heatmap" | "clay";

type ChatMessage = {
  id: string;
  role: "user" | "planner";
  text: string;
  candidateIds?: string[];
};

type PartDiscoveryResponse = {
  job_id: string | null;
  status: string;
  parts: PartRecord[];
  metadata: Record<string, unknown>;
};

type ActionAtom = {
  atom_id: string;
  tool: "hover" | "brush" | "annotation" | "drag" | "smooth" | "add" | "text" | "image" | "model";
  target: Record<string, unknown>;
  evidence: Record<string, unknown>;
  order: number;
  created_at?: string;
};

function isObjectBehaviorAtom(atom: ActionAtom) {
  return atom.evidence?.source !== "more_creative_prompt_chip";
}

type IntentDraft = {
  draft_id: string;
  session_id: string;
  asset_id: string | null;
  title: string;
  text: string | null;
  behavior_atoms: ActionAtom[];
  image_refs: string[];
  model_refs: string[];
  status: "draft" | "sent" | "archived";
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type IntentDraftListResponse = {
  drafts: IntentDraft[];
};

type IntentEpisodeResponse = {
  episode_id: string;
  session_id: string;
  asset_id: string | null;
  intent_draft_id: string | null;
  behavior_atoms: ActionAtom[];
  text: string | null;
  status: "submitted";
  metadata: Record<string, unknown>;
};

type AnalogyDirection = {
  direction_id: string;
  label: string;
  dimension: "Aesthetic" | "Functional" | "Structural" | "Cross-domain";
  divergence_mode: "local" | "whole_object" | "cross_domain";
  source_domain: string;
  target_domain: string;
  relation: string;
  transfer_rationale: string;
  constraints: string[];
  score: number;
  metadata: Record<string, unknown>;
};

type PromptToken = {
  token_id?: string;
  label: string;
  dimension?: "Aesthetic" | "Functional" | "Structural" | "Cross-domain";
  role?: string;
  source_direction_id?: string;
  weight?: number;
};

type LiveSignals = {
  dwell_ms: number;
  compare_dwell_ms: number;
  new_case_attempt_rate: number;
  mask_coverage: number;
  viewport_orbit_count: number;
  viewport_zoom_count: number;
  local_zoom_count: number;
  semantic_distance: number;
  drawing_content: string;
  tool_switch_count: number;
  reference_match_count: number;
  hover_count: number;
  brush_count: number;
  annotation_count: number;
};

const EMPTY_LIVE_SIGNALS: LiveSignals = {
  dwell_ms: 0,
  compare_dwell_ms: 0,
  new_case_attempt_rate: 0,
  mask_coverage: 0,
  viewport_orbit_count: 0,
  viewport_zoom_count: 0,
  local_zoom_count: 0,
  semantic_distance: 0,
  drawing_content: "",
  tool_switch_count: 0,
  reference_match_count: 0,
  hover_count: 0,
  brush_count: 0,
  annotation_count: 0,
};

type LivePerception = {
  summary: string;
  evidence: string[];
  confidence: number | null;
  source: "local" | "server";
  updatedAt: string;
};

type PerceptionLatestResponse = {
  perception?: {
    perception_id?: string;
    summary?: string;
    behavior_label?: string;
    confidence?: number;
    evidence?: Array<string | { type?: string; value?: string }>;
  } | null;
};

type ViewportInteractionSignal = {
  type: "orbit" | "zoom" | "pan";
  dwell_ms?: number;
  camera_distance?: number;
};

type AnnotationPoint = {
  x: number;
  y: number;
  t: number;
};
type AnnotationStroke = AnnotationPoint[];

type EditorSnapshot = {
  intentText: string;
  actionAtoms: ActionAtom[];
  imageRefs: ArtifactRecord[];
  modelRefs: ArtifactRecord[];
  selectedPromptTokens: PromptToken[];
  previewCandidate: Candidate | null;
  canvasPreview: { url: string; label: string } | null;
};

type CrossDomainDivergenceResponse = {
  session_id: string;
  asset_id: string;
  intent_draft_id: string | null;
  source_summary: string;
  directions: AnalogyDirection[];
  evidence: string[];
  metadata: Record<string, unknown>;
};

type DirectionsSuggestResponse = {
  session_id?: string;
  asset_id?: string;
  intent_draft_id?: string | null;
  directions: AnalogyDirection[];
  evidence?: string[];
  metadata?: Record<string, unknown>;
};

type PromptComposeResponse = {
  session_id: string;
  asset_id: string | null;
  final_prompt: string;
  analogy_prompt_package: Record<string, unknown>;
  event_id: string;
  memory_id: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

function timeoutAfter(ms: number, label: string): Promise<never> {
  return new Promise((_, reject) => {
    window.setTimeout(() => reject(new Error(`${label} timed out`)), ms);
  });
}

function centeredActiveCanvasPan() {
  const width = typeof window === "undefined" ? 1440 : window.innerWidth;
  const height = typeof window === "undefined" ? 900 : window.innerHeight;
  return {
    x: Math.max(320, Math.round((width - 520) / 2 - 40)),
    y: Math.max(80, Math.round((height - 520) / 2 - 10)),
  };
}

function App() {
  const [session, setSession] = useState<SessionRecord | null>(null);
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [parts, setParts] = useState<PartRecord[]>([]);
  const [stage, setStage] = useState<StageState | null>(null);
  const [interpretation, setInterpretation] = useState<Interpretation | null>(null);
  const [job, setJob] = useState<JobRecord | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [previewCandidate, setPreviewCandidate] = useState<Candidate | null>(null);
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
  const [partDiscovery, setPartDiscovery] = useState<PartDiscoveryResponse | null>(null);
  const [discoveringParts, setDiscoveringParts] = useState(false);
  const [hy3dCandidateIds, setHy3dCandidateIds] = useState<string[]>([]);
  const [fittingCandidateIds, setFittingCandidateIds] = useState<string[]>([]);
  const [autoDiscoverParts, setAutoDiscoverParts] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [intentText, setIntentText] = useState("");
  const [selectedPart, setSelectedPart] = useState("");
  const [partLabelDraft, setPartLabelDraft] = useState("");
  const [creativeStage, setCreativeStage] = useState("silhouette");
  const [creativeFidelity, setCreativeFidelity] = useState("low");
  const [canvasPrimitive, setCanvasPrimitive] = useState<CanvasPrimitive>(null);
  const [canvasTool, setCanvasTool] = useState<CanvasTool>("select");
  const [canvasDisplayMode, setCanvasDisplayMode] = useState<CanvasDisplayMode>("textured");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [plannerBusy, setPlannerBusy] = useState(false);
  const [plannerDecisionBusy, setPlannerDecisionBusy] = useState<"accepted" | "rejected" | null>(null);
  const [plannerDecision, setPlannerDecision] = useState<PlannerDecisionResponse | null>(null);
  const [sculptBusy, setSculptBusy] = useState<CanvasTool | null>(null);
  const [actionAtoms, setActionAtoms] = useState<ActionAtom[]>([]);
  const [intentDrafts, setIntentDrafts] = useState<IntentDraft[]>([]);
  const [activeIntentDraft, setActiveIntentDraft] = useState<IntentDraft | null>(null);
  const [referenceImages, setReferenceImages] = useState<ArtifactRecord[]>([]);
  const [referenceModels, setReferenceModels] = useState<ArtifactRecord[]>([]);
  const [intentBusy, setIntentBusy] = useState(false);
  const [crossDomainBusy, setCrossDomainBusy] = useState(false);
  const [crossDomainDirections, setCrossDomainDirections] = useState<AnalogyDirection[]>([]);
  const [crossDomainMetadata, setCrossDomainMetadata] = useState<Record<string, unknown> | null>(null);
  const [selectedPromptTokens, setSelectedPromptTokens] = useState<PromptToken[]>([]);
  const [annotationMode, setAnnotationMode] = useState(false);
  const [hoverMode, setHoverMode] = useState(false);
  const [hoverLabel, setHoverLabel] = useState<string | null>(null);
  const [hoverSamBusy, setHoverSamBusy] = useState(false);
  const [studioDrawerOpen, setStudioDrawerOpen] = useState(false);
  const [menuWidth, setMenuWidth] = useState(300);
  const menuDragRef = useRef<{
    pointerId: number;
    startX: number;
    startWidth: number;
    wasOpen: boolean;
    moved: boolean;
  } | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [showSignalDebug, setShowSignalDebug] = useState(false);
  const [canvasPan, setCanvasPan] = useState(centeredActiveCanvasPan);
  const [canvasZoom, setCanvasZoom] = useState(1);
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
  const directionsRequestSeqRef = useRef(0);
  const lastMeaningfulActionAtRef = useRef<number | null>(null);
  const fixationEnteredAtRef = useRef<number | null>(null);
  const [typedIntentStable, setTypedIntentStable] = useState(false);
  const [plannerNarration, setPlannerNarration] = useState("I'm watching the canvas quietly — take a move whenever you're ready.");
  const [plannerTypedText, setPlannerTypedText] = useState("");
  const plannerNarrationTimerRef = useRef<number | null>(null);
  const plannerNarrationLastAtRef = useRef(0);
  const plannerNarrationIntentRef = useRef("");
  const [perceptionHistoryOpen, setPerceptionHistoryOpen] = useState(false);
  const [workspaceChromeReady, setWorkspaceChromeReady] = useState(false);
  const [workspaceStartedAt, setWorkspaceStartedAt] = useState<string | null>(null);
  const [solutionSpaceReleased, setSolutionSpaceReleased] = useState(false);
  const [solutionSpaceTouchedAt, setSolutionSpaceTouchedAt] = useState(0);
  const [solutionSpaceGenerating, setSolutionSpaceGenerating] = useState(false);
  const versionCanvasDragRef = useRef<{
    active: boolean;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const livePerceptionSyncRef = useRef(0);
  const hoverLabelRef = useRef<string | null>(null);
  const hoverModeRef = useRef(false);
  const hoverCommittedRef = useRef<string | null>(null);
  const hoverDwellTimerRef = useRef<number | null>(null);
  const [liveSignals, setLiveSignals] = useState<LiveSignals>(EMPTY_LIVE_SIGNALS);
  const [livePerception, setLivePerception] = useState<LivePerception>({
    summary: "Waiting for your first move.",
    evidence: [],
    confidence: null,
    source: "local",
    updatedAt: new Date().toISOString(),
  });
  const [undoStack, setUndoStack] = useState<Array<{ label: string; snapshot: EditorSnapshot }>>([]);
  const [redoStack, setRedoStack] = useState<Array<{ label: string; snapshot: EditorSnapshot }>>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const referenceImageInputRef = useRef<HTMLInputElement | null>(null);
  const referenceModelInputRef = useRef<HTMLInputElement | null>(null);
  const textEditBaselineRef = useRef<EditorSnapshot | null>(null);
  const sourceSwitchSeqRef = useRef(0);
  const jobSourceSeqRef = useRef<Record<string, number>>({});
  const typedIntentDivergenceKeyRef = useRef("");

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
    lastMeaningfulActionAtRef.current = null;
    fixationEnteredAtRef.current = null;
    setCandidates([]);
    setPreviewCandidate(null);
    setCanvasPreview(null);
    setAcceptedCandidateIds([]);
    setCrossDomainDirections([]);
    setCrossDomainMetadata(null);
    setSelectedPromptTokens([]);
    setInterpretation(null);
    setPlannerDecision(null);
    setPlannerDecisionBusy(null);
    setPlannerBusy(false);
    setCrossDomainBusy(false);
    setSolutionSpaceReleased(false);
    setSolutionSpaceTouchedAt(0);
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
    setIntentDrafts([]);
    setActiveIntentDraft(null);
    setIntentText("");
    setChatInput("");
    setChatMessages([]);
    setTypedIntentStable(false);
    setIntentBubble({ visible: false, scope: null, status: null, shownAt: null });
    setHoverLabel(null);
    setHoverMode(false);
    setHoverSamBusy(false);
    setAnnotationMode(false);
    setAddMenuOpen(false);
    setSculptBusy(null);
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
    updateLiveSignals((current) => ({
      viewport_orbit_count:
        signal.type === "orbit" || signal.type === "pan"
          ? current.viewport_orbit_count + 1
          : current.viewport_orbit_count,
      viewport_zoom_count:
        signal.type === "zoom" ? current.viewport_zoom_count + 1 : current.viewport_zoom_count,
      dwell_ms: signal.dwell_ms ? Math.max(current.dwell_ms, signal.dwell_ms) : current.dwell_ms,
    }));
  };

  const applyLocalPerception = (signals: LiveSignals = liveSignals) => {
    setLivePerception({
      summary: livePerceptionSummary(signals, Boolean(asset?.mesh_url || asset?.obj_url), canvasPrimitive),
      evidence: livePerceptionEvidence(signals),
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
    const syncId = ++livePerceptionSyncRef.current;
    const hoveredLabel = hoverLabelRef.current ?? activeSelectedPart?.label ?? null;
    try {
      await putLiveSignals(signals);
      if (syncId !== livePerceptionSyncRef.current) return;
      await api<Interpretation>("/api/v1/interaction/interpret", {
        method: "POST",
        body: JSON.stringify({
          type: "camera_observation_ended",
          event_id: `evt_${crypto.randomUUID().slice(0, 8)}`,
          session_id: session.session_id,
          timestamp: new Date().toISOString(),
          payload: {
            asset_id: asset?.asset_id ?? null,
            active_asset_id: asset?.asset_id ?? null,
            assistance_policy: "interpret_silently",
            live_signals: signals,
            selected_part_label: hoveredLabel,
            pending_behavior_count: visibleBehaviorAtoms.length,
            signals: {
              interaction: {
                mode: hoveredLabel ? "projected_semantic_hover" : "live_observation",
                live_signals: signals,
              },
              semantic: {
                object_type: asset?.object_type ?? canvasPrimitive ?? "object",
                part_id: selectedPart || null,
                part_label: hoveredLabel,
                semantic_source: hoveredLabel
                  ? activeSelectedPart?.metadata?.source === "obj_group_fallback"
                    ? "obj_group_projected_hover"
                    : "projected_hover_tentative"
                  : null,
                drawing_content: signals.drawing_content || null,
              },
            },
          },
        }),
      });
    } catch (error) {
      if (syncId === livePerceptionSyncRef.current) {
        applyLocalPerception(signals);
        addLog("live perception", String(error).slice(0, 160));
      }
    }
  };

  const recordActionAtom = (
    tool: ActionAtom["tool"],
    target: Record<string, unknown> = {},
    evidence: Record<string, unknown> = {},
  ) => {
    pushEditorHistory(`add ${tool}`);
    setActionAtoms((current) => {
      const atom = {
        atom_id: `atom_${crypto.randomUUID().slice(0, 8)}`,
        tool,
        target,
        evidence: { ...evidence, live_signals: evidence.live_signals ?? liveSignals },
        order: current.length,
        created_at: new Date().toISOString(),
      };
      void syncActionAtom(atom);
      return [...current, atom];
    });
  };

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
    setUndoStack((items) => [...items, { label, snapshot }].slice(-30));
    setRedoStack([]);
  };

  const undoEditor = () => {
    setUndoStack((items) => {
      if (!items.length) return items;
      const next = [...items];
      const entry = next.pop();
      if (!entry) return items;
      setRedoStack((redo) => [...redo, { label: entry.label, snapshot: editorSnapshot() }].slice(-30));
      restoreEditorSnapshot(entry.snapshot);
      addLog("undo", entry.label);
      return next;
    });
  };

  const redoEditor = () => {
    setRedoStack((items) => {
      if (!items.length) return items;
      const next = [...items];
      const entry = next.pop();
      if (!entry) return items;
      setUndoStack((undo) => [...undo, { label: entry.label, snapshot: editorSnapshot() }].slice(-30));
      restoreEditorSnapshot(entry.snapshot);
      addLog("redo", entry.label);
      return next;
    });
  };

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
    void loadBenchmarkAssets();
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
      const created = await api<SessionRecord>("/api/v1/sessions", {
        method: "POST",
        body: JSON.stringify({ title: "Design DB exploration", user_id: "local-dev" }),
      });
      activeSession = created;
      window.localStorage.setItem(SESSION_STORAGE_KEY, created.session_id);
      setSession(created);
      setStage(created.stage);
      const createdAsset: AssetRecord | null = null;
      setCanvasPrimitive(null);
      setCanvasDisplayMode("textured");
      setCanvasTool("select");
      setAsset(createdAsset);
      setParts(createdAsset?.parts ?? []);
      setSelectedPart(createdAsset?.parts[0]?.part_id ?? "");
      setSelectedBenchmarkId("");
      addLog("session", "blank start; choose a Design DB model or upload refs");
    }
    setWorkspaceStartedAt(new Date().toISOString());
    setWorkspaceChromeReady(true);
    void refreshRemoteHealth();
    void loadCaseLibrary();
    void loadIntentDrafts(activeSession.session_id);
    void loadSolutionSpace(activeSession.session_id);

    const ws = new WebSocket(`${WS_BASE}/ws/sessions/${activeSession.session_id}`);
    socketRef.current = ws;
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      addLog(message.type, message.payload?.primary_intent ?? message.payload?.message ?? "received");
      if (message.type === "stage_update") setStage(message.payload);
      if (message.type === "live_signals_updated") {
        applyServerLiveSignals(message.payload?.live_signals as Partial<LiveSignals> | undefined);
      }
      if (message.type === "interaction_interpretation" && !isSilentObservationInterpretation(message.payload)) {
        setInterpretation(message.payload);
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
      if (message.type === "planner_interpretation_decision") {
        setPlannerDecision((current) => ({
          interpretation_id: message.payload?.interpretation_id ?? current?.interpretation_id ?? "",
          session_id: activeSession.session_id,
          decision: message.payload?.decision ?? current?.decision ?? "accepted",
          event_id: message.payload?.event_id ?? current?.event_id ?? "",
          memory_id: message.payload?.memory_id ?? current?.memory_id ?? "",
          updated_stage: current?.updated_stage ?? activeSession.stage,
        }));
      }
      if (message.type === "case_saved") addLog("case", message.payload?.case_id ?? "saved");
      if (message.type === "intent_draft_saved") {
        const draft = message.payload as IntentDraft;
        setIntentDrafts((current) => upsertIntentDraft(current, draft));
        setActiveIntentDraft(draft);
      }
      if (message.type === "reference_image_attached") {
        const artifact = message.payload?.artifact as ArtifactRecord | undefined;
        if (artifact?.artifact_id) {
          setReferenceImages((current) => upsertArtifact(current, artifact));
        }
      }
      if (message.type === "cross_domain_directions") {
        const payload = message.payload as CrossDomainDivergenceResponse;
        setCrossDomainDirections(payload.directions ?? []);
        setCrossDomainMetadata(payload.metadata ?? null);
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
    ws.onopen = () => addLog("websocket", "connected");
    ws.onerror = () => addLog("websocket", "connection error");
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
  const moreCreativeMode: "visual_inspiration" | "prompt_tokens" =
    intentText.trim().length >= 2 ||
    intentBubble.status === "accepted" ||
    plannerDecision?.decision === "accepted" ||
    selectedPromptTokens.length > 0 ||
    crossDomainDirections.length > 0
      ? "prompt_tokens"
      : "visual_inspiration";

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
        setHoverLabel(null);
        hoverLabelRef.current = null;
        if (hoverDwellTimerRef.current) {
          window.clearTimeout(hoverDwellTimerRef.current);
          hoverDwellTimerRef.current = null;
        }
      }
      return;
    }
    if (part.part_id !== selectedPart) setSelectedPart(part.part_id);
    if (source === "hover") {
      const switched = hoverLabelRef.current !== part.label;
      setHoverLabel(part.label);
      hoverLabelRef.current = part.label;
      setLiveSignals((current) => ({
        ...current,
        hover_count: current.hover_count + (switched ? 1 : 0),
        dwell_ms: Math.max(current.dwell_ms, switched ? 250 : current.dwell_ms + 250),
      }));
      setLivePerception({
        summary: `User is focusing on ${part.label}.`,
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

  const requestViewportSamForHover = async (part: PartRecord) => {
    if (!session || !asset || hoverSamBusy) return;
    setHoverSamBusy(true);
    try {
      const response = await api<{
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
          point: { x: 0.5, y: 0.45 },
          viewport: { width: 1280, height: 720, camera: canvasDisplayMode },
          metadata: {
            source: "hover_tentative_label",
            semantic_source:
              part.metadata?.source === "obj_group_fallback"
                ? "obj_group_projected_hover"
                : "projected_hover_tentative",
          },
        }),
      });
      if (typeof response.result?.mask_coverage === "number") {
        updateLiveSignals({ mask_coverage: response.result.mask_coverage });
      }
      addLog(
        "viewport sam",
        response.mask_url
          ? `${part.label} mask ready (${response.adapter ?? "viewport_sam"})`
          : response.result?.note ?? response.status,
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
  const canShowSolutionSpace = Boolean(hasRealModel);
  const canShowBrush = Boolean(hasRealModel && creativeflowReady && editablePartsReady);
  const canShowDrag = Boolean(hasRealModel && creativeflowReady);
  const canShowSculpt = Boolean(hasRealModel && geometryReady);
  const hasRunnableAction = canShowSolutionSpace || canShowBrush || canShowDrag || canShowSculpt;
  const visibleCandidates = candidates.filter(
    (candidate) =>
      candidate.thumbnail_url ||
      candidate.mesh_url ||
      candidate.obj_url ||
      candidate.metadata.remote_image_url ||
      candidate.metadata.remote_result_path,
  );
  const solutionSpaceIsHistory = Boolean(crossDomainMetadata?.restored_from_solution_space);
  const liveSolutionSpaceVisible = Boolean(
    !solutionSpaceIsHistory && !solutionSpaceReleased && (visibleCandidates.length || job || solutionSpaceGenerating),
  );
  const solutionSpaceComparing = Boolean(
    liveSolutionSpaceVisible && !solutionSpaceGenerating && visibleCandidates.length > 0,
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
      } else if (observed.state !== "ready_for_help") {
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
    const shouldOffer =
      !blockedByCooldown &&
      !blockedByGeneration &&
      !blockedByCompare &&
      !onlyOrbiting &&
      intentBubble.status !== "accepted" &&
      (creativeState === "ready_for_help" || (typedScopeAmbiguous && irConfidence >= 0.7));

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
    intentText,
    interpretation,
    activeSelectedPart,
    selectedPart,
    intentBubble.visible,
    intentBubble.status,
  ]);

  // Bubble auto-ignore after 10s.
  useEffect(() => {
    if (!intentBubble.visible || intentBubble.status !== "pending" || !intentBubble.shownAt) return undefined;
    const remain = Math.max(0, 10_000 - (Date.now() - intentBubble.shownAt));
    const timer = window.setTimeout(() => {
      bubbleCooldownUntilRef.current = Date.now() + 30_000;
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

  // Right-panel planner line: debounce signal-driven narration, then type it out.
  useEffect(() => {
    const intentKey = intentText.trim();
    const intentChanged = plannerNarrationIntentRef.current !== intentKey;
    const urgent = Boolean(intentChanged || solutionSpaceGenerating || generationBusy || intentBubble.status === "pending");
    if (intentChanged) plannerNarrationIntentRef.current = intentKey;
    const next = buildPlannerNarration({
      perceptionSummary: livePerception.summary,
      creativeState,
      hasModel: Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive),
      partLabel: inferChangeScopeFromText(intentText) === "part" ? activeSelectedPart?.label ?? null : null,
      intentText,
      bubbleScope: intentBubble.scope,
      bubbleStatus: intentBubble.status,
      moreCreativeMode,
      signals: liveSignals,
      generating: solutionSpaceGenerating || generationBusy,
    });
    if (next === plannerNarration) return undefined;
    const now = Date.now();
    if (!urgent && now - plannerNarrationLastAtRef.current < 8000) return undefined;
    if (plannerNarrationTimerRef.current) window.clearTimeout(plannerNarrationTimerRef.current);
    plannerNarrationTimerRef.current = window.setTimeout(() => {
      plannerNarrationLastAtRef.current = Date.now();
      setPlannerNarration(next);
    }, urgent ? 700 : 2400);
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
    moreCreativeMode,
    liveSignals,
    solutionSpaceGenerating,
    generationBusy,
    plannerNarration,
  ]);

  useEffect(() => {
    setPlannerTypedText("");
    if (!plannerNarration) return undefined;
    let index = 0;
    const timer = window.setInterval(() => {
      index += 1;
      setPlannerTypedText(plannerNarration.slice(0, index));
      if (index >= plannerNarration.length) window.clearInterval(timer);
    }, 46);
    return () => window.clearInterval(timer);
  }, [plannerNarration]);

  const solutionSpaceSignature = `${visibleCandidates.map((item) => item.candidate_id).join(",")}|${crossDomainDirections.map((item) => item.direction_id).join(",")}|${job?.job_id ?? ""}|${job?.status ?? ""}`;
  const segmentationPreviewUrl = partSegmentationUrl(parts);
  const analysisPreviewUrl =
    (canvasDisplayMode === "parts" || canvasDisplayMode === "heatmap") && segmentationPreviewUrl
      ? segmentationPreviewUrl
      : null;
  const activePreviewUrl = analysisPreviewUrl ?? canvasPreview?.url ?? previewCandidate?.mesh_url ?? previewCandidate?.obj_url ?? null;
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
    if (solutionSpaceIsHistory) return undefined;
    const hasStaticSuggestions = Boolean(visibleCandidates.length && !isActiveJobStatus(job?.status));
    if (!hasStaticSuggestions) {
      setSolutionSpaceReleased(false);
      return undefined;
    }
    setSolutionSpaceReleased(false);
    const shownAt = Date.now();
    const timer = window.setTimeout(() => {
      if (solutionSpaceTouchedAt < shownAt) setSolutionSpaceReleased(true);
    }, 18000);
    return () => window.clearTimeout(timer);
  }, [solutionSpaceSignature, solutionSpaceTouchedAt, solutionSpaceIsHistory]);

  useEffect(() => {
    if (!job?.job_id || job.job_id.startsWith("local_pending_") || !isActiveJobStatus(job.status)) return;
    const sourceSeq = jobSourceSeqRef.current[job.job_id] ?? sourceSwitchSeqRef.current;
    const timer = window.setInterval(() => {
      void refreshJob(job.job_id, sourceSeq);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

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

  const loadIntentDrafts = async (sessionId = session?.session_id) => {
    if (!sessionId) return;
    try {
      const response = await api<IntentDraftListResponse>(`/api/v1/sessions/${sessionId}/intent-drafts`);
      setIntentDrafts(response.drafts);
      setActiveIntentDraft(response.drafts.find((item) => item.status === "draft") ?? response.drafts[0] ?? null);
    } catch (error) {
      addLog("intent drafts", String(error));
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
      setCrossDomainDirections(response.directions ?? []);
      setCrossDomainMetadata((current) => current ?? { restored_from_solution_space: true });
      setSolutionSpaceReleased(true);
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

  const switchBenchmarkAsset = async (benchmarkId: string) => {
    if (!session || !benchmarkId || loadingBenchmark) return;
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
    } catch (error) {
      addLog("benchmark", String(error));
    } finally {
      setLoadingBenchmark(false);
    }
  };

  const startBlankWorkspace = () => {
    pushEditorHistory("start blank workspace");
    resetSourceDependentState("Blank workspace. Load a model, add a primitive, or type an intent.");
    setSelectedBenchmarkId("");
    setAsset(null);
    setParts([]);
    setSelectedPart("");
    addLog("blank", "text, reference images, and model refs can be composed before loading a mesh");
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
        tool_surface: "3d",
        live_signals: nextLiveSignals,
      },
    );
    return brushMaskArtifact;
  };

  const sendDrag = async (response?: GeometryWorkerResponse | null) => {
    if (!asset) return null;
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
    sendEvent("drag_end", {
      asset_id: asset.asset_id,
      part_id: selectedPart,
      selected_part_label: activeSelectedPart?.label ?? null,
      intent_text: intentText,
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
    if (activeSelectedPart) void requestViewportSamForHover(activeSelectedPart);
  };

  const toggleHoverMode = () => {
    if (!asset) return;
    if (!hoverMode) {
      setHoverMode(true);
      incrementLiveSignal("tool_switch_count");
      addLog("hover", "mode on — raycast tentative labels; click again or dwell to commit");
      return;
    }
    if (hoverLabelRef.current || activeSelectedPart) {
      void commitHoverFocus("toolbar_click");
      return;
    }
    setHoverMode(false);
    setHoverLabel(null);
    hoverLabelRef.current = null;
    hoverCommittedRef.current = null;
    addLog("hover", "mode off");
  };

  const recordAnnotation = async (strokes?: AnnotationStroke[]) => {
    if (!asset) return;
    const annotationPayload = buildAnnotationPayload({
      sessionId: session?.session_id ?? "",
      asset,
      partId: selectedPart || null,
      partLabel: activeSelectedPart?.label ?? null,
      text: intentText,
      displayMode: canvasDisplayMode,
      strokes,
    });
    let annotationArtifact: ArtifactRecord | null = null;
    try {
      annotationArtifact = await api<ArtifactRecord>("/api/v1/annotations", {
        method: "POST",
        body: JSON.stringify(annotationPayload),
      });
    } catch (error) {
      addLog("annotation artifact", String(error).slice(0, 160));
    }
    const nextLiveSignals = {
      ...liveSignals,
      drawing_content: intentText.trim() || "freehand_contour",
      annotation_count: liveSignals.annotation_count + 1,
    };
    setLiveSignals(nextLiveSignals);
    setLivePerception({
      summary: "User is drawing on the silhouette.",
      evidence: [
        `${annotationPayload.strokes.length} 2D pencil stroke${annotationPayload.strokes.length > 1 ? "s" : ""}`,
        String(annotationPayload.metadata.inferred_shape ?? "freehand_contour"),
      ],
      confidence: 0.82,
      source: "local",
      updatedAt: new Date().toISOString(),
    });
    setCreativeStagePreset("silhouette");
    recordActionAtom(
      "annotation",
      {
        asset_id: asset.asset_id,
        part_id: selectedPart || null,
        annotation_artifact_id: annotationArtifact?.artifact_id ?? null,
      },
      {
        annotation_mode: "2d_pencil",
        text: intentText,
        stroke_url: annotationArtifact?.url ?? null,
        annotation_artifact_id: annotationArtifact?.artifact_id ?? null,
        annotation_shape: "freehand_contour",
        stroke_count: annotationPayload.strokes.length,
        stroke_points: annotationPayload.strokes.flatMap((stroke) => stroke.points ?? []),
        stroke_point_count: annotationPayload.strokes.reduce((sum, stroke) => sum + (stroke.points?.length ?? 0), 0),
        projection: annotationPayload.projection,
        live_signals: nextLiveSignals,
      },
    );
    sendEvent("annotation_commit", {
      asset_id: asset.asset_id,
      part_id: selectedPart || null,
      annotation_text: intentText,
      artifact_id: annotationArtifact?.artifact_id ?? null,
      stroke_url: annotationArtifact?.url ?? null,
      annotation_shape: "freehand_contour",
      stroke_count: annotationPayload.strokes.length,
      stroke_point_count: annotationPayload.strokes.reduce((sum, stroke) => sum + (stroke.points?.length ?? 0), 0),
      projection: annotationPayload.projection,
      live_signals: nextLiveSignals,
    });
    addLog("annotation", annotationArtifact?.artifact_id ?? (intentText || "2D mark"));
  };

  const recordAddPrimitive = async (
    primitiveOverride?: Exclude<CanvasPrimitive, null>,
    response?: GeometryWorkerResponse | null,
  ) => {
    const primitive = primitiveOverride ?? canvasPrimitive ?? "sphere";
    if (!asset && !primitiveOverride && !canvasPrimitive) return;
    const primitivePayload = buildPrimitiveAdditionPayload({
      sessionId: session?.session_id ?? "",
      asset,
      partId: selectedPart || null,
      partLabel: activeSelectedPart?.label ?? null,
      primitive,
      text: intentText,
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
    });
    addLog("add", primitiveArtifact?.artifact_id ?? `${primitive} intent`);
  };

  const runCreativeSolutionSpace = () => {
    if (!session || !asset || generationBusy || solutionSpaceGenerating) return;
    setSolutionSpaceReleased(false);
    setSolutionSpaceGenerating(true);
    setSolutionSpaceTouchedAt(Date.now());
    setJob((current) =>
      current ?? {
        job_id: `local_pending_${Date.now()}`,
        session_id: session?.session_id ?? "",
        mode: "diverge",
        status: "running",
        stage: "queued",
        candidate_ids: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        error: null,
      },
    );
    const stageForSolutionSpace = creativeStage === "part" ? "rough_form" : creativeStage;
    void requestGeneration("diverge", {
      stage: stageForSolutionSpace,
      fidelity: defaultFidelityForStage(stageForSolutionSpace),
      metadata: {
        assistance_trigger: "primary_creative_solution_space",
      },
    }).catch((error) => {
      setSolutionSpaceGenerating(false);
      setJob(null);
      addLog("generation", String(error).slice(0, 160));
    });
  };

  const runBrushAction = async () => {
    if (!asset || !canShowBrush) return;
    const sourceMeshUrl = asset.mesh_url ?? asset.obj_url;
    let brushPart = activeSelectedPart;
    if (!brushPart) {
      const discovery = await discoverPartsForAsset(asset, "brush");
      brushPart = discovery?.parts[0] ?? brushPart;
    }
    if (brushPart) setSelectedPart(brushPart.part_id);
    const brushMaskArtifact = await sendBrush(brushPart ?? undefined);
    setCreativeStagePreset("part");
    if (!session || !sourceMeshUrl || !geometryReady) return;
    setSculptBusy("clay");
    try {
      const response = await api<GeometryWorkerResponse>("/api/v1/geometry/deform-preview", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset.asset_id,
          source_mesh_url: sourceMeshUrl,
          part: brushPart ?? undefined,
          options: {
            tool: "draw",
            sculpt_tool: "draw",
            radius: 0.36,
            strength: 0.48,
            preserve_boundary: true,
            display_name: "Draw brush preview",
            brush_mask_artifact_id: brushMaskArtifact?.artifact_id ?? null,
            brush_mask_url: brushMaskArtifact?.url ?? null,
          },
        }),
      });
      if (!response.ok || !response.preview_mesh_url) {
        throw new Error(response.error?.message ?? "Draw brush preview failed");
      }
      setPreviewCandidate(null);
      setCanvasPreview({
        url: response.preview_mesh_url,
        label: "Draw brush preview",
      });
      addLog("brush", `draw ${response.job_id}`);
    } catch (error) {
      addLog("brush", String(error).slice(0, 160));
    } finally {
      setSculptBusy(null);
    }
  };

  const runDragAction = async () => {
    if (!canShowDrag) return;
    await runSculptPreview("move");
  };

  const createPrimitive = async (primitive: Exclude<CanvasPrimitive, null>) => {
    incrementLiveSignal("new_case_attempt_rate");
    incrementLiveSignal("tool_switch_count");
    const sourceMeshUrl = asset?.mesh_url ?? asset?.obj_url;
    if (!session || !asset || !sourceMeshUrl || !geometryReady) {
      setCanvasPrimitive(primitive);
      setAsset(null);
      setParts([]);
      setSelectedPart("");
      setCandidates([]);
      setCrossDomainDirections([]);
      setCrossDomainMetadata(null);
      setPreviewCandidate(null);
      setCanvasPreview(null);
      handleDisplayModeChange("clay");
      setCanvasTool("clay");
      await recordAddPrimitive(primitive, null);
      addLog("primitive", primitive);
      return;
    }
    setSculptBusy("clay");
    try {
      const primitivePayload = buildPrimitiveAdditionPayload({
        sessionId: session.session_id,
        asset,
        partId: selectedPart || null,
        partLabel: activeSelectedPart?.label ?? null,
        primitive,
        text: intentText,
      });
      const response = await api<GeometryWorkerResponse>("/api/v1/geometry/add-primitive", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset.asset_id,
          source_mesh_url: sourceMeshUrl,
          part: activeSelectedPart ?? undefined,
          options: {
            primitive,
            transform: primitivePayload.transform,
            relation: primitivePayload.relation,
          },
        }),
      });
      if (!response.ok || !response.preview_mesh_url) {
        throw new Error(response.error?.message ?? "Add primitive preview failed");
      }
      setCanvasPrimitive(null);
      setPreviewCandidate(null);
      setCanvasPreview({
        url: response.preview_mesh_url,
        label: `Add ${primitive} preview`,
      });
      handleDisplayModeChange("clay");
      setCanvasTool("clay");
      await recordAddPrimitive(primitive, response);
      addLog("primitive", `${primitive} ${response.job_id}`);
    } catch (error) {
      addLog("primitive", String(error).slice(0, 160));
    } finally {
      setSculptBusy(null);
    }
  };

  const runSculptPreview = async (tool: Exclude<CanvasTool, "select">) => {
    if (!session || !asset || !geometryReady || sculptBusy) return;
    const sourceMeshUrl = asset.mesh_url ?? asset.obj_url;
    if (!sourceMeshUrl) return;
    if (tool !== canvasTool) incrementLiveSignal("tool_switch_count");
    setCanvasTool(tool);
    setCanvasDisplayMode("clay");
    setSculptBusy(tool);
    try {
      const sculptTool = tool === "move" ? "grab" : "plateau";
      const transform =
        tool === "move"
          ? { scale: 1.0, translation: [0.12, 0.0, 0.0] }
          : { scale: 1.0, translation: [0.0, 1.0, 0.0] };
      const response = await api<GeometryWorkerResponse>("/api/v1/geometry/deform-preview", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset.asset_id,
          source_mesh_url: sourceMeshUrl,
          part: activeSelectedPart ?? undefined,
          options: {
            transform,
            tool: sculptTool,
            sculpt_tool: sculptTool,
            radius: tool === "move" ? 0.45 : 0.38,
            strength: tool === "move" ? 0.75 : 0.62,
            preserve_boundary: true,
            display_name: tool === "clay" ? "Plateau preview" : "Grab preview",
          },
        }),
      });
      if (!response.ok || !response.preview_mesh_url) {
        throw new Error(response.error?.message ?? "Geometry preview failed");
      }
      setPreviewCandidate(null);
      setCanvasPreview({
        url: response.preview_mesh_url,
        label: tool === "clay" ? "Plateau preview" : "Grab preview",
      });
      let smoothOperationArtifact: ArtifactRecord | null = null;
      let smoothOperationPayload: ReturnType<typeof buildSmoothOperationPayload> | null = null;
      let dragOperationArtifact: ArtifactRecord | null = null;
      let dragOperationPayload: ReturnType<typeof buildDragOperationPayload> | null = null;
      if (tool === "clay") {
        smoothOperationPayload = buildSmoothOperationPayload({
          sessionId: session.session_id,
          asset,
          part: activeSelectedPart,
          partId: selectedPart || null,
          text: intentText,
          displayMode: canvasDisplayMode,
          response,
        });
        try {
          smoothOperationArtifact = await api<ArtifactRecord>("/api/v1/smooth-operations", {
            method: "POST",
            body: JSON.stringify(smoothOperationPayload),
          });
        } catch (error) {
          addLog("smooth artifact", String(error).slice(0, 160));
        }
        sendEvent("smooth_end", {
          asset_id: asset.asset_id,
          part_id: selectedPart || null,
          selected_part_label: activeSelectedPart?.label ?? null,
          intent_text: intentText,
          smooth_operation_artifact_id: smoothOperationArtifact?.artifact_id ?? null,
          smooth_operation_url: smoothOperationArtifact?.url ?? null,
          smooth_region: smoothOperationPayload.region,
          smooth_strength: smoothOperationPayload.parameters.strength,
          smooth_brush_radius: smoothOperationPayload.brush.radius,
          smooth_preserve_boundary: smoothOperationPayload.parameters.preserve_boundary,
          smooth_preview_mesh_url: response.preview_mesh_url,
          smooth_geometry_job_id: response.job_id,
        });
      } else if (tool === "move") {
        dragOperationPayload = buildDragOperationPayload({
          sessionId: session.session_id,
          asset,
          part: activeSelectedPart,
          partId: selectedPart || null,
          text: intentText,
          response,
        });
        try {
          dragOperationArtifact = await api<ArtifactRecord>("/api/v1/drag-operations", {
            method: "POST",
            body: JSON.stringify(dragOperationPayload),
          });
        } catch (error) {
          addLog("drag artifact", String(error).slice(0, 160));
        }
        sendEvent("drag_end", {
          asset_id: asset.asset_id,
          part_id: selectedPart || null,
          selected_part_label: activeSelectedPart?.label ?? null,
          intent_text: intentText,
          drag_operation_artifact_id: dragOperationArtifact?.artifact_id ?? null,
          drag_operation_url: dragOperationArtifact?.url ?? null,
          drag_preview_mesh_url: response.preview_mesh_url,
          drag_geometry_job_id: response.job_id,
          drag: dragOperationPayload.drag,
          region: dragOperationPayload.region,
        });
      }
      recordActionAtom(
        tool === "clay" ? "smooth" : "drag",
        { asset_id: asset.asset_id, part_id: selectedPart || null, label: activeSelectedPart?.label ?? null },
        {
          geometry_job_id: response.job_id,
          preview_mesh_url: response.preview_mesh_url,
          smooth_operation_artifact_id: smoothOperationArtifact?.artifact_id ?? null,
          smooth_operation_url: smoothOperationArtifact?.url ?? null,
          smooth_strength: smoothOperationPayload?.parameters.strength ?? null,
          smooth_brush_radius: smoothOperationPayload?.brush.radius ?? null,
          preserve_boundary: smoothOperationPayload?.parameters.preserve_boundary ?? null,
          drag_operation_artifact_id: dragOperationArtifact?.artifact_id ?? null,
          drag_operation_url: dragOperationArtifact?.url ?? null,
          drag_vector: dragOperationPayload?.drag.vector ?? null,
          drag_length: dragOperationPayload?.metrics.drag_length ?? null,
        },
      );
      addLog("sculpt", `${tool} ${response.job_id}`);
    } catch (error) {
      addLog("sculpt", String(error));
    } finally {
      setSculptBusy(null);
    }
  };

  const submitPlannerChat = async () => {
    if (!session || !chatInput.trim() || plannerBusy) return;
    const text = chatInput.trim();
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text,
    };
    setChatMessages((items) => [...items, userMessage]);
    setChatInput("");
    setPlannerBusy(true);
    try {
      const interpreted = await api<Interpretation>("/api/v1/interaction/interpret", {
        method: "POST",
        body: JSON.stringify({
          type: "intent_text_changed",
          event_id: `evt_${crypto.randomUUID().slice(0, 8)}`,
          session_id: session.session_id,
          timestamp: new Date().toISOString(),
          payload: {
            text,
            intent_text: text,
            asset_id: asset?.asset_id ?? null,
            active_asset_id: asset?.asset_id ?? null,
            part_id: selectedPart || null,
            selected_part_label: activeSelectedPart?.label ?? null,
            canvas_tool: canvasTool,
            canvas_display_mode: canvasDisplayMode,
            primitive: canvasPrimitive,
            image_refs: referenceImages.map((item) => item.url),
            reference_images: referenceImagesPayload(referenceImages),
            candidates: visibleCandidates.slice(0, 6).map((candidate) => ({
              candidate_id: candidate.candidate_id,
              label: candidate.label,
              stage: candidateStage(candidate),
              has_image: Boolean(candidatePreviewUrl(candidate)),
              has_mesh: Boolean(candidate.mesh_url || candidate.obj_url),
              scores: candidate.scores,
              evidence: pipelineEvidence(candidate),
            })),
            signals: {
              interaction: { mode: "chat", tool: canvasTool, display: canvasDisplayMode },
              semantic: {
                prompt: text,
                object_type: asset?.object_type,
                image_ref_count: referenceImages.length,
              },
              history: { candidate_count: visibleCandidates.length, accepted: acceptedCandidateIds },
            },
          },
        }),
      });
      setInterpretation(interpreted);
      const plannerText = plannerReply(interpreted);
      setChatMessages((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "planner",
          text: plannerText,
          candidateIds: visibleCandidates.map((candidate) => candidate.candidate_id),
        },
      ]);
    } catch (error) {
      setChatMessages((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "planner",
          text: `Planner unavailable: ${String(error).slice(0, 180)}`,
        },
      ]);
    } finally {
      setPlannerBusy(false);
    }
  };

  const applyAnalogyDirections = (
    directions: AnalogyDirection[],
    metadata: Record<string, unknown> | null | undefined,
    source: "directions_suggest" | "cross_domain",
  ) => {
    setCrossDomainDirections(cleanAnalogyDirections(directions));
    setCrossDomainMetadata({
      ...(metadata ?? {}),
      planner_source: source,
      status: "confirmed",
    });
    setSelectedPromptTokens([]);
    updateLiveSignals({
      semantic_distance: Math.min(1, Math.max(liveSignals.semantic_distance, directions.length / 10)),
    });
    addLog(
      source === "directions_suggest" ? "suggest directions" : "analogy words",
      `${analogyPromptTokens(directions).length} selectable tokens`,
    );
  };

  const applyInstantDirectionSeeds = (current: Interpretation | null) => {
    if (!asset) return;
    applyAnalogyDirections(
      buildLocalAnalogyDirections(asset, current, intentText, activeSelectedPart),
      { trigger: "instant_planner_accept", local_fast_path: true },
      "directions_suggest",
    );
  };

  const preferredSuggestDimensions = (
    current: Interpretation | null,
    scopeOverride?: BubbleScope | null,
  ): Array<"aesthetic" | "functional" | "structural"> => {
    const scope = scopeOverride ?? (current ? inferredChangeScope(current, activeSelectedPart?.label ?? selectedPart) : inferChangeScopeFromText(intentText));
    if (current) {
      if (scope === "material") return ["aesthetic"];
      if (scope === "part") return ["functional", "structural"];
      return ["structural", "aesthetic"];
    }
    const axes = (current?.features?.design_state_ir?.recommended_axes ?? [])
      .map((axis) => String(axis).trim().toLowerCase())
      .filter((axis): axis is "aesthetic" | "functional" | "structural" =>
        axis === "aesthetic" || axis === "functional" || axis === "structural",
      );
    if (axes.length) return Array.from(new Set(axes)).slice(0, 3);
    const scored = [...(current?.features?.design_state_ir?.axis_scores ?? [])]
      .sort((a, b) => b.score - a.score)
      .map((item) => String(item.axis).trim().toLowerCase())
      .filter((axis): axis is "aesthetic" | "functional" | "structural" =>
        axis === "aesthetic" || axis === "functional" || axis === "structural",
      );
    if (scored.length) return Array.from(new Set(scored)).slice(0, 2);
    return ["aesthetic", "structural"];
  };

  const runDirectionsSuggest = async (
    currentInterpretation: Interpretation | null = interpretation,
    scopeOverride?: BubbleScope | null,
  ) => {
    if (!session || !asset) return;
    const requestSeq = ++directionsRequestSeqRef.current;
    const scope = scopeOverride ?? (currentInterpretation ? inferredChangeScope(currentInterpretation, activeSelectedPart?.label ?? selectedPart) : inferChangeScopeFromText(intentText));
    setCrossDomainBusy(true);
    try {
      const draftId = activeIntentDraft?.status !== "archived" ? activeIntentDraft?.draft_id ?? null : null;
      const response = await api<DirectionsSuggestResponse>("/api/v1/directions/suggest", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset.asset_id,
          intent_draft_id: draftId,
          interpretation_id: currentInterpretation?.interpretation_id ?? null,
          preserved_constraints: [
            "preserve object identity",
            "preserve confirmed edits",
            "do not overwrite protected regions",
          ],
          dimensions: preferredSuggestDimensions(currentInterpretation, scope),
          direction_count: 6,
          scope: {
            type: scope === "part" && selectedPart ? "part" : "whole_object",
            part_id: scope === "part" ? selectedPart || null : null,
          },
          context_snapshot_id: `ctx_${Date.now()}`,
          minimum_semantic_distance: 0.55,
          metadata: {
            trigger: "planner_intent_accepted",
            change_scope: scope,
            live_signals: liveSignals,
            primary_intent: currentInterpretation?.primary_intent ?? null,
            ir_recommended_axes: currentInterpretation?.features?.design_state_ir?.recommended_axes ?? [],
          },
          live_signals: liveSignals,
        }),
      });
      if (requestSeq !== directionsRequestSeqRef.current) return;
      applyAnalogyDirections(
        response.directions ?? [],
        { ...(response.metadata ?? {}), change_scope: scope },
        "directions_suggest",
      );
    } catch (error) {
      if (requestSeq !== directionsRequestSeqRef.current) return;
      addLog("directions suggest", String(error));
    } finally {
      if (requestSeq === directionsRequestSeqRef.current) setCrossDomainBusy(false);
    }
  };

  useEffect(() => {
    const text = intentText.trim();
    if (!typedIntentStable || !asset || text.length < 3) return;
    const key = `${asset.asset_id}:${text}`;
    if (typedIntentDivergenceKeyRef.current === key) return;
    typedIntentDivergenceKeyRef.current = key;
    const scope = inferChangeScopeFromText(text);
    setCrossDomainDirections([]);
    setSelectedPromptTokens([]);
    setCrossDomainMetadata({ trigger: "typed_intent_auto_diverge", status: "loading", change_scope: scope });
    void runDirectionsSuggest(interpretation, scope);
  }, [typedIntentStable, intentText, asset?.asset_id]);

  const decidePlannerInterpretation = async (
    decision: "accepted" | "rejected",
    surface = "ai_behavior_panel",
    clarificationLabel?: string,
  ) => {
    if (!session || plannerDecisionBusy) return;
    const scope = intentBubble.scope ?? (interpretation ? inferredChangeScope(interpretation, activeSelectedPart?.label ?? selectedPart) : "contour");
    if (decision === "accepted") {
      setIntentBubble({
        visible: false,
        scope,
        status: "accepted",
        shownAt: null,
      });
      applyAnalogyDirections(
        buildLocalAnalogyDirections(asset, interpretation, intentText, scope === "part" ? activeSelectedPart : null, scope),
        { trigger: "scope_bubble_accept", local_fast_path: true, change_scope: scope },
        "directions_suggest",
      );
      void runDirectionsSuggest(interpretation, scope);
    } else {
      const nextScope = nextBubbleScope(scope);
      bubbleCooldownUntilRef.current = Date.now() + 1500;
      setIntentBubble({
        visible: true,
        scope: nextScope,
        status: "pending",
        shownAt: Date.now(),
      });
    }
    if (!interpretation) {
      addLog("intent bubble", `${decision} ${scope} (local)`);
      return;
    }
    setPlannerDecisionBusy(decision);
    try {
      const response = await api<PlannerDecisionResponse>(
        `/api/v1/interpretations/${interpretation.interpretation_id}/decision`,
        {
          method: "POST",
          body: JSON.stringify({
            session_id: session.session_id,
            decision,
            reason:
              decision === "accepted"
                ? `User accepted change scope ${scope} from ${surface}`
                : `User rejected change scope ${scope} from ${surface}`,
            metadata: {
              surface,
              clarification_label: clarificationLabel ?? null,
              change_scope: scope,
              creative_state: creativeState,
              creative_state_confidence: creativeStateConfidence,
              primary_intent: interpretation.primary_intent,
              confidence: interpretation.confidence,
              ir_top_confidence: designStateMatches(interpretation)[0]?.confidence ?? null,
            },
          }),
        },
      );
      setPlannerDecision(response);
      setStage(response.updated_stage);
      addLog("planner gate", `${decision} ${scope} · ${interpretation.interpretation_id}`);
    } catch (error) {
      addLog("planner gate", String(error));
    } finally {
      setPlannerDecisionBusy(null);
    }
  };

  const saveIntentDraft = async () => {
    if (!session || intentBusy) return null;
    setIntentBusy(true);
    const behaviorAtoms = visibleBehaviorAtoms;
    try {
      const draft = await api<IntentDraft>("/api/v1/intent-drafts", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset?.asset_id ?? null,
          title: intentText.trim() || `${behaviorAtoms.length || 1} behavior intent`,
          text: intentText.trim() || null,
          behavior_atoms: behaviorAtoms,
          image_refs: referenceImages.map((item) => item.url),
          model_refs: [
            ...referenceModels.map((item) => item.url),
            ...(asset ? [asset.mesh_url ?? asset.obj_url ?? asset.asset_id].filter(Boolean) : []),
          ],
          metadata: {
            canvas_tool: canvasTool,
            canvas_display_mode: canvasDisplayMode,
            primitive: canvasPrimitive,
            behavior_count: behaviorAtoms.length,
            live_signals: liveSignals,
            reference_images: referenceImagesPayload(referenceImages),
            reference_models: referenceModelsPayload(referenceModels),
          },
        }),
      });
      setActiveIntentDraft(draft);
      setIntentDrafts((current) => upsertIntentDraft(current, draft));
      pushEditorHistory("save intent draft");
      setActionAtoms([]);
      addLog("intent draft", draft.draft_id);
      return draft;
    } catch (error) {
      addLog("intent draft", String(error));
      return null;
    } finally {
      setIntentBusy(false);
    }
  };

  const restoreIntentDraft = (draft: IntentDraft) => {
    if (visibleBehaviorAtoms.length && draft.draft_id !== activeIntentDraft?.draft_id) {
      const replacePending = window.confirm(
        `Restore this draft and replace ${visibleBehaviorAtoms.length} pending behavior(s)?`,
      );
      if (!replacePending) return;
    }
    pushEditorHistory("restore intent draft");
    setActiveIntentDraft(draft);
    setIntentText(draft.text ?? "");
    setActionAtoms(renumberActionAtoms(draft.behavior_atoms ?? []));
    setReferenceImages(
      artifactRecordsFromDraftRefs(
        draft.image_refs ?? [],
        draft.metadata?.reference_images,
        "reference_image",
      ),
    );
    const activeModelRef = asset ? [asset.mesh_url ?? asset.obj_url ?? asset.asset_id].filter(Boolean)[0] : null;
    const referenceModelUrls = (draft.model_refs ?? []).filter((url) => url !== activeModelRef);
    setReferenceModels(
      artifactRecordsFromDraftRefs(
        referenceModelUrls,
        draft.metadata?.reference_models,
        "reference_model",
      ),
    );
    addLog("draft restored", draft.draft_id);
  };

  const archiveIntentDraft = async (draft: IntentDraft) => {
    if (!session) return;
    try {
      const archived = await api<IntentDraft>(`/api/v1/intent-drafts/${draft.draft_id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "archived",
          metadata: {
            ...draft.metadata,
            archived_at: new Date().toISOString(),
            archived_from: "composer_draft_list",
          },
        }),
      });
      setIntentDrafts((current) => current.filter((item) => item.draft_id !== archived.draft_id));
      if (activeIntentDraft?.draft_id === archived.draft_id) setActiveIntentDraft(null);
      addLog("draft archived", archived.draft_id);
    } catch (error) {
      addLog("draft archive", String(error));
    }
  };

  const sendIntentDraft = async () => {
    if (!session || plannerBusy) return;
    let draft = activeIntentDraft;
    if (!draft || visibleBehaviorAtoms.length) {
      if (draft && visibleBehaviorAtoms.length) {
        const includePending = window.confirm(
          `Send will include ${visibleBehaviorAtoms.length} unsaved behavior(s) in this intent. Continue?`,
        );
        if (!includePending) return;
      }
      draft = await saveIntentDraft();
    }
    if (!draft) return;
    setPlannerBusy(true);
    try {
      const sentDraft = await api<IntentDraft>(`/api/v1/intent-drafts/${draft.draft_id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "sent",
          metadata: {
            sent_at: new Date().toISOString(),
            active_asset_id: asset?.asset_id ?? null,
          },
        }),
      });
      setActiveIntentDraft(sentDraft);
      const episode = await api<IntentEpisodeResponse>(`/api/v1/sessions/${session.session_id}/episodes`, {
        method: "POST",
        body: JSON.stringify({
          intent_draft_id: sentDraft.draft_id,
          behavior_atoms: sentDraft.behavior_atoms,
          text: sentDraft.text,
          image_refs: sentDraft.image_refs,
          model_refs: sentDraft.model_refs,
          context_snapshot_id: `ctx_${Date.now()}`,
          metadata: {
            active_asset_id: asset?.asset_id ?? null,
            source: "send_intent_button",
            live_signals: liveSignals,
          },
        }),
      });
      const interpreted = await api<Interpretation>("/api/v1/interaction/interpret", {
        method: "POST",
        body: JSON.stringify({
          type: "intent_episode_sent",
          event_id: `evt_${crypto.randomUUID().slice(0, 8)}`,
          session_id: session.session_id,
          timestamp: new Date().toISOString(),
          payload: {
            asset_id: asset?.asset_id ?? null,
            active_asset_id: asset?.asset_id ?? null,
            intent_draft_id: sentDraft.draft_id,
            episode_id: episode.episode_id,
            intent_text: sentDraft.text,
            behavior_atoms: sentDraft.behavior_atoms,
            behavior_count: sentDraft.behavior_atoms.length,
            image_refs: sentDraft.image_refs,
            reference_images: referenceImagesPayload(referenceImages),
            model_refs: sentDraft.model_refs,
            reference_models: referenceModelsPayload(referenceModels),
            selected_part_label: activeSelectedPart?.label ?? null,
            live_signals: liveSignals,
            signals: {
              interaction: { mode: "intent_episode", behavior_count: sentDraft.behavior_atoms.length, live_signals: liveSignals },
              semantic: {
                prompt: sentDraft.text,
                object_type: asset?.object_type,
                image_ref_count: sentDraft.image_refs.length,
                model_ref_count: sentDraft.model_refs.length,
              },
              history: { candidate_count: visibleCandidates.length, accepted: acceptedCandidateIds },
            },
          },
        }),
      });
      setInterpretation(interpreted);
      setChatMessages((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "planner",
          text: plannerReply(interpreted),
          candidateIds: visibleCandidates.map((candidate) => candidate.candidate_id),
        },
      ]);
      addLog("intent sent", sentDraft.draft_id);
    } catch (error) {
      addLog("intent send", String(error));
    } finally {
      setPlannerBusy(false);
    }
  };

  const runCrossDomainDivergence = async () => {
    if (!session || !asset || crossDomainBusy) return;
    setCrossDomainBusy(true);
    try {
      let draftForDivergence = activeIntentDraft?.status !== "archived" ? activeIntentDraft : null;
      let unsavedBehaviorPolicy: "none" | "included_as_constraints" | "left_pending" = visibleBehaviorAtoms.length
        ? "left_pending"
        : "none";
      if (visibleBehaviorAtoms.length) {
        const includePending = window.confirm(
          `Cross-domain Diverge found ${visibleBehaviorAtoms.length} unsaved behavior(s). Include them as constraints for this divergence?`,
        );
        if (includePending) {
          const savedDraft = await saveIntentDraft();
          if (!savedDraft) return;
          draftForDivergence = savedDraft;
          unsavedBehaviorPolicy = "included_as_constraints";
        }
      }
      const response = await api<CrossDomainDivergenceResponse>("/api/v1/directions/suggest", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          asset_id: asset.asset_id,
          intent_draft_id: draftForDivergence?.draft_id ?? null,
          interpretation_id: interpretation?.interpretation_id ?? null,
          source_summary: intentText.trim() || null,
          constraints: [
            "preserve confirmed edits",
            "do not overwrite protected regions",
            ...(unsavedBehaviorPolicy === "included_as_constraints"
              ? ["honor the included pending behavior atoms as current divergence constraints"]
              : []),
          ],
          candidate_count: 6,
          metadata: {
            trigger: "composer_cross_domain_button",
            behavior_count: draftForDivergence?.behavior_atoms.length ?? visibleBehaviorAtoms.length,
            unsaved_behavior_policy: unsavedBehaviorPolicy,
            pending_behavior_count_at_trigger: visibleBehaviorAtoms.length,
            included_behavior_atom_ids:
              unsavedBehaviorPolicy === "included_as_constraints"
                ? draftForDivergence?.behavior_atoms.map((atom) => atom.atom_id) ?? []
                : [],
            excluded_pending_behavior_atom_ids:
              unsavedBehaviorPolicy === "left_pending" ? visibleBehaviorAtoms.map((atom) => atom.atom_id) : [],
            image_refs: referenceImages.map((item) => item.url),
            reference_images: referenceImagesPayload(referenceImages),
            local_planner_gate: plannerDecision
              ? {
                  decision: plannerDecision.decision,
                  interpretation_id: plannerDecision.interpretation_id,
                  event_id: plannerDecision.event_id,
                }
              : null,
            live_signals: liveSignals,
          },
        }),
      });
      applyAnalogyDirections(response.directions, response.metadata ?? null, "cross_domain");
    } catch (error) {
      addLog("cross-domain", String(error));
    } finally {
      setCrossDomainBusy(false);
    }
  };

  const togglePromptToken = (token: PromptToken) => {
    pushEditorHistory(`toggle ${token.label}`);
    const key = promptTokenKey(token);
    setSelectedPromptTokens((current) => {
      const exists = current.some((item) => promptTokenKey(item) === key);
      const next = exists ? current.filter((item) => promptTokenKey(item) !== key) : [...current, token];
      setIntentText((text) => composePromptWithTokens(text, next));
      updateLiveSignals({ semantic_distance: Math.min(1, next.length / 6) });
      return next;
    });
  };

  const requestGeneration = async (
    mode: "replace" | "drag_regenerate" | "diverge",
    overrides?: {
      stage?: string;
      fidelity?: string;
      metadata?: Record<string, unknown>;
      part?: PartRecord;
    },
  ) => {
    if (!session || !asset) return;
    const requestAssetId = stage?.active_asset_id ?? asset.asset_id;
    const endpoint =
      mode === "replace" ? "replace" : mode === "drag_regenerate" ? "drag" : "diverge";
    const requestStage = overrides?.stage ?? creativeStage;
    const requestFidelity = overrides?.fidelity ?? creativeFidelity;
    const partScoped = requestStage === "part";
    const effectivePart = overrides?.part ?? activeSelectedPart;
    const effectivePartId = effectivePart?.part_id ?? selectedPart;
    const partMetadata = effectivePart?.metadata ?? {};
    let analogyPromptPackage: Record<string, unknown> = buildAnalogyPromptPackage(
      intentText,
      selectedPromptTokens,
      crossDomainDirections,
    );
    let promptComposeEvidence: Record<string, unknown> | null = null;
    if (selectedPromptTokens.length) {
      try {
        const composed = await api<PromptComposeResponse>("/api/v1/prompt/compose", {
          method: "POST",
          body: JSON.stringify({
            session_id: session.session_id,
            asset_id: requestAssetId,
            base_prompt: intentText,
            selected_prompt_tokens: selectedPromptTokens,
            direction_ids: analogyPromptPackage.direction_ids ?? [],
            intent_draft_id: activeIntentDraft?.draft_id ?? null,
            metadata: {
              source: "generation_request",
              stage: requestStage,
              fidelity: requestFidelity,
              live_signals: liveSignals,
            },
          }),
        });
        analogyPromptPackage = composed.analogy_prompt_package;
        promptComposeEvidence = {
          event_id: composed.event_id,
          memory_id: composed.memory_id,
          source: "backend_prompt_compose",
        };
      } catch (error) {
        promptComposeEvidence = {
          source: "frontend_fallback",
          error: String(error).slice(0, 180),
        };
        addLog("prompt compose", String(error).slice(0, 160));
      }
    }
    const generationMetadata = {
      pipeline: selectedPromptTokens.length
        ? "flowstudio-prompt-chip-composition"
        : `creativeflow-${requestStage === "silhouette" ? "global" : requestStage}`,
      analogy_expansion_mode: selectedPromptTokens.length
        ? "prompt_chip_composition"
        : "none",
      stage: requestStage,
      fidelity: requestFidelity,
      divergence_axes: divergenceAxesForStage(requestStage),
      fit_policy: requestStage === "part" ? "preserve_socket" : "stage_default",
      target_part_metadata: partScoped ? partMetadata : undefined,
      analogy_prompt_package: analogyPromptPackage,
      direction_ids: analogyPromptPackage.direction_ids,
      selected_prompt_tokens: analogyPromptPackage.selected_prompt_tokens,
      prompt_token_mode: analogyPromptPackage.prompt_token_mode,
      active_intent_draft_id: activeIntentDraft?.draft_id ?? null,
      prompt_compose_evidence: promptComposeEvidence,
      behavior_atom_ids: visibleBehaviorAtoms.map((atom) => atom.atom_id),
      behavior_atoms: visibleBehaviorAtoms.map((atom) => ({
        atom_id: atom.atom_id,
        tool: atom.tool,
        target: atom.target,
        evidence: atom.evidence,
        order: atom.order,
      })),
      planner_decision: plannerDecision
        ? {
            decision: plannerDecision.decision,
            interpretation_id: plannerDecision.interpretation_id,
            event_id: plannerDecision.event_id,
          }
        : null,
      ir_recommended_axes: crossDomainMetadata?.ir_recommended_axes ?? null,
      image_refs: referenceImages.map((item) => item.url),
      reference_images: referenceImagesPayload(referenceImages),
      model_refs: referenceModels.map((item) => item.url),
      reference_models: referenceModelsPayload(referenceModels),
      ...(overrides?.metadata ?? {}),
    };
    const selection = {
      type: partScoped && effectivePartId ? "part" : "none",
      part_id: partScoped ? effectivePartId : null,
      label: partScoped ? effectivePart?.label ?? effectivePartId : null,
      bbox: partScoped ? effectivePart?.bbox ?? null : null,
      metadata:
        partScoped && effectivePart
          ? {
              part_record: effectivePart,
              partfield: partMetadata,
              preserve_boundary: true,
              socket_source: partMetadata.source ?? effectivePart.type,
            }
          : {},
    };
    sendEvent("generation_requested", {
      asset_id: requestAssetId,
      selection,
      mode,
      intent: {
        mode,
        text: intentText,
      },
      generation: {
        candidate_count: 1,
        diversity: 0.7,
        output_format: "glb",
        metadata: generationMetadata,
      },
      creative_stage: requestStage,
      fidelity: requestFidelity,
      divergence_axes: generationMetadata.divergence_axes,
    });
    const sourceSeq = sourceSwitchSeqRef.current;
    const createdJob = await api<JobRecord>(`/api/v1/generation/${endpoint}`, {
      method: "POST",
      body: JSON.stringify({
        session_id: session.session_id,
        asset_id: requestAssetId,
        selection,
        intent: {
          mode,
          text: intentText,
          drag:
            mode === "drag_regenerate"
              ? {
                  start: [0, 0, 0],
                  end: [0.42, 0.12, 0],
                  space: "world",
                  influence_radius: 0.25,
                }
              : null,
          constraints: ["preserve object identity"],
        },
        generation: {
          candidate_count: 1,
          diversity: 0.7,
          output_format: "glb",
          metadata: {
            ...generationMetadata,
          },
        },
      }),
    });
    if (sourceSeq !== sourceSwitchSeqRef.current) return;
    jobSourceSeqRef.current[createdJob.job_id] = sourceSeq;
    setJob(createdJob);
    addLog("generation", createdJob.job_id);
    window.setTimeout(() => void refreshJob(createdJob.job_id, sourceSeq), 300);
  };

  const continueSuggestedAction = () => {
    if (stage?.suggested_action === "continue_rough_form_exploration") {
      setCreativeStagePreset("rough_form");
      void requestGeneration("diverge", { stage: "rough_form", fidelity: "medium" });
      return;
    }
    if (stage?.suggested_action === "inspect_or_select_part") {
      setCreativeStagePreset("part");
      return;
    }
    if (stage?.suggested_action === "save_or_compare_finish") {
      setCreativeStagePreset("texture");
      return;
    }
    if (stage?.suggested_action === "revise_part_direction") {
      setCreativeStagePreset("part");
      void requestGeneration("replace", { stage: "part", fidelity: "medium" });
      return;
    }
    if (stage?.suggested_action === "revise_silhouette_direction") {
      setCreativeStagePreset("silhouette");
      void requestGeneration("diverge", { stage: "silhouette", fidelity: "low" });
      return;
    }
    if (
      stage?.suggested_action === "revise_global_form_direction" ||
      stage?.suggested_action === "revise_candidate_direction"
    ) {
      setCreativeStagePreset("rough_form");
      void requestGeneration("diverge", { stage: "rough_form", fidelity: "medium" });
    }
  };

  const runAssistanceSuggestion = (suggestion: AssistanceSuggestion) => {
    if (suggestion.type !== "generate") {
      const nextAction = suggestion.metadata?.suggested_next_action;
      const candidateId = suggestion.metadata?.candidate_id;
      const socketScore = suggestion.metadata?.socket_compatibility_score;
      if (nextAction === "preview_or_accept_candidate" && typeof candidateId === "string") {
        const candidate = candidates.find((item) => item.candidate_id === candidateId);
        if (candidate) void previewCandidateForComparison(candidate);
        return;
      }
      if (nextAction === "compare_more_candidates") {
        setCreativeStagePreset("part");
        addLog(
          "assist",
          `compare more variants${typeof socketScore === "number" ? ` / socket ${Math.round(socketScore * 100)}%` : ""}`,
        );
        void requestGeneration("replace", {
          stage: "part",
          fidelity: "medium",
          metadata: {
            assistance_trigger: "compare_more_candidates",
            source_candidate_id: typeof candidateId === "string" ? candidateId : null,
            source_socket_compatibility_score: typeof socketScore === "number" ? socketScore : null,
          },
        });
        return;
      }
      if (nextAction === "generate_boundary_refinements") {
        setCreativeStagePreset("part");
        void requestGeneration("replace", {
          stage: "part",
          fidelity: "medium",
          metadata: {
            assistance_trigger: "generate_boundary_refinements",
            preserve_boundary: true,
          },
        });
        return;
      }
      if (nextAction === "generate_drag_candidates") {
        setCreativeStagePreset("rough_form");
        void requestGeneration("drag_regenerate", {
          stage: "rough_form",
          fidelity: "medium",
          metadata: {
            assistance_trigger: "generate_drag_candidates",
          },
        });
      }
      return;
    }
    if (suggestion.mode === "replace") {
      setCreativeStagePreset("part");
      void requestGeneration("replace", { stage: "part", fidelity: "medium" });
      return;
    }
    if (suggestion.mode === "drag_regenerate") {
      setCreativeStagePreset("rough_form");
      void requestGeneration("drag_regenerate", { stage: "rough_form", fidelity: "medium" });
      return;
    }
    if (suggestion.mode === "diverge") {
      void requestGeneration("diverge");
    }
  };

  const canRunAssistanceSuggestion = (suggestion: AssistanceSuggestion) => {
    if (suggestion.type === "generate") return true;
    if (suggestion.metadata?.suggested_next_action === "compare_more_candidates") return Boolean(session && asset);
    if (suggestion.metadata?.suggested_next_action === "generate_boundary_refinements") return Boolean(session && asset);
    if (suggestion.metadata?.suggested_next_action === "generate_drag_candidates") return Boolean(session && asset);
    return (
      suggestion.metadata?.suggested_next_action === "preview_or_accept_candidate" &&
      typeof suggestion.metadata?.candidate_id === "string" &&
      candidates.some((candidate) => candidate.candidate_id === suggestion.metadata?.candidate_id)
    );
  };

  const discoverPartsForAsset = async (
    targetAsset: AssetRecord,
    trigger: "manual" | "upload" | "brush",
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
          },
        }),
      });
      if (sourceSeq !== sourceSwitchSeqRef.current) return null;
      setPartDiscovery(response);
      setParts(response.parts);
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
  };

  const decideCandidate = async (
    candidate: Candidate,
    decision: "accept" | "reject",
    makeActiveAsset = false,
  ) => {
    if (!session) return;
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
      setCrossDomainDirections([]);
      setCrossDomainMetadata(null);
      setJob(null);
      addLog("active asset", response.active_asset_id);
      return;
    }
    if (job?.candidate_ids) await loadCandidates(job.candidate_ids);
  };

  const generateCandidateHy3d = async (candidate: Candidate) => {
    if (!session || hy3dCandidateIds.includes(candidate.candidate_id)) return;
    setHy3dCandidateIds((current) => [...current, candidate.candidate_id]);
    addLog("hy3d", `started ${candidate.candidate_id}`);
    try {
      const updated = await api<Candidate>(`/api/v1/candidates/${candidate.candidate_id}/hy3d`, {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          reason: "generate 3D asset for selected CreativeFlow direction",
          make_active_asset: false,
        }),
      });
      setCandidates((current) =>
        rankCandidates(current.map((item) => (item.candidate_id === updated.candidate_id ? updated : item))),
      );
      setPreviewCandidate(updated);
      setCanvasPreview(null);
      addLog("hy3d", updated.mesh_url || updated.obj_url ? "mesh ready" : "completed without mesh");
    } catch (error) {
      addLog("hy3d", String(error));
    } finally {
      setHy3dCandidateIds((current) => current.filter((id) => id !== candidate.candidate_id));
      if (job?.candidate_ids) void loadCandidates(job.candidate_ids);
    }
  };

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

  const versionNodes = useMemo(() => {
    const sourceNode = {
      id: asset?.asset_id ?? "source",
      kind: "source" as const,
      label: asset?.label ?? canvasPrimitive ?? "Blank",
      x: 0,
      y: 0,
      width: 520,
      height: 520,
      previewUrl: null as string | null,
      candidate: null as Candidate | null,
    };
    const branchNodes = acceptedCandidateIds
      .map((id) => candidates.find((item) => item.candidate_id === id))
      .filter((item): item is Candidate => Boolean(item))
      .slice(0, 8)
      .map((candidate, index) => ({
        id: candidate.candidate_id,
        kind: "branch" as const,
        label: candidate.label,
        x: 620,
        y: index * 260 - ((Math.min(acceptedCandidateIds.length, 8) - 1) * 130) / 2,
        width: 220,
        height: 220,
        previewUrl: candidatePreviewUrl(candidate),
        candidate,
      }));
    return [sourceNode, ...branchNodes];
  }, [acceptedCandidateIds, asset?.asset_id, asset?.label, canvasPrimitive, candidates]);

  const versionLinks = useMemo(
    () =>
      versionNodes
        .filter((node) => node.kind === "branch")
        .map((node) => ({
          id: `link-${node.id}`,
          x1: 520,
          y1: 260,
          x2: node.x,
          y2: node.y + node.height / 2,
        })),
    [versionNodes],
  );

  const focusVersionCanvas = (mode: "all" | "active") => {
    if (mode === "active") {
      setCanvasPan(centeredActiveCanvasPan());
      setCanvasZoom(1);
      return;
    }
    const maxX = Math.max(...versionNodes.map((node) => node.x + node.width), 520);
    const maxY = Math.max(...versionNodes.map((node) => node.y + node.height), 520);
    const minY = Math.min(...versionNodes.map((node) => node.y), 0);
    const spanX = maxX + 160;
    const spanY = maxY - minY + 160;
    const nextZoom = Math.max(0.45, Math.min(1, Math.min(980 / spanX, 640 / spanY)));
    setCanvasZoom(nextZoom);
    setCanvasPan({
      x: 80,
      y: 90 - minY * nextZoom,
    });
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
    const nextWidth = Math.max(0, Math.min(420, drag.startWidth + delta));
    if (nextWidth < 48) {
      setStudioDrawerOpen(false);
      return;
    }
    setStudioDrawerOpen(true);
    setMenuWidth(Math.max(220, nextWidth));
  };

  const onMenuHandlePointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = menuDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    menuDragRef.current = null;
    if (!drag.moved) {
      setStudioDrawerOpen((value) => !value);
    } else if (menuWidth < 48) {
      setStudioDrawerOpen(false);
    }
  };

  return (
    <main className={`studio-shell ${studioDrawerOpen ? "menu-open" : ""}`}>
      <div className="brand-mark" style={studioDrawerOpen ? { left: Math.max(22, menuWidth + 18) } : undefined}>
        <div className="brand-mark-logo" aria-hidden="true" />
        <h1>Flow Studio</h1>
      </div>

      <aside
        className={`studio-rail ${studioDrawerOpen ? "is-open" : ""}`}
        style={{ width: studioDrawerOpen ? menuWidth : 0 }}
        aria-label="Studio menu"
        aria-hidden={!studioDrawerOpen}
      >
        <div className="studio-rail-scroll">
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
                      <img src={absoluteUrl(item.url)} alt="reference" />
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
              ) : null}
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
              <label className="drawer-inline-label">
                Viewport display
                <select
                  value={canvasDisplayMode}
                  onChange={(event) => handleDisplayModeChange(event.target.value as CanvasDisplayMode)}
                >
                  <option value="textured">Texture</option>
                  <option value="parts" disabled={!parts.length}>Parts</option>
                  <option value="heatmap" disabled={!parts.length}>Heat</option>
                  <option value="clay">Clay mesh</option>
                </select>
              </label>
              <button className="ghost compact" type="button" onClick={() => setShowSignalDebug((value) => !value)}>
                {showSignalDebug ? "Hide signal chips" : "Show signal chips"}
              </button>
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
        </div>
      </aside>
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
      >
        <GripVertical size={16} />
      </button>

      <section className="workspace">
        <section className="canvas-column">
          <div
            className="version-canvas-shell"
            onWheel={(event) => {
              if (event.ctrlKey || event.metaKey) {
                event.preventDefault();
                const delta = event.deltaY > 0 ? -0.08 : 0.08;
                setCanvasZoom((value) => Math.max(0.4, Math.min(1.8, Number((value + delta).toFixed(2)))));
              }
            }}
            onPointerDown={(event) => {
              if (!(spacePanArmed || event.button === 1 || event.altKey)) return;
              versionCanvasDragRef.current = {
                active: true,
                startX: event.clientX,
                startY: event.clientY,
                originX: canvasPan.x,
                originY: canvasPan.y,
              };
              (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              const drag = versionCanvasDragRef.current;
              if (!drag?.active) return;
              setCanvasPan({
                x: drag.originX + (event.clientX - drag.startX),
                y: drag.originY + (event.clientY - drag.startY),
              });
            }}
            onPointerUp={() => {
              if (versionCanvasDragRef.current) versionCanvasDragRef.current.active = false;
            }}
          >
            <div
              className="version-canvas-world"
              style={{ transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${canvasZoom})` }}
            >
              <svg className="version-canvas-links" aria-hidden="true">
                {versionLinks.map((link) => (
                  <line
                    key={link.id}
                    x1={link.x1}
                    y1={link.y1}
                    x2={link.x2}
                    y2={link.y2}
                    stroke="rgba(70, 90, 130, 0.45)"
                    strokeWidth="2"
                    strokeDasharray="8 8"
                  />
                ))}
              </svg>

              {versionNodes.map((node) =>
                node.kind === "source" ? (
                  <div
                    className="version-node active"
                    key={node.id}
                    style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
                  >
                    <div className="version-node-frame">
                      <ThreeViewport
                        asset={asset}
                        previewMeshUrl={activePreviewUrl}
                        previewLabel={activePreviewLabel}
                        onClearPreview={() => {
                          pushEditorHistory("clear preview");
                          setPreviewCandidate(null);
                          setCanvasPreview(null);
                        }}
                        selectedPart={selectedPart}
                        hoverLabel={hoverLabel}
                        canDrag={canShowDrag}
                        primitive={canvasPrimitive}
                        tool={canvasTool}
                        displayMode={canvasDisplayMode}
                        parts={parts}
                        onSelectPart={(part) => selectPartFromViewportHit(part, "click")}
                        onHoverPart={(part) => selectPartFromViewportHit(part, "hover")}
                        onDragPart={canShowDrag ? runDragAction : () => undefined}
                        onViewportInteraction={handleViewportInteraction}
                      />
                      <AnnotationCanvasOverlay
                        active={annotationMode}
                        onCancel={() => setAnnotationMode(false)}
                        onCommit={(strokes) => {
                          setAnnotationMode(false);
                          void recordAnnotation(strokes);
                        }}
                      />
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="version-node thumbnail"
                    key={node.id}
                    style={{ left: node.x, top: node.y, width: node.width, height: node.height }}
                    onClick={() => {
                      if (node.candidate) void previewCandidateForComparison(node.candidate);
                    }}
                    title="Preview this branch version"
                  >
                    {node.previewUrl ? (
                      <img src={node.previewUrl} alt={node.label} />
                    ) : (
                      <div className="version-thumb-fallback">
                        <Box size={22} />
                      </div>
                    )}
                    <strong>{node.label}</strong>
                    <span>accepted branch</span>
                  </button>
                ),
              )}
            </div>
          </div>

          <PlannerClarificationOverlay
            visible={Boolean(intentBubble.visible && intentBubble.status === "pending")}
            scope={intentBubble.scope}
            interpretation={plannerBubbleInterpretation}
            selectedPartLabel={activeSelectedPart?.label ?? selectedPart}
            busy={plannerDecisionBusy}
            onDecide={(decision, label) => void decidePlannerInterpretation(decision, "canvas_clarification_bubble", label)}
          />
          {liveSolutionSpaceVisible ? (
            <SolutionSpaceRail
              candidates={visibleCandidates}
              directions={[]}
              acceptedCandidateIds={acceptedCandidateIds}
              job={job}
              loading={solutionSpaceGenerating}
              hy3dCandidateIds={hy3dCandidateIds}
              onTouch={() => setSolutionSpaceTouchedAt(Date.now())}
              onCollapse={() => {
                setSolutionSpaceReleased(true);
                setSolutionSpaceTouchedAt(Date.now());
              }}
              onPreview={(candidate) => void previewCandidateForComparison(candidate)}
              onAcceptDirection={(candidate) => void decideCandidate(candidate, "accept", false)}
              onCommit3D={(candidate) => void decideCandidate(candidate, "accept", true)}
              onReject={(candidate) => void decideCandidate(candidate, "reject")}
              onGenerate3D={(candidate) => void generateCandidateHy3d(candidate)}
            />
          ) : null}
          <IntentBeadOverlay
            drafts={intentDrafts}
            activeDraftId={activeIntentDraft?.draft_id ?? null}
            onRestore={restoreIntentDraft}
            onArchive={(draft) => void archiveIntentDraft(draft)}
          />

          {workspaceChromeReady && session ? (
          <div className="workspace-chrome" aria-hidden={false}>
          <div
            className={`perception-float float-panel observe-float${perceptionHistoryOpen ? " is-open" : ""}`}
            aria-label="Perception"
            style={studioDrawerOpen ? { left: menuWidth + 18 } : undefined}
          >
            <div className="float-panel-label observe-head">
              <span>Perception</span>
              <button
                type="button"
                className={`observe-toggle${perceptionHistoryOpen ? " is-open" : ""}`}
                aria-expanded={perceptionHistoryOpen}
                aria-label={perceptionHistoryOpen ? "Collapse perception history" : "Expand perception history"}
                onClick={() => setPerceptionHistoryOpen((value) => !value)}
              >
                <ChevronDown size={14} />
              </button>
            </div>
            <p className="observe-sentence">{livePerception.summary || "Waiting for your first move."}</p>
            {hoverLabel || hoverMode ? (
              <div className="hover-chip-row">
                {hoverLabel ? <span className="hover-chip">{hoverLabel}</span> : null}
                {hoverMode ? <span className="hover-chip soft">{hoverSamBusy ? "SAM…" : "Hover mode"}</span> : null}
              </div>
            ) : null}
            {perceptionHistoryOpen ? (
              <div className="observe-log" aria-label="Perception history">
                {buildPerceptionLogEntries({
                  sessionStartedAt: workspaceStartedAt ?? session.created_at,
                  hasModel: Boolean(asset?.mesh_url || asset?.obj_url || canvasPrimitive),
                  perceptionSummary: livePerception.summary,
                  actionAtoms,
                }).map((entry) => (
                  <div className="observe-log-row" key={entry.id}>
                    <time>{entry.time}</time>
                    <em className={`tag-${entry.tag.toLowerCase()}`}>{entry.tag}</em>
                    <span>{entry.text}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <ResizableShell
            className="ai-behavior-float float-panel"
            ariaLabel="AI Behavior"
            defaultWidth={300}
            defaultHeight={520}
            minWidth={240}
            minHeight={280}
            maxWidth={520}
            maxHeight={860}
            handleCorner="sw"
          >
            <div className="float-panel-label">
              <span>AI Behavior</span>
              <div className="status-dots" aria-hidden="true">
                <i /><i /><i />
              </div>
            </div>
            <div className="behavior-context-card planner-speech" aria-live="polite">
              <p className="planner-typewriter">
                {plannerTypedText}
                <i className={plannerTypedText.length < plannerNarration.length ? "is-typing" : ""} />
              </p>
            </div>
            {intentBubble.status === "accepted" || plannerDecision?.decision === "accepted" ? (
              <div className="planner-gate-status accepted">
                Scope confirmed — pick dimensions and keywords below.
              </div>
            ) : intentBubble.status === "rejected" ? (
              <div className="planner-gate-status rejected">
                Scope rejected — kept as negative evidence.
              </div>
            ) : null}
            <p className="more-creative-title">More Creative?</p>
            {moreCreativeMode === "visual_inspiration" ? (
              <div className="visual-inspiration-board" aria-label="Visual inspiration search">
                <strong>Visual inspiration</strong>
                <div>
                  {visualInspirationItems(asset, activeSelectedPart, intentText).map((item) => (
                    <a href={item.url} target="_blank" rel="noreferrer" key={item.label}>
                      <span>{item.label}</span>
                      <em>{item.source}</em>
                    </a>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <p className="more-creative-scope">
                  {intentBubble.scope
                    ? `Change ${intentBubble.scope}`
                    : typeof crossDomainMetadata?.change_scope === "string"
                      ? `Change ${crossDomainMetadata.change_scope}`
                    : interpretation?.features?.design_state_ir?.matches?.[0]?.scope_hint
                      ? String(interpretation.features.design_state_ir.matches[0].scope_hint)
                      : "Prompt expansion"}
                </p>
                {crossDomainBusy ? (
                  <p className="prompt-token-hint">Fetching analogy directions…</p>
                ) : null}
                {crossDomainDirections.length ? (
                  <>
                    <div className="dimension-direction-list">
                      {dimensionGroupsForMoreCreative(
                        crossDomainDirections,
                        analogyPromptTokens(crossDomainDirections),
                        interpretation,
                      ).map((group) => (
                        <section className={`dimension-panel ${group.dimension.toLowerCase()}`} key={group.dimension}>
                          <div className="dimension-panel-head">
                            <strong>{group.dimension}</strong>
                            <span>{group.scoreLabel}</span>
                          </div>
                          {group.summary ? <p>{group.summary}</p> : null}
                          {group.tokens.length ? (
                            <div className="prompt-token-board grouped">
                              {group.tokens.map((token) => {
                                const selected = selectedPromptTokens.some((item) => promptTokenKey(item) === promptTokenKey(token));
                                return (
                                  <button
                                    className={`prompt-token ${selected ? "selected" : ""}`}
                                    key={promptTokenKey(token)}
                                    type="button"
                                    title={`${token.dimension ?? "Analogy"} · ${token.role ?? "keyword"}`}
                                    onClick={() => togglePromptToken(token)}
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
                    <button
                      className="behavior-generate-button"
                      type="button"
                      disabled={!session || !asset || generationBusy || solutionSpaceGenerating}
                      onClick={runCreativeSolutionSpace}
                    >
                      Generate
                    </button>
                  </>
                ) : (
                  <p className="prompt-token-hint">
                    {crossDomainBusy ? "Loading directions…" : "Accept a scope bubble or wait for direction suggestions."}
                  </p>
                )}
              </>
            )}
          </ResizableShell>

            <div
              className={`canvas-composer float-panel${visibleBehaviorAtoms.length || addMenuOpen ? " has-tray" : " is-compact"}`}
              aria-label="Intent composer"
            >
              <input
                value={intentText}
                onFocus={() => {
                  textEditBaselineRef.current = editorSnapshot();
                }}
                onChange={(event) => setIntentText(event.target.value)}
                onBlur={() => {
                  const baseline = textEditBaselineRef.current;
                  if (baseline && baseline.intentText !== intentText) {
                    pushEditorHistory("edit prompt", baseline);
                  }
                  textEditBaselineRef.current = null;
                }}
                placeholder="I want this snowman become more cute."
              />
              <div className="canvas-composer-row">
                <div className="composer-tools" aria-label="Intent composer tools">
                  <button
                    className={`icon-tool ${hoverMode ? "is-active" : ""}`}
                    title={hoverMode ? "Commit hover focus / toggle off" : "Hover mode"}
                    disabled={!asset}
                    onClick={toggleHoverMode}
                  >
                    <MousePointer2 size={17} />
                  </button>
                  <button className="icon-tool" title="Brush" disabled={!canShowBrush || generationBusy || discoveringParts} onClick={() => void runBrushAction()}>
                    <Paintbrush size={17} />
                  </button>
                  <button className={`icon-tool ${annotationMode ? "is-active" : ""}`} title="Annotation" disabled={!asset} onClick={() => setAnnotationMode((value) => !value)}>
                    <Pencil size={17} />
                  </button>
                  <button className="icon-tool tool-asset" title="Drag" disabled={!canShowDrag || generationBusy} onClick={runDragAction}>
                    <img src="/icons/drag.svg" alt="" width={34} height={38} draggable={false} />
                  </button>
                  <button className="icon-tool tool-asset" title="Smooth" disabled={!canShowSculpt || Boolean(sculptBusy)} onClick={() => void runSculptPreview("clay")}>
                    <img src="/icons/smooth.svg" alt="" width={34} height={38} draggable={false} />
                  </button>
                  <button
                    className="icon-tool tool-pink"
                    title="Add primitive"
                    disabled={!asset && !canvasPrimitive}
                    onClick={() => setAddMenuOpen((value) => !value)}
                  >
                    <Plus size={18} />
                  </button>
                  <button className="icon-tool tool-dark" title="Cross-domain Diverge" disabled={!asset || crossDomainBusy} onClick={() => void runCrossDomainDivergence()}>
                    <SmilePlus size={17} />
                  </button>
                </div>
                <div className="composer-actions">
                  <button className="composer-action" title="Compose multiple behaviors into one intent" disabled={!session || intentBusy || (!visibleBehaviorAtoms.length && !intentText.trim())} onClick={() => void saveIntentDraft()}>
                    <Sparkles size={17} />
                  </button>
                  <button
                    className="composer-action send"
                    title={visibleBehaviorAtoms.length ? "Compose behaviors into one intent" : "Submit composed intent"}
                    disabled={!session || plannerBusy || intentBusy || (!activeIntentDraft && !visibleBehaviorAtoms.length && !intentText.trim())}
                    onClick={() => {
                      if (visibleBehaviorAtoms.length) void saveIntentDraft();
                      else void sendIntentDraft();
                    }}
                  >
                    <Send size={17} />
                  </button>
                </div>
              </div>
              {addMenuOpen ? (
                <div className="primitive-menu" aria-label="Add primitive menu">
                  {(
                    [
                      ["plane", "Plane"],
                      ["cube", "Cube"],
                      ["circle", "Circle"],
                      ["sphere", "UV Sphere"],
                      ["ico_sphere", "Ico Sphere"],
                      ["cylinder", "Cylinder"],
                      ["cone", "Cone"],
                      ["torus", "Torus"],
                    ] as Array<[Exclude<CanvasPrimitive, null>, string]>
                  ).map(([primitive, label]) => (
                    <button
                      key={primitive}
                      type="button"
                      onClick={() => {
                        setAddMenuOpen(false);
                        void createPrimitive(primitive);
                      }}
                    >
                      <span className={`wire ${primitive === "sphere" || primitive === "ico_sphere" || primitive === "torus" ? "sphere" : primitive === "cylinder" || primitive === "cone" ? "cylinder" : ""}`} />
                      {label}
                    </button>
                  ))}
                </div>
              ) : null}
              {visibleBehaviorAtoms.length ? (
                <div className="composer-tray behavior-dot-tray">
                  <div className="behavior-dot-list" aria-label="Pending behavior atoms">
                    {visibleBehaviorAtoms.map((atom, index) => (
                      <button
                        className={`behavior-dot ${atom.tool}`}
                        key={atom.atom_id}
                        title={`${index + 1}. ${atom.tool} · ${atom.target?.label ? String(atom.target.label) : atom.target?.part_id ? String(atom.target.part_id) : "object"}`}
                        onClick={() => removeActionAtom(atom.atom_id)}
                      >
                        {index + 1}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          ) : null}

          {workspaceChromeReady ? (
          <div className="canvas-nav" aria-label="Canvas navigation">
            <button type="button" title="Undo" disabled={!undoStack.length} onClick={undoEditor}>
              <RotateCcw size={14} />
            </button>
            <button type="button" title="Redo" disabled={!redoStack.length} onClick={redoEditor}>
              <RefreshCw size={14} />
            </button>
            <button type="button" title="Zoom out" onClick={() => setCanvasZoom((value) => Math.max(0.4, Number((value - 0.1).toFixed(2))))}>
              <ZoomOut size={14} />
            </button>
            <button type="button" title="Fit all" onClick={() => focusVersionCanvas("all")}>
              <Maximize2 size={14} />
            </button>
            <button type="button" className="active" title="Focus active" onClick={() => focusVersionCanvas("active")}>
              <Focus size={14} />
            </button>
          </div>
          ) : null}
        </section>
      </section>
    </main>
  );
}

function ThreeViewport({
  asset,
  previewMeshUrl,
  previewLabel,
  onClearPreview,
  selectedPart,
  hoverLabel,
  canDrag,
  primitive,
  tool,
  displayMode,
  parts,
  onSelectPart,
  onHoverPart,
  onDragPart,
  onViewportInteraction,
}: {
  asset: AssetRecord | null;
  previewMeshUrl: string | null;
  previewLabel: string | null;
  onClearPreview: () => void;
  selectedPart: string;
  hoverLabel: string | null;
  canDrag: boolean;
  primitive: CanvasPrimitive;
  tool: CanvasTool;
  displayMode: CanvasDisplayMode;
  parts: PartRecord[];
  onSelectPart: (part: string) => void;
  onHoverPart: (part: string) => void;
  onDragPart: () => void;
  onViewportInteraction: (signal: ViewportInteractionSignal) => void;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const onSelectRef = useRef(onSelectPart);
  const onHoverRef = useRef(onHoverPart);
  const onDragRef = useRef(onDragPart);
  const onViewportInteractionRef = useRef(onViewportInteraction);
  const selectedRef = useRef(selectedPart);
  const lastHoverRef = useRef({ name: "", at: 0 });
  const [viewResetKey, setViewResetKey] = useState(0);
  const [modelLoadMessage, setModelLoadMessage] = useState<string | null>(null);

  useEffect(() => {
    onSelectRef.current = onSelectPart;
    onHoverRef.current = onHoverPart;
    onDragRef.current = onDragPart;
    onViewportInteractionRef.current = onViewportInteraction;
    selectedRef.current = selectedPart;
  }, [onDragPart, onHoverPart, onSelectPart, onViewportInteraction, selectedPart]);

  useEffect(() => {
    if (!mountRef.current) return;
    setModelLoadMessage(null);
    const mount = mountRef.current;
    const scene = new THREE.Scene();
    scene.background = null;
    const camera = new THREE.PerspectiveCamera(45, mount.clientWidth / mount.clientHeight, 0.1, 100);
    camera.position.set(0, 1.2, 5.2);
    camera.lookAt(0, 0.4, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.rotateSpeed = 0.7;
    controls.zoomSpeed = 0.85;
    controls.panSpeed = 0.65;
    controls.minDistance = 0.8;
    controls.maxDistance = 18;
    controls.target.set(0, 0.2, 0);
    controls.update();
    let interactionStartDistance = camera.position.distanceTo(controls.target);
    let interactionStartAt = Date.now();
    let lastInteractionEndAt = Date.now();
    const onControlsStart = () => {
      interactionStartDistance = camera.position.distanceTo(controls.target);
      interactionStartAt = Date.now();
    };
    const onControlsEnd = () => {
      const distance = camera.position.distanceTo(controls.target);
      const distanceDelta = Math.abs(distance - interactionStartDistance);
      const now = Date.now();
      const dwellMs = Math.min(12000, Math.max(0, interactionStartAt - lastInteractionEndAt));
      lastInteractionEndAt = now;
      onViewportInteractionRef.current({
        type: distanceDelta > 0.12 ? "zoom" : "orbit",
        dwell_ms: dwellMs,
        camera_distance: Number(distance.toFixed(3)),
      });
    };
    controls.addEventListener("start", onControlsStart);
    controls.addEventListener("end", onControlsEnd);

    addStudioPreviewLighting(scene);

    const group = new THREE.Group();
    group.position.y = 0.2;
    scene.add(group);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const interactive: THREE.Mesh[] = [];
    const resetModel = () => {
      for (const child of [...group.children]) group.remove(child);
      interactive.length = 0;
    };
    const trackMesh = (mesh: THREE.Mesh, fallbackName = "body") => {
      mesh.name = mesh.name || fallbackName;
      interactive.push(mesh);
    };
    const fitLoadedModel = (root: THREE.Object3D) => {
      const box = new THREE.Box3().setFromObject(root);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());
      const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
      root.position.sub(center);
      root.scale.setScalar(2.5 / maxDimension);
      controls.target.set(0, 0, 0);
      camera.position.set(0, Math.max(1.2, size.y / maxDimension), 5.2);
      camera.lookAt(controls.target);
      controls.update();
    };
    const primitiveObject = primitive ? buildPrimitiveObject(primitive) : null;
    if (primitiveObject) {
      resetModel();
      trackMesh(primitiveObject, primitive);
      group.add(primitiveObject);
    }

    const sourceMeshUrl = primitiveObject ? null : previewMeshUrl ?? asset?.mesh_url ?? asset?.obj_url ?? null;
    const modelUrl = sourceMeshUrl
      ? sourceMeshUrl.startsWith("http")
        ? sourceMeshUrl
        : `${API_BASE}${sourceMeshUrl}`
      : null;
    if (modelUrl) {
      const extension = inferMeshExtension(sourceMeshUrl);
      const applyLoadedModel = (root: THREE.Object3D) => {
        setModelLoadMessage(null);
        resetModel();
        fitLoadedModel(root);
        root.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.material = standardizeMeshMaterial(child.material);
            trackMesh(child, child.name || "body");
          }
        });
        group.scale.setScalar(1);
        group.add(root);
      };
      const handleLoadError = () => {
        resetModel();
        setModelLoadMessage(`Model failed to load: ${asset?.label ?? "selected asset"}`);
      };
      if (extension === "glb" || extension === "gltf") {
        const loader = new GLTFLoader();
        loader.load(modelUrl, (gltf) => applyLoadedModel(gltf.scene), undefined, handleLoadError);
      } else if (extension === "obj") {
        loadObjWithOptionalMtl(modelUrl, sourceMeshUrl, (object) => {
          object.traverse((child) => {
            if (child instanceof THREE.Mesh) {
              child.name = child.name || "body";
            }
          });
          applyLoadedModel(object);
        }, handleLoadError);
      } else if (extension === "ply") {
        const loader = new PLYLoader();
        loader.load(
          modelUrl,
          (geometry) => {
            geometry.computeVertexNormals();
            const mesh = new THREE.Mesh(
              geometry,
              new THREE.MeshStandardMaterial({
                color: "#6b7c93",
                metalness: 0.05,
                roughness: 0.58,
                vertexColors: geometry.hasAttribute("color"),
              }),
            );
            mesh.name = "body";
            applyLoadedModel(mesh);
          },
          undefined,
          handleLoadError,
        );
      } else {
        resetModel();
        setModelLoadMessage(`Unsupported model URL: ${asset?.label ?? "selected asset"}`);
      }
    } else if (!primitiveObject) {
      resetModel();
      if (asset) setModelLoadMessage(`No renderable source mesh: ${asset.label}`);
    }
    const updateMaterials = () => {
      interactive.forEach((mesh, index) => {
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const material of materials) {
          if (material instanceof THREE.MeshStandardMaterial) {
            applyDisplayMaterial(material, displayMode, index, parts.length);
            material.emissive = new THREE.Color(mesh.name === selectedRef.current ? "#2563eb" : "#000000");
            material.emissiveIntensity = mesh.name === selectedRef.current ? 0.28 : 0;
          }
        }
      });
    };
    updateMaterials();

    const onPointerDown = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(interactive, true)[0];
      if (hit?.object.name) onSelectRef.current(hit.object.name);
    };
    const onPointerMove = (event: PointerEvent) => {
      const now = Date.now();
      if (now - lastHoverRef.current.at < 250) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(interactive, true)[0];
      const name = hit?.object.name || "";
      if (!name || name === lastHoverRef.current.name) return;
      lastHoverRef.current = { name, at: now };
      onHoverRef.current(name);
    };
    const onDblClick = () => onDragRef.current();
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("dblclick", onDblClick);

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
      updateMaterials();
      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      camera.aspect = mount.clientWidth / mount.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(mount.clientWidth, mount.clientHeight);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("dblclick", onDblClick);
      controls.removeEventListener("start", onControlsStart);
      controls.removeEventListener("end", onControlsEnd);
      controls.dispose();
      mount.removeChild(renderer.domElement);
      renderer.dispose();
    };
  }, [asset?.mesh_url, asset?.obj_url, previewMeshUrl, viewResetKey, primitive, tool, displayMode, parts.length]);

  return (
    <div className="viewport-wrap">
      {previewLabel ? (
        <div className="viewport-tools">
          <button className="ghost compact" onClick={onClearPreview}>
            <RefreshCw size={15} /> Source
          </button>
        </div>
      ) : null}
      <div className="viewport" ref={mountRef} />
      {modelLoadMessage ? <div className="viewport-message">{modelLoadMessage}</div> : null}
      {hoverLabel ? (
        <div className="viewport-hover-label" aria-live="polite">
          {hoverLabel}
        </div>
      ) : null}
    </div>
  );
}

function buildPrimitiveObject(primitive: Exclude<CanvasPrimitive, null>) {
  const material = new THREE.MeshStandardMaterial({
    color: "#b7c4d4",
    roughness: 0.72,
    metalness: 0.03,
  });
  if (primitive === "sphere" || primitive === "ico_sphere") {
    const mesh = new THREE.Mesh(
      primitive === "ico_sphere" ? new THREE.IcosahedronGeometry(1, 1) : new THREE.SphereGeometry(1, 64, 32),
      material,
    );
    mesh.name = primitive;
    return mesh;
  }
  if (primitive === "cylinder") {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.82, 0.82, 1.8, 48), material);
    mesh.name = "cylinder";
    return mesh;
  }
  if (primitive === "cone") {
    const mesh = new THREE.Mesh(new THREE.ConeGeometry(0.95, 1.8, 48), material);
    mesh.name = "cone";
    return mesh;
  }
  if (primitive === "torus") {
    const mesh = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.32, 24, 48), material);
    mesh.name = "torus";
    return mesh;
  }
  if (primitive === "plane" || primitive === "circle") {
    const mesh = new THREE.Mesh(
      primitive === "circle" ? new THREE.CircleGeometry(1.1, 48) : new THREE.PlaneGeometry(2.2, 2.2, 1, 1),
      material,
    );
    mesh.name = primitive;
    return mesh;
  }
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1.7, 1.7, 1.7, 8, 8, 8), material);
  mesh.name = "cube";
  return mesh;
}

function addStudioPreviewLighting(scene: THREE.Scene) {
  scene.add(new THREE.AmbientLight("#ffffff", 1.45));
  scene.add(new THREE.HemisphereLight("#ffffff", "#eef4ff", 1.15));

  [
    { position: [0, 2.2, 5.5], intensity: 1.35 },
    { position: [0, 1.8, -5.5], intensity: 1.05 },
    { position: [-5.5, 1.8, 0], intensity: 1.0 },
    { position: [5.5, 1.8, 0], intensity: 1.0 },
    { position: [0, 6, 0], intensity: 0.9 },
    { position: [0, -3, 0], intensity: 0.35 },
  ].forEach(({ position, intensity }) => {
    const light = new THREE.DirectionalLight("#ffffff", intensity);
    light.position.set(position[0], position[1], position[2]);
    scene.add(light);
  });
}

function loadObjWithOptionalMtl(
  modelUrl: string,
  sourceUrl: string,
  onLoad: (object: THREE.Group) => void,
  onError: () => void,
) {
  const fallback = () => {
    new OBJLoader().load(modelUrl, onLoad, undefined, onError);
  };
  const mtlUrl = inferMtlUrl(sourceUrl);
  if (!mtlUrl) {
    fallback();
    return;
  }
  const manager = new THREE.LoadingManager();
  const mtlLoader = new MTLLoader(manager);
  const resourcePath = mtlUrl.slice(0, mtlUrl.lastIndexOf("/") + 1);
  mtlLoader.setResourcePath(resourcePath);
  mtlLoader.load(
    mtlUrl,
    (materials) => {
      materials.preload();
      const loader = new OBJLoader(manager);
      loader.setMaterials(materials);
      loader.load(modelUrl, onLoad, undefined, fallback);
    },
    undefined,
    fallback,
  );
}

function inferMtlUrl(sourceUrl: string) {
  try {
    const parsed = new URL(sourceUrl, API_BASE);
    const remotePath = parsed.searchParams.get("path");
    if (remotePath?.toLowerCase().endsWith(".obj")) {
      const mtlPath = remotePath.replace(/[^/]+\.obj$/i, "material.mtl");
      parsed.searchParams.set("path", mtlPath);
      return parsed.toString();
    }
  } catch {
    // Fall through to direct local path handling.
  }
  if (!sourceUrl.toLowerCase().split("?")[0].endsWith(".obj")) return null;
  const nextUrl = sourceUrl.replace(/[^/]+\.obj(\?.*)?$/i, "material.mtl");
  if (nextUrl.startsWith("http")) return nextUrl;
  return `${API_BASE}${nextUrl}`;
}

function applyDisplayMaterial(
  material: THREE.MeshStandardMaterial,
  displayMode: CanvasDisplayMode,
  index: number,
  partCount: number,
) {
  if (displayMode === "textured") {
    material.color.multiplyScalar(1);
    material.roughness = Math.min(material.roughness, 0.68);
    return;
  }
  material.map = null;
  material.normalMap = null;
  material.roughnessMap = null;
  material.metalness = 0.02;
  if (displayMode === "parts") {
    const palette = ["#4f7bd9", "#45a67b", "#d99b3d", "#c65f79", "#7d65c7", "#49aebd"];
    material.color = new THREE.Color(palette[index % Math.max(1, Math.min(partCount || 1, palette.length))]);
    material.roughness = 0.58;
    return;
  }
  if (displayMode === "heatmap") {
    const t = partCount > 1 ? index / Math.max(1, partCount - 1) : 0.45;
    material.color = new THREE.Color().setHSL(0.62 - t * 0.52, 0.78, 0.56);
    material.roughness = 0.5;
    return;
  }
  material.color = new THREE.Color("#b9c1cc");
  material.roughness = 0.82;
}

function standardizeMeshMaterial(material: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) return material.map((item) => standardizeSingleMaterial(item));
  return standardizeSingleMaterial(material);
}

function standardizeSingleMaterial(material: THREE.Material) {
  if (material instanceof THREE.MeshStandardMaterial) return material;
  const source = material as THREE.MeshPhongMaterial & {
    map?: THREE.Texture | null;
    normalMap?: THREE.Texture | null;
    roughnessMap?: THREE.Texture | null;
    metalnessMap?: THREE.Texture | null;
  };
  return new THREE.MeshStandardMaterial({
    color: source.color instanceof THREE.Color ? source.color.clone() : new THREE.Color("#6b7c93"),
    map: source.map ?? null,
    normalMap: source.normalMap ?? null,
    roughnessMap: source.roughnessMap ?? null,
    metalnessMap: source.metalnessMap ?? null,
    metalness: 0.05,
    roughness: 0.58,
    transparent: material.transparent,
    opacity: material.opacity,
    side: material.side,
  });
}

function ResizableShell({
  className,
  ariaLabel,
  defaultWidth,
  defaultHeight,
  minWidth = 200,
  minHeight = 120,
  maxWidth = 720,
  maxHeight = 900,
  handleCorner = "se",
  style,
  children,
}: {
  className: string;
  ariaLabel?: string;
  defaultWidth: number;
  defaultHeight: number;
  minWidth?: number;
  minHeight?: number;
  maxWidth?: number;
  maxHeight?: number;
  handleCorner?: "se" | "sw";
  style?: React.CSSProperties;
  children: React.ReactNode;
}) {
  const [size, setSize] = useState({ w: defaultWidth, h: defaultHeight });
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startW: number;
    startH: number;
  } | null>(null);

  const onPointerDown = (event: React.PointerEvent<HTMLSpanElement>) => {
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startW: size.w,
      startH: size.h,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLSpanElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;
    const nextW = Math.min(
      maxWidth,
      Math.max(minWidth, drag.startW + (handleCorner === "sw" ? -deltaX : deltaX)),
    );
    const nextH = Math.min(maxHeight, Math.max(minHeight, drag.startH + deltaY));
    setSize({ w: nextW, h: nextH });
  };

  const onPointerUp = (event: React.PointerEvent<HTMLSpanElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  };

  return (
    <div
      className={`${className} resizable-shell`}
      aria-label={ariaLabel}
      style={{ ...style, width: size.w, height: size.h }}
    >
      <div className="resizable-shell-body">{children}</div>
      <span
        className={`resize-handle corner-${handleCorner}`}
        title="Drag to resize"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
    </div>
  );
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="panel">
      <div className="panel-title">
        {icon}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function StatusPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="status-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong>{value ?? "none"}</strong>
    </div>
  );
}

function LiveSignalCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="live-signal-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PlannerClarificationOverlay({
  visible,
  scope,
  interpretation,
  selectedPartLabel,
  busy,
  onDecide,
}: {
  visible: boolean;
  scope: BubbleScope | null;
  interpretation: Interpretation | null;
  selectedPartLabel?: string | null;
  busy: "accepted" | "rejected" | null;
  onDecide: (decision: "accepted" | "rejected", label: string) => void;
}) {
  if (!visible) return null;
  const bubbles = interpretation
    ? plannerClarificationBubbles(interpretation, selectedPartLabel)
    : scope
      ? [
          {
            id: "planner-primary",
            label: scope === "material" ? "Change material?" : scope === "part" ? "Change part?" : "Change contour?",
            detail:
              scope === "material"
                ? "确认要改材质/颜色/表面风格吗？"
                : scope === "part"
                  ? "确认要改当前部件吗？"
                  : "确认要改整体轮廓吗？",
            kind: scope === "part" ? ("target" as const) : ("axis" as const),
            position: "right" as const,
          },
        ]
      : [];
  if (!bubbles.length) return null;
  return (
    <div className="planner-clarification-overlay pending" aria-label="Planner clarification bubbles">
      {bubbles.map((bubble) => (
        <div className={`planner-bubble ${bubble.position} ${bubble.kind}`} key={bubble.id}>
          <span>{bubble.label}</span>
          <strong>{bubble.detail}</strong>
          <div className="planner-bubble-actions">
            <button
              className="accept"
              disabled={Boolean(busy)}
              title="Accept this change scope"
              onClick={() => onDecide("accepted", bubble.label)}
            >
              <Check size={13} />
            </button>
            <button
              className="reject"
              disabled={Boolean(busy)}
              title="Reject this change scope"
              onClick={() => onDecide("rejected", bubble.label)}
            >
              <X size={13} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function SolutionSpaceRail({
  candidates,
  directions,
  acceptedCandidateIds,
  job,
  loading,
  hy3dCandidateIds,
  onTouch,
  onCollapse,
  onPreview,
  onAcceptDirection,
  onCommit3D,
  onReject,
  onGenerate3D,
}: {
  candidates: Candidate[];
  directions: AnalogyDirection[];
  acceptedCandidateIds: string[];
  job: JobRecord | null;
  loading: boolean;
  hy3dCandidateIds: string[];
  onTouch: () => void;
  onCollapse: () => void;
  onPreview: (candidate: Candidate) => void;
  onAcceptDirection: (candidate: Candidate) => void;
  onCommit3D: (candidate: Candidate) => void;
  onReject: (candidate: Candidate) => void;
  onGenerate3D: (candidate: Candidate) => void;
}) {
  if (!candidates.length && !directions.length && !job && !loading) return null;
  const compactLoading = loading && !candidates.length;
  const touch = <T,>(callback: (value: T) => void, value: T) => {
    onTouch();
    callback(value);
  };
  return (
    <ResizableShell
      key={compactLoading ? "solution-space-loading" : "solution-space-ready"}
      className={`solution-space-rail ${compactLoading ? "is-loading" : ""}`}
      ariaLabel="Solution Space"
      defaultWidth={compactLoading ? Math.min(520, typeof window !== "undefined" ? window.innerWidth - 360 : 520) : Math.min(720, typeof window !== "undefined" ? window.innerWidth - 360 : 720)}
      defaultHeight={compactLoading ? 74 : 220}
      minWidth={360}
      minHeight={compactLoading ? 64 : 160}
      maxWidth={1100}
      maxHeight={420}
    >
      <div className="solution-space-head">
        <span>Solution Space</span>
        <div className="solution-space-head-actions">
          <strong>{loading || (job && isActiveJobStatus(job.status)) ? "generating…" : `${candidates.length || directions.length} items`}</strong>
          <button type="button" className="solution-space-collapse" title="Collapse Solution Space" onClick={onCollapse}>
            <Minus size={13} />
          </button>
        </div>
      </div>
      {compactLoading ? (
        <div className="solution-loading-strip" aria-label="Generating image variants">
          <i /><i /><i />
          <span>Qwen-image is generating variants…</span>
        </div>
      ) : (
      <div className="solution-space-scroll">
        {candidates.map((candidate) => {
          const previewUrl = candidatePreviewUrl(candidate);
          const hasMesh = Boolean(candidate.mesh_url || candidate.obj_url);
          const accepted = acceptedCandidateIds.includes(candidate.candidate_id);
          return (
            <article className={`solution-card ${accepted ? "accepted" : ""}`} key={candidate.candidate_id}>
              {accepted ? <span className="accepted-mark">✓</span> : null}
              {previewUrl ? (
                <img src={previewUrl} alt={candidate.label} />
              ) : (
                <div className="solution-card-placeholder">
                  <Sparkles size={18} />
                </div>
              )}
              <div className="solution-card-body">
                <strong>{candidate.label}</strong>
                <span>{candidateStage(candidate)} · {candidateArtifactLevel(candidate)}</span>
                <em>{accepted ? "accepted" : candidate.decision}</em>
              </div>
              <div className="solution-card-actions">
                {hasMesh ? (
                  <button onClick={() => touch(onPreview, candidate)}>Preview</button>
                ) : canGenerateCandidateHy3d(candidate) ? (
                  <button disabled={hy3dCandidateIds.includes(candidate.candidate_id)} onClick={() => touch(onGenerate3D, candidate)}>
                    {hy3dCandidateIds.includes(candidate.candidate_id) ? "3D..." : "Make 3D"}
                  </button>
                ) : null}
                <button onClick={() => touch(onAcceptDirection, candidate)}>Accept</button>
                {hasMesh ? <button onClick={() => touch(onCommit3D, candidate)}>Commit</button> : null}
                <button onClick={() => touch(onReject, candidate)}>Reject</button>
              </div>
            </article>
          );
        })}
        {!candidates.length
          ? directions.slice(0, 8).map((direction) => (
              <article className="solution-card direction" key={direction.direction_id}>
                <div className="solution-card-placeholder">
                  <Sparkles size={18} />
                </div>
                <div className="solution-card-body">
                  <strong>{direction.label}</strong>
                  <span>{direction.dimension} · prompt direction</span>
                  <em>{direction.source_domain} → {direction.target_domain}</em>
                </div>
              </article>
            ))
          : null}
      </div>
      )}
    </ResizableShell>
  );
}

function IntentBeadOverlay({
  drafts,
  activeDraftId,
  onRestore,
  onArchive,
}: {
  drafts: IntentDraft[];
  activeDraftId: string | null;
  onRestore: (draft: IntentDraft) => void;
  onArchive: (draft: IntentDraft) => void;
}) {
  const visibleDrafts = drafts.filter((draft) => draft.status !== "archived").slice(0, 5);
  if (!visibleDrafts.length) return null;
  return (
    <div className="intent-bead-overlay" aria-label="Saved intent drafts around object">
      <div className="intent-bead-chain">
        {visibleDrafts.map((draft, index) => {
          const active = draft.draft_id === activeDraftId;
          return (
            <article className={`intent-bead ${active ? "active" : ""} ${draft.status}`} key={draft.draft_id}>
              <button
                className="intent-bead-main"
                type="button"
                title="Restore this intent draft"
                onClick={() => onRestore(draft)}
              >
                <span>{index + 1}</span>
                <strong>{draft.title}</strong>
                <em>{draft.behavior_atoms.length} behaviors · {draft.status}</em>
              </button>
              <button
                className="intent-bead-archive"
                type="button"
                title="Archive this intent draft"
                onClick={() => onArchive(draft)}
              >
                ×
              </button>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function AnnotationCanvasOverlay({
  active,
  onCommit,
  onCancel,
}: {
  active: boolean;
  onCommit: (strokes: AnnotationStroke[]) => void;
  onCancel: () => void;
}) {
  const [strokes, setStrokes] = useState<AnnotationStroke[]>([]);
  const [draft, setDraft] = useState<AnnotationStroke>([]);
  const [drawing, setDrawing] = useState(false);
  const startTimeRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setStrokes([]);
      setDraft([]);
      setDrawing(false);
    }
  }, [active]);

  if (!active) return null;

  const normalizePoint = (event: React.PointerEvent<HTMLDivElement>): AnnotationPoint => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: clamp01((event.clientX - rect.left) / Math.max(rect.width, 1)),
      y: clamp01((event.clientY - rect.top) / Math.max(rect.height, 1)),
      t: Math.max(0, Date.now() - startTimeRef.current),
    };
  };

  const appendPoint = (nextPoint: AnnotationPoint) => {
    setDraft((current) => {
      const last = current[current.length - 1];
      if (last && Math.hypot(last.x - nextPoint.x, last.y - nextPoint.y) < 0.004) return current;
      return [...current, nextPoint].slice(-240);
    });
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    startTimeRef.current = Date.now();
    setDrawing(true);
    setDraft([normalizePoint(event)]);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drawing) return;
    appendPoint(normalizePoint(event));
  };

  const finishDrawing = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!drawing) return;
    const finalPoint = normalizePoint(event);
    const committed = [...draft, finalPoint];
    setDrawing(false);
    setDraft([]);
    if (committed.length >= 2) setStrokes((current) => [...current, committed]);
  };

  const visibleStrokes = draft.length ? [...strokes, draft] : strokes;
  const hasStrokes = visibleStrokes.some((stroke) => stroke.length >= 2);

  return (
    <div
      className="annotation-canvas-overlay"
      role="presentation"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishDrawing}
      onPointerCancel={() => {
        setDraft([]);
        setDrawing(false);
      }}
    >
      <div className="annotation-hint">
        <strong>2D Pencil</strong>
        <span>连续画轮廓、箭头或标记；Done 后保存为 Planner 证据。</span>
      </div>
      <div className="annotation-actions" onPointerDown={(event) => event.stopPropagation()}>
        <button type="button" disabled={!strokes.length} onClick={() => setStrokes((current) => current.slice(0, -1))}>
          Undo
        </button>
        <button type="button" disabled={!hasStrokes} onClick={() => setStrokes([])}>
          Clear
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
        <button className="primary" type="button" disabled={!hasStrokes} onClick={() => onCommit(visibleStrokes.filter((stroke) => stroke.length >= 2))}>
          Done
        </button>
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {visibleStrokes.map((stroke, index) => {
          const svgPoints = stroke.map((point) => `${point.x * 100},${point.y * 100}`).join(" ");
          return svgPoints ? <polyline className="annotation-stroke" points={svgPoints} key={index} /> : null;
        })}
      </svg>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}

function clamp01(value: number) {
  return Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
}

function formatScore(value?: number | null) {
  if (value === null || value === undefined) return "none";
  return `${Math.round(value * 100)}%`;
}

function confidenceTone(value?: number | null) {
  if (typeof value !== "number") return "Waiting";
  if (value >= 0.78) return "正在";
  if (value >= 0.55) return "似乎正在";
  return "可能正在";
}

function isSilentObservationInterpretation(value: unknown) {
  const features = (value as { features?: { event_type?: unknown } } | null)?.features;
  return features?.event_type === "camera_observation_ended";
}

function livePerceptionSummary(
  signals: LiveSignals,
  hasModel: boolean,
  primitive: CanvasPrimitive,
): string {
  if (!hasModel && !primitive) return "Waiting for your first move.";
  if (signals.annotation_count > 0 && signals.drawing_content) {
    return `User is drawing on the silhouette (${signals.drawing_content}).`;
  }
  if (signals.annotation_count > 0) return "User is drawing on the silhouette.";
  if (signals.brush_count > 0) return "User is drawing on the part.";
  if (signals.hover_count > 0 && signals.viewport_zoom_count > 0) return "User is observing the part.";
  if (signals.hover_count > 0) return "User is focusing on a part.";
  if (signals.local_zoom_count > 0 || signals.viewport_zoom_count > 0) return "User is zooming to inspect local details.";
  if (signals.viewport_orbit_count > 0) return "User is overviewing the whole structure.";
  if (primitive) return `User added a ${primitive.replaceAll("_", " ")} volume.`;
  return "Overviewing the whole structure.";
}

function livePerceptionEvidence(signals: LiveSignals): string[] {
  const items = [
    signals.viewport_orbit_count ? `orbit×${signals.viewport_orbit_count}` : null,
    signals.viewport_zoom_count ? `zoom×${signals.viewport_zoom_count}` : null,
    signals.dwell_ms ? `dwell ${Math.round(signals.dwell_ms)}ms` : null,
    signals.hover_count ? `hover×${signals.hover_count}` : null,
    signals.brush_count ? `brush×${signals.brush_count}` : null,
    signals.annotation_count ? `annotation×${signals.annotation_count}` : null,
    signals.mask_coverage > 0 ? `mask ${Math.round(signals.mask_coverage * 100)}%` : null,
    signals.drawing_content || null,
  ].filter(Boolean) as string[];
  return items.length ? [items.join(" · ")] : ["No behavioral evidence yet."];
}

const CREATIVE_STATES = new Set<string>([
  "idle",
  "exploring",
  "focused_editing",
  "refining",
  "comparing",
  "possible_fixation",
  "ready_for_help",
]);

function observeCreativeState(input: {
  hasModel: boolean;
  signals: LiveSignals;
  behaviorCount: number;
  hasIntentText: boolean;
  hasSelectedPart: boolean;
  comparing: boolean;
  generating: boolean;
  lastActionAt: number | null;
  now: number;
}): { state: CreativeState; confidence: number } {
  const { signals } = input;
  if (!input.hasModel && input.behaviorCount === 0 && !input.hasIntentText) {
    return { state: "idle", confidence: 1 };
  }
  if (input.comparing || signals.compare_dwell_ms >= 2500) {
    return { state: "comparing", confidence: 0.82 };
  }
  if (input.generating) {
    return { state: "exploring", confidence: 0.55 };
  }
  if (signals.brush_count >= 2 && signals.dwell_ms >= 1200 && signals.new_case_attempt_rate < 0.35) {
    return { state: "refining", confidence: 0.7 };
  }
  if (
    input.hasSelectedPart &&
    (signals.hover_count > 0 || signals.brush_count > 0 || signals.annotation_count > 0)
  ) {
    const quietMs = input.lastActionAt ? input.now - input.lastActionAt : 0;
    if (
      input.behaviorCount > 0 &&
      quietMs >= 8000 &&
      signals.dwell_ms >= 2000 &&
      signals.new_case_attempt_rate < 0.3 &&
      (signals.hover_count > 0 || signals.viewport_orbit_count + signals.viewport_zoom_count >= 2)
    ) {
      return { state: "possible_fixation", confidence: 0.74 };
    }
    return { state: "focused_editing", confidence: 0.68 };
  }
  if (
    signals.new_case_attempt_rate >= 0.45 ||
    signals.semantic_distance >= 0.55 ||
    signals.reference_match_count > 0
  ) {
    return { state: "exploring", confidence: 0.66 };
  }
  const quietMs = input.lastActionAt ? input.now - input.lastActionAt : 0;
  if (
    (input.behaviorCount > 0 || signals.hover_count > 0 || signals.annotation_count > 0) &&
    quietMs >= 8000 &&
    signals.dwell_ms >= 2000 &&
    signals.new_case_attempt_rate < 0.3
  ) {
    return { state: "possible_fixation", confidence: 0.7 };
  }
  if (signals.viewport_orbit_count > 0 || signals.viewport_zoom_count > 0) {
    return { state: "exploring", confidence: 0.45 };
  }
  return { state: input.hasModel ? "exploring" : "idle", confidence: 0.4 };
}

function interactionHistoryItems(
  atoms: ActionAtom[],
  _signals: LiveSignals,
  perception: LivePerception,
  interpretation: Interpretation | null,
) {
  const items = atoms
    .filter((atom) => atom.evidence?.source !== "more_creative_prompt_chip")
    .slice(-5)
    .reverse()
    .map((atom) => {
      const target =
        atom.target?.label ??
        atom.target?.part_id ??
        atom.evidence?.drawing_content ??
        (atom.tool === "annotation" || atom.tool === "brush" ? "canvas" : "object");
      return `${atom.tool} · ${String(target)}`;
    });
  const irSummary = interpretation?.features?.design_state_ir?.matches?.[0]?.evidence_summary;
  const irLine =
    typeof irSummary === "string" && irSummary.trim()
      ? `IR · ${irSummary.slice(0, 72)}`
      : null;
  // Default history: observation + behaviors (+ optional IR summary). Signals stay behind debug toggle.
  return [perception.summary, ...items, irLine].filter(Boolean).slice(0, 6) as string[];
}

function formatClock(value?: string | number | null) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  }
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function buildPerceptionLogEntries(input: {
  sessionStartedAt?: string | null;
  hasModel: boolean;
  perceptionSummary: string;
  actionAtoms: ActionAtom[];
}): PerceptionLogEntry[] {
  const nowClock = formatClock();
  const initClock = formatClock(input.sessionStartedAt);
  const entries: PerceptionLogEntry[] = [
    {
      id: "sys-nav",
      time: nowClock,
      tag: "SYS",
      text: "Navigation mode — drag to orbit, click a version to inspect. Pick a tool or start typing.",
    },
    {
      id: "init-session",
      time: initClock,
      tag: "INIT",
      text: input.hasModel ? "Session started — model on canvas." : "Session started — canvas is empty.",
    },
    {
      id: "perception-latest",
      time: nowClock,
      tag: "PERCEPTION",
      text: input.perceptionSummary || "Waiting for your first move.",
    },
  ];

  for (const atom of input.actionAtoms.slice(-3).reverse()) {
    const target =
      atom.target?.label ??
      atom.target?.part_id ??
      atom.evidence?.drawing_content ??
      (atom.tool === "annotation" || atom.tool === "brush" ? "canvas" : "object");
    entries.push({
      id: `action-${atom.atom_id}`,
      time: formatClock(atom.created_at),
      tag: "ACTION",
      text: `${atom.tool} · ${String(target)}`,
    });
  }

  return entries;
}

function behaviorContextDescription(
  asset: AssetRecord | null,
  primitive: CanvasPrimitive,
  part: PartRecord | null,
  perception: LivePerception,
) {
  const objectLabel = asset?.label ?? (primitive ? primitive.replaceAll("_", " ") : "blank composition");
  const objectType = asset?.object_type ?? primitive ?? "object";
  const focus = part?.label ? ` Current focus: ${part.label}.` : "";
  return `This is a ${objectType} context: ${objectLabel}.${focus} ${perception.summary}`.trim();
}

function buildPlannerNarration(input: {
  perceptionSummary: string;
  creativeState: CreativeState;
  hasModel: boolean;
  partLabel: string | null;
  intentText: string;
  bubbleScope: BubbleScope | null;
  bubbleStatus: IntentBubbleUiState["status"];
  moreCreativeMode: "visual_inspiration" | "prompt_tokens";
  signals: LiveSignals;
  generating: boolean;
}): string {
  const observe = (input.perceptionSummary && input.perceptionSummary.toLowerCase() !== "unknown"
    ? input.perceptionSummary
    : "Overviewing the whole structure"
  ).replace(/\.$/, "");
  if (input.generating) {
    return "I'm generating image variants now — keep editing if you like; Solution Space will open when they're ready.";
  }
  if (input.bubbleStatus === "pending" && input.bubbleScope) {
    return `I think you may want to change the ${input.bubbleScope} — tell me with the bubble, or keep exploring.`;
  }
  if (input.bubbleStatus === "accepted" && input.bubbleScope) {
    return `Got it — we'll explore ${input.bubbleScope} changes next. Pick a few prompt chips below when you're ready to Generate.`;
  }
  if (input.intentText.trim().length >= 3) {
    const focus = input.partLabel ? ` on ${input.partLabel}` : "";
    return `I hear you want “${input.intentText.trim().slice(0, 72)}”${focus}. I'm gathering analogy directions so you can shape the prompt.`;
  }
  if (input.creativeState === "ready_for_help" || input.creativeState === "possible_fixation") {
    const focus = input.partLabel ? ` around ${input.partLabel}` : "";
    return `${observe}${focus}. You've stayed here a while — I can gently suggest a scope when it feels helpful.`;
  }
  if (input.creativeState === "focused_editing" || input.creativeState === "refining") {
    const focus = input.partLabel ? ` on ${input.partLabel}` : "";
    return `${observe}${focus}. Keep refining; I'll stay quiet unless you seem stuck.`;
  }
  if (input.moreCreativeMode === "visual_inspiration") {
    if (!input.hasModel) {
      return "This canvas is still blank — load a model or sketch a thought, and I'll start describing what I notice.";
    }
    return `${observe}. I'll stay quiet until you type a new intent or seem stuck.`;
  }
  return `${observe}. When the prompt chips look right, hit Generate and we'll open Solution Space.`;
}

function perceptionHeadline(interpretation: Interpretation) {
  const topMatch = designStateMatches(interpretation)[0];
  const route = topMatch?.route ? irRouteLabel(topMatch.route) : interpretation.primary_intent.replaceAll("_", " ");
  return `${confidenceTone(interpretation.confidence)}${route}`;
}

function perceptionEvidenceLine(interpretation: Interpretation) {
  const topMatch = designStateMatches(interpretation)[0];
  const axisScores = interpretation.features?.design_state_ir?.axis_scores ?? [];
  const axes = axisScores
    .slice(0, 3)
    .map((item) => `${item.axis} ${formatScore(item.score)}`)
    .join(" / ");
  const irSignals = topMatch?.signal_overlap?.slice(0, 4).join(", ");
  const base = interpretation.evidence?.[0] ?? "Waiting for more behavioral evidence.";
  const uncertainty =
    interpretation.confidence >= 0.78
      ? "High-confidence observation"
      : interpretation.confidence >= 0.55
        ? "Medium-confidence hypothesis"
        : "Low-confidence hypothesis";
  return [uncertainty, base, axes ? `Next axes: ${axes}` : null, irSignals ? `IR signals: ${irSignals}` : null]
    .filter(Boolean)
    .join(" · ");
}

function plannerClarificationBubbles(
  interpretation: Interpretation,
  selectedPartLabel?: string | null,
): PlannerClarificationBubble[] {
  const scope = inferredChangeScope(interpretation, selectedPartLabel);
  return [
    {
      id: "planner-primary",
      label: scope === "material" ? "Change material?" : scope === "part" ? "Change part?" : "Change contour?",
      detail:
        scope === "material"
          ? "确认要改材质/颜色/表面风格吗？"
          : scope === "part"
            ? "确认要改当前部件吗？"
            : "确认要改整体轮廓吗？",
      kind: scope === "part" ? "target" : "axis",
      position: "right",
    },
  ];
}

function inferredChangeScope(
  interpretation: Interpretation,
  selectedPartLabel?: string | null,
): "contour" | "part" | "material" {
  const text = [
    interpretation.primary_intent,
    ...(interpretation.evidence ?? []),
    ...(interpretation.features?.design_state_ir?.query_terms ?? []),
  ].join(" ").toLowerCase();
  return inferChangeScopeFromText(text, selectedPartLabel);
}

function inferChangeScopeFromText(text: string, _selectedPartLabel?: string | null): "contour" | "part" | "material" {
  const normalized = text.toLowerCase();
  if (/material|texture|surface|color|fabric|finish|材质|纹理|颜色|表面/.test(normalized)) return "material";
  if (/part|component|local|brush|部件|组件|局部|某个部分|当前部分/.test(normalized)) return "part";
  return "contour";
}

function explicitScopeFromText(text: string): "contour" | "part" | "material" | null {
  const normalized = text.toLowerCase();
  if (/material|texture|surface|color|fabric|finish|材质|纹理|颜色|表面/.test(normalized)) return "material";
  if (/part|component|local|brush|部件|组件|局部|某个部分|当前部分/.test(normalized)) return "part";
  if (/contour|silhouette|outline|shape|form|整体|轮廓|外形|形体|造型/.test(normalized)) return "contour";
  return null;
}

function nextBubbleScope(scope: BubbleScope | null): BubbleScope {
  if (scope === "contour") return "material";
  if (scope === "material") return "part";
  return "contour";
}

function predictorStatusLabel(interpretation: Interpretation) {
  const metadata = interpretation.predictor_metadata ?? {};
  if (interpretation.predictor === "vlm_multisignal") {
    return metadata.fallback_used ? "qwen fallback" : "qwen active";
  }
  if (metadata.fallback_used) return "rule fallback";
  return "rule";
}

function designStateMatches(interpretation: Interpretation | null) {
  return interpretation?.features?.design_state_ir?.matches ?? [];
}

function evidenceSummaryItems(interpretation: Interpretation | null): EvidenceSummaryItem[] {
  if (!interpretation) return [];
  const signals = interpretation.features?.signals ?? {};
  const geometric = signals.geometric ?? {};
  const semantic = signals.semantic ?? {};
  const visual = signals.visual_context ?? {};
  const interaction = signals.interaction ?? {};
  const rows: EvidenceSummaryItem[] = [
    {
      label: "Intent",
      value: interpretation.primary_intent,
      source: "Planner",
      confidence: interpretation.confidence,
    },
  ];
  if (interaction.event_type) rows.push({ label: "Behavior", value: interaction.event_type, source: "Interaction" });
  if (semantic.part_label || semantic.part_id) {
    rows.push({ label: "Target", value: semantic.part_label ?? semantic.part_id, source: "Semantic" });
  }
  if (geometric.dwell_ms) rows.push({ label: "Dwell", value: `${geometric.dwell_ms} ms`, source: "Attention" });
  if (geometric.brush_coverage) rows.push({ label: "Brush coverage", value: geometric.brush_coverage, source: "3D surface" });
  if (geometric.drag_length) rows.push({ label: "Drag length", value: geometric.drag_length, source: "3D transform" });
  if (geometric.smooth_strength) rows.push({ label: "Smooth strength", value: geometric.smooth_strength, source: "Local geometry" });
  if (semantic.primitive) rows.push({ label: "Primitive", value: semantic.primitive, source: "Add" });

  const artifact =
    visual.focus_observation_artifact_id ??
    visual.brush_mask_artifact_id ??
    visual.drag_operation_artifact_id ??
    visual.smooth_operation_artifact_id ??
    visual.primitive_addition_artifact_id ??
    visual.annotation_artifact_id;
  if (artifact) rows.push({ label: "Evidence artifact", value: artifact, source: "Memory" });

  const recommendedAxes = interpretation.features?.design_state_ir?.recommended_axes ?? [];
  if (recommendedAxes.length) {
    rows.push({
      label: "Next axes",
      value: recommendedAxes.slice(0, 3).join(" / "),
      source: "Design-state IR",
    });
  }

  const match = designStateMatches(interpretation)[0];
  if (match) {
    const route = irRouteLabel(match.route);
    const state = irStateLabel(match.design_state);
    rows.push({
      label: "IR state",
      value: `${state} → ${route}`,
      source: match.case_id ? `Design-state IR · ${match.case_id}` : "Design-state IR",
      score: match.score,
    });
  }
  return rows.slice(0, 8);
}

function evidenceValueLabel(value: unknown) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "string") return value.replaceAll("_", " ");
  if (value === null || value === undefined) return "none";
  return JSON.stringify(value);
}

function formatIRScore(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) return "IR";
  return `IR ${value.toFixed(2)}`;
}

function irRouteLabel(value: unknown) {
  if (typeof value !== "string" || !value) return "route unknown";
  return value.replaceAll("_", " ");
}

function irStateLabel(value: unknown) {
  if (typeof value !== "string" || !value) return "state unknown";
  return value.replaceAll("_", " ");
}

function plannerReply(interpretation: Interpretation) {
  const source = predictorStatusLabel(interpretation);
  const suggestion = interpretation.suggested_assistance?.[0];
  const action = suggestion ? suggestionActionLabel(suggestion) : interpretation.assistance_policy;
  const evidence = interpretation.evidence?.[0] ? ` Evidence: ${interpretation.evidence[0]}` : "";
  return `${interpretation.primary_intent} (${formatScore(interpretation.confidence)}, ${source}). Next: ${action}.${evidence}`;
}

function plannerGateStatus(metadata: Record<string, unknown> | null) {
  const gate = metadata?.planner_control_gate;
  if (!gate || typeof gate !== "object") return "unconfirmed";
  const status = (gate as Record<string, unknown>).status;
  return status === "confirmed" || status === "rejected" ? status : "unconfirmed";
}

function plannerGateStatusLabel(metadata: Record<string, unknown> | null) {
  const gate = metadata?.planner_control_gate;
  if (!gate || typeof gate !== "object") return "Planner gate: no confirmed intent yet";
  const record = gate as Record<string, unknown>;
  if (record.status === "confirmed") {
    const intent = record.confirmed_intent;
    const label =
      intent && typeof intent === "object"
        ? (intent as Record<string, unknown>).primary_intent
        : null;
    return `Planner gate: confirmed${typeof label === "string" ? ` · ${label}` : ""}`;
  }
  if (record.status === "rejected") return "Planner gate: previous interpretation rejected";
  return "Planner gate: no confirmed intent yet";
}

function dimensionGroupsForMoreCreative(
  directions: AnalogyDirection[],
  tokens: PromptToken[],
  interpretation: Interpretation | null,
) {
  const dimensions: Array<"Aesthetic" | "Functional" | "Structural"> = ["Aesthetic", "Functional", "Structural"];
  const axisScores = new Map(
    (interpretation?.features?.design_state_ir?.axis_scores ?? []).map((item) => [item.axis, item.score]),
  );
  const groups = dimensions.map((dimension) => {
    const dimensionDirections = directions.filter((direction) => direction.dimension === dimension);
    const directionIds = new Set(dimensionDirections.map((direction) => direction.direction_id));
    const dimensionTokens = tokens.filter(
      (token) => token.dimension === dimension || (token.source_direction_id && directionIds.has(token.source_direction_id)),
    );
    const score = axisScores.get(dimension) ?? Math.min(0.99, (dimensionDirections.length * 0.24 + dimensionTokens.length * 0.05));
    const firstDirection = dimensionDirections[0];
    return {
      dimension,
      score,
      scoreLabel: axisScores.has(dimension) ? `IR ${formatScore(score)}` : `${dimensionDirections.length} directions`,
      summary: firstDirection?.transfer_rationale ?? "",
      directions: dimensionDirections,
      tokens: dimensionTokens.slice(0, 8),
    };
  });
  return groups
    .filter((group) => group.directions.length || group.tokens.length || axisScores.has(group.dimension))
    .sort((a, b) => b.score - a.score);
}

function cleanAnalogyDirections(directions: AnalogyDirection[]): AnalogyDirection[] {
  return directions.map((direction) => ({
    ...direction,
    transfer_rationale: stripFallbackDirectionText(direction.transfer_rationale),
    metadata: {
      ...direction.metadata,
      prompt_tokens: aatNounPromptTokens(direction),
    },
  }));
}

function stripFallbackDirectionText(value: unknown) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return "";
  if (/analogy words|suggestions for|without generating|use, affordance|silhouette, proportion|style mood/i.test(text)) {
    return "";
  }
  return text;
}

const AAT_NOUN_BANK: Record<"Aesthetic" | "Functional" | "Structural", string[]> = {
  Aesthetic: [
    "glaze",
    "patina",
    "enamel",
    "iridescence",
    "translucency",
    "velvet",
    "mosaic",
    "marbling",
    "lacquer",
    "gradient",
  ],
  Functional: [
    "handle",
    "hinge",
    "grip",
    "socket",
    "strap",
    "fastener",
    "spout",
    "stand",
    "joint",
    "rim",
  ],
  Structural: [
    "silhouette",
    "contour",
    "profile",
    "arcade",
    "buttress",
    "rib",
    "vault",
    "module",
    "aperture",
    "facade",
  ],
};

function aatNounPromptTokens(direction: AnalogyDirection): PromptToken[] {
  const raw = Array.isArray(direction.metadata?.prompt_tokens) ? direction.metadata.prompt_tokens : [];
  const dimension = direction.dimension;
  const source = [...raw, ...(AAT_NOUN_BANK[dimension] ?? [])];
  const seen = new Set<string>();
  const tokens: PromptToken[] = [];
  for (const item of source) {
    const token = coercePromptToken(item, direction);
    if (!token) continue;
    const label = token.label
      .replace(/_/g, " ")
      .replace(/\b(transfer|use|create|suggest|make|turn|preserve|keeping|without)\b/gi, "")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/[.,;:]+$/g, "");
    if (!label || label.split(/\s+/).length > 3) continue;
    const key = `${dimension}:${label.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    tokens.push({
      ...token,
      label,
      dimension,
      role: token.role ?? "aat-noun",
    });
    if (tokens.length >= 7) break;
  }
  return tokens;
}

function suggestionActionLabel(suggestion: AssistanceSuggestion) {
  const nextAction = suggestion.metadata?.suggested_next_action;
  if (nextAction === "compare_more_candidates") return "Generate more fitted variants";
  if (nextAction === "generate_boundary_refinements") return "Generate boundary refinements";
  if (nextAction === "generate_drag_candidates") return "Generate drag-aware forms";
  if (nextAction === "preview_or_accept_candidate") return suggestion.label ?? "Preview fitted candidate";
  if (suggestion.mode === "replace") return suggestion.label ?? "Generate part replacements";
  if (suggestion.mode === "drag_regenerate") return suggestion.label ?? "Generate drag-aware forms";
  if (suggestion.mode === "diverge") return suggestion.label ?? "Generate divergent forms";
  return suggestion.label ?? suggestion.question ?? suggestion.type;
}

function rankCandidates(items: Candidate[]) {
  return [...items].sort((a, b) => {
    const socketDelta = socketCompatibilityScore(b) - socketCompatibilityScore(a);
    if (Math.abs(socketDelta) > 0.0001) return socketDelta;
    const alignDelta = (b.scores.intent_alignment ?? 0) - (a.scores.intent_alignment ?? 0);
    if (Math.abs(alignDelta) > 0.0001) return alignDelta;
    return 0;
  });
}

function socketCompatibilityScore(candidate: Candidate) {
  const direct = candidate.scores.socket_compatibility;
  if (typeof direct === "number" && !Number.isNaN(direct)) return direct;
  const evidence = pipelineEvidence(candidate);
  const evidenceScore = evidence.socket_compatibility_score;
  if (typeof evidenceScore === "number" && !Number.isNaN(evidenceScore)) return evidenceScore;
  return 0;
}

function artifactStatus(value: unknown) {
  if (typeof value !== "string" || !value) return "pending";
  return value.split("/").at(-1) || "ready";
}

function candidatePreviewUrl(candidate: Candidate) {
  const remoteUrl = candidate.metadata.remote_image_url;
  if (typeof remoteUrl === "string" && remoteUrl) return absoluteUrl(remoteUrl);
  return candidate.thumbnail_url ? absoluteUrl(candidate.thumbnail_url) : null;
}

function absoluteUrl(url: string) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url}`;
}

function candidateStage(candidate: Candidate) {
  return stringValue(candidate.metadata.stage);
}

function candidateFidelity(candidate: Candidate) {
  return stringValue(candidate.metadata.fidelity);
}

function candidateCommitPolicy(candidate: Candidate) {
  return candidate.mesh_url || candidate.obj_url ? "active_asset" : "direction_memory";
}

function candidateArtifactLevel(candidate: Candidate) {
  if (candidate.mesh_url || candidate.obj_url) return "3D mesh ready";
  if (canGenerateCandidateHy3d(candidate)) return "Image direction";
  if (candidate.thumbnail_url || candidate.metadata.remote_image_url) return "Image only";
  return "Contract";
}

function candidateProvenance(candidate: Candidate) {
  const value = pipelineEvidenceValue(candidate, "provenance") ?? candidate.metadata.adapter;
  if (typeof value !== "string" || !value) return "unknown";
  return value.replace("remote-staged-creativeflow", "remote_staged");
}

function canGenerateCandidateHy3d(candidate: Candidate) {
  return Boolean(candidate.metadata.remote_result_path && candidate.metadata.direction_id);
}

function pipelineEvidence(candidate: Candidate) {
  const value = candidate.metadata.pipeline_evidence;
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function pipelineEvidenceValue(candidate: Candidate, key: string) {
  return pipelineEvidence(candidate)[key];
}

function remoteJobLabel(candidate: Candidate) {
  const value = pipelineEvidenceValue(candidate, "remote_job_id") ?? candidate.metadata.remote_job_id;
  if (typeof value !== "string" || !value) return "none";
  return value.replace("rw_creativeflow_", "rw_cf_").slice(0, 28);
}

function directionLabel(candidate: Candidate) {
  const value = pipelineEvidenceValue(candidate, "direction_id") ?? candidate.metadata.direction_id;
  return typeof value === "string" && value ? value.replace("dir_", "") : "none";
}

function fitEvidenceLabel(candidate: Candidate) {
  const evidence = pipelineEvidence(candidate);
  const fitResult = candidate.metadata.fit_result;
  if (fitResult && typeof fitResult === "object" && "status" in fitResult) {
    return String((fitResult as { status?: string }).status ?? "fit");
  }
  if (typeof evidence.fit_status === "string" && evidence.fit_status) return evidence.fit_status;
  const policy = evidence.fit_policy;
  const hasMesh = evidence.has_mesh_glb || evidence.has_mesh_obj;
  if (typeof policy === "string" && policy) return policy;
  return hasMesh ? "mesh" : candidate.metadata.fit_contract ? "contract" : "pending";
}

function socketEvidenceLabel(candidate: Candidate) {
  const evidence = pipelineEvidence(candidate);
  const sourcePart = evidence.source_part_id;
  const faceCount = evidence.socket_face_count;
  if (typeof sourcePart === "string" && sourcePart) {
    return `${sourcePart}${faceCount ? ` / ${faceCount}` : ""}`;
  }
  return faceCount ? `${faceCount} faces` : "none";
}

function seamEvidenceLabel(candidate: Candidate) {
  const evidence = pipelineEvidence(candidate);
  const validation = evidence.seam_validation;
  if (validation && typeof validation === "object" && "status" in validation) {
    const status = String((validation as { status?: string }).status ?? "");
    const score = socketScoreLabel(evidence.socket_compatibility_score);
    if (status === "geometry_preview_pass") return `preview ok${score}`;
    if (status === "review_needed") return `review${score}`;
    if (status) return `${status.replace("geometry_", "")}${score}`;
  }
  const fitResult = candidate.metadata.fit_result;
  if (
    fitResult &&
    typeof fitResult === "object" &&
    "quality" in fitResult &&
    (fitResult as { quality?: unknown }).quality
  ) {
    const quality = (fitResult as { quality?: { seam_validation?: { status?: string } } }).quality;
    const status = quality?.seam_validation?.status;
    if (status === "geometry_preview_pass") return "preview ok";
    if (status === "review_needed") return "review";
  }
  return "none";
}

function socketScoreLabel(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) return "";
  return ` ${value.toFixed(2)}`;
}

function partDiscoveryAdapter(response: PartDiscoveryResponse) {
  const adapter = response.metadata?.adapter;
  if (adapter === "obj_group_fallback") return "OBJ groups (fallback)";
  return typeof adapter === "string" ? adapter : "unknown";
}

function partDiscoveryDisplayAdapter(response: PartDiscoveryResponse) {
  const remoteStatus = partDiscoveryRemoteValue(response, "status");
  if (remoteStatus === "completed" && partSegmentationUrl(response.parts)) return "partfield-real";
  return partDiscoveryAdapter(response);
}

function partDiscoveryRemoteValue(response: PartDiscoveryResponse, key: string) {
  const remote = response.metadata?.remote_result;
  if (!remote || typeof remote !== "object") return "none";
  const value = (remote as Record<string, unknown>)[key];
  if (value === null || value === undefined || value === "") return "none";
  if (typeof value === "object") return key === "error" ? JSON.stringify(value).slice(0, 120) : "available";
  return String(value);
}

function partSegmentationUrl(parts: PartRecord[]) {
  for (const part of parts) {
    const value = part.metadata?.segmented_mesh_url;
    if (typeof value === "string" && value) return value;
  }
  return null;
}

function inferMeshExtension(url: string | null | undefined) {
  if (!url) return null;
  if (["none", "null", "undefined", "nan"].includes(url.trim().toLowerCase())) return null;
  const directExtension = url.split("?")[0].toLowerCase().split(".").pop();
  if (directExtension && ["glb", "gltf", "obj", "ply"].includes(directExtension)) {
    return directExtension;
  }
  try {
    const parsed = new URL(url, API_BASE);
    const artifactPath = parsed.searchParams.get("path");
    const artifactExtension = artifactPath?.toLowerCase().split("?")[0].split(".").pop();
    if (artifactExtension && ["glb", "gltf", "obj", "ply"].includes(artifactExtension)) {
      return artifactExtension;
    }
  } catch {
    return null;
  }
  return null;
}

function assetExportUrl(assetId: string, format: "glb" | "obj") {
  return `${API_BASE}/api/v1/assets/${assetId}/export?format=${format}`;
}

function isRenderableBenchmarkAsset(asset: BenchmarkAsset) {
  const hasMeshUrl = Boolean(asset.mesh_url && inferMeshExtension(asset.mesh_url));
  const hasObjUrl = Boolean(asset.obj_url && inferMeshExtension(asset.obj_url));
  return asset.model_available !== false && (hasMeshUrl || hasObjUrl);
}

function findPartByViewportName(parts: PartRecord[], name: string) {
  const normalized = name.trim();
  if (!normalized) return null;
  return (
    parts.find((part) => part.part_id === normalized) ??
    parts.find((part) => part.label === normalized) ??
    parts.find((part) => String(part.metadata?.source_part_id ?? "") === normalized) ??
    null
  );
}

function benchmarkAssetGroupLabel(asset: BenchmarkAsset) {
  if (asset.metadata?.source === "local_white_model") {
    const category = String(asset.metadata.category ?? "white_models").replaceAll("_", " ");
    return `White Models · ${category.replace(/\b\w/g, (match) => match.toUpperCase())}`;
  }
  return "CreativeFlow / Design DB";
}

function compareBenchmarkAssets(a: BenchmarkAsset, b: BenchmarkAsset) {
  const priority = (asset: BenchmarkAsset) => (asset.metadata?.source === "local_white_model" ? 0 : 1);
  const priorityDelta = priority(a) - priority(b);
  if (priorityDelta !== 0) return priorityDelta;
  const group = benchmarkAssetGroupLabel(a).localeCompare(benchmarkAssetGroupLabel(b));
  if (group !== 0) return group;
  return a.label.localeCompare(b.label);
}

function benchmarkAssetGroups(assets: BenchmarkAsset[]) {
  const groups = new Map<string, BenchmarkAsset[]>();
  for (const asset of assets) {
    const label = benchmarkAssetGroupLabel(asset);
    groups.set(label, [...(groups.get(label) ?? []), asset]);
  }
  return Array.from(groups, ([label, groupAssets]) => ({ label, assets: groupAssets }));
}

function selectedPartFaceCount(parts: PartRecord[], selectedPart: string) {
  const part = parts.find((item) => item.part_id === selectedPart);
  const value = part?.metadata?.face_count;
  return value === null || value === undefined ? "none" : String(value);
}

function partSocketSummary(part: PartRecord | null) {
  if (!part?.metadata) return "none";
  const sourcePart = part.metadata.source_part_id;
  const faceCount = part.metadata.face_count;
  const bbox3d = part.metadata.bbox3d;
  const source = typeof sourcePart === "string" && sourcePart ? sourcePart : part.part_id;
  const faces = faceCount === null || faceCount === undefined ? "no faces" : `${faceCount} faces`;
  const bbox = bbox3d && typeof bbox3d === "object" ? "bbox3d" : "no bbox";
  return `${source} / ${faces} / ${bbox}`;
}

function stageShortLabel(stage: string) {
  const labels: Record<string, string> = {
    silhouette: "outline",
    rough_form: "form",
    part: "part",
    texture: "texture",
  };
  return labels[stage] ?? stage;
}

function caseCreativeStage(manifest: CaseManifest, fallback: string) {
  const metadataStage = manifest.case.metadata?.creative_stage;
  if (typeof metadataStage === "string" && isCreativeStage(metadataStage)) return metadataStage;
  const acceptedStage = manifest.accepted_candidates?.[0]?.metadata?.stage;
  if (typeof acceptedStage === "string" && isCreativeStage(acceptedStage)) return acceptedStage;
  return isCreativeStage(fallback) ? fallback : "part";
}

function isCreativeStage(stage: string) {
  return ["silhouette", "rough_form", "part", "texture"].includes(stage);
}

function commitPolicyForStage(stage: string, fidelity: string) {
  if (stage === "silhouette" && fidelity === "low") return "direction_memory";
  if (stage === "texture") return "material_state";
  return stage === "part" ? "fitted_asset" : "active_asset";
}

function isActiveJobStatus(status?: string | null) {
  if (!status) return false;
  return !["completed", "failed", "cancelled"].includes(status);
}

function formatBytes(value?: number) {
  if (!value) return "none";
  if (value > 1024 * 1024 * 1024) return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`;
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(0)} MB`;
  return `${value} B`;
}

function setupLogSummary(value?: string | null) {
  if (!value) return "none";
  const lines = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.at(-1)?.slice(0, 120) ?? "none";
}

function setupProcessSummary(
  processes?: Array<{ pid?: string; elapsed?: string; command?: string }>,
) {
  if (!processes?.length) return "none";
  const setup = processes.find((item) => item.command?.includes("setup_partfield_env.sh"));
  const pip = processes.find((item) => item.command?.includes("pip install"));
  const active = setup ?? pip ?? processes[0];
  return `pid ${active.pid ?? "?"} / ${active.elapsed ?? "?"} / ${processes.length} proc`;
}

function creativeflowSummary(health: RemoteWorkerHealth | null) {
  const pipeline = health?.creativeflow_pipeline;
  if (!pipeline) return "unchecked";
  const ready = [
    pipeline.legacy_pipeline_ready,
    pipeline.structured_transfer_ready,
    pipeline.minimal_transfer_ready,
    pipeline.hy3d_ready,
  ].filter(Boolean).length;
  return ready === 4 ? "ready / legacy + transfer + hy3d" : `${ready}/4 ready`;
}

function preflightBlockingSummary(preflight: RemoteWorkerPreflight | null) {
  if (!preflight) return "unchecked";
  const blocks = [];
  if (!preflight.qwen_image?.probe?.reachable) blocks.push("qwen");
  const kb = preflight.kb_network ?? {};
  if (Object.values(kb).some((probe) => !probe.reachable)) blocks.push("kb");
  const ossKeys = preflight.oss?.configured_keys ?? {};
  if (Object.values(ossKeys).some((ready) => !ready)) blocks.push("oss");
  return blocks.length ? `blocked: ${blocks.join(", ")}` : "blocked";
}

function probeSummary(probe?: {
  reachable?: boolean;
  status?: number | null;
  elapsed_sec?: number;
  error?: string | null;
}) {
  if (!probe) return "unchecked";
  const state = probe.reachable ? "reachable" : "offline";
  const code = probe.status ? ` ${probe.status}` : "";
  const time = typeof probe.elapsed_sec === "number" ? ` / ${probe.elapsed_sec}s` : "";
  return `${state}${code}${time}`;
}

function kbSummary(preflight: RemoteWorkerPreflight | null) {
  const entries = Object.entries(preflight?.kb_network ?? {});
  if (!entries.length) return "unchecked";
  return entries
    .map(([name, probe]) => `${name}:${probe.reachable ? "ok" : probe.error ?? "fail"}`)
    .join(" / ");
}

function ossSummary(preflight: RemoteWorkerPreflight | null) {
  const keys = preflight?.oss?.configured_keys;
  if (!keys) return "unchecked";
  const ready = Object.values(keys).filter(Boolean).length;
  return `${ready}/${Object.keys(keys).length} keys`;
}

function readCandidateMemory(session: SessionRecord | null) {
  const memory = session?.metadata?.candidate_memory;
  if (!memory || typeof memory !== "object") {
    return {
      lastAcceptedStage: "none",
      lastCommitPolicy: "none",
      lastAcceptedCandidateId: "none",
      directionCount: 0,
      rejectedCount: 0,
      lastRejectedCandidateId: "none",
      lastRejectedStage: "none",
    };
  }
  const record = memory as Record<string, unknown>;
  const directions = Array.isArray(record.accepted_direction_ids)
    ? record.accepted_direction_ids
    : [];
  const rejected = Array.isArray(record.rejected) ? record.rejected : [];
  return {
    lastAcceptedStage: stringValue(record.last_accepted_stage),
    lastCommitPolicy: stringValue(record.last_commit_policy),
    lastAcceptedCandidateId: stringValue(record.last_accepted_candidate_id),
    directionCount: directions.length,
    rejectedCount: rejected.length,
    lastRejectedCandidateId: stringValue(record.last_rejected_candidate_id),
    lastRejectedStage: stringValue(record.last_rejected_stage),
  };
}

function stringValue(value: unknown) {
  return typeof value === "string" && value ? value : "none";
}

function divergenceAxesForStage(stage: string) {
  const axes: Record<string, string[]> = {
    silhouette: ["silhouette", "proportion", "stance", "mass_distribution"],
    rough_form: ["curvature", "volume_distribution", "structural_language"],
    part: ["motif", "structure", "boundary_behavior", "surface_depth"],
    texture: ["material", "color", "surface_pattern", "finish"],
  };
  return axes[stage] ?? axes.part;
}

function defaultFidelityForStage(stage: string) {
  if (stage === "silhouette") return "low";
  if (stage === "texture") return "high";
  return "medium";
}

function upsertIntentDraft(items: IntentDraft[], draft: IntentDraft) {
  const next = items.filter((item) => item.draft_id !== draft.draft_id);
  return [draft, ...next].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

function upsertArtifact(items: ArtifactRecord[], artifact: ArtifactRecord) {
  const next = items.filter((item) => item.artifact_id !== artifact.artifact_id);
  return [artifact, ...next].slice(0, 12);
}

function referenceImagesPayload(items: ArtifactRecord[]) {
  return items.map((item) => ({
    artifact_id: item.artifact_id,
    url: item.url,
    role: item.metadata?.role ?? "shape_reference",
    type: item.type,
  }));
}

function referenceModelsPayload(items: ArtifactRecord[]) {
  return items.map((item) => ({
    artifact_id: item.artifact_id,
    url: item.url,
    role: item.metadata?.role ?? "model_reference",
    type: item.type,
    filename: item.metadata?.uploaded_filename ?? null,
  }));
}

function artifactRecordsFromDraftRefs(
  rawRefs: string[],
  structuredRefs: unknown,
  fallbackType: "reference_image" | "reference_model",
): ArtifactRecord[] {
  const rows = Array.isArray(structuredRefs) ? structuredRefs : [];
  const byUrl = new Map<string, Record<string, unknown>>();
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const record = row as Record<string, unknown>;
    const url = typeof record.url === "string" ? record.url : null;
    if (url) byUrl.set(url, record);
  }
  return rawRefs.map((url, index) => {
    const record = byUrl.get(url) ?? {};
    const artifactId =
      typeof record.artifact_id === "string" && record.artifact_id
        ? record.artifact_id
        : `draft_ref_${index}_${Math.abs(hashString(url))}`;
    return {
      artifact_id: artifactId,
      type: typeof record.type === "string" ? record.type : fallbackType,
      url,
      session_id: null,
      asset_id: null,
      worker: "manual",
      operation: null,
      metadata: {
        ...record,
        role: record.role ?? (fallbackType === "reference_image" ? "shape_reference" : "model_reference"),
      },
      created_at: new Date().toISOString(),
    };
  });
}

function hashString(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index);
    hash |= 0;
  }
  return hash;
}

function buildAnnotationPayload({
  sessionId,
  asset,
  partId,
  partLabel,
  text,
  displayMode,
  strokes,
}: {
  sessionId: string;
  asset: AssetRecord;
  partId: string | null;
  partLabel: string | null;
  text: string;
  displayMode: CanvasDisplayMode;
  strokes?: AnnotationStroke[];
}) {
  const normalizedText = text.trim();
  const fallbackPoints = [
    { x: 0.36, y: 0.68, t: 0 },
    { x: 0.5, y: 0.24, t: 80 },
    { x: 0.66, y: 0.68, t: 160 },
    { x: 0.36, y: 0.68, t: 240 },
  ];
  const normalizedStrokes = strokes?.length
    ? strokes
        .map((stroke) =>
          stroke.map((point) => ({
            x: clamp01(point.x),
            y: clamp01(point.y),
            t: Math.max(0, Math.round(point.t)),
          })),
        )
        .filter((stroke) => stroke.length >= 2)
    : [fallbackPoints];
  const allPoints = normalizedStrokes.flat();
  const shapeHint = normalizedText.match(/triangle|三角/i)
    ? "triangle"
    : inferAnnotationShape(allPoints);
  return {
    session_id: sessionId,
    asset_id: asset.asset_id,
    part_id: partId,
    text: normalizedText || null,
    strokes: normalizedStrokes.map((strokePoints, index) => ({
        stroke_id: `stroke_${index}_${crypto.randomUUID().slice(0, 8)}`,
        tool: "pencil",
        shape_hint: shapeHint,
        points: strokePoints,
        bbox: annotationBoundingBox(strokePoints),
        style: { color: "#0f172a", width: 2 },
      })),
    projection: {
      space: "screen_normalized",
      viewport: displayMode,
      target: partId ? "part" : "whole_object",
      part_label: partLabel,
    },
    metadata: {
      source: strokes?.length ? "annotation_canvas_overlay" : "intent_composer_annotation_button",
      object_type: asset.object_type,
      asset_label: asset.label,
      stroke_count: normalizedStrokes.length,
      point_count: allPoints.length,
      inferred_shape: shapeHint,
      bbox: annotationBoundingBox(allPoints),
    },
  };
}

function annotationBoundingBox(points: AnnotationPoint[]) {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return {
    x: Math.min(...xs),
    y: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
  };
}

function inferAnnotationShape(points: AnnotationPoint[]) {
  if (points.length < 4) return "point_mark";
  const first = points[0];
  const last = points[points.length - 1];
  const closed = Math.hypot(first.x - last.x, first.y - last.y) < 0.04;
  const bbox = annotationBoundingBox(points);
  if (closed && bbox.width > 0.08 && bbox.height > 0.08) return "closed_contour";
  if (bbox.width > bbox.height * 2.4) return "horizontal_stroke";
  if (bbox.height > bbox.width * 2.4) return "vertical_stroke";
  return "freehand_contour";
}

function buildBrushMaskPayload({
  sessionId,
  asset,
  part,
  partId,
  text,
  displayMode,
}: {
  sessionId: string;
  asset: AssetRecord;
  part?: PartRecord;
  partId: string | null;
  text: string;
  displayMode: CanvasDisplayMode;
}) {
  const normalizedText = text.trim();
  const label = part?.label ?? partId ?? "selected surface";
  return {
    session_id: sessionId,
    asset_id: asset.asset_id,
    part_id: partId,
    label,
    mask: {
      kind: "surface_region",
      representation: "normalized_screen_polyline_with_part_anchor",
      screen_path: [
        { x: 0.37, y: 0.42, pressure: 0.48, t: 0 },
        { x: 0.45, y: 0.38, pressure: 0.7, t: 70 },
        { x: 0.55, y: 0.41, pressure: 0.76, t: 140 },
        { x: 0.6, y: 0.51, pressure: 0.62, t: 210 },
        { x: 0.51, y: 0.58, pressure: 0.58, t: 280 },
        { x: 0.41, y: 0.54, pressure: 0.52, t: 350 },
      ],
      bbox: [0.37, 0.38, 0.6, 0.58],
      anchor_part_id: partId,
      anchor_part_label: label,
      intent_hint: normalizedText || null,
    },
    projection: {
      space: "screen_to_surface",
      viewport: displayMode,
      target: partId ? "part_surface" : "whole_object_surface",
      camera_position: [0, 1.5, 4],
      camera_target: [0, 0.8, 0],
      part_label: label,
    },
    metrics: {
      coverage: 0.18,
      stroke_count: 1,
      confidence: part?.metadata?.source === "partfield" ? 0.78 : 0.58,
    },
    metadata: {
      source: "intent_composer_brush_button",
      object_type: asset.object_type,
      asset_label: asset.label,
      part_record: part ?? null,
    },
  };
}

function buildSmoothOperationPayload({
  sessionId,
  asset,
  part,
  partId,
  text,
  displayMode,
  response,
}: {
  sessionId: string;
  asset: AssetRecord;
  part?: PartRecord | null;
  partId: string | null;
  text: string;
  displayMode: CanvasDisplayMode;
  response: GeometryWorkerResponse;
}) {
  const normalizedText = text.trim();
  const label = part?.label ?? partId ?? "local surface";
  return {
    session_id: sessionId,
    asset_id: asset.asset_id,
    part_id: partId,
    label,
    region: {
      type: "local_surface_patch",
      target: partId ? "part_surface" : "whole_object_surface",
      part_id: partId,
      label,
      normalized_bbox: [0.34, 0.36, 0.63, 0.62],
      viewport: displayMode,
    },
    brush: {
      kind: "smoothing_brush",
      radius: 0.18,
      falloff: "soft",
      path: [
        { x: 0.42, y: 0.48, pressure: 0.62, t: 0 },
        { x: 0.48, y: 0.44, pressure: 0.7, t: 80 },
        { x: 0.56, y: 0.49, pressure: 0.66, t: 160 },
      ],
    },
    parameters: {
      strength: 0.64,
      iterations: 2,
      preserve_boundary: true,
      intent_hint: normalizedText || null,
    },
    preview: {
      geometry_job_id: response.job_id,
      preview_mesh_url: response.preview_mesh_url,
      result_mesh_url: response.result_mesh_url,
    },
    metrics: {
      ...(response.metrics ?? {}),
      local_region_coverage: 0.16,
    },
    metadata: {
      source: "smooth_tool_preview",
      object_type: asset.object_type,
      asset_label: asset.label,
      part_record: part ?? null,
    },
  };
}

function buildPrimitiveAdditionPayload({
  sessionId,
  asset,
  partId,
  partLabel,
  primitive,
  text,
}: {
  sessionId: string;
  asset: AssetRecord | null;
  partId: string | null;
  partLabel: string | null;
  primitive: Exclude<CanvasPrimitive, null>;
  text: string;
}) {
  const normalizedText = text.trim();
  return {
    session_id: sessionId,
    asset_id: asset?.asset_id ?? null,
    part_id: partId,
    primitive,
    transform: {
      position: [0, 0.6, 0],
      scale: primitive === "cube" ? [0.28, 0.28, 0.28] : [0.25, 0.25, 0.25],
      rotation: [0, 0, 0],
      space: "world",
    },
    relation: {
      type: partId ? "attached_to_part_or_nearby" : "attached_or_nearby",
      target_part_id: partId,
      target_part_label: partLabel,
      rationale: normalizedText || "user added primitive as structural intent evidence",
    },
    constraints: ["preserve object identity", "keep existing accepted regions unless explicitly edited"],
    preview: {
      local_preview_only: true,
      canvas_primitive: primitive,
    },
    metadata: {
      source: "intent_composer_add_button",
      object_type: asset?.object_type ?? "blank_scene",
      asset_label: asset?.label ?? null,
      intent_hint: normalizedText || null,
    },
  };
}

function buildDragOperationPayload({
  sessionId,
  asset,
  part,
  partId,
  text,
  response,
}: {
  sessionId: string;
  asset: AssetRecord;
  part?: PartRecord | null;
  partId: string | null;
  text: string;
  response?: GeometryWorkerResponse | null;
}) {
  const start = [0.0, 0.0, 0.0];
  const end = [0.42, 0.12, 0.0];
  const vector = end.map((value, index) => Number((value - start[index]).toFixed(4)));
  const length = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
  const normalizedText = text.trim();
  const label = part?.label ?? partId ?? "selected part";
  return {
    session_id: sessionId,
    asset_id: asset.asset_id,
    part_id: partId,
    label,
    drag: {
      start,
      end,
      vector,
      space: "world",
      influence_radius: 0.25,
      handle: "local_part_handle",
      intent_hint: normalizedText || null,
    },
    region: {
      type: "local_part_or_region",
      target: partId ? "part" : "whole_object",
      part_id: partId,
      label,
    },
    preview: {
      geometry_job_id: response?.job_id ?? null,
      preview_mesh_url: response?.preview_mesh_url ?? null,
      result_mesh_url: response?.result_mesh_url ?? null,
    },
    metrics: {
      ...(response?.metrics ?? {}),
      drag_vector: vector,
      drag_length: Number(length.toFixed(4)),
      direction_relation: length > 0.05 ? "outward_from_part_center" : "small_adjustment",
    },
    metadata: {
      source: response ? "move_tool_preview" : "intent_composer_drag_button",
      object_type: asset.object_type,
      asset_label: asset.label,
      part_record: part ?? null,
    },
  };
}

function buildFocusObservationPayload({
  sessionId,
  asset,
  partId,
  partLabel,
  displayMode,
  focusSource = "toolbar_hover_commit",
}: {
  sessionId: string;
  asset: AssetRecord;
  partId: string | null;
  partLabel: string | null;
  displayMode: CanvasDisplayMode;
  focusSource?: string;
}) {
  return {
    session_id: sessionId,
    asset_id: asset.asset_id,
    part_id: partId,
    label: partLabel ?? partId ?? asset.label,
    observation: {
      focus_source: focusSource,
      selection_type: partId ? "part" : "whole_object",
      selected_part_label: partLabel,
      object_label: asset.label,
      interaction_mode: "projected_semantic_hover",
    },
    viewport: {
      display_mode: displayMode,
      camera_position: [0, 1.5, 4],
      camera_target: [0, 0.8, 0],
    },
    metrics: {
      dwell_ms: 1200,
      confidence: partId ? 0.72 : 0.58,
    },
    metadata: {
      source: "intent_composer_hover_button",
      semantic_source: "projected_hover_tentative",
      object_type: asset.object_type,
    },
  };
}

function analogyPromptTokens(directions: AnalogyDirection[]): PromptToken[] {
  const tokens: PromptToken[] = [];
  const seen = new Set<string>();
  for (const direction of directions) {
    const raw = direction.metadata?.prompt_tokens;
    const rows = Array.isArray(raw) ? raw : [];
    for (const row of rows) {
      const token = coercePromptToken(row, direction);
      if (!token) continue;
      const key = promptTokenKey(token);
      if (seen.has(key)) continue;
      seen.add(key);
      tokens.push(token);
    }
  }
  return tokens.slice(0, 24);
}

function buildLocalAnalogyDirections(
  asset: AssetRecord | null,
  interpretation: Interpretation | null,
  prompt: string,
  part: PartRecord | null,
  scopeOverride?: BubbleScope | null,
): AnalogyDirection[] {
  const object = asset?.object_type || asset?.label || "object";
  const focus = part?.label || "whole form";
  const seed = prompt.trim() || interpretation?.primary_intent || object;
  const scope = scopeOverride ?? (prompt.trim() ? inferChangeScopeFromText(prompt) : interpretation ? inferredChangeScope(interpretation, part?.label) : "contour");
  const rows: Array<[AnalogyDirection["dimension"], string, string[]]> = [
    ["Aesthetic", "Style mood", ["personalized character", "soft color rhythm", "decorative accent", "cute proportion"]],
    ["Structural", "Form logic", ["layered silhouette", "modular outline", "clear boundary", "balanced proportion"]],
    ["Functional", "Use analogy", ["handle affordance", "protective shell", "support structure", "interactive detail"]],
  ];
  const scopedRows = rows.filter(([dimension]) =>
    scope === "material" ? dimension === "Aesthetic" : scope === "part" ? dimension !== "Aesthetic" : dimension !== "Functional",
  );
  return scopedRows.map(([dimension, label, tokens], index) => ({
    direction_id: `local_${dimension.toLowerCase()}_${index}`,
    label: `${dimension}: ${object}`,
    dimension,
    divergence_mode: "local",
    source_domain: seed,
    target_domain: object,
    relation: "prompt_keyword_seed",
    transfer_rationale: `${label} suggestions for ${focus} without generating yet.`,
    constraints: ["preserve object identity", "wait for explicit Generate"],
    score: 0.62,
    metadata: {
      source: "frontend_fast_seed",
      prompt_tokens: tokens.map((token) => ({ label: token, dimension, role: "analogy" })),
    },
  }));
}

function visualInspirationItems(asset: AssetRecord | null, part: PartRecord | null, prompt: string) {
  const object = asset?.label || asset?.object_type || "creative 3d object";
  const focus = part?.label || "design";
  const intent = prompt.trim() || "creative reference";
  const queries = [
    `${object} ${intent} pinterest`,
    `${object} ${focus} design inspiration`,
    `${object} material style moodboard`,
  ];
  return queries.map((query, index) => ({
    label: index === 0 ? "Pinterest search" : index === 1 ? "Part references" : "Material mood",
    source: query.replace(/\s+pinterest$/i, ""),
    url: `https://www.pinterest.com/search/pins/?q=${encodeURIComponent(query.replace(/\s+pinterest$/i, ""))}`,
  }));
}

function coercePromptToken(value: unknown, direction: AnalogyDirection): PromptToken | null {
  if (typeof value === "string") {
    const label = value.trim();
    return label
      ? {
          label,
          dimension: direction.dimension,
          role: "analogy",
          source_direction_id: direction.direction_id,
        }
      : null;
  }
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const label = typeof record.label === "string" ? record.label.trim() : "";
  if (!label) return null;
  return {
    token_id: typeof record.token_id === "string" ? record.token_id : undefined,
    label,
    dimension: promptTokenDimension(record.dimension, direction.dimension),
    role: typeof record.role === "string" ? record.role : "analogy",
    source_direction_id: direction.direction_id,
    weight: typeof record.weight === "number" ? record.weight : undefined,
  };
}

function promptTokenDimension(value: unknown, fallback: PromptToken["dimension"]): PromptToken["dimension"] {
  return value === "Aesthetic" || value === "Functional" || value === "Structural" || value === "Cross-domain"
    ? value
    : fallback;
}

function promptTokenKey(token: PromptToken) {
  return `${token.dimension ?? "Any"}:${token.role ?? "word"}:${token.label.toLowerCase()}`;
}

function composePromptWithTokens(text: string, tokens: PromptToken[]) {
  const base = text.replace(/\n?Analogy keywords:.*$/s, "").trim();
  if (!tokens.length) return base;
  const words = tokens.map((token) => token.label).join(", ");
  return `${base}\nAnalogy keywords: ${words}`.trim();
}

function buildAnalogyPromptPackage(
  promptText: string,
  tokens: PromptToken[],
  directions: AnalogyDirection[],
) {
  const selectedDirectionIds = Array.from(
    new Set(
      tokens
        .map((token) => token.source_direction_id)
        .filter((value): value is string => typeof value === "string" && value.length > 0),
    ),
  );
  const selectedDirections = directions
    .filter((direction) => selectedDirectionIds.includes(direction.direction_id))
    .map((direction) => ({
      direction_id: direction.direction_id,
      label: direction.label,
      dimension: direction.dimension,
      source_domain: direction.source_domain,
      target_domain: direction.target_domain,
      relation: direction.relation,
      transfer_rationale: direction.transfer_rationale,
      constraints: direction.constraints,
      score: direction.score,
    }));
  return {
    prompt_token_mode: "human_selectable_chips",
    final_prompt: promptText.trim(),
    selected_prompt_text: tokens.map((token) => token.label).join(", "),
    selected_prompt_tokens: tokens.map((token) => ({
      token_id: token.token_id ?? promptTokenKey(token),
      label: token.label,
      dimension: token.dimension ?? "Cross-domain",
      role: token.role ?? "keyword",
      source_direction_id: token.source_direction_id ?? null,
      weight: token.weight ?? null,
    })),
    direction_ids: selectedDirectionIds,
    selected_directions: selectedDirections,
    source: "front_end_more_creative_prompt_chips",
  };
}

function inferObjectType(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.includes("speaker")) return "speaker";
  if (lower.includes("chair")) return "chair";
  if (lower.includes("lamp")) return "lamp";
  if (lower.includes("shoe")) return "shoe";
  return "object";
}

function isDiscoverableMeshFile(filename: string) {
  const lower = filename.toLowerCase();
  return lower.endsWith(".glb") || lower.endsWith(".obj");
}

function signalSummary(values: Record<string, unknown>) {
  const active = Object.entries(values)
    .filter(([, value]) => value !== null && value !== undefined && value !== false && value !== "")
    .slice(0, 2)
    .map(([key, value]) => {
      if (typeof value === "object") return key;
      return `${key}:${String(value)}`;
    });
  return active.length ? active.join(" / ") : "none";
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
