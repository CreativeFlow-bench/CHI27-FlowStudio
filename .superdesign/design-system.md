# FlowStudio Design System

## Product context

FlowStudio is a desktop-first creative 3D workspace for observing a user's editing behavior, confirming the scope of an intent revision, exploring semantic divergence, generating solution candidates, and branching model versions. The canvas and active model are the product's primary surface; panels support the creative task and must never visually dominate it.

The primary workspace contains:

- Brand mark and compact Perception panel on the left.
- Active 3D model/version canvas in the center.
- Optional horizontal Solution Space across the upper center/right.
- Compact AI Behavior panel on the right.
- Intent Composer fixed inside the bottom-center viewport.
- Planner clarification bubbles placed near the relevant subject on canvas.

## Visual source of truth

Use the user-approved Figure 4 direction: an airy white dotted canvas, a large central model, restrained translucent-white panels, compact typography, generous negative space, and small blue/cyan/pink signals. Preserve FlowStudio's real logo, friendly handwritten accent, and existing blue-to-pink creative language.

The UI must feel like a creative spatial canvas, not an enterprise dashboard. Avoid dense card stacks, full-height sidebars, large status banners, repeated headings, and heavy shadows.

## Color tokens

Use only these colors and transparent variants derived from them:

- Primary ink: `#1a1f2c`
- Secondary ink: `#5c6578`
- Muted ink: `#8a93a6`
- Solid panel: `#ffffff`
- Translucent panel: `rgba(255, 255, 255, 0.78)`
- Panel border: `rgba(210, 216, 228, 0.85)`
- Canvas background: `#f4f5f7`
- Canvas dots: `#c8ccd4`
- Accent blue: `#2f7bff`
- Deep blue: `#1b5fd4`
- Accent pink: `#ff4f9a`
- Accent cyan: `#2ad4e8`
- Accent violet: `#9b7bff`
- Success mint: `#34d399`

Gradients are reserved for tiny creative signals, selected tool fills, and the subtle Composer track. Do not use large decorative gradients in panel backgrounds.

## Typography

- UI family: `Manrope`, then `ui-sans-serif`, then `sans-serif`.
- Handwritten accent: `Caveat`, then `Segoe Print`, then `cursive`.
- Use handwritten type only for the FlowStudio wordmark, Composer intent text, and `More Creative?` heading.
- Panel labels: 10-11px, uppercase, 700-800 weight, 0.10-0.14em tracking.
- Primary panel narrative: 13-15px, 600-700 weight, 1.4-1.5 line height.
- Supporting text: 10-12px, regular or medium.
- Never introduce serif, display, monospace, or alternative handwritten fonts.

## Spacing and geometry

- Base spacing: 4px.
- Workspace gap: 16px.
- Viewport edge: `clamp(12px, 1.4vw, 24px)`.
- Compact control height: 32-38px.
- Primary touch target on narrow screens: at least 44px.
- Panel radius: 18-22px.
- Composer radius: 26-28px.
- Chips and icon tools: pill or circular.
- Borders are 1px and low contrast.
- Default panels have no drop shadow; use subtle blur and border separation.

## Desktop layout contract

The desktop reference viewport is 1440x900; 1280x720 is the minimum acceptance viewport.

- Perception width: `clamp(280px, 24vw, 340px)`.
- Solution Space starts after the left brand/perception zone: `clamp(360px, 34vw, 440px)`.
- Solution Space height: `clamp(176px, 23vh, 220px)`.
- AI Behavior width: `clamp(292px, 22vw, 340px)`.
- Composer width: at most 720px and at least 24px from viewport edges.
- The active editor uses the remaining safe rectangle and keeps the whole subject visible.

When Solution Space does not exist, AI Behavior is docked on the right side in the middle-upper part of the available vertical region, not attached to the top-right corner. When Solution Space exists, AI Behavior moves below the result rail with one 16px gap.

The page itself does not scroll. Only a deliberate internal details region may scroll. The Composer is always completely visible.

## Information ownership

Every message has one primary location:

- Perception: one verifiable current user action, maximum two lines.
- Planner bubble: the only location for a Gate question and accept/reject actions.
- AI Behavior: one short AI narrative plus More Creative controls.
- Solution Space: generation progress and candidate results.
- Collapsed details: raw model output, runtime metadata, and debugging evidence.

Do not repeat Gate status, scope confirmation, the Gate question, phenomenon/next-step synonyms, or generation progress across panels.

## Component styling

### Perception

Compact two-part white panel with a 36-44px label row and a short body. It should read as a quiet observation note rather than a primary card.

### Solution Space

A wide, shallow horizontal rail. Candidate imagery is the dominant content. Use a simple label row and compact result tiles with small accepted markers. Horizontal scrolling is acceptable inside the rail.

### AI Behavior

A narrow right-side panel with a compact label row, one short narrative, three tiny status dots, and `More Creative?`. Do not render a full-height dock. Do not show the backend four-stage process. Advanced parameters and model details are progressive disclosure.

### Composer

Bottom-centered and fully inside the viewport. Use a large handwritten intent line, a compact blue/pink tool track, circular tool buttons, and a clear send action. The central model must remain visible above it.

### Planner bubble

Use a small blue/pink translucent pill near the target, one question, and compact accept/reject controls. Avoid duplicating its content elsewhere.

## Interaction and motion

- Use explicit property transitions only, never `transition: all`.
- Motion duration: 120-220ms for panel movement, opacity, border, or transform.
- Moving AI Behavior below Solution Space should feel like a single coordinated layout transition.
- Honor `prefers-reduced-motion` and remove non-essential animation.
- Preserve visible `:focus-visible` outlines using deep blue.

## Responsive behavior

- At 1280px and above, use the complete Figure 4 spatial composition.
- Between 900px and 1279px, tighten gaps and panel widths while preserving the same hierarchy.
- Below 900px, collapse Perception to a single-line status and AI Behavior to an expandable drawer; keep Composer visible and Solution Space horizontally scrollable.

## Forbidden patterns

- Full-height AI Behavior dock on desktop.
- Empty Solution Space frame before generation begins.
- Multiple cards repeating the same state or question.
- Contradictory scope chips.
- Fixed element dimensions controlled simultaneously by React inline state and CSS overrides.
- New `!important` layout rules.
- Large shadows, glassmorphism haze, neon gradients, or dense dashboard framing.
