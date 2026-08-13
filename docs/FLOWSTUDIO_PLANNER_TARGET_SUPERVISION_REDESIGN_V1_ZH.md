# FlowStudio Planner / 监督信号 / IR-RAG 重设计：语义目标 → KG 扩展 V1

日期：2026-08-03  
依据：当前实现（interaction_understanding / multimodal_intent_predictor / design_state_ir /
contextual_divergence / 前端 BubbleScope）与增量规格（contextual divergence fragment pipeline）

## 0. 一句话

把“轮廓 / 部件 / 材质”从**一个字符串 scope**升级为**一个带语义的 `SemanticTarget` 对象**
（label_zh/en、semantic_role、wikidata 可落地、mask/part 引用、置信度、证据、监督信号投票），
Planner 输出它，IR-RAG 监督它，KG 扩展从它出发。  
**三类创意信号各有一个专门监督模块**（3D 几何编辑 / GUI 界面交互 / 自然语言及图像），
它们独立产出目标投票与证据，再由融合层 + IR-RAG 先验合并成 SemanticTarget。

## 0.1 三类创意信号（论文口径）与对应监督模块

按用户论文的三类创意信号划分，架构上设置三个专职监督器：

| 类 | 信号内容（论文口径） | 监督模块 | 典型证据产出 |
| --- | --- | --- | --- |
| ① 人的思考行为信号 | 停顿时间、犹豫状态（反复查看/撤销重做循环/比较停留/固化凝视） | `cognition_supervisor.py` | dwell/pause 时长、undo/redo 循环、重复微调、compare 时长、possible_fixation / ready_for_help 状态 |
| ② GUI 界面交互信号 | 3D 几何编辑（Drag/Brush/Smooth/Add）+ 点选 + 视口缩放/旋转 | `gui_interaction_supervisor.py` | editorScene 编辑命令、drag 向量/目标、brush mask、选择序列、orbit/zoom |
| ③ 自然语言及图像信号 | 语义距离、用户手绘、上传内容（参考图/模型）、文本 | `semantic_language_supervisor.py` | 部件/属性语义词、semantic_distance 变化、笔画形状/OCR、参考图角色（shape/material/aesthetic/function）、上传模型引用 |

三者角色不同：

- ① 回答“用户在想什么、是否犹豫”——**决定要不要介入/要不要确认/置信度门控**（调制器）；
- ② 回答“用户在界面上对哪块做了什么”——**提供空间目标候选**（部件/区域/整体）；
- ③ 回答“用户说了/画了什么语义”——**提供语义命名与操作暗示**（target 语义 + operation_hint）。

① 不直接投票给目标部件，而是调制融合层的置信度：高犹豫 → 强制澄清/降低置信；
稳定固化 → 提升 ②③ 目标候选的置信。② 与 ③ 冲突时进澄清。

## 1. 现状与断点（结合当前代码）

```text
当前：
前端 live_signals / ActionAtom
  → interaction_understanding（规则+IR+creative_state）
      → InteractionInterpretation.primary_intent（IntentLabel：target_part/deform_surface…）
      + features.design_state_ir.scope_hint（whole_object / part_or_region / mixed_whole_and_part / unknown）
      + features.change_scope_hint（contour / part / material，来自前端 BubbleScope）
  → 前端确认泡泡（"Change contour?/part?/material?"）
  → /directions/suggest（metadata.scope + part_id）→ contextual_divergence
      → Wikidata grounding（用 object_type / part label 现拼）→ first-hop → Getty/AskNature → 词片
```

断点/缺陷：

1. **目标不是语义对象**：Planner 不输出“展开哪个轮廓 / 哪个部件（胡萝卜鼻子）”，只输出
   意图标签 + scope 字符串；语义（label、role、mask、QID）散落在别处或干脆没有。
2. **监督信号没有形成“对目标的投票”**：camera/hover/brush/annotation/drag/smooth/add
   各自强烈暗示不同目标，但当前被拍平成 live_signals 计数，IR 特征里只留下
   `part_id`/`selection_type` 之类的粗线索。
3. **IR-RAG 不监督目标选择**：只输出 `recommended_axes` 和粗 `scope_hint`；
   没有 `target_level` 先验，也没有“这个状态不该假设 part”的负监督。
4. **KG 入口与目标脱节**：contextual_divergence 用 `metadata.scope + part_id` 起步，
   部件语义名靠 ZH_LABELS 硬映射；没有把“目标语义 → Wikidata 落地 → 缓存 QID”做成
   正式环节。
