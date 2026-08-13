# FlowStudio 语义发散核心机制设计

**日期：** 2026-08-06  
**状态：** 待用户书面复核  
**范围：** Gate 接受后的关键词发散，不修改常驻 Observation、Gate 触发原则、图片生成与 3D 替换主线

## 1. 目标

将当前“Planner 返回少量 `divergence_seeds`，前端原样显示”的浅层链路替换为独立的 Semantic Divergence。系统应根据已经确认的对象、部件或材质范围，将用户语义、锁定行为窗口和继承关键词转译成 9–15 个简短、具体、与上下文相关的候选词，并在用户选择后驱动 6–8 个 Solution。

本机制承担论文中的核心研究问题：行为与语言上下文如何共同约束可控的语义迁移，以及知识增强是否能提高新颖性、可解释性和用户选择率，同时保持对象 identity 与修改范围。

## 2. 已确认的设计决策

1. Qwen2.5-VL 继续承担常驻 Observation 编码，不负责 Gate 决策。
2. Gemini Planner 只产生目标、范围和一句 Gate 问句，不再产生用户可选关键词。
3. Gate 接受后调用独立 Semantic Divergence 服务。
4. Gemini 是语义发散主模型；GPU 上本地 Qwen2.5-VL 使用相同契约作为模型 fallback。
5. Wikidata、Getty AAT、AskNature 是按 `scope × temperature × intent` 动态启用的知识增强层，不是每次请求都必须成功的阻塞依赖。
6. 前端只显示短关键词或短语；后台保留目标、操作、语义锚点、完整生成短语、评分与来源路径。
7. `Aesthetic / Structural / Functional / Cross-domain` 只能作为内部类别或显示分组，禁止成为用户可选择的关键词。
8. 两个滑杆必须影响真实请求、模型参数、知识路由和校验阈值，不能只改变前端 state。
9. 任一模型或知识源的降级必须通过 provenance 显式记录，禁止用固定大类词伪装成模型结果。

## 3. 系统边界与职责

```text
常驻 Observation
  → Qwen Observation Encoder
  → 用户点击发送并锁定行为窗口
  → Gemini Planner
  → 单句 Gate
  → 用户接受 Gate
  → Semantic Divergence Orchestrator
       ├─ Knowledge Router
       │    └─ Wikidata → Getty AAT / AskNature
       ├─ Gemini Semantic Generator（主）
       └─ Qwen2.5-VL Semantic Generator（fallback）
  → Deterministic Validator
  → 9–15 个短关键词
  → 用户选择
  → 6–8 个 Solution
```

### 3.1 Planner

Planner 只负责：

- 锁定 `asset_id` 与 object identity；
- 判断 `scope`；
- 确认 `target_part_id` 或 `surface_ref`；
- 汇总硬约束；
- 生成一句 Gate 问句。

`DecisionIR.options[].divergence_seeds` 在迁移期可保留兼容字段，但新前端不得以它作为关键词来源。

### 3.2 Semantic Divergence Orchestrator

Orchestrator 负责：

- 校验 Gate 已接受；
- 组装完整上下文；
- 根据 scope、temperature 和 intent 选择知识源；
- 调用 Gemini；
- 在技术失败或质量失败时调用本地 VLM；
- 合并、去重、评分和过滤；
- 返回稳定、可审计的响应。

### 3.3 Knowledge Router

知识层只提供 donor concepts 与可追溯证据，不直接把词库标题显示给用户。Wikidata 先完成实体 grounding 和 first-hop；Getty AAT、AskNature 只能基于 first-hop 邻域进行二阶检索。

### 3.4 Deterministic Validator

Validator 独立于模型，统一检查 Gemini 与本地 VLM 输出。模型不能自行声明候选合格。

## 4. 数据契约

### 4.1 `SemanticDivergenceRequest`

