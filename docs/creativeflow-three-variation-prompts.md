# CreativeFlow 三类 Variation：原始 Pipeline 与提示词变体

> **状态：已被工程设计文档取代。** KG 迁移应作为独立的第一阶段工程模块，而不是将 graph path 直接写进生图提示词。最新实现规范见 [`creativeflow-three-variation-engineering-design.md`](creativeflow-three-variation-engineering-design.md)。本文仅保留为问题追溯和 prompt compiler 参考。

## 1. 设计原则

Low Fidelity、Part 和 Texture 不是三套固定关键词库，而是同一条 CreativeFlow 类比迁移链路的三种 facet lock contract：

- **Low Fidelity** 只开放全局轮廓、比例、质量分布和触感形式。
- **Part** 只开放 mask 内选中部件的身份、形状、语义与局部材质。
- **Texture** 只开放材质、颜色、微结构、涂层、风化和颗粒，几何不变。

“三段、细长、软绵、硬邦、胡萝卜、木头、金属、脏雪、糖果颗粒”只是结果示例，不写入生产词库。每次的具体输出都应来自 source observation + KG path + semantic bridge。

---

## 2. CreativeFlow 原始 Pipeline

原始主链位于 `pipeline_transfer_engine.py::run_pipeline()`：

1. `materialize_source_assets()`：保存 source image / mesh。
2. `infer_abstract_descriptors()`：基于 source + prompt 提取情感、几何、材质和行为等抽象发散词。
3. `interpret_prompt()`：提取 3–6 个可执行 seed attributes。
4. `expand_paths()`：在 Wikidata / Getty AAT 等图谱中扩展，保留 label、description、provenance、graph distance 和 semantic bridge，并组织 near / mid / far 路径。
5. `generate_local_plan()`：把图谱路径解码为 `parts_to_modify` 和 `part_operations`。
6. `divergent_pruning()`：去重、删除 identity conflict 和不可解码路径。
7. `build_execution_prompt()`：将 source identity、KG path、expanded attributes、part operations 和 preserve constraints 编译为生成提示词。
8. 生成 canonical image 并做 compliance check。
9. canonical image 进入 multiview + Hunyuan3D，输出 GLB / OBJ / PBR。

### 2.1 原版 KG Scoring Engine

KG expansion 不是“查到哪些节点就直接用”。原版会对 raw candidates 做多层评分、清洗和配额选择。

#### A. Raw candidate aggregation

`build_graph_candidates()` 从以下来源合并候选：

- source object concept、seed attributes 和 abstract descriptors；
- Wikidata concept / neighbor / second-hop neighbor；
- Getty AAT label / broader concept / search result；
- AskNature structure term（开启时）；
- qualified probes；
- 外部 KG 完全无可用结果时才使用 prompt fallback。

同名节点会合并 provenance，并记录与多个 query/seed 的 overlap。

#### B. Hard cleaning

`clean_graph_direction_candidates()` 先执行硬过滤：

1. `contains_blacklist_semantics()`：删除黑名单语义。
2. `looks_like_noisy_title()`：删除过长标题、列表/字典字面量、编号噪声和其他非 concept title。
3. `is_bare_object_direction_candidate()`：删除只重复 source object、但没有方向性属性的 bare anchor。
4. strict mode 下，形态评分不达标且不能归入 aesthetic modifier pool 的节点被删除。

#### C. Morphology relevance score

`morphology_relevance()` 根据 label 与 description 中的证据评分：

```text
morph_score =
    1.8 * label_morphology_hits
  + min(2.0, 0.35 * text_morphology_hits)
  + min(1.6, 0.55 * object_hint_hits)
  + min(1.2, 0.25 * prompt_hits)
  + object/qualifier bonuses
  + positive-category bonus
  + AAT qualifier bonus
  + AskNature / cross-source provenance bonus
  - generic-direction penalty
```

默认通过阈值是 `CF_KG_MIN_MORPH_SCORE=1.2`。评分明细保存为 `morphology_relevance`，不应只保存总分。

#### D. Aesthetic modifier score

非主形态节点可以进入 aesthetic modifier pool，但不能取代主 anchor。`aesthetic_modifier_relevance()` 综合：

