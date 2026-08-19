/**
 * Pure App-side helpers: perception / narration / directions / candidates /
 * benchmark / draft payloads (refactor plan P1a).
 */
import type {
  ActionAtom,
  AnalogyDirection,
  AnnotationPoint,
  AnnotationStroke,
  AssetRecord,
  AssistanceSuggestion,
  ArtifactRecord,
  BenchmarkAsset,
  BubbleScope,
  CanvasDisplayMode,
  CaseManifest,
  Candidate,
  CanvasPrimitive,
  CaseIndexItem,
  ContextualFragment,
  CreativeState,
  DesignStateIRMatch,
  EvidenceSummaryItem,
  GeometryWorkerResponse,
  Interpretation,
  IntentBubbleUiState,
  IntentDraft,
  LivePerception,
  LiveSignals,
  PartDiscoveryResponse,
  PartRecord,
  PerceptionLogEntry,
  PromptToken,
  RemoteWorkerHealth,
  RemoteWorkerPreflight,
  SessionRecord,
  StageState,
} from "../types";
import { absoluteUrl, inferMeshExtension } from "../api";
import { clamp01, confidenceTone, formatScore, stringValue } from "./format";
import { inferChangeScopeFromText, inferredChangeScope } from "./scope";

export function isSilentObservationInterpretation(value: unknown) {
  const features = (value as { features?: { event_type?: unknown } } | null)?.features;
  return features?.event_type === "camera_observation_ended";
}

export function livePerceptionSummary(
  signals: LiveSignals,
  hasModel: boolean,
  primitive: CanvasPrimitive,
  partLabel: string | null,
  interpretation: Interpretation | null,
): string {
  if (!hasModel && !primitive) return "Waiting for your first move.";
  const ir = interpretation?.features?.design_state_ir as
    | { scope_hint?: string; change_scope_hint?: string }
    | undefined;
  const scopeHint = ir?.change_scope_hint ?? ir?.scope_hint ?? null;
  const scopeText =
    scopeHint === "part" || scopeHint === "part_or_region"
      ? "part"
      : scopeHint === "material" || scopeHint === "material_region"
        ? "material region"
        : scopeHint === "silhouette" || scopeHint === "contour"
          ? "overall silhouette"
          : scopeHint === "whole_object" || scopeHint === "whole"
            ? "whole object"
            : null;
  // Framing state mirrors the reference observation model: `detail` means
  // the user has zoomed into a single region; `survey`/`compare`/`empty`
  // means the whole silhouette is in view. Part-level labels only apply
  // while scrutinising detail; otherwise the observation is of the contour.
  const viewMode = signals.view_mode ?? "empty";
  const scrutinizingDetail = viewMode === "detail";
  const sustainedOnPart = Boolean(partLabel && signals.dwell_ms >= 4000);
  if (partLabel) {
    if (signals.brush_count > 0) return `Brushing part “${partLabel}”.`;
    if (sustainedOnPart) {
      return `Dwelling on part “${partLabel}” as the current focus (${Math.round(signals.dwell_ms / 1000)}s).`;
    }
    if (scrutinizingDetail && signals.hover_count > 0) {
      return `Inspecting part “${partLabel}” in close detail.`;
    }
    if (scrutinizingDetail) {
      return `Focusing on part “${partLabel}”${scopeText ? ` (${scopeText})` : ""}.`;
    }
    if (signals.hover_count > 0) {
      return `Observing the overall silhouette around “${partLabel}”.`;
    }
    return `Orbiting to read the overall structure of “${partLabel}”.`;
  }
  if (scopeText) {
    if (signals.brush_count > 0) return `Brushing a local ${scopeText} region.`;
    if (signals.hover_count > 0) {
      return scrutinizingDetail
        ? `Inspecting ${scopeText} details.`
        : `Observing the ${scopeText}.`;
    }
    if (signals.annotation_count > 0) return `Drawing along the ${scopeText}.`;
    if (signals.viewport_orbit_count > 0) return `Orbiting to survey the ${scopeText}.`;
  }
  if (signals.annotation_count > 0 && signals.drawing_content) {
    return `User is drawing on the silhouette (${signals.drawing_content}).`;
  }
  if (signals.annotation_count > 0) return "User is drawing on the silhouette.";
  if (signals.brush_count > 0) return "User is drawing on the part.";
  if (signals.hover_count > 0) {
    return scrutinizingDetail
      ? "User is inspecting silhouette details."
      : "User is surveying the silhouette of the object.";
  }
  if (signals.local_zoom_count > 0 || signals.viewport_zoom_count > 0) {
    return scrutinizingDetail
      ? "User is zooming in to scrutinise a single region."
      : "User is zoomed out — surveying the whole silhouette.";
  }
  if (signals.viewport_orbit_count > 0) {
    return scrutinizingDetail
      ? "User is orbiting to inspect the form's parts."
      : "User is orbiting to survey the whole structure.";
  }
  if (primitive) return `User added a ${primitive.replaceAll("_", " ")} volume.`;
  return "Overviewing the whole structure.";
}

