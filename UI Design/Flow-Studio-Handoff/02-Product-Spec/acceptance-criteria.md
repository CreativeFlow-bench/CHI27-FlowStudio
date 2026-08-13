# Acceptance criteria

## Project and persistence

- A project can be created, renamed, reopened and archived.
- Reloading restores the active version, camera, intents and version tree.
- Failed saves show retry without discarding local work.

## 3D workspace

- A valid GLB/GLTF model renders and can be rotated, panned and zoomed.
- Invalid or oversized files produce a useful error.
- Brush marks remain attached to the same model surface after rotation.
- Floating UI does not cover the active model at the reference desktop sizes.

## Intent

- Operations appear as evidence in the live intent.
- Users can edit, confirm and dismiss an intent.
- Confirmed intent text is immutable until an explicit edit action.
- A new operation after confirmation starts a new live intent.
- AI failure preserves evidence and offers retry/manual entry.

## Divergence and versions

- Diverge is unavailable with zero confirmed intents.
- Combined intent can be edited before direction generation.
- Selected direction terms persist with the generated references.
- Building creates a child linked to the correct parent.
- Branching from an old version never deletes or moves unrelated descendants.

## Localization and accessibility

- English/Chinese switching preserves all project state.
- Every icon-only control has an accessible name.
- All primary actions are keyboard reachable.
- Loading, success and failure are not communicated by colour alone.

## Performance

- The workspace remains responsive with eight model versions.
- Expensive generation uses asynchronous jobs and does not block navigation.