5. **确认门确认的是 scope 字符串**，用户接受“轮廓/部件/材质”时不知道 Planner 具体指
   哪个语义部件（鼻子还是围巾），空间化泡泡也没有部件名。

## 2. 核心新概念：SemanticTarget

```json
{
  "target_id": "tgt_001",
  "level": "part",
  "semantic": {
    "label_zh": "胡萝卜鼻子",
    "label_en": "carrot nose",
    "semantic_role": "protrusion/face feature",
    "wikidata_qid": "Q..." ,
    "part_id": "part_nose",
    "mask_ref": "mask_nose_01",
    "surface_ref": null
  },
  "operation_hint": "deform",
  "confidence": 0.78,
  "evidence": [
    {"type": "hover_dwell", "value": "nose region 2.4s"},
    {"type": "brush_region", "value": "mask_nose_01"},
    {"type": "ir_prior", "value": "part_or_region → generate_local_variants"}
  ],
  "supervision_sources": {"camera": 0.1, "hover": 0.72, "brush": 0.55, "annotation": 0.15},
  "kg_ready": false
}
```

level 枚举：`whole | silhouette | part | material_region`。  
“轮廓”不再是裸字符串，而是 `level=silhouette + semantic=雪人的整体轮廓（Q483985）`；
“材质”是 `level=material_region + semantic=围巾表面/雪体表面 + 材料候选`。

## 3. 监督信号模块：三个专职监督器 + 融合层

### 3.1 模块结构

```text
┌──────────────────────── 前端输入层 ────────────────────────┐
│ ① 思考行为（停顿/犹豫/撤销重做循环/比较停留/固化凝视）           │
│ ② GUI 界面交互（drag/brush/smooth/add/点选/视口缩放旋转）       │
│ ③ 自然语言及图像（text/语义距离/手绘/参考图/参考模型）            │
└────────────────────────────────────────────────────────────┘
        │①                 │②                 │③
        ▼                   ▼                   ▼
 cognition_supervisor     gui_interaction_supervisor  semantic_language_supervisor
 （犹豫/固化/置信调制）      （编辑命令/拖拽/点选/视口）      （语义名/笔画/语义距离/参考角色）
        │                   │                   │
        └─────────┬─────────┴─────────┬─────────┘
                  ▼                   ▼
           TargetFusion（加权合并 + 冲突检测 + 置信调制）  ←  IR-RAG recommend_target（设计状态先验+负监督）
                  ▼
           SemanticTarget[]（Planner 输出）
```

### 3.2 每个监督器的输出

```json
{
  "supervisor": "gui_interaction",
  "level_scores": {"whole": 0.05, "silhouette": 0.2, "part": 0.8, "material_region": 0.15},
  "part_candidates": [
    {"part_id": "part_nose", "label_zh": "胡萝卜鼻子", "role": "protrusion", "score": 0.8, "evidence": ["brush mask_nose", "drag vector (0.1,0.2,0)"]}
  ],
  "material_candidates": [],
  "silhouette_evidence": [],
  "conflict": null
}
```

`cognition_supervisor.py`（①，调制器）：dwell/pause 时长、undo/redo 循环、重复微调、
compare 时长、possible_fixation / ready_for_help → 输出：

```json
{
  "supervisor": "cognition",
  "hesitation": 0.7,
  "fixation_stable": true,
  "creative_state": "ready_for_help",
  "confidence_modifier": 0.8,
  "require_clarification": true,
  "evidence": ["dwell 4.2s", "undo_redo×3", "compare 3.1s"]
}
```

`gui_interaction_supervisor.py`（②）：从 editorScene 编辑命令（drag/brush/smooth/add 的
tool+target+半径/向量）与 brush mask 解析目标部件/区域；drag 指向部件时给 part 高分；
点选序列与视口缩放/旋转提供注意力线索；mask 落在未命名表面 → material_region 候选。

`semantic_language_supervisor.py`（③）：文本词（"鼻子/轮廓/哑光"）→ 部件/属性候选与
operation_hint；semantic_distance 变化 → 是否“求变/发散”；annotation 笔画 →
包围整体=轮廓 / 局部标记=部件；参考图角色判定 → shape→silhouette /
material→material_region；上传模型引用 → 目标候选；用户命名/澄清答复 → 语义名 + Wikidata 候选。

### 3.3 融合层（TargetFusion）

```text
target_score(level, candidate) =
   0.6 * gui_interaction_vote + 0.4 * semantic_language_vote
   （语义监督命中部件名时，其权重提升）
   + IR-RAG recommend_target 先验（±，并可按 evidence_strength 缩放）

最终置信 = target_score × cognition.confidence_modifier
高犹豫（hesitation ≥ 0.7）且无固化 → requires_clarification（不输出 target）
```

