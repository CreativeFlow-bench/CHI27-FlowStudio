# FlowStudio IR Runtime Usage Spec v1

日期：2026-08-02  
目标：定义 FlowStudio 如何把清洗后的 Design-State IR 用在实时交互推理中，使系统能少打扰地理解用户当前创意状态，并把推理结果转化为 Intent Bubble、More Creative 发散维度和生成提示词。

关联文档：

- `FLOWSTUDIO_INTERACTION_FLOW_SPEC_V1_ZH.md`
- `FLOWSTUDIO_PROTOTYPE_FRONTEND_BACKEND_DEV_SPEC_V1_ZH.md`
- `FLOWSTUDIO_BACKEND_CONVERGENCE_STRATEGY_V1_ZH.md`
- `intentdatabase/cleaned/README.md`

---

## 1. 核心立场

IR 不应该被当成一个硬分类器。

它不是要直接判断“用户真实想法是什么”，而是作为一个带不确定性的 weighted prior，帮助系统回答三个问题：

```text
现在是否应该介入？
如果介入，应该问 contour / part / material 哪一类范围问题？
如果用户开始表达意图，More Creative 应该优先展示哪些发散维度？
```

因此 IR 的系统角色是：

```text
low-level interaction signals
→ IR weighted prior
→ lightweight scope question / divergence ranking
→ user remains in control
```

系统不能因为 IR 命中某个历史 case，就直接替用户生成、替用户确认意图，或在 Perception 中输出推理结论。

---

## 2. IR 数据状态

当前清洗后的 IR 来自 5 位 coder 的标注，但不是所有 case 都由 5 人完整重叠标注。

当前数据规模：

```text
raw annotation rows: 470
unique cases after merge: 207
duplicate case groups merged: 106
cases with ≥2 coders: 43
cases with all 5 coders: 16
```

重叠标注一致性：

```text
design-state pairwise agreement: 0.578
route pairwise agreement: 0.536
signal pairwise Jaccard: 0.405
```

这意味着 IR 有研究价值和系统价值，但不应写成 ground truth classifier。系统实现时必须保留 confidence / evidence strength。

论文中建议表述：

> Five coders participated in the annotation. A subset of cases was overlap-coded to estimate inter-coder consistency. Because signal annotations are multi-label and design behavior is ambiguous, we use the IR as a weighted prior rather than deterministic ground truth.

---

## 3. 三层使用边界

### 3.1 Perception：不用 IR 做结论

Perception 只展示前端真实观察到的行为。

允许：

```text
User is moving the view.
User is focusing on a part.
User is drawing on the silhouette.
User is drawing on the part.
User is editing material.
```

禁止：

```text
User wants explore_shape.
User is changing part.
Structural + Aesthetic?
IR suggests local variant.
```

原因：Perception 是观察层，不是推理层。它应该让用户觉得“系统在看见我做什么”，而不是“系统在替我判断我要什么”。

### 3.2 Intent Bubble：IR 只决定是否问一个小问题

Intent Bubble 只问 coarse scope：

```text
Change contour?
Change part?
Change material?
```

IR 的作用：

- 判断是否到了可能需要帮助的时机；
- 判断三个 scope 哪个优先问；
- 根据用户接受 / 拒绝更新 negative evidence。

IR 不负责在 bubble 中问细粒度意图，例如：

```text
Make it cuter?
Try organic continuity?
Use architecture analogy?
```

这些应该放在 More Creative。

### 3.3 More Creative：IR 用来排序发散维度

More Creative 是发散区。它接收：

```text
typed intent
+ current object / part context
+ frontend signals
+ accepted / rejected bubble evidence
+ IR matched cases
```

然后输出：

```text
ranked dimensions:
  Structural
  Aesthetic
  Functional
  Cross-domain

prompt chips:
  soft silhouette
  rounded proportion
  plush toy
  translucent material
```

如果用户已经输入文字意图，即使没有接受 bubble，也应该先发散。Bubble 只影响排序和 scope，不应该阻塞 More Creative。

---

## 4. Runtime Pipeline

