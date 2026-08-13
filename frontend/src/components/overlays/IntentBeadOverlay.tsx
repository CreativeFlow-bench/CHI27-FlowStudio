/** Saved intent drafts as beads around the object (refactor plan P1a). */
import type { IntentDraft } from "../../types";

export function IntentBeadOverlay({
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

