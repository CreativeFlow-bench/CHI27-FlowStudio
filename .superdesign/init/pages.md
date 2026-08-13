# Page Dependency Trees

## / (Flow Studio workspace)

Entry: `frontend/src/main.tsx`

Dependencies:
- `frontend/src/state/studioStore.ts`
  - `frontend/src/api.ts`
  - `frontend/src/types.ts`
  - `frontend/src/editorScene.ts`
  - `frontend/src/utils/appHelpers.ts`
  - `frontend/src/utils/experimentProject.ts`
  - `frontend/src/utils/uiBrief.ts`
  - `frontend/src/utils/versionGraph.ts`
- `frontend/src/components/menu/StudioMenu.tsx`
  - `frontend/src/components/project/ProjectSection.tsx`
  - `frontend/src/components/project/ProjectDialog.tsx`
  - `frontend/src/components/project/ProjectTimeline.tsx`
  - `frontend/src/components/ui/primitives.tsx`
- `frontend/src/components/StudioCanvas.tsx`
  - `frontend/src/components/ThreeViewport.tsx`
  - `frontend/src/components/ui/primitives.tsx`
- `frontend/src/components/panels/PerceptionPanel.tsx`
- `frontend/src/components/panels/AIBehaviorPanel.tsx`
- `frontend/src/components/panels/IntentComposer.tsx`
- `frontend/src/components/panels/SolutionSpaceRail.tsx`
- `frontend/src/components/overlays/PlannerClarificationOverlay.tsx`
- `frontend/src/components/overlays/AnnotationCanvasOverlay.tsx`
- `frontend/src/styles.css`