系统运行时的 IR 使用流程：

```text
1. Frontend collects observable signals
2. Backend maps signals to IR signal codes
3. IR retriever finds similar design-state cases
4. Backend aggregates matched cases into priors
5. Creative State Observer decides intervention timing
6. UI renders:
   - Perception: observed behavior only
   - Intent Bubble: one scope question if needed
   - More Creative: ranked dimensions and prompt chips
   - Solution Space: candidates after Generate
```

---

## 5. Frontend Signal → IR Signal Mapping

第一版使用可解释规则，不上复杂模型。

| Frontend observation | IR signal code | Meaning |
|---|---|---|
| `hover_count`, `dwell_ms` | `pause_hover` | user is pausing or hovering |
| `viewport_orbit_count` | `global_orbit` | user is inspecting whole shape |
| `viewport_zoom_count`, `local_zoom_count` | `local_zoom` / `zoom_out` | user is inspecting scale or detail |
| `part_id`, `hovered_part_id` | `select_part` | user is focusing on a part |
| object selected, no part | `select_object` | user is focusing on whole object |
| brush / mask small area | `small_brush` | user is editing local region |
| large brush / broad mask | `large_brush` | user is editing broad form |
| 2D drawing / annotation | `form_change` | user is changing silhouette or contour |
| material words / texture edit | `surface_change` | user is changing material or surface |
| many undo / redo | `undo_redo_loop` | user may be uncertain |
| many rejected candidates | `seek_alternative` | user is searching alternatives |
| low activity after focus | `stuck_uncertain` | possible fixation |

Cleaned mapping file:

```text
intentdatabase/cleaned/frontend_signal_mapping.json
```

---

## 6. Scope Prior

IR should produce a scope prior, not a final answer.

Recommended scope categories:

```text
contour
part
material
```

Scope aggregation:

```text
contour:
  form_change
  select_object
  global_orbit
  multi_view_check
  zoom_out

part:
  select_part
  local_zoom
  small_brush
  repeated_micro_edit

material:
  surface_change
  match_reference
```

Important rule:

```text
typed intent has stronger scope priority than hover.
```

Example:

If the user hovers a snowman body but types:

```text
make this snowman cuter
```

the default scope should be contour / whole-object aesthetic, not part. Hover is attention evidence, not intent evidence.

---

## 7. Confidence Use

IR confidence should be used differently in different UI layers.

| Confidence / evidence | System action |
|---|---|
| high | Can show a small Intent Bubble |
| medium | Rank More Creative dimensions, but do not interrupt |
| low | Stay quiet or show visual inspiration only |

Suggested thresholds for prototype:

```text
high:   score >= 0.70
medium: score >= 0.45 and < 0.70
low:    score < 0.45
```

This score should combine:

```text
retrieval similarity
+ frontend signal overlap
+ scope match
+ annotation agreement
+ recent user feedback
```

Current cleaned IR already exposes:

```text
state_agreement
route_agreement
signal_agreement
evidence_strength
```

Runtime confidence must be shown as explainable evidence, not as an absolute truth.

Good UI text:

```text
IR evidence: similar cases often involved whole-object contour exploration.
```

Bad UI text:

```text
The user is definitely changing contour.
```

---

## 8. Intervention Timing

IR should not trigger UI immediately after the first event.

Bubble should appear only when:

```text
meaningful behavior exists
+ the state is stable for a short window
+ no recent ignored / rejected same-scope bubble
+ user is possibly stuck, comparing, or expressing ambiguous intent
```

Suggested first-version rules:

```text
No bubble:
  - before first meaningful action
  - while user is actively drawing / dragging
  - within 10 seconds after ignored bubble
  - within 15 seconds after rejected same-scope bubble

May show bubble:
  - typed intent is stable but scope ambiguous
  - user focuses same part/object for 8–15 seconds
  - user repeatedly rotates/zooms without new action
  - user repeatedly edits and undoes
  - user rejects generated candidates repeatedly
```

Bubble auto-dismiss:

```text
If no response after about 10 seconds, dismiss and record ignored.
```

---