- label/text 中的 aesthetic term hits；
- Getty AAT aesthetic evidence 和 AAT source bonus；
- 与 user prompt 的 overlap；
- 过长 label 和 morphology-term 冲突惩罚。

默认阈值为 `CF_KG_MIN_AESTHETIC_SCORE=1.0`；AAT 默认可用更低阈值 `0.8`。`blend_aesthetic_modifiers()` 只将高分 modifier 附加到已选主 anchor。

#### E. Candidate ranking score

清洗后的主候选按以下逻辑排名：

```text
base_score = overlap + 0.3 * provenance_count
total_score = base_score + semantic_consistency_bonus

sort key:
  total_score DESC
  overlap DESC
  provenance_count DESC
  label ASC
```

`score_breakdown` 需保留 `base_score`、`consistency_bonus` 和 `morphology_relevance`。

#### F. Semantic distance score

`scripts/kb_semantic_distance.py::compute_semantic_distance()` 组合三类证据：

```text
distance_score =
    0.35 * local_embedding_distance
  + 0.45 * min(structural_graph_distance / 4, 1)
  + 0.20 * decodeability_penalty
```

- `local_embedding_distance`：词汇/局部语义差异。
- `structural_graph_distance`：图上结构路径距离。
- `decodeability_penalty`：该节点能否解码为设计操作的惩罚。

当前代码中的 bucket 判定包括：

- near：`graph_distance <= 1` 且 local distance / decodeability penalty 低于阈值；
- far：`graph_distance >= 3` 且 decodeability penalty 不超过可解码阈值；
- 其余根据组合分数归入 mid / unknown。

far 不代表“越奇怪越好”。如果 decodeability penalty 过高，节点即使图距离很远也不应使用。

#### G. Source-family and distance quotas

`expand_paths()` 使用两组配额防止候选被单一图谱或单一距离占满：

```yaml
source_family_quota:
  wikidata: CF_GRAPH_WIKIDATA_QUOTA
  aat: CF_GRAPH_AAT_QUOTA
  asknature: CF_GRAPH_ASKNATURE_QUOTA
distance_quota:
  near: CF_GRAPH_NEAR_QUOTA
  mid: CF_GRAPH_MID_QUOTA
  far: CF_GRAPH_FAR_QUOTA
```

选择顺序为 near → far → mid → unknown，同时满足 source-family quota。本项目的 4 个 direction 默认目标为 2 near + 2 far，但不可为填满数量而接受低分或不可解码节点。

#### H. Path pruning and result scoring

`divergent_pruning()` 在 path 级别继续检查：

- expanded attributes + operations 去重；
- local plan 必须可解码；
- local plan 不能与 identity constraints 冲突。

图像生成后，`run_compliance_check()` 生成 `compliance_score`。原版 benchmark 分类为：

```text
compliance >= 0.65 and distance in {mid, far} -> candidate
compliance >= 0.45                         -> needs_review
otherwise                                  -> discard
```

当前未配置 `CF_COMPLIANCE_SCORER_URL` 时，会退回 `heuristic_text_proxy`，它只检查 operation 文本是否出现在 prompt 中，不能证明图像真的发生了变化。三类 variation 必须增加图像级 scorer。

### 2.2 Variation 对 Scoring Engine 的扩展方式

不重写一套独立 scoring engine，而是在原版总分上增加 stage-specific 项：

```text
variation_candidate_score =
    original_KG_candidate_score
  + semantic_distance_quality
  + graph_path_decodeability
  + open_facet_relevance
  + source_observation_alignment
  - locked_facet_conflict_penalty
  - ontology_noise_penalty
```

`open_facet_relevance` 和 `locked_facet_conflict_penalty` 由 variation contract 决定：

- Low Fidelity 奖励 silhouette / proportion / mass / tactile-form 证据，惩罚 material / accessory replacement。
- Part 奖励 selected-part identity / shape / attachment 证据，对 outside-mask / global-body operation 给予硬拒绝。
- Texture 奖励 material / color / roughness / coating / microstructure 证据，对 geometry operation 给予硬拒绝。