```json
{
  "run_id": "fsrun_xxx",
  "decision_id": "decision_xxx",
  "session_id": "sess_xxx",
  "asset_id": "asset_xxx",
  "object_identity": "snowman",
  "semantic_target": {
    "level": "part",
    "part_id": "hat",
    "label_zh": "帽子",
    "label_en": "hat",
    "wikidata_qid": null,
    "mask_ref": null
  },
  "scope": "part",
  "user_semantic_intent": "make the hat more playful",
  "behavior_summary": "dragged and smoothed the hat tip",
  "behavior_window_id": "window_xxx",
  "inherited_keywords": ["柔软曲线"],
  "hard_constraints": ["preserve snowman identity", "change hat only"],
  "temperature": 0.6,
  "strictness": 0.8,
  "candidate_count": 13
}
```

约束：

- 只有 `scope_gate.status == accepted` 才能创建请求。
- `temperature`、`strictness` 范围均为 `[0, 1]`。
- `candidate_count` 范围为 `[9, 15]`。
- `behavior_window_id` 必须引用用户点击发送前锁定的窗口。
- Gate 接受后产生的新行为不进入当前请求，只进入下一个 intent 窗口。

### 4.2 `SemanticCandidate`

```json
{
  "candidate_id": "kw_xxx",
  "display_label_zh": "熔岩流线",
  "label_en": "lava flow lines",
  "group": "semantic_transfer",
  "target_ref": {
    "asset_id": "asset_xxx",
    "type": "part",
    "id": "table_support"
  },
  "operation": "deform",
  "semantic_anchor": "cooling lava flow",
  "prompt_phrase": "reshape only the table support with solidified flowing-lava contours",
  "attribute_delta": {
    "attribute": "contour",
    "change": "flowing solidified ridges"
  },
  "scores": {
    "identity": 0.93,
    "scope": 0.97,
    "relevance": 0.89,
    "specificity": 0.86,
    "novelty": 0.78
  },
  "provenance": {
    "generator": "gemini",
    "mode": "knowledge_augmented",
    "wikidata": [],
    "getty_aat": [],
    "asknature": []
  }
}
```

### 4.3 `SemanticDivergenceResponse`

响应包含：

- `divergence_id`、`run_id`、`decision_id`；
- `generator_model`；
- `fallback_used` 与 `fallback_reason`；
- `knowledge_route` 与各知识源状态；
- 原始候选数、各校验阶段淘汰数；
- 9–15 个通过校验的 `candidates`；
- `latency_ms` 与 prompt/schema 版本。

## 5. 滑杆语义

### 5.1 发散温度

`temperature` 同时影响候选跨度、知识路由和模型采样，但不能降低 identity 硬约束。

第一版映射：

```text
model_temperature = 0.15 + 0.75 × temperature
requested_count   = clamp(round(9 + 6 × temperature), 9, 15)
```

分段策略：

| 温度 | 候选策略 | 知识策略 |
| --- | --- | --- |
| 0.0–0.3 | 同域属性和局部 refinement | 默认不访问外部知识源 |
| 0.4–0.6 | 邻域类比与有限语义迁移 | 按 scope 启用 Wikidata/Getty |
| 0.7–1.0 | 明显跨域类比 | 启用 Wikidata，并按 intent 启用 Getty/AskNature |

### 5.2 评分严谨度

`strictness` 只控制保真、范围和语义相关性的过滤阈值，不控制模型创造力。

第一版映射：

```text
identity_min  = 0.55 + 0.35 × strictness
scope_min     = 0.55 + 0.40 × strictness
relevance_min = 0.45 + 0.40 × strictness
```

`part` 与 `material_region` 请求还必须通过离散硬门：目标存在、操作兼容、锁定约束未破坏。严格度再低也不能放过越界候选。

## 6. 知识增强路由

### 6.1 路由规则

| 条件 | Wikidata | Getty AAT | AskNature |
| --- | --- | --- | --- |
| 低温、局部 refinement | 可跳过 | 可跳过 | 跳过 |
| 材质、纹理、工艺意图 | grounding | 启用 | 默认跳过 |
| 形态、构件、连接意图 | grounding + first-hop | 启用 | 条件启用 |
| 功能、仿生、机制意图 | grounding + first-hop | 条件启用 | 启用 |
| 高温或明确跨域迁移 | grounding + first-hop | 启用 | 启用 |

路由依据使用结构化字段，不能仅匹配一两个英文单词：

