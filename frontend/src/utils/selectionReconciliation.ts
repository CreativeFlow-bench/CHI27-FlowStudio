import type { PromptToken } from "../types.ts";

export function resolveServerSelectedCandidateIds({
  revisionSelectedCandidateIds,
  runSelectedCandidateIds,
}: {
  revisionSelectedCandidateIds: string[] | null | undefined;
  runSelectedCandidateIds: string[] | null | undefined;
}): string[] {
  return revisionSelectedCandidateIds ?? runSelectedCandidateIds ?? [];
}

export function reconcileSelectedPromptTokens({
  availableTokens,
  serverSelectedCandidateIds,
  optimisticTokens,
  persistencePending,
}: {
  availableTokens: PromptToken[];
  serverSelectedCandidateIds: string[];
  optimisticTokens: PromptToken[];
  persistencePending: boolean;
}): PromptToken[] {
  if (persistencePending) return optimisticTokens;
  const selected = new Set(serverSelectedCandidateIds);
  return availableTokens.filter(
    (token) => token.candidate_id && selected.has(token.candidate_id),
  );
}
