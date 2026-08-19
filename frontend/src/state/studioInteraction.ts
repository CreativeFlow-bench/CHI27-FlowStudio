import type { Candidate } from "../types";

export function fourStageCandidateId(
  runId: string | null | undefined,
  index: number,
  artifact?: { candidate_id?: unknown } | null,
): string {
  const fromArtifact = artifact?.candidate_id;
  if (typeof fromArtifact === "string" && fromArtifact.trim()) return fromArtifact.trim();
  return `fourstage_${runId || "run"}_${index + 1}`;
}

export function summarizeKeywords(keywords: string[], limit = 3): string {
  const shown = keywords.map((item) => item.trim()).filter(Boolean).slice(0, limit);
  if (!shown.length) return "";
  const extra = keywords.length - shown.length;
  return extra > 0 ? `${shown.join(" · ")} +${extra}` : shown.join(" · ");
}

export function candidateSeriesLabel(
  intentSeq: number | null | undefined,
  promptIndex: number,
  keywords: string[] = [],
): string {
  const seq = typeof intentSeq === "number" && intentSeq > 0 ? `Gen${intentSeq}` : "Gen";
  const scheme = summarizeKeywords(keywords, 2);
  return scheme ? `${seq} · ${promptIndex + 1} · ${scheme}` : `${seq} · ${promptIndex + 1}`;
}

export function inheritedKeywordsFromRevisions(
  revisions: Array<{ intent_seq: number; status: string; effective_keywords?: string[] }>,
  activeIntentSeq: number | null,
): string[] {
  if (activeIntentSeq == null) return [];
  return (
    [...revisions]
      .filter((item) =>
        item.intent_seq < activeIntentSeq
        && ["accepted", "generating", "completed"].includes(item.status),
      )
      .reverse()
      .find((item) => (item.effective_keywords ?? []).length)?.effective_keywords
    ?? []
  );
}

export function visibleInheritedKeywords(inherited: string[], excluded: string[]): string[] {
  const skip = new Set(excluded);
  return inherited.filter((keyword) => keyword && !skip.has(keyword));
}

export function fourStageCandidateFromArtifact({
  runId,
  index,
  artifact,
  sessionId,
  assetId,
  partId,
  intentSeq,
  revisionId,
  keywords = [],
  extraMetadata = {},
}: {
  runId: string;
  index: number;
  artifact: { candidate_id?: unknown; kind?: string | null; url?: string | null };
  sessionId: string;
  assetId: string;
  partId: string | null;
  intentSeq?: number | null;
  revisionId?: string | null;
  keywords?: string[];
  extraMetadata?: Record<string, unknown>;
}): Candidate {
  const kind = String(artifact.kind ?? "png");
  const url = String(artifact.url ?? "");
  return {
    candidate_id: fourStageCandidateId(runId, index, artifact),
    job_id: runId,
    session_id: sessionId,
    source_asset_id: assetId,
    source_part_id: partId,
    label: candidateSeriesLabel(intentSeq, index, keywords),
    decision: "suggested",
    mesh_url: kind === "glb" ? url : null,
    obj_url: kind === "obj" ? url : null,
    thumbnail_url: kind === "png" ? url : null,
    scores: {},
    metadata: {
      stage: "four_stage_generated",
      fidelity: "medium",
      four_stage_artifact: true,
      run_id: runId,
      revision_id: revisionId ?? null,
      intent_seq: intentSeq ?? null,
      artifact_kind: kind,
      prompt_index: index,
      delta_keywords: keywords,
      ...extraMetadata,
    },
  };
}