export function livePerceptionEvidence(
  signals: LiveSignals,
  partLabel: string | null,
  interpretation: Interpretation | null,
): string[] {
  const items = [
    partLabel ? `part=${partLabel}` : null,
    interpretation?.features?.design_state_ir?.change_scope_hint
      ? `scope=${interpretation.features.design_state_ir.change_scope_hint}`
      : interpretation?.features?.design_state_ir?.scope_hint
        ? `scope=${interpretation.features.design_state_ir.scope_hint}`
        : null,
    signals.viewport_orbit_count ? `orbit×${signals.viewport_orbit_count}` : null,
    signals.viewport_zoom_count ? `zoom×${signals.viewport_zoom_count}` : null,
    signals.view_mode && signals.view_mode !== "empty" ? `view=${signals.view_mode}` : null,
    signals.dwell_ms ? `dwell ${Math.round(signals.dwell_ms)}ms` : null,
    signals.hover_count ? `hover×${signals.hover_count}` : null,
    signals.brush_count ? `brush×${signals.brush_count}` : null,
    signals.annotation_count ? `annotation×${signals.annotation_count}` : null,
    signals.mask_coverage > 0 ? `mask ${Math.round(signals.mask_coverage * 100)}%` : null,
    signals.drawing_content || null,
  ].filter(Boolean) as string[];
  return items.length ? [items.join(" · ")] : ["No behavioral evidence yet."];
}

export const CREATIVE_STATES = new Set<string>([
  "idle",
  "exploring",
  "focused_editing",
  "refining",
  "comparing",
  "possible_fixation",
  "ready_for_help",
]);

