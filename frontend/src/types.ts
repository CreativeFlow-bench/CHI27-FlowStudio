/**
 * Shared FlowStudio types (refactor plan P1a).
 * Extracted from the former single-file frontend; import these instead of
 * re-declaring types in components.
 */

import type * as THREE from "three";

export type StageState = {
  phase: string;
  confidence: number;
  current_goal: string | null;
  active_asset_id: string | null;
  active_part_id: string | null;
  suggested_action: string | null;
  evidence?: string[];
};

export type SessionRecord = {
  session_id: string;
  title: string;
  stage: StageState;
  metadata: Record<string, unknown>;
  created_at?: string;
};

export type AssetRecord = {
  asset_id: string;
  session_id?: string;
  object_type: string;
  label: string;
  mesh_url: string | null;
  obj_url: string | null;
  thumbnail_url?: string | null;
  created_at?: string;
  parts: PartRecord[];
  metadata: Record<string, unknown>;
};

export type PartRecord = {
  part_id: string;
  label: string;
  type?: string;
  lifecycle?: "tentative_raycast" | "obj_group_fallback" | "viewport_2d_mask" | "segmented_3d" | string;
  bbox?: number[] | null;
  mask_url?: string | null;
  metadata?: Record<string, unknown>;
};

export type Hypothesis = {
  intent: string;
  confidence: number;
  evidence?: string[];
};

