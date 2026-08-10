# FlowStudio Divergence Controls and Version Meta Design

Date: 2026-08-10

## Goal

Make post-Gate divergence visibly reliable, return a useful and balanced set of design keywords, and reduce the active version label to the minimum information needed on the canvas.

## Approved interaction design

### Stable keyword selection

- Keyword clicks update the visible selection immediately.
- Background run polling must not replace an optimistic selection while its persistence request is pending.
- Successful persistence promotes the server response to the new authoritative selection.
- Failed persistence keeps the visible selection, exposes a compact save error, and disables Generate until the user retries a selection change successfully.
- Multiple rapid clicks are serialized per intent revision; only the latest selection may update the visible authoritative state.

### Content amount

- Replace the visible `评分严谨度` control with `内容数量`.
- The control represents candidates per semantic dimension, not a total count.
- Range: 5–8 per dimension. Default: 5 per dimension.
- Keep divergence temperature visible.
- Keep strictness as an internal fixed value of `0.6`; it is no longer user-facing.
- Every completed response must contain the requested quota in all four canonical dimensions: `shape`, `connection`, `surface`, and `semantic_transfer`.
- The default completed response therefore contains 20 candidates. A response missing any group quota is incomplete and must enter the existing repair path instead of being shown as completed.

## Backend contract

- Add an explicit per-group quantity to semantic-divergence parameters and derive the total candidate count as `per_group_count * 4`.
- Remove the external model client's hard-coded count of 9.
- The request schema and prompt must require exact quotas for all four groups.
- Validation must reject an underfilled group and include the shortage in repair feedback.
- Persist the selected content amount with the active revision's divergence parameters so reruns and recovery use the same value.
- Keep legacy strictness fields accepted for compatibility, but local runtime always sends the fixed value `0.6` from this UI.

## Frontend data flow

1. Gate acceptance starts divergence with temperature, fixed strictness, and per-group count.
2. AI Behavior stays in its loading state until a quota-complete response hydrates.
3. Changing temperature or content amount reruns divergence for the active accepted revision.
4. Keyword selection updates an optimistic per-revision snapshot and queues persistence.
5. Four-stage polling hydrates selections only when that revision has no pending local selection transaction.
6. Generate waits for the latest selection transaction and remains disabled on persistence failure.

## Visual design

### AI Behavior

- Keep the existing translucent grey panel, rounded group cards, blue/cyan selected chips, and compact Manrope hierarchy.
- Show `发散温度` and `内容数量` as two compact parameter rows.
- Display the content amount as `5 / 维` through `8 / 维` so the meaning cannot be confused with the total.
- Retain four vertical semantic sections; each section shows at least five chips at the default setting.

### Active version metadata

- Replace the dark overlay with a compact translucent white capsule using the existing panel border and blur treatment.
- Content order: blue-tinted `V1` badge, normalized object name `Snowman`, icon-only version-tree action.
- Remove `可编辑 3D` and the visible `全部版本` text.
- Keep `aria-label="查看全部版本"` and a visible keyboard focus ring on the icon action.
- Normalize display labels by keeping only the final non-empty segment after `·`; `Christmas · Snowman` displays as `Snowman`.

Chosen visual direction: [FlowStudio AI Behavior & Canvas Updates](https://p.superdesign.dev/draft/4427397b-68b1-4fa0-9090-216de037c063).

## Error handling

- Model timeout or quota failure ends loading with a retryable divergence error; it must not show a partial group set as final.
- Selection persistence failure never silently removes a selected chip.
- Stale responses from earlier parameter values or earlier click sequences cannot overwrite the active revision.

## Verification

- Unit tests for quota derivation, group-quota validation, label normalization, and optimistic selection reconciliation.
- API/service tests proving the external model payload requests 20 candidates by default and five candidates in each group.
- Frontend contract tests proving `评分严谨度` is absent, `内容数量` is present, the visible version metadata is `V1` + `Snowman` + icon, and status copy is absent.
- Browser test with rapid multi-chip clicks while polling is active; every clicked chip remains selected after persistence settles.
- Browser test of a default divergence response showing at least five visible chips in each of the four groups.
- TypeScript check, frontend production build, focused backend tests, and diff whitespace check.

## Out of scope

- Hunyuan3D and other 3D generation paths.
- GPU deployment or remote source changes.
- Redesign of Solution Space, Perception, or the overall workspace layout.