export function observeCreativeState(input: {
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

export function interactionHistoryItems(
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

export function formatClock(value?: string | number | null) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  }
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function buildPerceptionLogEntries(input: {
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

export function behaviorContextDescription(
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

export function buildPlannerNarration(input: {
  perceptionSummary: string;
  creativeState: CreativeState;
  hasModel: boolean;
  partLabel: string | null;
  intentText: string;
  bubbleScope: BubbleScope | null;
  bubbleStatus: IntentBubbleUiState["status"];
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
  return `${observe}. When the prompt chips look right, hit Generate and we'll open Solution Space.`;
}

export function perceptionHeadline(interpretation: Interpretation) {
  const topMatch = designStateMatches(interpretation)[0];
  const route = topMatch?.route ? irRouteLabel(topMatch.route) : interpretation.primary_intent.replaceAll("_", " ");
  return `${confidenceTone(interpretation.confidence)}${route}`;
}

export function perceptionEvidenceLine(interpretation: Interpretation) {
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

export function predictorStatusLabel(interpretation: Interpretation) {
  const metadata = interpretation.predictor_metadata ?? {};
  if (interpretation.predictor === "vlm_multisignal") {
    return metadata.fallback_used ? "qwen fallback" : "qwen active";
  }
  if (metadata.fallback_used) return "rule fallback";
  return "rule";
}

export function designStateMatches(interpretation: Interpretation | null) {
  return interpretation?.features?.design_state_ir?.matches ?? [];
}

export function evidenceSummaryItems(interpretation: Interpretation | null): EvidenceSummaryItem[] {
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

export function evidenceValueLabel(value: unknown) {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  if (typeof value === "string") return value.replaceAll("_", " ");
  if (value === null || value === undefined) return "none";
  return JSON.stringify(value);
}

export function formatIRScore(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) return "IR";
  return `IR ${value.toFixed(2)}`;
}

export function irRouteLabel(value: unknown) {
  if (typeof value !== "string" || !value) return "route unknown";
  return value.replaceAll("_", " ");
}

export function irStateLabel(value: unknown) {
  if (typeof value !== "string" || !value) return "state unknown";
  return value.replaceAll("_", " ");
}

export function plannerReply(interpretation: Interpretation) {
  const source = predictorStatusLabel(interpretation);
  const suggestion = interpretation.suggested_assistance?.[0];
  const action = suggestion ? suggestionActionLabel(suggestion) : interpretation.assistance_policy;
  const evidence = interpretation.evidence?.[0] ? ` Evidence: ${interpretation.evidence[0]}` : "";
  return `${interpretation.primary_intent} (${formatScore(interpretation.confidence)}, ${source}). Next: ${action}.${evidence}`;
}

export function plannerGateStatus(metadata: Record<string, unknown> | null) {
  const gate = metadata?.planner_control_gate;
  if (!gate || typeof gate !== "object") return "unconfirmed";
  const status = (gate as Record<string, unknown>).status;
  return status === "confirmed" || status === "rejected" ? status : "unconfirmed";
}

export function plannerGateStatusLabel(metadata: Record<string, unknown> | null) {
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

export function dimensionGroupsForMoreCreative(
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

export function contextualFragmentGroups(fragments: ContextualFragment[]) {
  const groups = new Map<string, { key: string; label_zh: string; fragments: ContextualFragment[] }>();
  for (const fragment of fragments) {
    const key = fragment.group?.key ?? "form";
    const labelZh = fragment.group?.label_zh ?? "形态";
    const entry = groups.get(key) ?? { key, label_zh: labelZh, fragments: [] };
    entry.fragments.push(fragment);
    groups.set(key, entry);
  }
  return Array.from(groups.values());
}

export function cleanAnalogyDirections(directions: AnalogyDirection[]): AnalogyDirection[] {
  return directions.map((direction) => ({
    ...direction,
    transfer_rationale: stripFallbackDirectionText(direction.transfer_rationale),
    metadata: direction.metadata,
  }));
}

export function stripFallbackDirectionText(value: unknown) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) return "";
  if (/analogy words|suggestions for|without generating|use, affordance|silhouette, proportion|style mood/i.test(text)) {
    return "";
  }
  return text;
}

export function suggestionActionLabel(suggestion: AssistanceSuggestion) {
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

export function rankCandidates(items: Candidate[]) {
  return [...items].sort((a, b) => {
    const socketDelta = socketCompatibilityScore(b) - socketCompatibilityScore(a);
    if (Math.abs(socketDelta) > 0.0001) return socketDelta;
    const alignDelta = (b.scores.intent_alignment ?? 0) - (a.scores.intent_alignment ?? 0);
    if (Math.abs(alignDelta) > 0.0001) return alignDelta;
    return 0;
  });
}

export function socketCompatibilityScore(candidate: Candidate) {
  const direct = candidate.scores.socket_compatibility;
  if (typeof direct === "number" && !Number.isNaN(direct)) return direct;
  const evidence = pipelineEvidence(candidate);
  const evidenceScore = evidence.socket_compatibility_score;
  if (typeof evidenceScore === "number" && !Number.isNaN(evidenceScore)) return evidenceScore;
  return 0;
}

export function artifactStatus(value: unknown) {
  if (typeof value !== "string" || !value) return "pending";
  return value.split("/").at(-1) || "ready";
}

export function pipelineEvidence(candidate: Candidate) {
  const value = candidate.metadata.pipeline_evidence;
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function pipelineEvidenceValue(candidate: Candidate, key: string) {
  return pipelineEvidence(candidate)[key];
}

export function candidatePreviewUrl(candidate: Candidate) {
  const remoteUrl = candidate.metadata.remote_image_url;
  if (typeof remoteUrl === "string" && remoteUrl) return absoluteUrl(remoteUrl);
  return candidate.thumbnail_url ? absoluteUrl(candidate.thumbnail_url) : null;
}

export function candidateStage(candidate: Candidate) {
  return stringValue(candidate.metadata.stage);
}

export function candidateFidelity(candidate: Candidate) {
  return stringValue(candidate.metadata.fidelity);
}

export function candidateCommitPolicy(candidate: Candidate) {
  return candidate.mesh_url || candidate.obj_url ? "active_asset" : "direction_memory";
}

export function candidateArtifactLevel(candidate: Candidate) {
  if (candidate.mesh_url || candidate.obj_url) return "3D mesh ready";
  if (canGenerateCandidateHy3d(candidate)) return "Image direction";
  if (candidate.thumbnail_url || candidate.metadata.remote_image_url) return "Image only";
  return "Contract";
}

export function candidateProvenance(candidate: Candidate) {
  const value = pipelineEvidenceValue(candidate, "provenance") ?? candidate.metadata.adapter;
  if (typeof value !== "string" || !value) return "unknown";
  return value.replace("remote-staged-creativeflow", "remote_staged");
}

export function canGenerateCandidateHy3d(candidate: Candidate) {
  return Boolean(candidate.metadata.remote_result_path && candidate.metadata.direction_id);
}

export function remoteJobLabel(candidate: Candidate) {
  const value = pipelineEvidenceValue(candidate, "remote_job_id") ?? candidate.metadata.remote_job_id;
  if (typeof value !== "string" || !value) return "none";
  return value.replace("rw_creativeflow_", "rw_cf_").slice(0, 28);
}

export function directionLabel(candidate: Candidate) {
  const value = pipelineEvidenceValue(candidate, "direction_id") ?? candidate.metadata.direction_id;
  return typeof value === "string" && value ? value.replace("dir_", "") : "none";
}

export function fitEvidenceLabel(candidate: Candidate) {
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

export function socketEvidenceLabel(candidate: Candidate) {
  const evidence = pipelineEvidence(candidate);
  const sourcePart = evidence.source_part_id;
  const faceCount = evidence.socket_face_count;
  if (typeof sourcePart === "string" && sourcePart) {
    return `${sourcePart}${faceCount ? ` / ${faceCount}` : ""}`;
  }
  return faceCount ? `${faceCount} faces` : "none";
}

export function seamEvidenceLabel(candidate: Candidate) {
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

export function socketScoreLabel(value: unknown) {
  if (typeof value !== "number" || Number.isNaN(value)) return "";
  return ` ${value.toFixed(2)}`;
}

export function partDiscoveryAdapter(response: PartDiscoveryResponse) {
  const adapter = response.metadata?.adapter;
  if (adapter === "obj_group_fallback") return "OBJ groups (fallback)";
  return typeof adapter === "string" ? adapter : "unknown";
}

export function partDiscoveryDisplayAdapter(response: PartDiscoveryResponse) {
  const remoteStatus = partDiscoveryRemoteValue(response, "status");
  if (remoteStatus === "completed" && partSegmentationUrl(response.parts)) return "partfield-real";
  return partDiscoveryAdapter(response);
}

export function partDiscoveryRemoteValue(response: PartDiscoveryResponse, key: string) {
  const remote = response.metadata?.remote_result;
  if (!remote || typeof remote !== "object") return "none";
  const value = (remote as Record<string, unknown>)[key];
  if (value === null || value === undefined || value === "") return "none";
  if (typeof value === "object") return key === "error" ? JSON.stringify(value).slice(0, 120) : "available";
  return String(value);
}

export function partSegmentationUrl(parts: PartRecord[]) {
  for (const part of parts) {
    const value = part.metadata?.segmented_mesh_url;
    if (typeof value === "string" && value) return value;
  }
  return null;
}

export function isRenderableBenchmarkAsset(asset: BenchmarkAsset) {
  const hasMeshUrl = Boolean(asset.mesh_url && inferMeshExtension(asset.mesh_url));
  const hasObjUrl = Boolean(asset.obj_url && inferMeshExtension(asset.obj_url));
  return asset.model_available !== false && (hasMeshUrl || hasObjUrl);
}

export function findPartByViewportName(parts: PartRecord[], name: string) {
  const normalized = name.trim();
  if (!normalized) return null;
  return (
    parts.find((part) => part.part_id === normalized) ??
    parts.find((part) => part.label === normalized) ??
    parts.find((part) => String(part.metadata?.source_part_id ?? "") === normalized) ??
    null
  );
}

export function benchmarkAssetGroupLabel(asset: BenchmarkAsset) {
  if (asset.metadata?.source === "local_white_model") {
    const category = String(asset.metadata.category ?? "white_models").replaceAll("_", " ");
    return `White Models · ${category.replace(/\b\w/g, (match) => match.toUpperCase())}`;
  }
  return "CreativeFlow / Design DB";
}

export function benchmarkPreviewUrl(asset: BenchmarkAsset): string | null {
  const image = asset.metadata?.image;
  if (typeof image !== "string" || !image.trim()) return null;
  return absoluteUrl(image.trim());
}

export function compareBenchmarkAssets(a: BenchmarkAsset, b: BenchmarkAsset) {
  const priority = (asset: BenchmarkAsset) => (asset.metadata?.source === "local_white_model" ? 0 : 1);
  const priorityDelta = priority(a) - priority(b);
  if (priorityDelta !== 0) return priorityDelta;
  const group = benchmarkAssetGroupLabel(a).localeCompare(benchmarkAssetGroupLabel(b));
  if (group !== 0) return group;
  return a.label.localeCompare(b.label);
}

export function benchmarkAssetGroups(assets: BenchmarkAsset[]) {
  const groups = new Map<string, BenchmarkAsset[]>();
  for (const asset of assets) {
    const label = benchmarkAssetGroupLabel(asset);
    groups.set(label, [...(groups.get(label) ?? []), asset]);
  }
  return Array.from(groups, ([label, groupAssets]) => ({ label, assets: groupAssets }));
}

export function selectedPartFaceCount(parts: PartRecord[], selectedPart: string) {
  const part = parts.find((item) => item.part_id === selectedPart);
  const value = part?.metadata?.face_count;
  return value === null || value === undefined ? "none" : String(value);
}

export function partSocketSummary(part: PartRecord | null) {
  if (!part?.metadata) return "none";
  const sourcePart = part.metadata.source_part_id;
  const faceCount = part.metadata.face_count;
  const bbox3d = part.metadata.bbox3d;
  const source = typeof sourcePart === "string" && sourcePart ? sourcePart : part.part_id;
  const faces = faceCount === null || faceCount === undefined ? "no faces" : `${faceCount} faces`;
  const bbox = bbox3d && typeof bbox3d === "object" ? "bbox3d" : "no bbox";
  return `${source} / ${faces} / ${bbox}`;
}

export function stageShortLabel(stage: string) {
  const labels: Record<string, string> = {
    silhouette: "outline",
    rough_form: "form",
    part: "part",
    texture: "texture",
  };
  return labels[stage] ?? stage;
}

export function caseCreativeStage(manifest: CaseManifest, fallback: string) {
  const metadataStage = manifest.case.metadata?.creative_stage;
  if (typeof metadataStage === "string" && isCreativeStage(metadataStage)) return metadataStage;
  const acceptedStage = manifest.accepted_candidates?.[0]?.metadata?.stage;
  if (typeof acceptedStage === "string" && isCreativeStage(acceptedStage)) return acceptedStage;
  return isCreativeStage(fallback) ? fallback : "part";
}

export function isCreativeStage(stage: string) {
  return ["silhouette", "rough_form", "part", "texture"].includes(stage);
}

export function commitPolicyForStage(stage: string, fidelity: string) {
  if (stage === "silhouette" && fidelity === "low") return "direction_memory";
  if (stage === "texture") return "material_state";
  return stage === "part" ? "fitted_asset" : "active_asset";
}

export function divergenceAxesForStage(stage: string) {
  const axes: Record<string, string[]> = {
    silhouette: ["silhouette", "proportion", "stance", "mass_distribution"],
    rough_form: ["curvature", "volume_distribution", "structural_language"],
    part: ["motif", "structure", "boundary_behavior", "surface_depth"],
    texture: ["material", "color", "surface_pattern", "finish"],
  };
  return axes[stage] ?? axes.part;
}

export function defaultFidelityForStage(stage: string) {
  if (stage === "silhouette") return "low";
  if (stage === "texture") return "high";
  return "medium";
}

export function upsertIntentDraft(items: IntentDraft[], draft: IntentDraft) {
  const next = items.filter((item) => item.draft_id !== draft.draft_id);
  return [draft, ...next].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function upsertArtifact(items: ArtifactRecord[], artifact: ArtifactRecord) {
  const next = items.filter((item) => item.artifact_id !== artifact.artifact_id);
  return [artifact, ...next].slice(0, 12);
}

export function referenceImagesPayload(items: ArtifactRecord[]) {
  return items.map((item) => ({
    artifact_id: item.artifact_id,
    url: item.url,
    role: item.metadata?.role ?? "shape_reference",
    type: item.type,
  }));
}

export function referenceModelsPayload(items: ArtifactRecord[]) {
  return items.map((item) => ({
    artifact_id: item.artifact_id,
    url: item.url,
    role: item.metadata?.role ?? "model_reference",
    type: item.type,
    filename: item.metadata?.uploaded_filename ?? null,
  }));
}

export function artifactRecordsFromDraftRefs(
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

export function hashString(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index);
    hash |= 0;
  }
  return hash;
}

export function buildAnnotationPayload({
  sessionId,
  asset,
  partId,
  partLabel,
  text,
  displayMode,
  strokes,
  brushStrokes,
}: {
  sessionId: string;
  asset: AssetRecord;
  partId: string | null;
  partLabel: string | null;
  text: string;
  displayMode: CanvasDisplayMode;
  strokes?: AnnotationStroke[];
  brushStrokes?: Array<{ brush: string; points: AnnotationStroke }>;
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
  const brushSummary = brushStrokes?.length
    ? brushStrokes.map((stroke, index) => ({
        stroke_id: `brush_${index}_${crypto.randomUUID().slice(0, 8)}`,
        brush: stroke.brush,
        point_count: stroke.points.length,
        points: stroke.points,
      }))
    : null;
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
      brush_summary: brushSummary,
      brush_count: brushStrokes?.length ?? 0,
      brush_kinds: [...new Set(brushStrokes?.map((stroke) => stroke.brush) ?? [])],
    },
  };
}

export function annotationBoundingBox(points: AnnotationPoint[]) {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  return {
    x: Math.min(...xs),
    y: Math.min(...ys),
    width: Math.max(...xs) - Math.min(...xs),
    height: Math.max(...ys) - Math.min(...ys),
  };
}

export function inferAnnotationShape(points: AnnotationPoint[]) {
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

export function buildBrushMaskPayload({
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

export function buildSmoothOperationPayload({
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

export function buildPrimitiveAdditionPayload({
  sessionId,
  asset,
  partId,
  partLabel,
  primitive,
  text,
  transform,
}: {
  sessionId: string;
  asset: AssetRecord | null;
  partId: string | null;
  partLabel: string | null;
  primitive: Exclude<CanvasPrimitive, null>;
  text: string;
  transform?: { position: number[], rotation: number[], scale: number[] } | null;
}) {
  const normalizedText = text.trim();
  return {
    session_id: sessionId,
    asset_id: asset?.asset_id ?? null,
    part_id: partId,
    primitive,
    transform: transform ? {
      position: transform.position,
      rotation: transform.rotation,
      scale: transform.scale,
      space: "world",
    } : {
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

export function buildDragOperationPayload({
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

export function buildFocusObservationPayload({
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

export function analogyPromptTokens(directions: AnalogyDirection[]): PromptToken[] {
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

export function coercePromptToken(value: unknown, direction: AnalogyDirection): PromptToken | null {
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

export function promptTokenDimension(value: unknown, fallback: PromptToken["dimension"]): PromptToken["dimension"] {
  return value === "Aesthetic" || value === "Functional" || value === "Structural" || value === "Cross-domain"
    ? value
    : fallback;
}

export function promptTokenKey(token: PromptToken) {
  return `${token.dimension ?? "Any"}:${token.role ?? "word"}:${token.label.toLowerCase()}`;
}

export function composePromptWithTokens(text: string, tokens: PromptToken[]) {
  const base = text.replace(/\n?Analogy keywords:.*$/s, "").trim();
  if (!tokens.length) return base;
  const words = tokens
    .map((token) => token.full_phrase_zh ?? token.label)
    .join(", ");
  return `${base}\nAnalogy keywords: ${words}`.trim();
}

export function buildAnalogyPromptPackage(
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

export function inferObjectType(filename: string) {
  const lower = filename.toLowerCase();
  if (lower.includes("speaker")) return "speaker";
  if (lower.includes("chair")) return "chair";
  if (lower.includes("lamp")) return "lamp";
  if (lower.includes("shoe")) return "shoe";
  return "object";
}

export function isDiscoverableMeshFile(filename: string) {
  const lower = filename.toLowerCase();
  return lower.endsWith(".glb") || lower.endsWith(".obj");
}

export function signalSummary(values: Record<string, unknown>) {
  const active = Object.entries(values)
    .filter(([, value]) => value !== null && value !== undefined && value !== false && value !== "")
    .slice(0, 2)
    .map(([key, value]) => {
      if (typeof value === "object") return key;
      return `${key}:${String(value)}`;
    });
  return active.length ? active.join(" / ") : "none";
}