冲突检测：② 与 ③ 矛盾（GUI 刷了 A 部件、文本说 B 部件）→ `requires_clarification`；
① 高犹豫 + ② 目标漂移（刷了 A 又刷 B）→ 降低置信并进澄清。

```json
{
  "level_scores": {"whole": 0.1, "silhouette": 0.35, "part": 0.72, "material_region": 0.2},
  "part_candidates": [{"part_id": "part_nose", "label_zh": "胡萝卜鼻子", "role": "protrusion", "score": 0.72}],
  "material_candidates": [{"label_zh": "围巾", "score": 0.4}],
  "silhouette_evidence": ["annotation 外轮廓", "camera orbit"],
  "conflict": null
}
```

冲突检测：同时出现“整体外轮廓”和“局部刷选”时进入 clarification（对应现有
Silhouette/Part 消歧），而不是默认选一个。

## 4. IR-RAG：从“只推轴”到“监督目标”

### 4.1 语料加 `target_level`

`intentdatabase/cleaned/design_state_ir_retrieval.jsonl` 每行增加抽象化字段：

```json
{
  "design_state": "early_exploration",
  "route": "generate_local_variants",
  "signals": ["select_part", "form_change"],
  "scope_hint": "part_or_region",
  "target_level": "part",
  "target_semantic_hint": ["nose", "handle", "protrusion"],
  "recommended_axes": ["Structural", "Aesthetic"],
  "evidence_strength": "medium"
}
```

运行时检索字段仍然只含抽象字段（不引入 software/task_group/原始动作），
`target_semantic_hint` 只提供目标语义类型先验，不把案例身份带进线上文本。

### 4.2 `recommend_target()`

`design_state_ir.py` 增加 `recommend_target(matches, features) -> TargetVoteTable`，
与 `recommend_axes` 同构：

- 按匹配案例的 `target_level` 聚合先验分（考虑 evidence_strength）；
- 用当前信号（part_id、hover/brush 目标、annotation 类型）叠加局部分；
- 输出 level_scores + 候选部件/材质（从 signals 与当前 part 语义解析）；
- 输出负监督：若 IR 案例表明该状态“不应假设 part”，降低 part 分并标记
  `require_clarification`。

### 4.3 检索与监督解耦

IR 仍然只回答“用户处于什么设计状态、下一步沿哪些轴、监督哪个目标层”，
不做词片偏好排序（与增量规格一致）。

## 5. Planner：输出 SemanticTarget 列表

### 5.1 数据契约

`InteractionInterpretation` 增加：

```json
{
  "semantic_targets": [
    {"target_id": "tgt_001", "level": "part", "semantic": {...}, "operation_hint": "deform", "confidence": 0.78, "evidence": [...]}
  ]
}
```

`primary_intent`（IntentLabel）保留为兼容字段；hypotheses 对应 targets。

### 5.2 推断顺序（规则优先，VLM 增强）

```text
事件+live_signals 分流到三个监督器：
  ① cognition_supervisor（停顿/犹豫/撤销重做/比较/固化 → 置信调制）
  ② gui_interaction_supervisor（drag/brush/smooth/add/点选/视口）
  ③ semantic_language_supervisor（文本/语义距离/笔画/参考图/命名）
  → TargetFusion 加权合并（②③ 目标票 0.75 + IR recommend_target 先验 0.25，
     × cognition.confidence_modifier）
  → target = argmax，>0.55 才输出 top target
  → 多假设：top2 目标各带 operation_hint
  → 冲突（② vs ③、目标漂移、高犹豫无固化、信号 vs IR 分歧大）
     → requires_clarification
  → InteractionInterpretation.semantic_targets 输出
```

### 5.3 确认门升级

前端泡泡从 “Change part?” 升级为带语义的目标候选：

```text
想展开哪个？
  [整体轮廓]  (0.35)
  [胡萝卜鼻子] 部件  (0.78)  ← 高亮在模型对应位置
  [围巾表面] 材质  (0.40)
```

接受 → 把 `SemanticTarget`（含语义名+part_id+mask+QID 缓存）传给
`/directions/suggest`，而不是 scope 字符串。

## 6. KG 扩展：从语义目标出发

`contextual_divergence._resolve_scope_and_target` 改为消费 `SemanticTarget`：

1. level → scope（whole/silhouette/part/material_region）；
2. target 语义：`label_en + semantic_role + parent object` → Wikidata grounding；
3. **QID 缓存**：target 首次落地后把 `wikidata_qid` 回写（存 asset/part metadata），
   后续编辑直接复用（增量规格 §15 缓存键）；