当前 variation wrapper 设置了 `CF_KG_CLEAN_STRICT=false`、`CF_GRAPH_ALLOW_GENERIC_ANCHORS=true`，实际上放宽了原版 scoring/cleaning gate，这是抽象垃圾节点进入生成的直接原因之一。生产版应恢复 strict cleaning，再使用 stage-specific score 补充原版通用 morphology score。

### 当前 variation wrapper 为什么失败

当前包装实际上只生成了：

```text
fixed stage instruction
+ Use the knowledge-graph anchor "<anchor>" as an analogy
+ fixed locked-facet sentence
```

它没有把 `semantic_bridging`、`expanded_attributes` 和 `local_plan.part_operations` 编译为方向特定的可视操作。

同时，当前服务器没有配置原版 planning/vision LLM，导致三个关键阶段都退回 heuristic fallback。对 snowman，fallback 不认识其部件 schema，所有方向都得到相同的：

```text
main_body: volume_rearticulation
support_structure: support_rearticulation
edge_profile: profile_rewrite
silhouette_profile: profile_rewrite
```

更严重的是，Part 和 Texture 也收到了这套 morphology operations。因此“存在 KG label”不等于“完成了结构化图谱跳跃”。

---

## 3. 共用的结构化 Direction Schema

每个 direction 必须先产生这个结构，然后才能编译为提示词：

```json
{
  "source_observation": {
    "object_identity": "<vision-derived identity>",
    "part_inventory": ["<visible parts>"],
    "selected_part": "<mask-region identity>",
    "current_materials": ["<visible materials>"],
    "current_form_attributes": ["<form attributes>"]
  },
  "graph_transfer": {
    "source_concept": "<request-dependent concept>",
    "seed_attribute": "<vision/prompt-derived seed>",
    "path": ["<node>", "<relation>", "<node>"],
    "target_anchor": "<KG result>",
    "semantic_distance_bucket": "near | mid | far",
    "bridge_explanation": "<how the path becomes a visible property>"
  },
  "variation_contract": {
    "open_facets": ["<allowed facets>"],
    "locked_facets": ["<immutable facets>"],
    "target_region": "global | mask | material-region"
  },
  "execution_plan": {
    "operations": [
      {
        "target": "<part or facet>",
        "operation": "<observable operation>",
        "magnitude": "<controlled strength>",
        "evidence": "<graph path segment>"
      }
    ],
    "negative_operations": ["<forbidden edits>"]
  }
}
```

### Direction 准入条件

- KG provenance 和 graph path 非空。
- 具有 near / mid / far 距离证据。
- `bridge_explanation` 可以转换为当前 variation 的可视属性。
- `operations` 非空，且只修改 open facets。
- 不允许仅将 anchor 原样拼入 prompt。
- `document`、`manifestation`、`probability distribution`、`hierarchy name` 等不可执行本体分支必须删除。

---

## 4. Low Fidelity 提示词变体

### Facet contract

```yaml
open_facets:
  - outer_contour
  - body_segment_count
  - global_proportion
  - mass_distribution
  - posture_envelope
  - tactile_form_impression
locked_facets:
  - object_identity
  - part_inventory
  - accessory_identity
  - local_part_semantics
  - base_material
  - color_scheme
  - background_and_camera
```

### Prompt template

```text
TASK
Generate one Low Fidelity variation of the supplied <object_identity>.

SOURCE OBSERVATION
- Current global form: <current_form_attributes>.
- Identity-defining parts/accessories: <part_inventory>.

KNOWLEDGE-GRAPH TRANSFER
- Source concept / seed: <source_concept> / <seed_attribute>.
- Traversed path: <graph_path>.
- Target anchor: <target_anchor>.
- Semantic distance: <distance_bucket>.
- Transfer rationale: <bridge_explanation>.

EXECUTION PLAN
Translate the rationale into visible global-form operations:
<target + operation + magnitude + graph evidence>

CHANGE ONLY
Outer contour, segment rhythm/count, global proportion, mass distribution,
posture envelope, and perceived softness/rigidity of the global form.

PRESERVE EXACTLY
Object identity, recognizable part inventory, accessory identity, local part
semantics, base material, color scheme, background, camera and lighting.

OUTPUT
One complete, fully visible, centered object with a clean silhouette, suitable
for single-view 3D reconstruction.

FORBIDDEN
Changing materials, replacing accessories, adding a second object, or using
the target anchor as a literal unrelated object.
```

