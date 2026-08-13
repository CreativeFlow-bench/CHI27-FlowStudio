# Theme

## Compact token summary

- Canvas: `#f4f5f7` with `#c8ccd4` dot grid.
- Ink: primary `#1a1f2c`, secondary `#5c6578`, muted `#8a93a6`.
- Panels: translucent white `rgba(255,255,255,.78)`, border `rgba(210,216,228,.85)`, default radius `22px`, intentionally minimal shadow.
- Accents: blue `#2f7bff`, deep blue `#1b5fd4`, pink `#ff4f9a`, cyan `#2ad4e8`, violet `#9b7bff`, mint `#34d399`.
- Typography: Manrope for UI; Caveat / Segoe Print for handwritten creative labels.
- Current visual language: pale grey point-grid workspace, white rounded floating cards, blue/pink/cyan decision accents, compact uppercase labels.
- Responsive breakpoints in CSS center around 1100px, 820px, 620px, and 390px behavior.

## Raw `frontend/src/styles.css`

```css
:root {
  --ink: #1a1f2c;
  --ink-soft: #5c6578;
  --ink-mute: #8a93a6;
  --panel-bg: rgba(255, 255, 255, 0.78);
  --panel-solid: #ffffff;
  --panel-border: rgba(210, 216, 228, 0.85);
  --panel-radius: 22px;
  --panel-shadow: none;
  --accent-blue: #2f7bff;
  --accent-blue-deep: #1b5fd4;
  --accent-pink: #ff4f9a;
  --accent-cyan: #2ad4e8;
  --accent-violet: #9b7bff;
  --accent-mint: #34d399;
  --canvas-bg: #f4f5f7;
  --canvas-dot: #c8ccd4;
  --font-ui: "Manrope", ui-sans-serif, sans-serif;
  --font-hand: "Caveat", "Segoe Print", cursive;
  color: var(--ink);
  background: var(--canvas-bg);
  font-family: var(--font-ui);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}

* {
  box-sizing: border-box;
}

html,
body,
#root {
  min-height: 100%;
  margin: 0;
}

button,
textarea,
input,
select {
  font: inherit;
}

button {
  border: 1px solid var(--panel-border);
  background: var(--panel-solid);
  color: var(--ink);
  border-radius: 12px;
  padding: 9px 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  cursor: pointer;
  min-height: 38px;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}

button:hover:not(:disabled) {
  border-color: var(--accent-blue);
  transform: translateY(-1px);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

button.ghost {
  width: 100%;
  background: rgba(248, 250, 252, 0.9);
}

button.compact {
  width: auto;
  min-height: 32px;
  padding: 6px 9px;
  border-radius: 999px;
  font-size: 12px;
}

button.icon-button {
  width: 30px;
  min-width: 30px;
  min-height: 30px;
  padding: 0;
  border-radius: 50%;
}

/* ---------- Floating shell ---------- */

.studio-shell {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background-color: var(--canvas-bg);
  background-image: radial-gradient(var(--canvas-dot) 1.15px, transparent 1.15px);
  background-size: 22px 22px;
}

.studio-error-screen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-content: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
  background: var(--canvas-bg);
}

.studio-error-screen h2 {
  margin: 0;
  font-size: 18px;
}

.studio-error-screen p {
  margin: 0;
  color: var(--ink-soft);
  font-size: 13px;
  max-width: 460px;
}

.studio-error-screen button {
  justify-self: center;
  padding: 8px 18px;
  border-radius: 999px;
  border: 1px solid var(--panel-border);
  background: #111827;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.studio-shell::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 40% 30% at 18% 20%, rgba(47, 123, 255, 0.05), transparent 70%),
    radial-gradient(ellipse 35% 28% at 82% 30%, rgba(255, 79, 154, 0.04), transparent 70%);
}

.brand-mark {
  position: absolute;
  top: 18px;
  left: 22px;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 10px;
  pointer-events: auto;
}

.brand-mark-logo {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background:
    conic-gradient(from 210deg, #47b7ff, #9b7bff, #ff4f9a, #47b7ff);
  box-shadow: 0 8px 20px rgba(80, 100, 160, 0.22);
  position: relative;
}

.brand-mark-logo::after {
  content: "";
  position: absolute;
  inset: 7px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.88);
}

.brand-mark h1 {
  margin: 0;
  font-family: var(--font-hand);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0.01em;
  color: var(--ink);
  line-height: 1;
}

.brand-mark button {
  margin-left: 4px;
  min-height: 30px;
  border-radius: 999px;
  padding: 5px 11px;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  background: var(--panel-bg);
  backdrop-filter: blur(12px);
  border-color: var(--panel-border);
}

.workspace {
  position: relative;
  min-height: 100vh;
  display: block;
}

/* Left pull-out studio menu */

.studio-rail {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 28;
  width: 0;
  overflow: hidden;
  background: #e8eaef;
  border-right: 1px solid rgba(190, 196, 208, 0.85);
  transition: width 0.2s ease;
}

.studio-rail.is-open {
  overflow: visible;
}

.studio-rail-scroll {
  height: 100%;
  overflow: auto;
  padding: 78px 18px 28px;
  display: grid;
  gap: 14px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease;
}

.studio-rail.is-open .studio-rail-scroll {
  opacity: 1;
  pointer-events: auto;
}

.studio-rail-handle {
  position: fixed;
  top: 50%;
  z-index: 30;
  width: 28px;
  height: 58px;
  min-height: 58px;
  padding: 0;
  border-radius: 14px;
  border: 1px solid rgba(190, 196, 208, 0.95);
  background: #eceef2;
  color: #7a8498;
  transform: translateY(-50%);
  box-shadow: none;
  cursor: ew-resize;
  touch-action: none;
}

.studio-rail-handle:hover:not(:disabled) {
  transform: translateY(-50%);
  border-color: rgba(47, 123, 255, 0.4);
  color: var(--accent-blue-deep);
}

.studio-rail-handle.is-open {
  background: #f4f5f8;
}

.resizable-shell {
  position: absolute;
  overflow: hidden;
}

.resizable-shell-body {
  height: 100%;
  overflow-x: hidden;
  overflow-y: scroll;
  scrollbar-gutter: stable;
  display: grid;
  gap: inherit;
  min-height: 0;
}

.resizable-shell-body > .float-panel-label {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--panel-bg);
}

.resize-handle {
  position: absolute;
  width: 16px;
  height: 16px;
  z-index: 4;
  border-radius: 4px 0 10px 0;
  background:
    linear-gradient(135deg, transparent 45%, rgba(120, 130, 150, 0.45) 46%, rgba(120, 130, 150, 0.45) 54%, transparent 55%),
    linear-gradient(135deg, transparent 60%, rgba(120, 130, 150, 0.35) 61%, rgba(120, 130, 150, 0.35) 69%, transparent 70%);
  touch-action: none;
  opacity: 0.55;
  border: 0;
  padding: 0;
}

.resize-handle:hover {
  opacity: 1;
}

.resize-handle.corner-se {
  right: 2px;
  bottom: 2px;
  cursor: nwse-resize;
}

.resize-handle.corner-sw {
  left: 2px;
  bottom: 2px;
  cursor: nesw-resize;
  border-radius: 0 4px 0 10px;
  transform: scaleX(-1);
}

.canvas-column {
  position: relative;
  min-height: 100vh;
  min-width: 0;
  padding: 0;
  z-index: 1;
}

.canvas-loading {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 30;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--panel-border);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
  font-size: 13px;
  font-weight: 700;
  color: #2c3344;
}

.canvas-loading-spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2.5px solid rgba(59, 130, 246, 0.25);
  border-top-color: #3b82f6;
  animation: studio-spin 0.8s linear infinite;
}

.benchmark-loading {
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(59, 130, 246, 0.08);
  color: #2458a8;
  font-size: 11px;
  font-weight: 700;
}

.mc-pane-busy {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  color: #3b82f6;
}

.mc-spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid rgba(59, 130, 246, 0.25);
  border-top-color: #3b82f6;
  animation: studio-spin 0.8s linear infinite;
}

.mc-param-row {
  display: grid;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 10px;
  background: rgba(90, 110, 150, 0.06);
  border: 1px solid rgba(90, 110, 150, 0.14);
}

.mc-param {
  display: grid;
  grid-template-columns: 76px 1fr 30px;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--ink-soft);
}

.mc-param input[type="range"] {
  width: 100%;
  accent-color: #3b82f6;
}

.mc-param em {
  font-style: normal;
  font-weight: 700;
  text-align: right;
  color: #2458a8;
}

.four-stage-mini {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.28);
  font-size: 11px;
  font-weight: 700;
  color: #2458a8;
}

.four-stage-mini.stage-generation,
.four-stage-mini.stage-awaiting_gate {
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.35);
  color: #9a6408;
}

.four-stage-mini.stage-completed {
  background: rgba(34, 140, 90, 0.1);
  border-color: rgba(34, 140, 90, 0.32);
  color: #1c7a4c;
}

.four-stage-mini-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #3b82f6;
  animation: studio-spin 1s linear infinite;
  border: 1.5px solid rgba(255, 255, 255, 0.85);
}

.four-stage-mini.stage-completed .four-stage-mini-dot {
  animation: none;
  background: #1c7a4c;
}

.four-stage-mini-label {
  white-space: nowrap;
}

.four-stage-mini-note {
  color: inherit;
  opacity: 0.8;
  font-weight: 600;
}

.four-stage-mini-artifacts {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  width: 100%;
}

.four-stage-mini-artifacts img {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--panel-border);
}

@keyframes studio-spin {
  to {
    transform: rotate(360deg);
  }
}

.sidebar,
.inspector,
.topbar,
.status-strip {
  display: none;
}

.studio-rail .panel {
  border: 0;
  background: transparent;
  padding: 0;
  box-shadow: none;
}

.studio-rail .panel-title {
  margin-bottom: 8px;
}

.studio-rail .panel-title h2 {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-mute);
  font-weight: 800;
}

/* Floating panels */

.float-panel {
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  background: var(--panel-bg);
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(18px);
  padding: 14px 16px;
}

.float-panel-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  cursor: move;
  touch-action: none;
}

.float-panel-label span {
  color: var(--ink-mute);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.mobile-panel-toggle {
  display: none;
}

.status-dots {
  display: flex;
  gap: 5px;
}

.status-dots i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: block;
}

.status-dots i:nth-child(1) {
  background: var(--accent-cyan);
}

.status-dots i:nth-child(2) {
  background: var(--accent-violet);
}

.status-dots i:nth-child(3) {
  background: var(--accent-pink);
}

.workspace-chrome {
  display: contents;
}

.perception-float {
  position: absolute;
  top: 68px;
  left: 22px;
  z-index: 12;
  min-width: 0;
  width: auto;
  max-width: min(360px, calc(100vw - 360px));
  height: auto;
}

.perception-float.observe-float.is-open {
  max-width: min(460px, calc(100vw - 280px));
}

.perception-float:not(.observe-float) p {
  margin: 0;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(244, 246, 250, 0.9);
  color: var(--ink);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
}

.perception-float .perception-meta {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--ink-soft);
  font-size: 11px;
}

.perception-signal-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.perception-signal-row span {
  border-radius: 999px;
  background: #eef3ff;
  color: #2f4f86;
  padding: 3px 7px;
  font-size: 10px;
  font-weight: 700;
}

.hover-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.hover-chip {
  border-radius: 999px;
  background: rgba(47, 123, 255, 0.12);
  color: var(--accent-blue-deep, #1f5fd6);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
}

.hover-chip.soft {
  background: rgba(255, 79, 154, 0.12);
  color: #b41f63;
}

.perception-history {
  margin-top: 8px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.88);
  padding: 7px 10px;
}

.perception-history summary {
  cursor: pointer;
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 800;
}

.perception-history div {
  display: grid;
  gap: 5px;
  margin-top: 7px;
}

.perception-history span {
  color: var(--ink-soft);
  font-size: 10px;
  line-height: 1.35;
}

.float-panel.observe-float {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: min(300px, calc(100vw - 340px));
  max-width: min(360px, calc(100vw - 320px));
  padding: 10px 12px;
  border-radius: 18px;
  box-shadow: none;
  transition: width 0.18s ease, max-width 0.18s ease, padding 0.18s ease;
}

.float-panel.observe-float.is-open {
  width: min(420px, calc(100vw - 300px));
  max-width: min(460px, calc(100vw - 280px));
  padding-bottom: 12px;
}

.float-panel.observe-float .observe-log {
  max-height: min(42vh, 320px);
  overflow: auto;
}

.float-panel.canvas-composer {
  box-shadow: none;
}

.observe-head {
  margin-bottom: 0;
}

.observe-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ink-mute);
  cursor: pointer;
  transition: transform 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.observe-toggle:hover {
  background: rgba(255, 255, 255, 0.72);
  color: var(--ink);
}

.observe-toggle.is-open {
  transform: rotate(180deg);
  color: var(--ink);
}

.observe-sentence {
  margin: 0;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.35;
  font-weight: 600;
}

.observe-log {
  display: grid;
  gap: 0;
  margin-top: 4px;
  border-top: 1px solid rgba(120, 130, 150, 0.14);
}

.observe-log-row {
  display: grid;
  grid-template-columns: 36px 72px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 8px 0;
  border-bottom: 1px solid rgba(120, 130, 150, 0.12);
}

.observe-log-row:last-child {
  border-bottom: 0;
  padding-bottom: 2px;
}

.observe-log-row time {
  color: #9aa3b5;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
}

.observe-log-row em {
  color: #8b7cc8;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.4;
}

.observe-log-row em.tag-perception {
  color: #6f8fdb;
}

.observe-log-row em.tag-action {
  color: #c46a9a;
}

.observe-log-row em.tag-init {
  color: #7a86c9;
}

.observe-log-row span {
  color: var(--ink);
  font-size: 12px;
  line-height: 1.4;
  font-weight: 500;
}

.drawer-inline-label {
  display: grid;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
}

.drawer-inline-label select {
  min-height: 34px;
}

.ai-behavior-float {
  top: 72px;
  right: 18px;
  z-index: 12;
  gap: 12px;
}

.ai-behavior-float .resizable-shell-body {
  gap: 12px;
  align-content: start;
  padding-right: 4px;
}

.ai-behavior-float .mc-keywords-pane,
.ai-behavior-float .mc-keywords-pane .dimension-direction-list {
  min-height: 0;
  overflow: visible;
  flex: none;
}

.ai-behavior-float .scene-copy {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.45;
  font-weight: 500;
}

.behavior-context-card {
  display: grid;
  gap: 5px;
  border-radius: 16px;
  background: rgba(248, 250, 252, 0.92);
  padding: 10px 12px;
}

.behavior-context-card.planner-speech {
  min-height: 64px;
  background: linear-gradient(160deg, rgba(255, 246, 252, 0.95), rgba(241, 247, 255, 0.95));
}

.behavior-context-card strong {
  color: var(--ink);
  font-size: 13px;
}

.behavior-context-card p,
.planner-typewriter {
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  line-height: 1.5;
  font-weight: 550;
  letter-spacing: 0.01em;
}

.planner-typewriter i {
  display: inline-block;
  width: 0.55em;
  height: 1em;
  margin-left: 1px;
  vertical-align: -0.12em;
  background: transparent;
}

.planner-typewriter i.is-typing {
  background: rgba(70, 90, 140, 0.55);
  animation: planner-caret 0.9s steps(1) infinite;
}

@keyframes planner-caret {
  50% {
    opacity: 0;
  }
}

.behavior-context-card span {
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 700;
}

.behavior-mode-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.behavior-mode-row span {
  border-radius: 999px;
  background: #eef4ff;
  color: var(--accent-blue-deep);
  padding: 4px 9px;
  font-size: 10px;

  font-weight: 800;
}

.behavior-generate-button {
  width: 100%;
  min-height: 38px;
  border-radius: 999px;
  background: linear-gradient(145deg, #4a8fff, var(--accent-blue-deep));
  color: #fff;
  font-size: 13px;
  font-weight: 800;
  box-shadow: 0 10px 22px rgba(47, 123, 255, 0.22);
}

.behavior-generate-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.more-creative-title {
  margin: 4px 0 0;
  font-family: var(--font-hand);
  font-size: 28px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1;
}

.more-creative-scope {
  margin: 2px 0 8px;
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 600;
}

.mc-pane {
  border: 1px solid rgba(120, 140, 180, 0.22);
  border-radius: 12px;
  background: rgba(14, 20, 34, 0.38);
  padding: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.mc-pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.mc-pane-head span {
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  letter-spacing: 0.02em;
}

.mc-keywords-pane {
  gap: 6px;
}

.mc-keywords-pane .dimension-direction-list {
  flex: 1;
  min-height: 140px;
  overflow-y: auto;
}

.mc-keywords-pane .behavior-generate-button {
  flex-shrink: 0;
}

.solution-space-rail {
  left: 50%;
  top: 18px;
  z-index: 24;
  transform: translateX(-50%);
  border: 1px solid var(--panel-border);
  border-radius: 20px;
  background: var(--panel-bg);
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(16px);
  padding: 10px 12px;
  max-width: calc(100vw - 40px);
}

.solution-space-rail.is-loading {
  padding: 8px 12px;
}

.solution-space-rail .resizable-shell-body {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 8px;
}

.solution-space-rail .solution-space-scroll {
  flex: 1;
  min-height: 0;
}

.solution-space-rail.is-loading .resizable-shell-body {
  gap: 4px;
}

.solution-space-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  padding: 0 2px;
}

.solution-space-head span {
  color: var(--ink-mute);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.solution-space-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.solution-space-head strong {
  color: var(--ink-soft);
  font-size: 11px;
  font-weight: 700;
}

.solution-space-collapse {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  height: 22px;
  padding: 0 9px;
  gap: 4px;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
  color: var(--ink-soft);
  cursor: pointer;
  font-size: 11px;
  font-weight: 800;
}

.solution-space-collapse:hover {
  background: rgba(255, 255, 255, 0.85);
  color: var(--ink);
}

.solution-space-launcher {
  position: absolute;
  top: 18px;
  left: 50%;
  z-index: 24;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid var(--panel-border);
  background: rgba(255, 255, 255, 0.94);
  color: var(--ink);
  box-shadow: var(--panel-shadow);
  cursor: pointer;
  font-size: 11px;
  font-weight: 800;
}

.solution-space-launcher:hover,
.solution-space-launcher:focus-visible {
  border-color: rgba(47, 123, 255, 0.55);
  color: var(--accent-blue-deep);
}

.perception-state-chip {
  display: inline-block;
  margin-top: 4px;
  color: var(--ink-mute);
  font-size: 10px;
  letter-spacing: 0.04em;
}

.solution-space-scroll {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.solution-loading-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 700;
  min-height: 24px;
}

.solution-loading-strip i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-pink));
  animation: solution-loading-dot 0.9s ease-in-out infinite alternate;
}

.solution-loading-strip i:nth-child(2) {
  animation-delay: 0.12s;
}

.solution-loading-strip i:nth-child(3) {
  animation-delay: 0.24s;
}

@keyframes solution-loading-dot {
  from {
    opacity: 0.35;
    transform: translateY(2px);
  }
  to {
    opacity: 1;
    transform: translateY(-2px);
  }
}

.solution-card {
  flex: 0 0 132px;
  display: grid;
  grid-template-rows: 86px auto auto;
  gap: 6px;
  border: 1px solid rgba(220, 226, 236, 0.95);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  padding: 8px;
  position: relative;
}

.solution-card.accepted {
  border-color: rgba(52, 211, 153, 0.65);
  box-shadow: inset 0 0 0 1px rgba(52, 211, 153, 0.2);
}

.solution-card.accepted::after,
.solution-card .accepted-mark {
  content: "";
}

.solution-card .accepted-mark {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent-mint);
  color: white;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 900;
  z-index: 1;
}

.solution-card.direction {
  border-style: dashed;
}

.solution-card.loading {
  border-style: dashed;
  opacity: 0.92;
}

.solution-card img,
.solution-card-placeholder {
  width: 100%;
  height: 86px;
  border-radius: 12px;
  background: #eef1f6;
  object-fit: cover;
}

.solution-card-placeholder {
  display: grid;
  place-items: center;
  color: var(--ink-mute);
}

.solution-card-placeholder.shimmer {
  background: linear-gradient(90deg, #eef1f6 0%, #f8fafc 45%, #eef1f6 90%);
  background-size: 220% 100%;
  animation: flowstudio-shimmer 1.15s ease-in-out infinite;
}

@keyframes flowstudio-shimmer {
  from {
    background-position: 120% 0;
  }
  to {
    background-position: -120% 0;
  }
}

.solution-card-body {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.solution-card-body strong {
  color: var(--ink);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.solution-card-body span,
.solution-card-body em {
  color: var(--ink-soft);
  font-size: 9px;
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.solution-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.solution-card-actions button {
  min-height: 34px;
  padding: 3px 7px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
}

/* Infinite version canvas */

.version-canvas-shell {
  position: absolute;
  inset: 0;
  overflow: hidden;
  z-index: 1;
}

.version-canvas-shell.is-drop-target {
  background: rgba(47, 123, 255, 0.06);
  outline: 3px dashed rgba(47, 123, 255, 0.58);
  outline-offset: -12px;
}

.version-drop-hint {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 20;
  transform: translate(-50%, -50%);
  padding: 14px 22px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(47, 123, 255, 0.5);
  color: var(--accent-blue-deep);
  font-size: 14px;
  font-weight: 800;
  pointer-events: none;
}

.version-canvas-world {
  position: absolute;
  inset: 0;
  transform-origin: 0 0;
  will-change: transform;
}

.version-canvas-links {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  overflow: visible;
}

.version-link {
  fill: none;
  stroke: rgba(70, 90, 130, 0.22);
  stroke-width: 2;
  stroke-dasharray: 8 8;
}

.version-link.is-active-path {
  stroke: rgba(47, 123, 255, 0.72);
  stroke-width: 3;
  stroke-dasharray: none;
}

.version-node {
  position: absolute;
  width: 420px;
  height: 420px;
  border-radius: 28px;
  border: 1px solid transparent;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.version-node.active {
  border-color: transparent;
  box-shadow: none;
}

.version-node:not(.is-active-path) {
  opacity: 0.68;
}

.version-node-meta {
  position: absolute;
  left: 18px;
  top: 14px;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 36px);
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(210, 216, 228, 0.9);
  backdrop-filter: blur(8px);
}

.version-node-meta button {
  flex: 0 0 auto;
  min-height: 24px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(47, 123, 255, 0.28);
  background: #fff;
  color: var(--accent-blue-deep);
  cursor: pointer;
  font-size: 10px;
  font-weight: 800;
}

.version-node-meta strong,
.version-node-meta span,
.version-node-meta em {
  font-size: 11px;
  white-space: nowrap;
}

.version-node-meta span {
  overflow: hidden;
  text-overflow: ellipsis;
}

.version-node-meta em,
.version-node.thumbnail em {
  color: var(--accent-blue-deep);
  font-style: normal;
  font-weight: 700;
}

.version-node.thumbnail.is-active-version {
  border-color: rgba(59, 130, 246, 0.55);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.22);
}

.version-node.thumbnail.is-active-version img {
  object-fit: contain;
}

.version-node-frame {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 28px;
  overflow: hidden;
  background: transparent;
}

.version-active-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #fff;
}

.version-retry {
  position: absolute;
  right: 18px;
  bottom: 18px;
  z-index: 5;
  min-height: 34px;
  border-radius: 999px;
  border-color: rgba(220, 70, 70, 0.45);
  color: #b42318;
}

.version-node.thumbnail {
  width: 220px;
  height: 220px;
  border: 1px solid var(--panel-border);
  background: var(--panel-bg);
  backdrop-filter: blur(10px);
  box-shadow: var(--panel-shadow);
  padding: 10px;
  cursor: pointer;
}

.version-node.thumbnail img,
.version-node.thumbnail .version-thumb-fallback {
  width: 100%;
  height: 150px;
  border-radius: 16px;
  object-fit: cover;
  background: #e8ecf2;
}

.version-node.thumbnail .version-thumb-fallback {
  display: grid;
  place-items: center;
  color: var(--ink-mute);
  font-size: 12px;
}

.version-node.thumbnail strong {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-node.thumbnail span,
.version-node.thumbnail em {
  display: block;
  color: var(--ink-soft);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-node.thumbnail em {
  color: var(--accent-blue-deep);
}

.version-node.thumbnail.status-mesh-failed {
  border-color: rgba(220, 70, 70, 0.42);
}

.version-retry-inline {
  position: absolute;
  right: 10px;
  bottom: 8px;
  padding: 2px 7px;
  border-radius: 999px;
  background: #fff1f0;
  color: #b42318 !important;
  font-weight: 800;
}

.solution-card[draggable="true"] {
  cursor: grab;
}

.solution-card[draggable="true"]:active {
  cursor: grabbing;
}

.canvas-nav {
  position: absolute;
  left: 18px;
  bottom: 28px;
  z-index: 14;
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
  box-shadow: none;
}

.canvas-nav button {
  width: 34px;
  min-height: 34px;
  border-radius: 999px;
  padding: 0;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--ink-soft);
  background: transparent;
  border: 0;
}

.canvas-nav button.active {
  background: rgba(47, 123, 255, 0.16);
  color: var(--accent-blue-deep, #1f5fd6);
}

/* Viewport */

.viewport-wrap {
  width: 100%;
  height: 100%;
  min-height: 420px;
  border: 0;
  border-radius: 0;
  background: transparent;
  overflow: hidden;
  position: relative;
}

.viewport-head {
  position: absolute;
  left: 14px;
  top: 12px;
  z-index: 2;
  display: none;
}

.viewport {
  width: 100%;
  height: 100%;
  min-height: 420px;
  background: transparent !important;
}

.viewport canvas {
  display: block;
  width: 100% !important;
  height: 100% !important;
  background: transparent !important;
}

.viewport-tools {
  position: absolute;
  z-index: 2;
  display: flex;
  gap: 6px;
  right: 12px;
  top: 12px;
}

.viewport-mode-switch {
  display: none;
}

.viewport-hover-label {
  position: absolute;
  left: 50%;
  bottom: 18%;
  z-index: 3;
  transform: translateX(-50%);
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(28, 31, 40, 0.78);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.01em;
  pointer-events: none;
  box-shadow: none;
}

.viewport-hover-mask {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 2;
  pointer-events: none;
  mix-blend-mode: screen;
  opacity: 0.9;
}

.viewport-message {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid var(--panel-border);
  color: var(--ink-soft);
  font-size: 12px;
  font-weight: 600;
}

/* Composer */

.canvas-composer-shell {
  position: absolute;
  left: 50%;
  bottom: 16px;
  z-index: 16;
  transform: translateX(-50%);
  width: min(720px, calc(100vw - 48px));
  display: grid;
  gap: 8px;
}

.canvas-composer {
  position: relative;
  display: grid;
  gap: 8px;
  width: 100%;
  height: auto;
  padding: 10px 12px;
  border: 1px solid var(--panel-border);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: none;
  backdrop-filter: blur(18px);
}

.canvas-composer.is-compact {
  padding-bottom: 10px;
}

/* While a sculpt/brush tool is active the canvas must stay reachable, but the
 * keyword/diverge panel and the composer keep their interactivity (no deadlock
 * between brush strokes and keyword selection). Only passive observation
 * panels become click-through. */
.workspace-chrome.sculpting .perception-float,
.workspace-chrome.sculpting .observe-float {
  pointer-events: none;
}

.workspace-chrome.sculpting .ai-behavior-float,
.workspace-chrome.sculpting .mc-keywords-pane,
.workspace-chrome.sculpting .prompt-token {
  pointer-events: auto;
}

.canvas-composer > input {
  width: 100%;
  min-height: 38px;
  border: 0;
  border-radius: 18px;
  background: transparent;
  font-family: var(--font-hand);
  font-size: 24px;
  font-weight: 600;
  color: var(--ink);
  padding: 2px 8px;
}

.canvas-composer > input::placeholder {
  color: #b0b7c6;
}

.canvas-composer > input:focus {
  outline: none;
  background: rgba(244, 246, 250, 0.55);
}

.canvas-composer-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
}

.editor-history-actions {
  display: none;
}

.composer-tools {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
  padding: 4px 6px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(232, 240, 255, 0.9), rgba(255, 236, 246, 0.85));
}

.composer-tools::-webkit-scrollbar {
  display: none;
}

.icon-tool {
  width: 38px;
  height: 38px;
  min-height: 38px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 0;
  background: var(--accent-blue);
  color: #fff;
  padding: 0;
  box-shadow: 0 8px 16px rgba(47, 123, 255, 0.22);
}

.icon-tool span {
  display: none;
}

.icon-tool svg {
  color: #fff;
}

.icon-tool.is-active {
  outline: 2px solid #fff;
  outline-offset: 2px;
  box-shadow: 0 0 0 3px rgba(47, 123, 255, 0.35), 0 8px 16px rgba(47, 123, 255, 0.22);
}

.icon-tool.tool-pink {
  background: linear-gradient(145deg, #ff7eb6, var(--accent-pink));
  box-shadow: 0 8px 16px rgba(255, 79, 154, 0.28);
}

.icon-tool.tool-dark {
  background: #1c1f28;
  box-shadow: 0 8px 16px rgba(20, 24, 36, 0.28);
}

.icon-tool.tool-soft {
  background: linear-gradient(145deg, #ffe4f1, #ffd0e8);
  color: #a1195a;
  box-shadow: 0 6px 14px rgba(255, 79, 154, 0.16);
}

.icon-tool.tool-soft svg {
  color: #c2185b;
}

.icon-tool.tool-asset {
  width: 38px;
  height: 38px;
  min-height: 38px;
  padding: 0;
  border-radius: 50%;
  background: var(--accent-blue);
  box-shadow: 0 8px 16px rgba(47, 123, 255, 0.22);
}

.icon-tool.tool-asset img {
  display: block;
  width: 24px;
  height: 26px;
  object-fit: contain;
  pointer-events: none;
}

.icon-tool.tool-asset:disabled {
  opacity: 0.42;
}

.icon-tool.tool-asset:not(:disabled):hover {
  transform: translateY(-1px);
}

.composer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.cross-domain-button,
.composer-action {
  width: 40px;
  height: 40px;
  min-height: 40px;
  display: grid;
  place-items: center;

  border-radius: 50%;
  border: 0;
  padding: 0;
}

.cross-domain-button {
  background: #17191f;
  color: #fff;
  box-shadow: 0 8px 16px rgba(20, 24, 36, 0.25);
}

.composer-action {
  background: var(--accent-blue);
  color: #fff;
  box-shadow: 0 8px 18px rgba(47, 123, 255, 0.28);
}

.composer-action.send {
  background: linear-gradient(145deg, #4a8fff, var(--accent-blue-deep));
}

.primitive-menu {
  position: absolute;
  left: 18px;
  bottom: 78px;
  z-index: 17;
  width: 168px;
  padding: 8px;
  border-radius: 18px;
  background: rgba(36, 40, 52, 0.92);
  color: #fff;
  box-shadow: 0 18px 40px rgba(20, 24, 36, 0.35);
  backdrop-filter: blur(12px);
  display: grid;
  gap: 2px;
}

.primitive-menu button {
  justify-content: flex-start;
  gap: 10px;
  min-height: 34px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #f4f6fb;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
}

.primitive-menu button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  transform: none;
}

.primitive-menu button span.wire {
  width: 18px;
  height: 18px;
  border: 1.5px solid rgba(255, 255, 255, 0.75);
  border-radius: 4px;
  display: inline-block;
}

.primitive-menu button span.wire.sphere {
  border-radius: 50%;
}

.primitive-menu button span.wire.cylinder {
  border-radius: 6px 6px 4px 4px;
}

.primitive-menu button span.wire.cone {
  clip-path: polygon(50% 0, 100% 100%, 0 100%);
  border: 0;
  background: rgba(255, 255, 255, 0.75);
}

.composer-tray {
  display: grid;
  gap: 8px;
  border-top: 1px solid rgba(40, 50, 70, 0.08);
  padding-top: 6px;
}

.composer-tray > summary {
  list-style: none;
  cursor: pointer;
}

.composer-tray > summary::-webkit-details-marker {
  display: none;
}

.intent-composer-summary {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  min-width: 0;
  padding: 0 4px;
}

.intent-composer-summary strong,
.intent-composer-summary span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.intent-composer-summary strong {
  font-size: 12px;
  color: var(--ink);
}

.intent-composer-summary span {
  font-size: 11px;
  color: var(--ink-soft);
}

.atom-list,
.direction-list,
.draft-list {
  display: grid;
  gap: 8px;
}

.atom-list {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.behavior-dot-tray {
  gap: 8px;
}

.behavior-history-rail {
  width: 100%;
  min-height: 40px;
  padding: 6px 12px;
  border: 1px solid rgba(215, 223, 236, 0.94);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(14px);
  box-shadow: 0 8px 20px rgba(50, 65, 90, 0.07);
}

.behavior-dot-list {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  padding: 0 4px;
}

.behavior-dot {
  width: 26px;
  height: 26px;
  min-height: 26px;
  border-radius: 50%;
  padding: 0;
  border: 0;
  display: grid;
  place-items: center;
  background: var(--accent-blue);
  color: #fff;
  font-size: 11px;
  font-weight: 900;
  box-shadow: 0 6px 12px rgba(47, 123, 255, 0.18);
  cursor: pointer;
}

.behavior-dot.is-active {
  animation: behavior-pulse 1.4s ease-in-out infinite;
}

.behavior-dot.is-selected {
  outline: 2px solid #fff;
  box-shadow: 0 0 0 3px rgba(47, 123, 255, 0.45), 0 6px 12px rgba(47, 123, 255, 0.18);
}

@keyframes behavior-pulse {
  50% { transform: scale(0.88); opacity: 0.65; }
}

.behavior-history-inspector {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(205, 216, 234, 0.96);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 14px 34px rgba(40, 55, 80, 0.14);
}

.behavior-inspector-head,
.behavior-inspector-meta,
.behavior-view-pairs,
.behavior-view-pair > div {
  display: flex;
  align-items: center;
}

.behavior-inspector-head {
  justify-content: space-between;
  gap: 12px;
}

.behavior-inspector-head strong {
  font-size: 12px;
}

.behavior-inspector-head button {
  width: 24px;
  min-height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #eef2f8;
}

.behavior-inspector-meta {
  gap: 12px;
  margin-top: 5px;
  color: var(--ink-soft);
  font-size: 10px;
}

.behavior-view-pairs {
  gap: 8px;
  margin-top: 8px;
}

.behavior-view-pair {
  flex: 1;
  min-width: 0;
}

.behavior-view-pair small {
  display: block;
  margin-bottom: 3px;
  color: var(--ink-mute);
  text-transform: uppercase;
}

.behavior-view-pair > div {
  gap: 4px;
}

.behavior-view-pair img,
.behavior-view-pair span {
  width: 50%;
  height: 46px;
  border-radius: 7px;
  object-fit: cover;
  background: #eef2f7;
}

.behavior-view-pair span {
  display: grid;
  place-items: center;
  padding: 3px;
  color: var(--ink-mute);
  font-size: 8px;
  text-align: center;
}

.behavior-dot.annotation,
.behavior-dot.text {
  background: var(--accent-pink);
}

.behavior-dot.drag,
.behavior-dot.smooth,
.behavior-dot.add {
  background: #111827;
}

.atom-chip,
.draft-chip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  min-width: 0;
  border: 1px solid rgba(220, 226, 236, 0.95);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  padding: 8px;
}

.atom-chip strong,
.draft-chip strong {
  display: block;
  color: var(--ink);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.atom-chip span,
.draft-chip span {
  display: block;
  color: var(--ink-soft);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.atom-actions,
.draft-actions {
  display: flex;
  gap: 3px;
}

.atom-actions button,
.draft-actions button {
  min-height: 22px;
  width: auto;
  padding: 0 7px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
}

.draft-chip.active {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 1px rgba(42, 212, 232, 0.25);
}

.draft-list {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.creative-space-button {
  justify-self: start;
  min-height: 32px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-blue-deep);
  background: #eef4ff;
  border-color: #c9dbff;
}

/* Clarification bubbles */

.planner-clarification-overlay {
  position: absolute;
  inset: 90px 320px 220px 40px;
  z-index: 18;
  pointer-events: none;
}

.planner-bubble {
  position: absolute;
  min-width: 148px;
  max-width: 220px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 8px;
  align-items: center;
  border: 0;
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(255, 214, 236, 0.95), rgba(214, 232, 255, 0.95));
  box-shadow: none;
  padding: 10px 12px;
  backdrop-filter: blur(12px);
  pointer-events: auto;
}

.planner-bubble.is-selectable {
  cursor: pointer;
}

.planner-bubble.is-active-revision {
  box-shadow: 0 0 0 3px rgba(75, 137, 255, 0.24), 0 16px 34px rgba(55, 70, 110, 0.18);
}

.planner-bubble::after {
  content: "";
  position: absolute;
  width: 34px;
  border-top: 1.5px dashed rgba(90, 110, 150, 0.45);
}

.planner-bubble.top {
  left: 50%;
  top: 6%;
  transform: translateX(-50%);
}

.planner-bubble.top::after {
  left: 50%;
  top: 100%;
  transform: rotate(90deg);
  transform-origin: left top;
}

.planner-bubble.left {
  left: 8%;
  top: 34%;
}

.planner-bubble.left::after {
  left: 100%;
  top: 50%;
}

.planner-bubble.right {
  right: 8%;
  top: 38%;
}

.planner-bubble.right::after {
  right: 100%;
  top: 50%;
}

/* Multiple immutable intent revisions occupy stable slots around the subject. */
.multi-gate .revision-slot-0 { right: 7%; top: 28%; }
.multi-gate .revision-slot-1 { left: 7%; top: 52%; }
.multi-gate .revision-slot-2 { left: 50%; top: 30%; }
.multi-gate .revision-slot-3 { right: 11%; top: 64%; }
.multi-gate .revision-slot-4 { left: 10%; top: 16%; }
.multi-gate .revision-slot-5 { left: 50%; top: 76%; transform: translateX(-50%); }

.planner-bubble span {
  grid-column: 1 / -1;
  color: #1e3a6e;
  font-size: 13px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.planner-bubble strong {
  color: #3a4558;
  font-size: 11px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.planner-bubble-actions {
  display: flex;
  gap: 4px;
}

.planner-bubble-actions button {
  width: 24px;
  height: 24px;
  min-height: 24px;
  border-radius: 50%;
  padding: 0;
  display: grid;
  place-items: center;
  border: 0;
}

.planner-bubble-actions .accept {
  background: #34d399;
  color: #fff;
}

.planner-bubble-actions .reject {
  background: #ff6b6b;
  color: #fff;
}

.planner-bubble-status {
  left: 50%;
  top: 10%;
  transform: translateX(-50%);
  grid-template-columns: minmax(0, 1fr);
  background: rgba(232, 255, 245, 0.95);
}

.planner-clarification-overlay.rejected .planner-bubble-status {
  background: rgba(255, 236, 236, 0.95);
}

/* Intent beads */

.intent-bead-overlay {
  position: absolute;
  right: 360px;
  top: 360px;
  z-index: 19;
  width: min(220px, calc(100% - 380px));
  pointer-events: none;
}

.intent-bead-chain {
  display: grid;
  gap: 8px;
}

.intent-bead {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 24px;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--panel-border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: none;
  padding: 5px 6px 5px 5px;
  backdrop-filter: blur(10px);
  pointer-events: auto;
}

.intent-bead::before {
  content: "";
  position: absolute;
  right: 100%;
  top: 50%;
  width: 28px;
  border-top: 1.5px dashed rgba(90, 110, 150, 0.35);
}

.intent-bead.active {
  border-color: var(--accent-cyan);
}

.intent-bead.sent {
  background: rgba(236, 253, 245, 0.92);
}

.intent-bead-main {
  min-width: 0;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 2px 7px;
  align-items: center;
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
}

.intent-bead-main span {
  grid-row: 1 / 3;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent-blue);
  color: #fff;
  font-size: 10px;
  font-weight: 900;
}

.intent-bead-main strong,
.intent-bead-main em {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.intent-bead-main strong {
  color: var(--ink);
  font-size: 11px;
}

.intent-bead-main em {
  color: var(--ink-soft);
  font-size: 9px;
  font-style: normal;
}

.intent-bead-archive {
  width: 22px;
  height: 22px;
  min-height: 22px;
  border-radius: 50%;
  padding: 0;
  color: var(--ink-mute);
  background: #fff;
}

/* Annotation */

.annotation-canvas-overlay {
  position: absolute;
  inset: 0;
  z-index: 7;
  cursor: crosshair;
  background: rgba(255, 255, 255, 0.02);
}

.annotation-hint {
  position: absolute;
  left: 18px;
  top: 16px;
  z-index: 2;
  display: grid;
  gap: 2px;
  padding: 8px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--panel-border);
}

.annotation-hint strong {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.annotation-hint span {
  color: var(--ink-soft);
  font-size: 11px;
}

.annotation-actions {
  position: absolute;
  right: 18px;
  top: 16px;
  z-index: 2;
  display: flex;
  gap: 6px;
}

.annotation-actions button {
  min-height: 30px;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
}

.annotation-actions button.primary {
  color: #fff;
  background: #111827;
}

.annotation-actions button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.annotation-stroke {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  fill: none;
  stroke: #050505;
  stroke-width: 0.55;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.annotation-canvas-overlay.is-completed {
  cursor: default;
  background: rgba(8, 12, 22, 0.45);
  display: grid;
  place-items: center;
}

.annotation-brush-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 1;
  pointer-events: none;
}

.annotation-brush-palette {
  position: absolute;
  left: 18px;
  bottom: 18px;
  z-index: 3;
  display: flex;
  gap: 6px;
  padding: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--panel-border);
}

.annotation-brush-palette button {
  min-height: 26px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  font-size: 11px;
  color: var(--ink-soft);
  cursor: pointer;
}

.annotation-brush-palette button.is-active {
  background: #111827;
  color: #fff;
}

.annotation-done-card {
  width: min(320px, 78%);
  padding: 18px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--panel-border);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.45);
  text-align: center;
}

.annotation-done-card img {
  width: 100%;
  border-radius: 10px;
  border: 1px solid rgba(17, 24, 39, 0.15);
  display: block;
}

.annotation-done-title {
  margin-top: 12px;
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.annotation-done-text {
  margin: 8px 0 14px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-soft);
}

.annotation-done-card .annotation-actions {
  position: static;
  justify-content: center;
}

/* Shared panels / forms */

.panel {
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.9);
  padding: 12px;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  color: var(--ink-soft);
}

.panel-title h2 {
  font-size: 13px;
  margin: 0;
}

label {
  display: grid;
  gap: 6px;
  color: var(--ink-soft);
  font-size: 12px;
  margin-bottom: 10px;
}

textarea,
input,
select {
  width: 100%;
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.95);
  color: var(--ink);
  padding: 9px 10px;
  outline: none;
}

textarea {
  min-height: 86px;
  resize: vertical;
}

textarea:focus,
input:focus,
select:focus {
  border-color: var(--accent-blue);
  background: #fff;
}

button:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
[tabindex]:focus-visible,
.canvas-composer > input:focus-visible {
  outline: 2px solid var(--accent-blue-deep);
  outline-offset: 2px;
}

.upload-row {
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
}

.upload-row input[type="file"] {
  display: none;
}

.reference-image-strip,
.reference-model-strip {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  margin-bottom: 10px;
}

.reference-image-chip,
.reference-model-chip {
  flex: 0 0 auto;
  display: grid;
  gap: 4px;
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 6px;
  background: #fff;
  font-size: 10px;
  color: var(--ink-soft);
}

.reference-image-chip img {
  width: 72px;
  height: 52px;
  object-fit: cover;
  border-radius: 8px;
}

.primitive-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.key-value {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 10px;
  align-items: start;
  padding: 8px 0;
  border-bottom: 1px solid #edf1f6;
}

.key-value:last-child {
  border-bottom: 0;
}

.key-value span {
  color: var(--ink-mute);
  font-size: 12px;
}

.key-value strong {
  font-size: 12px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.empty {
  color: var(--ink-soft);
  font-size: 12px;
  line-height: 1.4;
  padding: 8px 0;
}

.export-note {
  margin: 0 0 8px;
  color: var(--ink-soft);
  font-size: 12px;
}

.case-link-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.case-link-row a {
  color: var(--accent-blue-deep);
  font-size: 12px;
  font-weight: 700;
}

.status-pill {
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  background: #fff;
  padding: 7px 9px;
  min-width: 86px;

}

.status-pill span {
  display: block;
  color: var(--ink-mute);
  font-size: 11px;
}

.status-pill strong {
  display: block;
  color: var(--ink);
  font-size: 12px;
  margin-top: 1px;
  overflow-wrap: anywhere;
}

/* Perception / AI behavior content */

.perception-card {
  display: grid;
  gap: 8px;
}

.perception-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.perception-head span {
  font-weight: 700;
  font-size: 13px;
}

.perception-head strong {
  color: var(--accent-blue-deep);
  font-size: 12px;
}

.planner-gate {
  display: flex;
  gap: 6px;
}

.planner-accept {
  background: #e6fcf5;
  border-color: #96f2d7;
  color: #087f5b;
}

.planner-reject {
  background: #fff5f5;
  border-color: #ffc9c9;
  color: #c92a2a;
}

.planner-gate-status {
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 700;
}

.planner-gate-status.accepted {
  background: #e6fcf5;
  color: #087f5b;
}

.planner-gate-status.rejected {
  background: #fff5f5;
  color: #c92a2a;
}

.evidence-drawer {
  margin-top: 8px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.9);
  padding: 8px 10px;
  font-size: 12px;
  color: var(--ink-soft);
}

.evidence-drawer summary {
  cursor: pointer;
  font-weight: 700;
  color: var(--ink);
}

.evidence-summary-grid {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.evidence-summary-item {
  display: grid;
  gap: 2px;
}

.evidence-summary-item span {
  color: var(--ink-mute);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.evidence-summary-item strong {
  font-size: 12px;
}

.evidence-summary-item em {
  font-style: normal;
  color: var(--ink-soft);
  font-size: 10px;
}

.ir-evidence-list {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.ir-evidence-card {
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.85);
}

.ir-evidence-card strong {
  font-size: 12px;
}

.ir-evidence-card span,
.ir-evidence-card p {
  margin: 4px 0 0;
  color: var(--ink-soft);
  font-size: 11px;
}

.ir-case-source {
  color: var(--ink-mute) !important;
}

.ir-axis-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.ir-axis-row span {
  border-radius: 999px;
  background: #eef4ff;
  color: var(--accent-blue-deep);
  padding: 3px 7px;
  font-size: 10px;
  font-weight: 700;
}

.ai-behavior-thread {
  display: grid;
  gap: 8px;
}

.chat-message {
  border-radius: 14px;
  background: rgba(246, 248, 252, 0.95);
  padding: 10px;
}

.chat-message span {
  display: block;
  color: var(--ink-mute);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 4px;
}

.chat-message p {
  margin: 0;
  font-size: 13px;
  line-height: 1.4;
}

.chat-message.planner {
  background: linear-gradient(180deg, #f7faff, #fbfcfe);
}

.ai-chat-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 34px;
  gap: 6px;
}

.ai-chat-form input {
  min-height: 34px;
  font-size: 12px;
}

.ai-chat-form button {
  min-height: 34px;
  border-radius: 999px;
  padding: 0;
  display: grid;
  place-items: center;
}

.live-signal-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.live-signal-card {
  min-width: 0;
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  background: #fff;
  padding: 7px 8px;
}

.live-signal-card span {
  display: block;
  color: var(--ink-mute);
  font-size: 10px;
  font-weight: 800;
}

.live-signal-card strong {
  display: block;
  margin-top: 3px;
  color: var(--ink);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.ir-query-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.ir-query-row span {
  border-radius: 999px;
  background: #f1f5f9;
  color: var(--ink-soft);
  padding: 3px 7px;
  font-size: 10px;
  font-weight: 700;
}

.job-progress {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
}

.job-progress strong {
  font-size: 12px;
}

.job-progress span {
  color: var(--ink-soft);
  font-size: 11px;
}

.job-progress progress {
  width: 100%;
  height: 8px;
}

.candidate-list {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}

.candidate {
  border: 1px solid var(--panel-border);
  border-radius: 14px;
  background: #fff;
  padding: 10px;
}

.candidate-preview {
  width: 100%;
  height: 96px;
  object-fit: cover;
  border-radius: 10px;
  margin-bottom: 8px;
  background: #eef1f6;
}

.candidate-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.candidate-actions button {
  min-height: 28px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.dimension-direction-list {
  display: grid;
  gap: 10px;
  margin-top: 8px;
}

.dimension-panel {
  border: 1px solid var(--panel-border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.88);
  padding: 10px;
}

.dimension-panel.aesthetic {
  border-color: #f3c4e7;
  background: linear-gradient(180deg, #fff8fd, #ffffff);
}

.dimension-panel.functional {
  border-color: #bfe2cf;
  background: linear-gradient(180deg, #f7fff9, #ffffff);
}

.dimension-panel.structural {
  border-color: #bfd4ff;
  background: linear-gradient(180deg, #f7faff, #ffffff);
}

.dimension-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.dimension-panel-head strong {
  color: var(--ink);
  font-size: 12px;
}

.dimension-panel-head span {
  border: 1px solid var(--panel-border);
  border-radius: 999px;
  background: #fff;
  color: var(--ink-soft);
  padding: 3px 7px;
  font-size: 9px;
  font-weight: 800;
}

.dimension-panel > p {
  margin: 6px 0 0;
  color: var(--ink-soft);
  font-size: 10px;
  line-height: 1.35;
}

.prompt-token-hint {
  margin: 0 0 8px;
  color: var(--ink-soft);
  font-size: 11px;
  line-height: 1.35;
}

.semantic-keyword-skeleton > div {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.semantic-keyword-skeleton i {
  display: block;
  height: 34px;
  border-radius: 999px;
  background: linear-gradient(90deg, #eef1f7 25%, #f8f9fc 50%, #eef1f7 75%);
  background-size: 200% 100%;
  animation: semantic-keyword-loading 1.2s ease-in-out infinite;
}

@keyframes semantic-keyword-loading {
  to { background-position: -200% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .semantic-keyword-skeleton i { animation: none; }
}

.planner-context-pill {
  width: fit-content;
  max-width: 100%;
  margin: 0 0 8px;
  border-radius: 999px;
  padding: 5px 8px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.2;
}

.planner-context-pill.confirmed {
  background: #e6fcf5;
  color: #087f5b;
}

.planner-context-pill.rejected {
  background: #fff0f0;
  color: #c92a2a;
}

.planner-context-pill.unconfirmed {
  background: #f1f5f9;
  color: #52657a;
}

.prompt-token-board {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.prompt-token-board.grouped {
  margin-top: 7px;
}

.prompt-token {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 6px 10px;
  border: 1px solid var(--panel-border);
  border-radius: 999px;
  background: #fff;
  color: var(--ink);
  box-shadow: 0 4px 10px rgba(40, 60, 100, 0.05);
}

.prompt-token:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  transform: translateY(-1px);
}

.prompt-token.selected {
  border-color: var(--accent-blue);
  background: linear-gradient(135deg, #e8f2ff, #e8fbff);
  color: #0a3977;
}

.prompt-token span {
  font-size: 11px;
  font-weight: 700;
}

.prompt-token small {
  color: var(--ink-mute);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.direction-chip {
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  background: #fff;
  padding: 9px;
}

.direction-chip div {
  display: grid;
  gap: 2px;
}

.direction-chip strong {
  color: var(--ink);
  font-size: 12px;
}

.direction-chip span,
.direction-chip p {
  color: var(--ink-soft);
  font-size: 11px;
  line-height: 1.35;
  margin: 0;
}

.direction-chip p {
  margin-top: 6px;
}

.direction-list.compact {
  gap: 6px;
  margin-top: 8px;
}

.runtime-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.runtime-chip-row span {
  border-radius: 999px;
  background: #f1f5f9;
  color: var(--ink-soft);
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 700;
}

.service-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.service-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.service-item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  padding: 4px 6px;
  border-radius: 8px;
  background: #f8fafc;
}

.service-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: 0 0 auto;
  background: #94a3b8;
}

.service-item.state-up .service-dot {
  background: #22c55e;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.18);
}

.service-item.state-down .service-dot {
  background: #ef4444;
}

.service-item.state-starting .service-dot {
  background: #f59e0b;
  animation: pulse-dot 1s ease-in-out infinite;
}

@keyframes pulse-dot {
  50% {
    opacity: 0.35;
  }
}

.service-name {
  display: flex;
  flex-direction: column;
  min-width: 0;
  color: var(--ink);
  font-weight: 650;
}

.service-name em {
  font-style: normal;
  color: var(--ink-soft);
  font-size: 10px;
  font-weight: 500;
}

.service-start {
  margin-left: auto;
  flex: 0 0 auto;
}

.service-starting {
  margin-left: auto;
  color: #b45309;
  font-size: 10px;
  font-weight: 700;
}

.service-note {
  margin: 8px 0 0;
  font-size: 10px;
  color: var(--ink-soft);
  line-height: 1.45;
}

@media (max-width: 1180px) {
  .ai-behavior-float {
    width: min(260px, 32vw);
  }

  .solution-space-rail {
    width: min(560px, calc(100% - 300px));
  }

  .intent-bead-overlay {
    right: 280px;
  }

  .planner-clarification-overlay {
    inset: 90px 280px 220px 24px;
  }
}

@media (max-width: 900px) {
  .ai-behavior-float {
    display: block;
    top: 18px;
    right: 12px;
    max-height: 44px;
    max-width: calc(100vw - 40px);
  }

  .ai-behavior-float:not(.is-mobile-open) {
    width: 160px !important;
    height: 44px !important;
    padding: 8px 10px;
  }

  .ai-behavior-float:not(.is-mobile-open) .resizable-shell-body {
    overflow: hidden;
    scrollbar-gutter: auto;
  }

  .ai-behavior-float:not(.is-mobile-open) .resizable-shell-body > :not(.float-panel-label),
  .ai-behavior-float:not(.is-mobile-open) .resize-handle {
    display: none;
  }

  .ai-behavior-float.is-mobile-open {
    width: min(300px, calc(100vw - 24px)) !important;
    height: min(46vh, 420px) !important;
    max-height: min(46vh, 420px);
    top: 72px;
    right: 12px;
    z-index: 22;
  }

  .ai-behavior-float .mobile-panel-toggle {
    display: inline-flex;
    width: auto;
    min-height: 26px;
    padding: 3px 8px;
    border: 0;
    border-radius: 999px;
    background: rgba(47, 123, 255, 0.1);
    color: var(--accent-blue-deep);
    font-size: 10px;
    font-weight: 800;
  }

  .ai-behavior-float .status-dots {
    display: none;
  }

  .perception-float,
  .float-panel.observe-float {
    width: min(240px, calc(100vw - 40px));
    max-width: calc(100vw - 40px);
  }

  .solution-space-rail {
    width: calc(100% - 40px);
    top: 64px;
  }

  .intent-bead-overlay {
    display: block;
    width: min(220px, calc(100vw - 24px));
    right: 12px;
    top: auto;
    bottom: 176px;
  }

  .planner-clarification-overlay {
    inset: 120px 20px 200px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}

.sculpt-float-panel {
  position: absolute;
  left: 18px;
  bottom: 118px;
  z-index: 60;
  width: 350px;
  padding: 10px 12px;
  background: rgba(18, 24, 36, 0.94);
  border: 1px solid rgba(120, 140, 180, 0.28);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(6px);
}

.sculpt-float-panel .float-panel-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.sculpt-exit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: 1px solid rgba(200, 90, 90, 0.45);
  background: rgba(180, 60, 60, 0.16);
  color: #f0a5a5;
  cursor: pointer;
}

.sculpt-sliders {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-bottom: 9px;
}

.sculpt-sliders label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #b8c6e0;
  white-space: nowrap;
}

.sculpt-sliders input[type="range"] {
  flex: 1;
  accent-color: #3b82f6;
}

.sculpt-sliders span {
  min-width: 32px;
  text-align: right;
  color: #e6edff;
  font-variant-numeric: tabular-nums;
}

.sculpt-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.sculpt-save {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid rgba(90, 160, 255, 0.5);
  background: #1e3a5f;
  color: #dbeafe;
  font-size: 12px;
  cursor: pointer;
}

.sculpt-actions em {
  font-style: normal;
  font-size: 11px;
  color: #7f93b8;
}

.sculpt-state-line {
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px solid rgba(120, 140, 180, 0.18);
  font-size: 11px;
  color: #8fa3c4;
}

.sculptgl-modal {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  flex-direction: column;
  background: rgba(8, 12, 20, 0.94);
}

.sculptgl-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #141a26;
  color: #e6edff;
  border-bottom: 1px solid rgba(120, 140, 180, 0.25);
}

.sculptgl-modal-head strong {
  font-size: 13px;
  font-weight: 600;
}

.sculptgl-modal-actions {
  display: flex;
  gap: 10px;
}

.sculptgl-modal-actions button {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid rgba(120, 140, 180, 0.35);
  background: #1e2736;
  color: #dfe8ff;
  font-size: 12px;
  cursor: pointer;
}

.sculptgl-modal-actions .sculptgl-done {
  background: #2563eb;
  border-color: #3b82f6;
}

.sculptgl-modal-actions button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.sculptgl-frame {
  flex: 1;
  width: 100%;
  border: 0;
}

.project-notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin: 8px 10px 0;
  padding: 7px 10px;
  border-radius: 6px;
  background: rgba(180, 140, 60, 0.14);
  border: 1px solid rgba(210, 170, 90, 0.35);
  color: #e7cf9a;
  font-size: 12px;
}

.project-notice button {
  border: 0;
  background: rgba(210, 170, 90, 0.22);
  color: #f3e3bd;
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}
/* Experiment files reuse the existing soft panels and blue/pink decision language. */
.project-section {
  margin: 10px 10px 12px;
  padding: 15px;
  border: 1px solid var(--panel-border, rgba(25, 35, 50, 0.12));
  border-radius: 20px;
  background: linear-gradient(145deg, rgba(255,255,255,.96), rgba(242,247,250,.92));
  box-shadow: 0 10px 28px rgba(25, 42, 55, .07);
}
.project-section.tone-recording { border-color: rgba(77, 191, 211, .42); }
.project-section-kicker, .project-dialog header span, .project-timeline header span {
  color: #8b9299; font-size: 10px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase;
}
.project-section-title-row strong { display: block; margin: 5px 0 4px; font-size: 15px; color: #27333c; }
.project-recording-status { display: flex; align-items: center; gap: 6px; color: #6e7880; font-size: 11px; }
.project-recording-status i { width: 7px; height: 7px; border-radius: 50%; background: #b8bec3; }
.tone-recording .project-recording-status i { background: #65cede; box-shadow: 0 0 0 4px rgba(101,206,222,.14); }
.tone-warning .project-recording-status i { background: #f067ad; }
.project-recording-error { margin: 8px 0 0; color: #b23c75; font-size: 11px; }
.project-section-actions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
.project-section-actions button { min-height: 32px; }
.project-primary, .project-submit {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  border: 0; border-radius: 11px; color: #16323a; font-weight: 750;
  background: linear-gradient(105deg, #9ee5ef, #f3a5df); box-shadow: 0 5px 15px rgba(71,181,204,.16);
}
.project-dialog-backdrop { position: fixed; inset: 0; z-index: 1300; display: grid; place-items: center; padding: 24px; background: rgba(31,39,45,.22); backdrop-filter: blur(7px); }
.project-dialog { width: min(760px, 94vw); max-height: min(720px, 90vh); overflow: auto; border: 1px solid rgba(28,40,48,.14); border-radius: 26px; background: rgba(249,250,249,.98); box-shadow: 0 30px 90px rgba(31,45,55,.2); }
.project-dialog header, .project-timeline header { display: flex; align-items: flex-start; justify-content: space-between; padding: 20px 22px 16px; border-bottom: 1px solid rgba(25,35,42,.08); }
.project-dialog h2, .project-timeline h2 { margin: 4px 0 0; color: #27333c; font-size: 19px; }
.icon-button { display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border-radius: 50%; }
.project-dialog-grid { display: grid; grid-template-columns: 1.08fr .92fr; gap: 18px; padding: 20px 22px 24px; }
.project-dialog form { display: grid; gap: 13px; }
.project-dialog label { display: grid; gap: 6px; color: #5f6970; font-size: 11px; font-weight: 700; }
.project-dialog input:not([type=radio]) { min-width: 0; border-radius: 11px; background: white; }
.project-field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.project-dialog fieldset { display: grid; gap: 8px; margin: 0; padding: 0; border: 0; }
.project-dialog legend { margin-bottom: 7px; color: #5f6970; font-size: 11px; font-weight: 700; }
.baseline-option { grid-template-columns: 18px 1fr !important; align-items: start; padding: 11px; border: 1px solid rgba(27,42,52,.11); border-radius: 13px; background: white; cursor: pointer; }
.baseline-option input { margin-top: 3px; accent-color: #63c8db; }
.baseline-option span { display: grid; gap: 3px; }
.baseline-option strong { color: #2f3c45; font-size: 12px; }
.baseline-option em { color: #828a90; font-size: 10px; font-style: normal; line-height: 1.45; }
.project-submit { min-height: 40px; margin-top: 2px; }
.project-open-list { border-left: 1px solid rgba(25,35,42,.08); padding-left: 18px; }
.project-open-list h3 { margin: 0 0 10px; color: #4c5961; font-size: 12px; }
.project-open-list > button { display: grid; width: 100%; gap: 4px; margin-bottom: 8px; padding: 11px 12px; text-align: left; border-radius: 13px; background: white; }
.project-open-list > button strong { color: #35424b; font-size: 12px; }
.project-open-list > button span, .project-open-list > p { color: #8a9297; font-size: 10px; }
.project-timeline { position: fixed; z-index: 1250; top: 18px; bottom: 18px; left: 18px; width: min(390px, calc(100vw - 36px)); display: flex; flex-direction: column; border: 1px solid rgba(28,40,48,.13); border-radius: 24px; background: rgba(249,250,249,.98); box-shadow: 0 24px 70px rgba(31,45,55,.18); overflow: hidden; }
.project-timeline-actions { display: flex; gap: 8px; padding: 12px 18px; border-bottom: 1px solid rgba(25,35,42,.08); }
.project-timeline ol { flex: 1; overflow: auto; list-style: none; margin: 0; padding: 8px 18px 22px; }
.project-timeline li { content-visibility: auto; contain-intrinsic-size: 54px; display: grid; grid-template-columns: 10px 1fr auto; gap: 10px; align-items: start; padding: 11px 0; border-bottom: 1px solid rgba(25,35,42,.07); }
.project-timeline li > i { width: 7px; height: 7px; margin-top: 4px; border-radius: 50%; background: linear-gradient(135deg,#78d7e5,#ef8fd1); }
.project-timeline li div { display: grid; gap: 3px; min-width: 0; }
.project-timeline li strong { overflow: hidden; color: #34414a; font-size: 11px; text-overflow: ellipsis; }
.project-timeline li span, .project-timeline li em { color: #92999e; font-size: 9px; font-style: normal; }
.behavior-brief { display: grid; gap: 7px; margin: 10px 12px; padding: 15px; border: 1px solid rgba(31,44,53,.09); border-radius: 17px; background: rgba(255,255,255,.82); }
.behavior-brief-label { color: #93999e; font-size: 9px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.behavior-brief p { margin: 0 0 3px; color: #28363f; font-size: 15px; font-weight: 650; line-height: 1.45; }
.behavior-brief strong { color: #28363f; font-size: 13px; line-height: 1.42; }
.behavior-brief em { color: #768187; font-size: 9px; font-style: normal; }
.behavior-details { margin: 0 14px 11px; color: #737d84; font-size: 10px; }
.behavior-details summary { cursor: pointer; color: #68757c; font-weight: 750; }
.behavior-details p { margin: 7px 0; line-height: 1.5; }
.behavior-details code { color: #92999e; font-size: 8px; }
.mc-keywords-pane.is-locked { opacity: .55; filter: saturate(.55); }
.mc-keywords-pane.is-locked::before { content: "先确认当前改动范围"; display: block; margin: 0 0 8px; color: #737f86; font-size: 10px; }
@media (max-width: 620px) {
  .project-dialog-grid { grid-template-columns: 1fr; }
  .project-open-list { border-left: 0; border-top: 1px solid rgba(25,35,42,.08); padding: 16px 0 0; }
  .project-field-row { grid-template-columns: 1fr; }
}

```

## Raw frontend package/config

```text
{
  "name": "flowstudio-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "vite build --config vite.verify.config.ts",
    "preview": "vite preview --host 127.0.0.1 --port 4173"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "lucide-react": "^0.468.0",
    "onnxruntime-web": "^1.20.1",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "three": "^0.179.0",
    "typescript": "^5.7.0",
    "vite": "^7.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.4",
    "@types/three": "^0.185.3"
  }
}
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react": ["react", "react-dom"],
          "vendor-three": [
            "three",
            "three/examples/jsm/loaders/GLTFLoader.js",
            "three/examples/jsm/loaders/MTLLoader.js",
            "three/examples/jsm/loaders/OBJLoader.js",
            "three/examples/jsm/loaders/PLYLoader.js",
            "three/examples/jsm/controls/OrbitControls.js",
          ],
        },
      },
    },
  },
  server: {
    proxy: Object.fromEntries(
      ["/api", "/health", "/files", "/ws"].map((path) => [path, { target, ws: path === "/ws" }]),
    ),
  },
});

```

