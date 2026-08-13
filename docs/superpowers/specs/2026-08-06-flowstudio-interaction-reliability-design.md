# FlowStudio Interaction Reliability Design

## Goal

Make the August 5 interaction flow behave as defined: observation remains live, Send immediately locks an immutable intent revision, each revision produces one concise scope Gate, multiple Gates can coexist, and accepted revisions expose keyword-driven 6–8-solution generation without blocking the editor.

## Decisions

- Explicit local targets such as 帽子/围巾 override whole-object words that occur inside preservation or negation clauses.
- “保持整体身份”“不改变轮廓” are hard preservation constraints, not requested change scopes.
- Send creates an optimistic local revision immediately. The bubble says that scope is being inferred until the server revision arrives, then the same slot is replaced.
- Loading a benchmark asset makes its geometry interactive as soon as the asset record and mesh are available. Semantic part discovery stays asynchronous.
- MobileSAM/ONNX is imported only when local segmentation is first requested.
- Floating panels remain pointer-draggable and scrollable, while resize controls and icon actions also expose keyboard and accessible names.

## Error handling

- Failed revision creation removes the optimistic revision and retains/restores the submitted text with an inline error notice.
- Part discovery failure does not remove or disable the loaded model.
- Local segmentation failure continues to the existing backend segmentation fallback.

## Acceptance

- “只改变帽子，保持整体身份不变” yields a part Gate for 帽子.
- “只改围巾，不改变身体轮廓” yields a part Gate for 围巾.
- A Gate placeholder appears immediately after Send and two rapid Sends occupy two stable slots.
- Snowman geometry becomes usable without waiting for part discovery.
- Initial production bundle no longer contains ONNX runtime/WASM as an eager entry dependency.
- The AI panel can move, scroll, resize by pointer and resize by keyboard; icon-only buttons and the intent input have accessible names and visible keyboard focus.