export type Interpretation = {
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
  semantic_targets?: SemanticTarget[];
  supervision_votes?: Record<string, unknown>;
  features?: {
    signals?: Record<string, Record<string, unknown>>;
    creative_state?: string;
    creative_state_confidence?: number;
    change_scope_hint?: string;
    recommended_axes?: string[];
    design_state_ir?: {
      ready?: boolean;
      change_scope_hint?: string;
      scope_hint?: string;
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

export type SemanticTarget = {
  target_id: string;
  level: "whole" | "silhouette" | "part" | "material_region";
  semantic: {
    label_zh?: string | null;
    label_en?: string | null;
    semantic_role?: string | null;
    wikidata_qid?: string | null;
    part_id?: string | null;
    mask_ref?: string | null;
  };
  operation_hint?: string | null;
  confidence?: number;
  evidence?: string[];
  supervision_sources?: Record<string, number>;
  kg_ready?: boolean;
  requires_clarification?: boolean;
};

export type EvidenceSummaryItem = {
  label: string;
  value: unknown;
  source: string;
  confidence?: number;
  score?: unknown;
};

export type PlannerDecisionResponse = {
  interpretation_id: string;
  session_id: string;
  decision: "accepted" | "rejected";
  event_id: string;
  memory_id: string;
  updated_stage: StageState;
};

export type DesignStateIRMatch = {
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
  change_scope_hint?: string;
  evidence_summary?: unknown;
  recommended_axes?: string[];
  evidence_strength?: string;
  text?: string;
};

export type AssistanceSuggestion = {
  type: "generate" | "ask" | "notify" | "highlight";
  mode?: "replace" | "drag_regenerate" | "diverge" | "refine" | null;
  label?: string | null;
  question?: string | null;
  metadata?: Record<string, unknown>;
};

export type PlannerClarificationBubble = {
  id: string;
  label: string;
  detail: string;
  kind: "target" | "axis" | "action";
  position: "left" | "right" | "top";
};

export type CreativeState =
  | "idle"
  | "exploring"
  | "focused_editing"
  | "refining"
  | "comparing"
  | "possible_fixation"
  | "ready_for_help";

export type BubbleScope = "contour" | "part" | "material";

export type IntentBubbleUiState = {
  visible: boolean;
  scope: BubbleScope | null;
  status: "pending" | "accepted" | "rejected" | "ignored" | null;
  shownAt: number | null;
};

export type JobRecord = {
  job_id: string;
  mode?: string;
  status: string;
  stage: string;
  progress: number;
  message: string | null;
  candidate_ids: string[];
  error?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
};

export type Candidate = {
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

export type CandidateDecisionResponse = {
  candidate_id: string;
  decision: string;
  active_asset_id: string | null;
  updated_stage: StageState;
};

export type CaseRecord = {
  case_id: string;
  session_id: string;
  title: string;
  asset_id: string;
  accepted_candidate_ids: string[];
  notes: string | null;
  report_url: string | null;
  metadata: Record<string, unknown>;
};

export type ArtifactRecord = {
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

export type CaseIndexItem = {
  case_id: string;
  session_id: string;
  title: string;
  asset_id: string;
  report_url: string | null;
  case_url: string | null;
  accepted_candidate_ids: string[];
  created_at: string;
};

export type CaseIndexResponse = {
  schema_version: string;
  cases: CaseIndexItem[];
};

export type CaseManifest = {
  schema_version: string;
  case: CaseRecord;
  stage: StageState;
  asset: AssetRecord;
  accepted_candidates: Candidate[];
};

export type SessionSnapshotResponse = {
  session: SessionRecord;
  active_asset: AssetRecord | null;
  active_parts: PartRecord[];
  active_job: JobRecord | null;
  live_signals?: Partial<LiveSignals>;
  visible_candidates: Candidate[];
  recent_interpretations: Interpretation[];
};

export type SolutionSpaceResponse = {
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

export type BenchmarkAsset = {
  benchmark_id: string;
  label: string;
  object_type: string;
  mesh_url: string | null;
  obj_url: string | null;
  thumbnail_url?: string | null;
  model_available?: boolean;
  file_size_bytes: number;
  vertex_count: number | null;
  face_count: number | null;
  metadata: Record<string, unknown>;
};

export type BenchmarkAssetListResponse = {
  assets: BenchmarkAsset[];
};

export type LogItem = {
  id: string;
  label: string;
  detail: string;
  at?: number;
};

export type PerceptionLogEntry = {
  id: string;
  time: string;
  tag: "SYS" | "INIT" | "PERCEPTION" | "ACTION";
  text: string;
};

export type RemoteWorkerHealth = {
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

export type RemoteWorkerPreflight = {
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

export type BackendHealth = {
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

export type SystemServiceInfo = {
  id: string;
  name?: string;
  name_zh?: string;
  port?: number;
  group?: "core" | "gpu" | "network" | "optional";
  required?: boolean;
  description?: string;
  state: "up" | "down" | "starting" | "unknown";
  detail?: string;
  latency_ms?: number;
  startable?: boolean;
  starting?: string | null;
  last_start?: {
    pid?: number;
    started_at?: string;
    log?: string;
    error?: string | null;
  } | null;
};

export type SystemServicesResponse = {
  ok: boolean;
  enabled: boolean;
  bootstrap?: {
    running?: string[];
    recent?: Record<string, { done?: boolean; cancelled?: boolean }>;
  };
  services: SystemServiceInfo[];
};

export type ModelApiProbeCheck = {
  ok: boolean;
  model?: string;
  latency_ms?: number | null;
  error?: string | null;
  bytes?: number;
  skipped?: boolean;
};

export type ModelApiProbeResult = {
  ok: boolean;
  configured: boolean;
  api_base?: string | null;
  legacy_local_models?: boolean;
  text: ModelApiProbeCheck;
  image: ModelApiProbeCheck;
  hint?: string | null;
};

export type GeometryWorkerResponse = {
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

export type CanvasPrimitive =
  | "plane"
  | "cube"
  | "circle"
  | "sphere"
  | "ico_sphere"
  | "cylinder"
  | "cone"
  | "torus"
  | null;

export type CanvasTool = "select" | "clay" | "move";

export type CanvasDisplayMode = "textured" | "parts" | "heatmap" | "clay";

export type ChatMessage = {
  id: string;
  role: "user" | "planner";
  text: string;
  candidateIds?: string[];
};

export type PartDiscoveryResponse = {
  job_id: string | null;
  status: string;
  parts: PartRecord[];
  metadata: Record<string, unknown>;
};

export type ActionAtom = {
  atom_id: string;
  tool: "hover" | "brush" | "annotation" | "drag" | "smooth" | "add" | "text" | "image" | "model";
  target: Record<string, unknown>;
  evidence: Record<string, unknown>;
  order: number;
  created_at?: string;
};

export type FourStageStage =
  | "raw_events"
  | "encoding"
  | "retrieval"
  | "re_representation"
  | "awaiting_gate"
  | "generation"
  | "completed"
  | "failed"
  | "cancelled";

export type FourStageGateAction = "accept_option" | "reject_all" | "request_revision" | "clarify";

export type FourStageDecisionOption = {
  option_id: string;
  label: string;
  rationale: string | null;
  confidence: number;
  evidence_refs: string[];
  constraints: string[];
  divergence_seeds: string[];
};

export type FourStageDecision = {
  decision_id: string;
  run_id: string;
  intent_ir_id: string;
  retrieval_id: string | null;
  summary: string | null;
  semantic_target?: string | null;
  gate_question?: string | null;
  recommended_scope: string | null;
  options: FourStageDecisionOption[];
  needs_clarification: boolean;
  clarification_question: string | null;
  confidence: number;
  model: string;
  prompt_version: string;
  created_at: string;
};

export type SemanticCandidateGroup = "shape" | "connection" | "surface" | "semantic_transfer";

export type SemanticKnowledgeRoute = {
  mode: "model_only" | "knowledge_augmented";
  use_wikidata: boolean;
  use_getty_aat: boolean;
  use_asknature: boolean;
  reasons: string[];
  source_statuses: Record<string, string>;
};

export type SemanticCandidate = {
  candidate_id: string;
  display_label_zh: string;
  label_en: string;
  group: SemanticCandidateGroup;
  target_ref: { asset_id: string; type: string; id: string | null };
  operation: string;
  semantic_anchor: string;
  prompt_phrase: string;
  attribute_delta: { attribute: string; change: string };
  scores: Record<"identity" | "scope" | "relevance" | "specificity" | "novelty", number>;
  provenance: {
    generator: string;
    mode: string;
    wikidata: Array<Record<string, unknown>>;
    getty_aat: Array<Record<string, unknown>>;
    asknature: Array<Record<string, unknown>>;
  };
};

export type SemanticDivergenceResponse = {
  schema_version: string;
  divergence_id: string;
  run_id: string;
  decision_id: string;
  request_key: string;
  status: "completed" | "failed" | "running";
  generator_model: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  knowledge_route: SemanticKnowledgeRoute;
  validation_counts: Record<string, number>;
  latency_ms: number;
  prompt_version: string;
  candidates: SemanticCandidate[];
};

export type FourStageRun = {
  schema_version: string;
  run_id: string;
  session_id: string;
  idempotency_key: string | null;
  episode_id: string | null;
  stage: FourStageStage;
  run_hy3d: boolean;
  events: Array<{ type: string; event_id: string; timestamp: string; payload: Record<string, unknown> }>;
  source_event_ids: string[];
  intent_ir: Record<string, unknown> | null;
  retrieval: Record<string, unknown> | null;
  decision: FourStageDecision | null;
  semantic_divergence?: SemanticDivergenceResponse | null;
  source_context?: {
    asset_id: string;
    object_type: string;
    version_id?: string | null;
    source_image_ref?: string | null;
    source_model_ref?: string | null;
    target_part_id?: string | null;
    target_mask_ref?: string | null;
    camera_ref?: string | null;
  } | null;
  scope_gate?: {
    gate_id: string;
    target: string;
    scope: string;
    question: string;
    status: "pending" | "accepted" | "rejected" | "ignored";
    user_action?: string | null;
  } | null;
  divergence_selection?: {
    scope: string;
    target_part_id?: string | null;
    selected_candidate_ids?: string[];
    selected_keywords: string[];
    resolved_prompt_phrases?: string[];
    user_text?: string | null;
    dimensions?: Record<string, string[]>;
    system_keywords?: string[];
  } | null;
  gate_decision: {
    decision_id: string;
    run_id: string;
    action: FourStageGateAction;
    selected_option_id: string | null;
    user_revision: string | null;
    reason: string | null;
    created_at: string;
  } | null;
  generation_spec: Record<string, unknown> | null;
  generation_artifacts: Array<Record<string, unknown>>;
  error: { code: string; message: string; retryable: boolean } | null;
  failed_stage: FourStageStage | null;
  retry_count: number;
  stage_timestamps: Record<string, Record<string, string>>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type FourStageGateRequest = {
  run_id: string | null;
  action: FourStageGateAction;
  selected_option_id?: string | null;
  user_revision?: string | null;
  reason?: string | null;
  auto_generate?: boolean;
};

export type FourStageUiState = {
  runId: string | null;
  stage: FourStageStage | null;
  decision: FourStageDecision | null;
  gateOpen: boolean;
  gateBusy: boolean;
  gateTimeoutAt: number | null;
  gateQuestion: string | null;
  scopeAccepted: boolean;
  divergenceSelection: FourStageRun["divergence_selection"];
  generationArtifacts: Array<{ url: string; kind: "png" | "glb" | "obj" }>;
  generationCompleted: number;
  generationTotal: number;
  error: { code: string; message: string; retryable: boolean } | null;
  creatingRun: boolean;
};

export type FourStageWsEvent = {
  type: string;
  event_id: string;
  session_id: string;
  timestamp: string;
  payload: Record<string, unknown> & {
    run_id?: string;
    stage?: string;
    decision_id?: string;
    artifact_count?: number;
    event_count?: number;
    generation_id?: string;
    candidate_count?: number;
    error_code?: string;
    action?: string;
    selected_option_id?: string | null;
  };
};

export type BehaviorViewSet = {
  front?: string | null;
  side?: string | null;
  top?: string | null;
};

export type BehaviorSession = {
  behavior_id: string;
  session_id: string;
  behavior_seq: number;
  tool: string;
  target: Record<string, unknown>;
  status: "active" | "committed";
  started_at: string;
  ended_at: string | null;
  stroke_count: number;
  operation_summary: Record<string, unknown>;
  start_views: BehaviorViewSet;
  end_views: BehaviorViewSet;
  evidence_refs: string[];
};

export type LiveObservationState = {
  session_id: string;
  latest_behavior_seq: number;
  encoded_through_seq: number;
  operation: string;
  scope: string;
  target: Record<string, unknown>;
  confidence: number;
  intent_confidence: number;
  behavior_count: number;
  retrieval_query: string[];
  retrieval_fingerprint?: string | null;
  intent_summary?: string | null;
  updated_at: string;
};

export type IntentRevisionStatus =
  | "planning"
  | "awaiting_gate"
  | "accepted"
  | "rejected"
  | "generating"
  | "completed"
  | "failed"
  | "cancelled";

export type IntentRevision = {
  revision_id: string;
  session_id: string;
  intent_seq: number;
  parent_revision_id: string | null;
  window_start_seq: number;
  cutoff_seq: number;
  behavior_ids: string[];
  user_text: string;
  source_context: NonNullable<FourStageRun["source_context"]>;
  status: IntentRevisionStatus;
  version: number;
  selection_version: number;
  run_id: string | null;
  gate_id: string | null;
  gate_question: string | null;
  gate_target: string | null;
  gate_scope: string | null;
  /** True while question is a fast draft before encoding finishes. */
  gate_provisional?: boolean;
  base_keywords: string[];
  delta_keywords: string[];
  effective_keywords: string[];
  divergence_selection: FourStageRun["divergence_selection"];
  semantic_divergence_status: "running" | "completed" | "failed" | null;
  semantic_divergence_error: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  /** Frontend-only marker: which event created this revision.
   *  - manual: user clicked Send intent
   *  - idle:   auto-created after 30s stillness following the last interaction */
  trigger?: "manual" | "idle" | null;
  /** LLM-generated natural-language description of current design phenomenon. */
  phenomenon?: string | null;
};

export type DivergenceSelection = {
  scope: string;
  target_part_id?: string | null;
  selected_candidate_ids: string[];
  selected_keywords: string[];
  resolved_prompt_phrases?: string[];
  user_text?: string | null;
  dimensions?: Record<string, string[]>;
  system_keywords?: string[];
  command_id?: string;
  idempotency_key?: string;
  expected_version?: number;
  expected_selection_version?: number;
};

export type SolutionBatch = {
  batch_id: string;
  session_id: string;
  revision_id: string;
  intent_seq: number;
  run_id: string;
  append_index: number;
  parent_batch_id: string | null;
  keyword_mode: string;
  base_keywords: string[];
  delta_keywords: string[];
  cumulative_keywords: string[];
  source_context: IntentRevision["source_context"] | null;
  gate_id: string | null;
  status: string;
  artifacts: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
};

export type VersionNodeStatus =
  | "image_ready"
  | "generating_3d"
  | "mesh_ready"
  | "mesh_failed";

export type VersionGraphNode = {
  node_id: string;
  session_id: string;
  version_number: number;
  parent_node_id: string | null;
  candidate_id: string | null;
  label: string;
  preview_url: string | null;
  mesh_url: string | null;
  obj_url: string | null;
  status: VersionNodeStatus;
  hy3d_job_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type VersionGraphState = {
  active_node_id: string | null;
  nodes: VersionGraphNode[];
};

export type UiBrief = {
  phenomenon: string;
  next_question: string;
  requires_response: boolean;
  question_id: string | null;
  status: string;
  confidence: number;
  details_ref: string | null;
  pending_decision_count: number;
};

export type ExperimentProjectFile = {
  project_id: string;
  title: string;
  participant_code: string | null;
  condition_label: string | null;
  notes: string | null;
  tags: string[];
  status: "active" | "completed" | "archived";
  active_run_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ExperimentRun = {
  run_id: string;
  project_id: string;
  session_id: string;
  run_number: number;
  baseline_mode: "blank" | "current_state";
  started_at: string;
  ended_at: string | null;
  next_event_seq: number;
  recording_status: "healthy" | "degraded" | "paused" | "ended";
};

export type ExperimentProjectDetail = {
  project: ExperimentProjectFile;
  active_run: ExperimentRun | null;
  asset_refs: Array<Record<string, unknown>>;
};

export type ExperimentEvent = {
  event_id: string;
  project_id: string;
  run_id: string;
  session_id: string;
  seq: number;
  event_type: string;
  actor: "user" | "model" | "system" | "worker";
  occurred_at: string | null;
  recorded_at: string;
  correlation_id: string | null;
  parent_event_id: string | null;
  idempotency_key: string;
  payload: Record<string, unknown>;
};

export type ExperimentExportRecord = {
  export_id: string;
  project_id: string;
  status: "queued" | "completed" | "failed";
  file_url: string | null;
  file_path: string | null;
  missing_asset_refs: string[];
  error: string | null;
};

export type RealtimeObservationSnapshot = {
  observation: LiveObservationState;
  behaviors: BehaviorSession[];
  revisions: IntentRevision[];
  solution_batches: SolutionBatch[];
  version_graph: VersionGraphState;
  ui_brief: UiBrief;
};

export type IntentDraft = {
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

export type IntentDraftListResponse = {
  drafts: IntentDraft[];
};

export type IntentEpisodeResponse = {
  episode_id: string;
  session_id: string;
  asset_id: string | null;
  intent_draft_id: string | null;
  behavior_atoms: ActionAtom[];
  text: string | null;
  status: "submitted";
  metadata: Record<string, unknown>;
};

export type AnalogyDirection = {
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

export type PromptToken = {
  token_id?: string;
  candidate_id?: string;
  label: string;
  dimension?: "Aesthetic" | "Functional" | "Structural" | "Cross-domain";
  role?: string;
  source_direction_id?: string;
  weight?: number;
  full_phrase_zh?: string;
  group_key?: string;
  full_prompt_phrase?: string;
  target_ref?: Record<string, unknown>;
  operation?: string;
  attribute_delta?: Record<string, string>;
  provenance_path?: Record<string, unknown>;
};

export type ContextualFragment = {
  fragment_id: string;
  display_label_zh: string;
  full_phrase_zh: string;
  label_en?: string;
  group: { key: string; label_zh: string; legacy_dimension?: string };
  legacy_dimension?: string;
  scope: string;
  target_ref: { asset_id?: string; type?: string; id?: string | null; label_zh?: string };
  operation: string;
  attribute_delta: Record<string, string>;
  provenance_path?: Record<string, unknown>;
  hard_gates?: { passed: boolean };
  constraints?: string[];
  source_direction_id?: string | null;
};

export type LiveSignals = {
  dwell_ms: number;
  compare_dwell_ms: number;
  new_case_attempt_rate: number;
  mask_coverage: number;
  view_mode: ViewMode;
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

export type LivePerception = {
  summary: string;
  evidence: string[];
  confidence: number | null;
  source: "local" | "server";
  updatedAt: string;
};

export type PerceptionLatestResponse = {
  perception?: {
    perception_id?: string;
    summary?: string;
    behavior_label?: string;
    confidence?: number;
    evidence?: Array<string | { type?: string; value?: string }>;
  } | null;
};

export type ViewportInteractionSignal = {
  type: "orbit" | "zoom" | "pan";
  dwell_ms?: number;
  camera_distance?: number;
  view_mode?: ViewMode;
  /** True for the one-shot framing signal emitted after a model loads; it should not count as a user interaction. */
  initial?: boolean;
};

/**
 * Framing state of the viewport, mirroring the reference Flow Studio
 * observation logic: `survey` = whole form / silhouette framing,
 * `detail` = single region fills the viewport, `compare` = in between,
 * `empty` = no renderable object yet.
 */
export type ViewMode = "empty" | "survey" | "detail" | "compare";

export type AnnotationPoint = {
  x: number;
  y: number;
  t: number;
  p?: number;
};

export type AnnotationStroke = AnnotationPoint[];

export type EditorSnapshot = {
  intentText: string;
  actionAtoms: ActionAtom[];
  imageRefs: ArtifactRecord[];
  modelRefs: ArtifactRecord[];
  selectedPromptTokens: PromptToken[];
  previewCandidate: Candidate | null;
  canvasPreview: { url: string; label: string } | null;
};

export type CrossDomainDivergenceResponse = {
  session_id: string;
  asset_id: string;
  intent_draft_id: string | null;
  source_summary: string;
  directions: AnalogyDirection[];
  evidence: string[];
  metadata: Record<string, unknown>;
};

export type DirectionsSuggestResponse = {
  session_id?: string;
  asset_id?: string;
  intent_draft_id?: string | null;
  directions: AnalogyDirection[];
  evidence?: string[];
  metadata?: Record<string, unknown>;
};

export type PromptComposeResponse = {
  session_id: string;
  asset_id: string | null;
  final_prompt: string;
  analogy_prompt_package: Record<string, unknown>;
  event_id: string;
  memory_id: string;
};

export type SculptTool = "brush" | "drag" | "smooth";

export type ModelScreenBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ThreeViewportHandle = {
  applySculptSnapshot: (positions: Float32Array | null) => void;
  capturePositions: () => Float32Array | null;
  captureJpeg: (width?: number, quality?: number) => string | null;
  captureThreeViews: (width?: number, quality?: number) => BehaviorViewSet;
  getLastPointer: () => { x: number; y: number } | null;
  exportMeshOBJ: () => string | null;
  /** Axis-aligned model bounds in CSS pixels relative to the viewport mount. */
  getModelScreenBounds: () => ModelScreenBounds | null;
  getPrimitiveTransform?: () => { position: number[]; rotation: number[]; scale: number[] } | null;
};

export type ThreeViewportProps = {
  asset: AssetRecord | null;
  previewMeshUrl: string | null;
  previewLabel: string | null;
  onClearPreview: () => void;
  selectedPart: string;
  hoverLabel: string | null;
  primitive: CanvasPrimitive;
  tool: CanvasTool;
  displayMode: CanvasDisplayMode;
  parts: PartRecord[];
  onSelectPart: (part: string) => void;
  onHoverPart: (part: string) => void;
  onViewportInteraction: (signal: ViewportInteractionSignal) => void;
  sculptTool: SculptTool | null;
  onSculptAction: (tool: SculptTool, evidence: Record<string, unknown>) => void;
  sculptRadius: number;
  sculptStrength: number;
  /** 2D version-canvas zoom applied around the viewport; the 3D framing
   * classifier folds it in so canvas zoom does not distort observation. */
  canvasZoom?: number;
  hoverMaskDataUrl?: string | null;
  onGeometryReady?: (geometry: THREE.BufferGeometry | null) => void;
};