- `scope`；
- Planner 的 operation hint；
- 用户语义意图；
- Observation 编码出的设计状态；
- temperature；
- 已继承关键词。

### 6.2 降级原则

- Wikidata grounding 失败：记录失败，允许 Gemini 使用当前语义上下文直接发散。
- Getty 失败：保留 Gemini 与可信 AskNature 候选。
- AskNature 失败：保留 Gemini 与可信 Getty 候选。
- 知识源全部失败：进入 `model_only`，不能让交互整体失败。
- 知识源返回的标题或 preferred term 不得直接显示，必须由模型解码成与当前 target 绑定的短词。

## 7. 模型主备与 fallback

### 7.1 Gemini 主服务

Gemini 输入完整请求和可用 donor evidence，输出结构化候选。提示词必须明确：

- 生成短标签而非完整句子；
- 中文标签建议 2–8 个字，英文建议 1–4 个词；
- 标签不能是分类名；
- 后台字段必须包含 target、operation、semantic anchor 和 prompt phrase；
- 不改变 Gate 外的对象或部件；
- 不生成与已有继承词重复的候选。

### 7.2 本地 Qwen2.5-VL fallback

触发条件：

1. Gemini 超时、限流或不可用；
2. JSON schema 经一次修复仍无效；
3. Validator 过滤后不足 9 个候选；
4. 输出主要由分类名、重复词或无关词组成；
5. 输出 target 与已接受 Gate 不一致。

本地 VLM 使用完全相同的 request/response schema、donor evidence 与 Validator。fallback 不重新解释 Gate，也不扩大锁定行为窗口。

### 7.3 双模型失败

如果两个模型都无法产生至少 9 个合格候选：

- 返回结构化失败；
- 前端显示“语义发散暂时不可用，请重试或补充意图”；
- 保留已继承关键词；
- 不显示固定大类词或无来源模板词；
- 不自动开始图片生成。

## 8. 展示与关键词长度

前端分组：

- 形态 `shape`
- 连接 `connection`
- 表面/材质 `surface`
- 语义迁移 `semantic_transfer`

显示标签示例：

| 形态 | 连接 | 表面/材质 | 语义迁移 |
| --- | --- | --- | --- |
| 帽檐外卷 | 一体衔接 | 磨砂硅胶 | 石像质感 |
| 柔软螺旋 | 嵌套连接 | 冰晶颗粒 | 熔岩流线 |
| 低矮比例 | 悬浮连接 | 编织表面 | 生物骨架 |

前端只展示 `display_label_zh`；Tooltip、调试面板或研究日志可以查看完整 `prompt_phrase` 与 provenance。用户选择后，系统使用完整后台语义组装生成 Prompt。

## 9. 强校验

### 9.1 禁止项

以下标签单独出现时禁止成为候选：

```text
Aesthetic
Structural
Functional
Cross-domain
shape
connection
material
surface
silhouette
ornament
```

同时禁止：空字符串、完整句子、只表达“改变/优化/更有创意”的泛化词、对象或部件不存在的词、与继承词同义重复的词。

### 9.2 单候选校验

前端短标签不必重复对象名，但后台候选必须具备：

- 有效 `target_ref`；
- 与 scope 相容的 `operation`；
- 非空 `semantic_anchor`；
- 可执行的 `prompt_phrase`；
- 明确 `attribute_delta`；
- identity、scope、relevance、specificity 分数；
- 可识别的模型与知识来源。

### 9.3 集合校验

- 最终返回 9–15 个候选；
- 至少覆盖两个与当前 intent 相关的分组；
- 高温请求必须包含通过校验的 `semantic_transfer` 候选；
- 同组候选不得只做近义改写；
- `part` Gate 不得改变整体对象；
- `material_region` Gate 不得擅自重构轮廓；
- 所有候选必须保留 object identity；
- 新 intent 接受后，在既有结果后追加新的非重复关键词，不清空已接受结果。

## 10. 状态与并发