4. operation_hint → operations（仍按 scope 校验）；
5. first-hop / Getty / AskNature 从落地后的实体出发（现状保持不变）。

## 7. 监督闭环（编辑 → 目标 → 扩展 → 编辑）

```text
雕刻/编辑笔触（part X）
  → ActionAtom + live_signals（含 hover/brush 目标证据）
  → 三个监督器重投（gui_interaction 因编辑上升，cognition 因 dwell/犹豫调制，
     semantic_language 若有“鼻子”等词则命中命名）
  → IR recommend_target（design-state 先验）
  → Planner 输出 SemanticTarget（X，deform，0.7+）
  → 确认泡泡（语义名 + 空间定位）
  → 接受 → /directions/suggest（contextual_fragments_v1 + semantic_target）
  → Wikidata → first-hop → Getty/AskNature 词片
  → 用户选词片 → 生成 → 回到编辑
```

## 8. 具体改动清单（文件级）

| 文件 | 改动 |
| --- | --- |
| `backend/app/models.py` | 新增 `SemanticTarget`、`SignalTargetVote`、`TargetVoteTable`；`InteractionInterpretation` 加 `semantic_targets`；`CrossDomainDivergenceRequest` 加 `semantic_target` 字段 |
| `backend/app/services/cognition_supervisor.py` | 新模块：① 思考行为（停顿/犹豫/撤销重做/比较/固化）→ 置信调制 + 澄清门 |
| `backend/app/services/gui_interaction_supervisor.py` | 新模块：② GUI 界面交互（drag/brush/smooth/add/点选/视口）→ 目标投票 |
| `backend/app/services/semantic_language_supervisor.py` | 新模块：③ 自然语言及图像（文本/语义距离/手绘/参考图/模型）→ 语义目标+operation_hint |
| `backend/app/services/target_fusion.py` | 新模块：②③ 加权合并 + ① 置信调制 + 冲突检测 + IR 先验融合 |
| `backend/app/services/interaction_understanding.py` | 按信号族分流到三个监督器；`_attach_design_state_ir` 接 `recommend_target`；`_build_interpretation` 输出 `semantic_targets` |
| `backend/app/services/design_state_ir.py` | 语料加 `target_level/target_semantic_hint`；`recommend_target()`；负监督标记 |
| `backend/app/services/contextual_divergence.py` | `_resolve_scope_and_target` 消费 `SemanticTarget`；QID 缓存写回 part/asset metadata |
| `backend/app/main.py` | interpret/decision 透传 `semantic_targets`；`create_direction_suggestions` 接收 `semantic_target` |
| `intentdatabase/cleaned/design_state_ir_retrieval.jsonl` | 生成 `target_level`（按案例标注/规则回填） |
| `frontend/src/main.tsx` | BubbleScope → 语义目标候选（部件名+空间定位）；接受后传 `semantic_target`；Perception 显示目标语义 |
| `frontend/src/editorScene.ts` | 编辑笔触证据带目标引用（part_id/mask），供 voter 使用 |
| `tests/*` | voter 投票优先级、IR target 聚合、冲突澄清、KG 从语义目标 grounding 的单测 |

## 9. 分阶段落地

**Phase A（目标即语义对象）**：SemanticTarget 模型 + 三个监督器
（cognition 复用现有 creative_state/dwell/undo_redo 规则；
gui_interaction 覆盖编辑命令+drag+点选+视口；
semantic_language 覆盖文本+语义距离+手绘+参考角色）+
TargetFusion + IR `recommend_target`；Planner 规则输出 semantic_targets；
前端泡泡显示语义候选。

**Phase B（确认 → KG）**：确认的 SemanticTarget 驱动 contextual_divergence grounding；
QID 缓存写回。

**Phase C（闭环与负监督）**：编辑笔触重投 → 目标更新；IR 负监督（不该假设 part 的状态）；
VLM 增强目标语义命名（未命名部件先用 PartField/SAM 命名）。

## 10. 验收口径

- 输入“围绕胡萝卜鼻子做几次 hover+brush+文本‘让鼻子更弯曲’”→ Planner 输出
  `SemanticTarget(level=part, label_zh=胡萝卜鼻子, operation_hint=deform, confidence≥0.6)`；
- 接受后 `/directions/suggest` 的问题为“你想如何改变这个胡萝卜鼻子？”，词片带
  Wikidata→first-hop→Getty/AskNature 溯源；
- IR 只监督目标层/轴，不参与词片排序；确认门展示语义名而非裸 scope；
- 编辑后目标重投分数随 hover/brush 证据变化，冲突时进入澄清。