三段、细长、软绵和硬邦可以是某次 graph bridge 的解码结果，但不是固定四选项。

---

## 5. Part 提示词变体

### Facet contract

```yaml
open_facets:
  - masked_part_identity
  - masked_part_shape
  - masked_part_semantics
  - masked_part_local_material
  - attachment_transition_inside_mask
locked_facets:
  - every_pixel_outside_mask
  - object_identity
  - global_silhouette
  - global_proportion
  - pose
  - unselected_parts
  - accessories
  - background_and_camera
```

### Prompt template

```text
TASK
Create one Part variation by regenerating only the supplied mask.

SOURCE OBSERVATION
- Object identity: <object_identity>.
- Selected region currently depicts: <selected_part_identity>.
- Current geometry/material/attachment: <selected_part_attributes>.

KNOWLEDGE-GRAPH TRANSFER
- Source part concept / seed: <source_concept> / <seed_attribute>.
- Traversed path: <graph_path>.
- Target anchor: <target_anchor>.
- Semantic distance: <distance_bucket>.
- Transfer rationale: <bridge_explanation>.

EXECUTE INSIDE THE MASK ONLY
<replace/reform/resemanticize selected part operation>
<natural attachment transition operation>

The target anchor is an analogy source. Transfer only its relevant shape,
function, semantic role or local material properties into a plausible part.

PRESERVE EXACTLY
Every pixel and design decision outside the mask, global silhouette, global
proportion, pose, all unselected parts, accessories, background and camera.

OUTPUT
One seamless inpainted image of the same complete object, suitable for 3D
reconstruction, with a natural attachment boundary.

FORBIDDEN
Editing outside the mask, changing the body/scene, duplicating the part, or
creating a pasted sticker-like boundary.
```

对雪人鼻子，source concept 应由 mask-region caption 得到“锥形胡萝卜鼻子”等具体观察，再做 near/far 扩展。只从泛化的 `nose` 出发会走向 `animal organ / sensory organ`，却不能形成设计部件迁移。

---

## 6. Texture 提示词变体

### Facet contract

```yaml
open_facets:
  - material_identity
  - color
  - roughness
  - gloss_or_metalness
  - surface_microstructure
  - coating
  - weathering
  - embedded_particles
locked_facets:
  - object_identity
  - geometry
  - outer_contour
  - global_proportion
  - every_part_shape
  - part_layout
  - pose
  - background_and_camera
```

### Prompt template

```text
TASK
Create one Texture variation of the supplied <object_identity>.

SOURCE OBSERVATION
- Current geometry and parts: <geometry_and_part_summary>.
- Current visible materials: <current_materials>.
- Current surface attributes: <current_surface_attributes>.

KNOWLEDGE-GRAPH TRANSFER
- Source material concept / seed: <source_concept> / <seed_attribute>.
- Traversed path: <graph_path>.
- Target anchor: <target_anchor>.
- Semantic distance: <distance_bucket>.
- Transfer rationale: <bridge_explanation>.

EXECUTE AS A SURFACE-ONLY TRANSFER
<material/color/roughness/microstructure operation>
<coating/weathering/particle operation>

Keep the exact same geometry, silhouette, proportions, pose, part shapes and
part layout. Express the transfer only through material response and surface
appearance.

PRESERVE EXACTLY
Object identity, geometry, outer contour, every part shape, attachment points,
pose, background, camera and composition.

OUTPUT
One complete object with clearly readable PBR cues: base color, roughness,
metalness/specularity and microstructure.

FORBIDDEN
Adding/removing/reshaping parts, changing silhouette or pose, texturing the
background, or producing a flat sticker overlay.
```

例如，局部 material mask 可保持胡萝卜鼻子锥形几何，只将材质迁移为木质或金属；整体表面可保持雪人几何，只迁移为风化脏雪或嵌入糖果颗粒的表面。这些仍然只是示例，实际 target 由当次 KG path 决定。