- 每次点击意图发送创建独立的锁定窗口和 divergence request。
- 多个 Gate 泡泡可以同时存在，并分别指向自己的 `decision_id`。
- 一个 Gate 的发散完成后，结果追加到对应版本分支；不得覆盖其他已接受 Gate 的结果。
- Gate 被拒绝时不调用 Semantic Divergence。
- 请求必须幂等：相同 `decision_id + parameters + inherited_keywords` 重试不能产生重复记录。
- Observation 在发散期间继续运行，新事件只属于下一个 intent 窗口。

## 11. 可观测性与论文数据

每次请求记录：

- 锁定行为窗口及其摘要；
- 用户语义与 Gate 范围；
- temperature、strictness 与实际映射值；
- 知识路由决策及原因；
- Gemini、本地 VLM 调用结果和 fallback 原因；
- 原始候选数、每条拒绝规则的数量；
- 最终候选、用户选择和继承关系；
- 6–8 个 Solution 及接受、拒绝结果；
- 各阶段延迟。

研究指标：

- Semantic Relevance；
- Keyword Specificity；
- Identity Preservation；
- Scope Compliance；
- Intra-set Diversity；
- Keyword Selection Rate；
- Solution Acceptance Rate；
- Gemini → VLM Fallback Rate；
- 知识源命中率与端到端延迟。

## 12. 消融实验

保留三个实验条件：

1. `LLM-only`：Gemini，不使用知识增强；
2. `Knowledge-only`：知识片段经确定性解码，不使用生成模型补充；
3. `Knowledge-augmented LLM`：知识片段作为 Gemini donor evidence。

统一使用三个基准场景：

1. 青蛙到石像青蛙：叙事语义迁移，文字 + drag/smooth；
2. 同一皮包的材质多样性：文字 + 意图识别 + 2D 笔刷；
3. 茶几到熔岩结构：语义意图 + 3D 笔刷。

每个场景从白模开始，最终生成 6–8 个白色背景、完整单体结果，并分别评价 identity、局部范围、语义相关性与多样性。

## 13. 失败处理

| 失败 | 用户可见行为 | 系统行为 |
| --- | --- | --- |
| Gate 未接受 | 不显示新关键词 | 拒绝 divergence 请求 |
| 上下文缺少具体对象 | 请求确认对象 | 不调用模型与知识源 |
| Gemini 失败 | 保持加载状态并尝试本地 VLM | 记录 fallback 原因 |
| 知识源失败 | 仍可返回 model-only 结果 | 记录 partial sources |
| 两模型均失败 | 显示可重试错误 | 保留继承词，不生成图片 |
| 合格候选不足 9 个 | 尝试一次 fallback | 不用泛词补足数量 |
| 请求重复 | 返回原有结果 | 使用幂等键去重 |

## 14. 验收标准

1. 调整任一滑杆后，请求 payload 与后端实际参数发生可验证变化。
2. Gate 接受前不会调用 Semantic Divergence；接受后只调用一次，重试保持幂等。
3. 正常响应包含 9–15 个候选，中文显示标签为 2–8 个字，且不存在禁用大类词。
4. 每个候选具有 target、operation、semantic anchor、完整 prompt、分数和 provenance。
5. 低温局部任务可不访问知识源；材质、仿生和高温跨域任务按规则触发对应知识源。
6. Gemini 技术或质量失败时，本地 Qwen2.5-VL 返回相同 schema；fallback 在日志和响应中可见。
7. 知识源失败不会阻塞 model-only 发散；双模型失败不会显示伪造关键词。
8. `part` 和 `material_region` 场景通过 scope 硬门，不出现明显整体越界。
9. 多 Gate、多 intent 的关键词按版本追加，继承词保留且不重复。
10. 三个基准场景均能完成关键词选择并生成 6–8 个结果，且保留白色背景、完整单体和可评估的 object identity。

## 15. 非目标

- 本阶段不更换 Qwen Observation Encoder。
- 本阶段不改变 Gate“一次只问一句范围问题”的产品定义。
- 本阶段不重新设计图片节点到 3D 节点的原位替换机制。
- 本阶段不要求 Getty 或 AskNature 成为高可用强依赖。
- 本阶段不以规则词表替代模型生成结果。
- 本阶段不进行 GitHub 提交、推送或部署。
