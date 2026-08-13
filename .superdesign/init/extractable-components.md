# Extractable Components

## StudioMenu
- Source: `frontend/src/components/menu/StudioMenu.tsx`
- Category: layout
- Description: Resizable left experiment/source/runtime rail.
- Extractable props: studioDrawerOpen, project, projectBusy, recordingError
- Hardcoded: section labels, lucide icons, CSS classes

## AIBehaviorPanel
- Source: `frontend/src/components/panels/AIBehaviorPanel.tsx`
- Category: layout
- Description: Resizable right hierarchy for phenomenon, next question, details, and divergence controls.
- Extractable props: uiBrief, pendingRevisionCount, semanticDivergenceLoading, divergence parameters
- Hardcoded: AI Behavior label, status dots, group labels

## IntentComposer
- Source: `frontend/src/components/panels/IntentComposer.tsx`
- Category: layout
- Description: Bottom-centered intent input and tool action bar.
- Extractable props: intentText, enabled tool flags, canSendIntent
- Hardcoded: tool icons and primary placeholder

## ProjectSection
- Source: `frontend/src/components/project/ProjectSection.tsx`
- Category: basic
- Description: Temporary/recording/ended experiment-file card.
- Extractable props: project, recordingError
- Hardcoded: Experiment file label and action icon set

## ProjectDialog
- Source: `frontend/src/components/project/ProjectDialog.tsx`
- Category: basic
- Description: New/open experiment file modal with baseline choice.
- Extractable props: projects, busy
- Hardcoded: baseline descriptions and form layout

## ProjectTimeline
- Source: `frontend/src/components/project/ProjectTimeline.tsx`
- Category: basic
- Description: Ordered experiment event drawer.
- Extractable props: project, events
- Hardcoded: event-row visual structure

## ResizableShell / Panel / StatusPill
- Source: `frontend/src/components/ui/primitives.tsx`
- Category: basic
- Description: Shared floating panel, content panel, and status patterns.
- Extractable props: size bounds, title, tone, status
- Hardcoded: resize mechanics and CSS class vocabulary