---

## 7. Near / Far 候选组织

每类 variation 默认保留 2 near + 2 far，但语义距离不能代替可执行性：

- Near 与 source/seed 的图距离较近，变化较可预期。
- Far 可跨越更多关系，但 bridge decoder 仍必须将它翻译为 open facets 上的可视操作。
- 无法生成非空 operation 的 far node 必须删除，而不是因为“它距离远”就使用。

---

## 8. 生成前后质量门

### 生成前

```text
graph_path_nonempty == true
graph_provenance_nonempty == true
semantic_distance_bucket in {near, mid, far}
bridge_explanation_nonempty == true
operations_nonempty == true
operations ⊆ open_facets
operations ∩ locked_facets == ∅
prompt_mentions_graph_path == true
prompt_mentions_observable_operations == true
```

### 生成后

- Low Fidelity：轮廓/比例差异超过阈值，但配件、颜色和部件清单保持。
- Part：mask 内差异超过阈值，mask 外像素级一致。
- Texture：边缘/几何差异低于阈值，材质外观差异超过阈值。

只有通过质量门的 canonical image 才能进入 Hunyuan3D。

---

## 9. 实现要求

1. variation wrapper 停止自行拼接 `Use the anchor ...` 的弱提示词。
2. 保留原版 `build_execution_prompt()` 编译思路，将通用 morphology planner 扩展为三种 stage-aware schema。
3. 恢复 planning/vision LLM，不允许在生产 variation 中静默使用通用 heuristic fallback。
4. Part 的 source concept 来自 mask-region caption；Texture 的 source concept 来自 material-region caption。
5. 每个候选对外记录 graph path、distance、bridge rationale、open/locked facets 和 operations，使迁移可审计。
6. Blender 预览需验证 GLB 的材质节点实际引用 PBR 贴图，不能只因为磁盘上存在 `material_0.png` 就宣称已渲染。

---

## 10. 下一步开发计划

### Phase 0：固化基线与失败样例

**目标**：保留当前 12 个失败候选作为 regression fixtures，防止再次把“有文件”当作“有迁移”。

**工作**：

1. 保存 source image、masks、variation requests、graph candidates、execution prompts、canonical images 和 GLB。
2. 标记已知失败：候选同质、抽象 anchor、错误 local plan、灰模预览。
3. 为三类 variation 建立可量化基线。

**验收**：一个 fixture 命令可重现当前失败，且报告不再把它判为 pass。

### Phase 1：恢复 source-aware planning

**目标**：让 KG 从正确的 source concept 出发。

**工作**：

1. 恢复/部署原版 planning/vision LLM endpoint，配置 `call_planning_json()` 所需环境。
2. 生成全局 source observation：identity、part inventory、form attributes、materials。
3. Part 对 mask crop 做 region caption，得到具体 selected-part concept。
4. Texture 对 material-region 做 caption，得到具体 current-material concept。
5. LLM 不可用时显式失败，不允许生产任务静默退回 generic heuristic。

**验收**：雪人 fixture 能输出具体 source observation；Part 不再只从 `nose`出发，Texture 不再只从 `material`出发。

### Phase 2：恢复原版 KG expansion + scoring

**目标**：完整复用原版 candidate aggregation、cleaning、scoring、distance 和 quota。

**工作**：

1. variation 不再直接自建 `SeedAttribute` 列表替代 `interpret_prompt()`。
2. 恢复 `CF_KG_CLEAN_STRICT=true`，关闭 generic/bare anchor 的宽松通道。
3. 保留 morphology relevance、aesthetic modifier、candidate score breakdown 和 semantic distance 明细。
4. 实现 `variation_candidate_score`，增加 open-facet relevance 与 locked-facet conflict hard gate。
5. 保留 2 near + 2 far；合格数量不足时返回 insufficient-candidates，不用垃圾节点补齐。

**验收**：

- 每个 retained direction 有 provenance、path、score breakdown、distance breakdown 和 bridge。
- `document / manifestation / probability distribution / hierarchy name` 无法通过。
- 四个方向之间 operations 不完全相同。

