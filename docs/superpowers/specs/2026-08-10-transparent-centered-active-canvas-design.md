# FlowStudio Transparent Centered Active Canvas Design

## Goal

Make the active 3D model feel embedded directly in the spatial workspace:

- remove the active version frame's white fill, rounded-card silhouette, and shadow;
- center the active model on the browser viewport rather than inside the left-over safe-area column;
- keep the version metadata as a lightweight floating pill;
- keep Perception, AI Behavior, Composer, Solution Space, and navigation anchored as they are.

## Layout Contract

The active version node is a transparent positioning surface, not a visible card. Its horizontal center must equal `50vw`. Its vertical center uses the unobstructed workspace above the Composer, with a small upward bias so the model is not hidden by the Composer.

The Three.js renderer remains transparent. The global dotted workspace is therefore visible behind the model. The model keeps its existing camera fitting, lighting, orbit, sculpting, and selection behavior.

The version metadata pill stays near the active model's upper-left edge and remains clickable. Overview/history thumbnails keep their existing card treatment; only the expanded active node becomes visually frameless.

## Implementation Boundary

The change is limited to active-node positioning and presentation:

- `frontend/src/state/studioStore.ts`: calculate the active-canvas pan from the current viewport and the active editor dimensions instead of the legacy fixed 520px node assumption;
- `frontend/src/styles.css` and/or `frontend/src/workspaceLayout.css`: remove expanded active-frame fill, radius, and shadow while preserving thumbnail styles;
- `frontend/tests/workspaceBrowserContract.ts`: verify the active editor is centered, transparent, inside the viewport, and nonzero in size.

No API, model loading, Three.js parsing, camera, backend, generation, or panel-state behavior changes.

## Responsive Behavior

At desktop widths, centering uses the full viewport. At narrow widths, the active model remains centered in the viewport while its existing max-width/max-height constraints prevent it from leaving the screen. Floating panels retain their current responsive stacking and z-index behavior.

## Verification

At 1280×720 with a loaded Snowman:

- active editor center is within 2px of the viewport center;
- active frame and node have transparent backgrounds and no box shadow;
- version canvas and document have no horizontal or vertical overflow;
- the Snowman is visibly rendered;
- Perception, AI Behavior, Composer, and navigation remain within the viewport;
- frontend tests, TypeScript checking, and Vite build pass.