## 9. More Creative Behavior

### 9.1 Before typed intent

More Creative shows visual inspiration:

```text
Pinterest-like references
similar objects
part references
material mood
cross-domain image sources
```

IR can rank what kind of inspiration appears first, but should not force a text prompt UI.

### 9.2 After typed intent

More Creative switches to prompt-chip mode.

Even if no bubble is accepted:

```text
typed intent stable → generate divergence chips
```

If bubble is accepted:

```text
accepted contour → prioritize Structural / Aesthetic
accepted part → prioritize Structural / Functional
accepted material → prioritize Aesthetic / Functional
```

If bubble is rejected:

```text
record negative evidence
ask another scope if still helpful
do not block generic divergence
```

---

## 10. Solution Space Relationship

IR does not directly generate final candidates.

IR influences:

```text
which dimensions are shown
which prompt chips are ranked higher
which scope metadata is attached to generation
which areas are protected or emphasized
```

Generation is still explicitly triggered by the user:

```text
select / type prompt chips
→ click Generate
→ Solution Space opens with loading cards
→ generated candidates appear
```

If no chips are selected, Generate should still work by using the default CreativeFlow-style auto-divergence prompt based on current context.

---

## 11. Backend Contract

Interpretation response should include:

```json
{
  "features": {
    "design_state_ir": {
      "query_signals": ["global_orbit", "form_change"],
      "matches": [
        {
          "case_id": "example_case",
          "confidence": 0.72,
          "design_state": "coarse_forming",
          "route": "generate_contour_variants",
          "scope_hint": "whole_object",
          "recommended_axes": ["Structural", "Aesthetic"],
          "signal_overlap": ["global_orbit", "form_change"],
          "evidence_strength": "medium"
        }
      ],
      "recommended_axes": ["Structural", "Aesthetic"],
      "axis_scores": [
        {"axis": "Structural", "score": 0.58},
        {"axis": "Aesthetic", "score": 0.42}
      ],
      "policy": "infer_next_divergence_dimension_from_ui_actions"
    }
  }
}
```

The frontend should treat this as evidence for UI ranking, not as a user-facing final label.

---

## 12. GraphRAG Decision

Do not introduce full GraphRAG in the prototype yet.

Reason:

- the current IR has only 207 merged cases;
- labels are structured and already graph-like;
- full GraphRAG adds indexing cost and additional LLM extraction noise;
- runtime needs fast, explainable inference.

Instead, use the cleaned lightweight graph file:

```text
intentdatabase/cleaned/design_state_ir_graph_edges.jsonl
```

This gives enough structure for:

```text
case → signal → route → scope → axis
```

If the dataset later grows to thousands of cases with richer unstructured text, then GraphRAG can be reconsidered.

---

## 13. Minimal Implementation Plan

### Phase 1: Use cleaned IR as runtime prior

- Load `design_state_ir_retrieval.jsonl`.
- Map frontend live signals to IR signal codes.
- Retrieve top-k similar cases.
- Aggregate scope prior and axis ranking.
- Weight by annotation agreement.

### Phase 2: Fix UI routing

- Perception uses only observed frontend behavior.
- Intent Bubble uses only coarse scope questions.
- More Creative uses IR-ranked dimensions.
- Generate works regardless of selected chips.

### Phase 3: Add evidence display for debugging

Optional developer mode:

```text
IR matched cases
signal overlap
scope prior
axis scores
agreement score
```

This should be hidden from study participants unless explicitly needed.

---

## 14. Research Claim Supported by This Design

This IR design supports the following research claim:

> FlowStudio uses interaction-derived IR as a weighted prior for situated creative assistance. Rather than predicting a complete user intention, the system estimates when to intervene, what design scope to ask about, and which divergent dimensions to prioritize. This keeps the user in control while enabling proactive, context-sensitive creative support.

This is safer and more defensible than claiming:

> The system accurately predicts the user's full creative intent.

The paper should emphasize:

- situated inference;
- uncertainty-aware assistance;
- coarse scope clarification;
- prompt-space divergence;
- non-disruptive intervention.