### Phase 3：stage-aware rationale 和 prompt compiler

**目标**：将 KG path 真正编译为三类可执行提示词。

**工作**：

1. 实现 Low Fidelity / Part / Texture 三种 local-plan schema。
2. planner 输入必须包含 source observation、graph path、semantic bridge 和 facet contract。
3. planner 输出必须包含 target、operation、magnitude 和 graph evidence。
4. 由结构化 plan 编译 prompt，删除当前弱化的 `Use the anchor ...` 拼接。
5. 增加 schema validator 和 locked-facet conflict validator。

**验收**：每个 prompt 都能回答“图谱走了哪条路、因此改哪个 facet、怎么改、哪些不能改”。

### Phase 4：二维条件生成和图像级 scoring

**目标**：先证明三类 variation 在二维图像上真的有效，再进入 3D。

**工作**：

1. Low Fidelity：使用轮廓/深度条件，允许全局形式改变。
2. Part：使用 inpaint ControlNet，生成后 hard composite 确保 mask 外像素级不变。
3. Texture：使用 material-region mask，限制只修改表面。
4. 实现图像 scorer：轮廓差异、mask 内外差异、geometry edge 一致性、material appearance 差异、identity similarity。
5. 不通过的 candidate 自动重试/换方向，不进入 Hunyuan3D。

**验收**：

- Low Fidelity 的全局轮廓有可量化差异。
- Part 的 mask 外差异为 0，mask 内差异超过阈值。
- Texture 的几何边缘保持，但颜色/材质特征差异超过阈值。
- 同一组四张图之间不能被多样性 scorer 判为近乎重复。

### Phase 5：Hunyuan3D 与 PBR 验证

**目标**：只将合格 canonical image 转换为可审查的带材质 3D 资产。

**工作**：

1. 三组 Hunyuan3D 串行执行，每组 4 个 candidate。
2. 验证 mesh.glb、mesh.obj、MTL 和 texture 非空。
3. 用 Blender 检查 GLB material node tree，确认 Base Color / PBR texture 真正连接。
4. 使用 Material Preview / Eevee 渲染正面、侧面、3/4 视图，不使用灰色 workbench 结果作为最终图。
5. 比较 12 个 mesh 的 silhouette / geometry / texture diversity，防止 2D 差异在 3D 阶段丢失。

**验收**：每个候选的三面渲染可见材质，且差异与对应 KG rationale 一致。

### Phase 6：一键链路、OSS 与案例库

**目标**：将验证通过的三类 variation 接回完整 CreativeFlow 产品链路。

**工作**：

1. API 输出 source observation、KG candidates + scores、retained rationales、prompts、images、meshes 和 QA scores。
2. 上传 canonical images、multiview、GLB、OBJ、PBR textures、score report 到 OSS。
3. 生成 `case.json` 和 HTML report，注册到前端 case library。
4. 前端显示 near/far、graph path、score breakdown、rationale 和三面带材质渲染。

**验收**：从一个 source + optional mask 开始，一键产生三组合格 variation，并可从网站访问全部审计证据与 3D 资产。

### 建议开发顺序与粗略工作量

| 阶段 | 交付 | 估计 |
|---|---|---:|
| Phase 0 | regression fixtures + QA baseline | 0.5 天 |
| Phase 1 | vision/source observation + fail-closed planner | 1–2 天 |
| Phase 2 | 原版 scoring 恢复 + variation scoring | 1.5–2.5 天 |
| Phase 3 | 三种 structured rationale/prompt compiler | 1.5–2 天 |
| Phase 4 | Qwen 条件生成 + image scorers | 2–3 天 |
| Phase 5 | Hunyuan3D + PBR/material render QA | 1–2 天 |
| Phase 6 | OSS + case library + website | 1–2 天 |

合计约 **8–13 个工作日**。已有原版 CreativeFlow、Qwen-Image、Hunyuan3D 和服务器环境能明显减少工作量；主要不确定性在 planning/vision LLM 恢复、scorer 阈值标定和 Texture 的 PBR 忠实度。
