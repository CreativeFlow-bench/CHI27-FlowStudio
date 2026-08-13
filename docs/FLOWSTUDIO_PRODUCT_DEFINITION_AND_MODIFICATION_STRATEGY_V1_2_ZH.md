# FlowStudio 产品定义与四阶段修改策略 V1.2

日期：2026-08-05  
状态：产品基线与实现修改策略（供前后端、模型和 UI 联调使用）

## UI 规范来源

本产品定义使用项目 UI 交接目录作为唯一视觉与交互参考：

`/Users/primav/Documents/博一/CHI27-FlowStudio/UI Design`

其中 `Flow-Studio-Handoff/02-Product-Spec`、`01-Prototype`、`03-API-Spec` 和 `04-Content` 优先于临时截图。用户附带的三张 `codex-clipboard-*.png` 是当前系统错误案例，不是目标 UI 设计稿。
适用仓库：`CHI27-FlowStudio`

关联文档：

- `docs/FLOWSTUDIO_2026_08_05_PRODUCT_DELIVERY_MODIFICATION_STRATEGY_ZH.md`
- `docs/FLOWSTUDIO_REALTIME_OBSERVATION_MULTI_INTENT_MODIFICATION_STRATEGY_2026_08_05_ZH.md`
- `docs/FLOWSTUDIO_FOUR_STAGE_DEEPSEEK_IMPLEMENTATION_STRATEGY_V1_ZH.md`
- `docs/FLOWSTUDIO_INTERACTION_FLOW_SPEC_V1_ZH.md`
- `docs/FLOWSTUDIO_FRONTEND_STRATEGY_V1_ZH.md`
- `docs/FLOWSTUDIO_CONTEXTUAL_DIVERGENCE_FRAGMENT_PIPELINE_V1_ZH.md`

## 0. 本版本要解决的核心问题

当前系统可以调用后端、Planner、Gemini、Qwen-Image 和 Hy3D，但“能生成”不等于“实现了 FlowStudio”。当前最严重的问题是：

1. 发散后原始物体的 identity 丢失；
2. Gate 泡泡中出现大量模型解释和多个方向，打扰用户决策；
3. 用户选的关键词没有成为生成的主导条件；
4. 关键词点击后又触发一次方向推理，导致 Gate 与 More Creative 互相覆盖；
5. Solution Space、图片 URL、失败状态和线上构建版本不稳定。

本文件将产品定义收敛为一条不可歧义的主线：

```text
观察具体对象的行为
  → 编码当前意图与目标部件
  → 只用一句话确认改变范围
  → 用户在 More Creative 中选择/输入关键词
  → 带原图、局部 mask 和保持约束进行条件生成
  → Solution Space 展示 6–8 个可比较结果
  → 用户选择结果后，按需进入 Hy3D、OSS、case library 和网站同步
```

## 1. 产品定义

### 1.1 产品定位

FlowStudio 是一个**保留原始对象身份的行为驱动设计发散工作台**。

它不是普通的“输入 prompt → 生成图片”工具，也不是一个只根据模型聊天内容自动替用户设计的系统。它观察用户对具体模型的旋转、停留、点选、绘制、拖拽、平滑、添加体积、文字描述和参考资料，把这些行为编码成可追踪的设计意图，再让用户用低负担的方式选择发散方向，最后生成可比较的形态、连接和表面方案。

### 1.2 核心价值

FlowStudio 必须同时满足四个价值：

| 价值 | 产品含义 | 不可破坏的验收条件 |
| --- | --- | --- |
| 身份保持 | 生成结果仍然是用户当前的具体物体 | 不得使用 `object`/`unknown` 代替具体物体；每张结果可追溯到 source asset |
| 目标局部性 | 用户只改把手、鼻子、接口或轮廓时，非目标区域保持稳定 | 必须传入 source image/viewport、part 或 mask；视觉 QA 检查 locality |
| 人在回路 | AI 负责编码、检索和提出一句轻确认，不替用户选择细粒度方向 | 每个 IntentRevision 的 Gate 只有一句问题；不同 revision 可并行显示；生成必须由用户显式触发 |
| 可发散可收束 | 关键词可以产生足够多样的候选，但每个候选都能解释“改了什么、保留什么” | Solution Space 展示 6–8 张合格结果；每张带方向、关键词、seed 和来源 |

### 1.3 产品边界

FlowStudio 负责：

- 观察和编码用户行为；
- 识别具体对象、部件、区域和操作范围；
- 检索设计状态先验；
- 给出一句范围确认问题；
- 提供结构化发散关键词；
- 生成保留身份的 2D 方案；
- 将用户选中的方案接入可选 3D、OSS、case library 和网站主线。

FlowStudio 不负责：

- 在用户没有明确意图时自动生成一堆方案；
- 用模型长段落代替用户的设计决策；
- 把先验案例名直接当成用户看到的方向；
- 在没有具体物体和原始条件图时生成“通用对象”；
- 用一个纯文本 prompt 假装完成局部编辑；
- 用占位图、破图 URL 或空 mesh 标记流程成功。

## 2. 四阶段系统定义

四阶段是后端能力边界，不是四个需要用户逐一阅读的聊天步骤。

### 阶段一：Encoding —— 把行为变成 IntentIR

输入包括：

- 具体 asset、object type、当前版本；
- viewport 观察、旋转、缩放和停留；
- part hover、part select、brush、drag、smooth、annotation、primitive add；
- 用户文本；
- 参考图、参考模型和当前截图；
- 最近的选择、拒绝、撤销和比较行为。

输出必须至少包含：

```json
{
  "target": {
    "asset_id": "asset_xxx",
    "object_type": "teapot",
    "part_id": "lid_knob",
    "region": null
  },
  "intent": {
    "operation": "explore_variations",
    "scope": "part",
    "goal": "make the lid knob more organic",
    "constraints": ["preserve socket", "preserve non-target body"]
  },
  "observations": {
    "source_image_ref": "...",
    "mask_ref": "...",
    "behavior_summary": "..."
  }
}
```

只旋转视角、只停留或只浏览候选，不得直接编码为生成意图。

### 阶段二：Retrieval —— 只提供先验证据

检索回答：

- 用户当前处于什么设计状态；
- 该对象/部件有哪些相近的设计状态先验；
- 可能适合哪些发散维度；
- 是否应该 abstain。

检索不得回答“用户一定想要哪个具体风格”，也不得把案例名、长 rationale 和未经用户选择的方向直接投影到 Gate。

至少按以下字段过滤：

```text
object_type
target_level
part_id / semantic target
operation
design_state
language
```

最高分不足、对象类型缺失或 top-1/top-2 冲突时，必须暂停进入 Gate，先要求补充对象/目标信息。

### 阶段三：Re-representation —— 生成一句 Gate 问句

Gemini 或本地 fallback 可以在后台为每个 IntentRevision 生成多假设 `DecisionIR`，但该 revision 在前端只展示一个经过压缩的 Gate 问句。不同 revision 的问句可以同时作为多个泡泡显示。

Gate 问句模板：

```text
你想改变这个把手的形状吗？
你想改变这个物体的整体轮廓吗？
你想改变这个区域的表面材质吗？
```

规则：

- 每个 IntentRevision 只问一句；
- 句子必须包含具体目标或“整体轮廓”；
- 不展示模型长 summary、多个 option、confidence、prior case id；
- 用户接受后才打开 More Creative；
- 用户拒绝时记录 negative evidence；显式 Intent Send 创建的 revision 不因 10 秒未操作而自动删除、接受或阻止下一次显式提交；
- 不得 90 秒后自动接受方向或自动生成。

### 阶段四：Divergence + Generation —— 关键词和条件生成

第四阶段分为两个明确动作：

1. **发散面板**：给用户可点选、可输入、可删除的关键词材料；
2. **生成器**：把用户选择与原图、目标 mask、保持约束组合成 GenerationSpec。

用户关键词是设计方向的主导输入。模型可以补充同义词或解释，但不得覆盖、删除或改写用户已选的有效关键词。

默认前端目标是 **6–8 个 Solution**。实现上可以采用：

```text
4 个发散方向 × 每个方向 2 个候选 = 8 个候选上限
```

如果某些候选未通过 identity/locality/关键词质量 Gate，可以减少到 6 个，但不得把未通过质量 Gate 的图当作有效结果补位。

## 3. 前端产品结构

### 3.1 Perception：只观察

左上角 Perception 只展示低阶、可验证的事实：

- User is moving the view.
- User is observing the part.
- User is drawing on the silhouette.
- User is drawing on the handle.
- User added a primitive volume.

禁止在 Perception 中展示：

- Change part?
- Structural + Aesthetic
- explore_shape
- 先验案例名
- 自动生成结论。

### 3.2 Intent Bubble：每个 revision 只做一件事

Bubble 位于当前目标附近或画布空白区域。它只确认：

- 改整体轮廓；
- 改某个具体部件；
- 改材质/表面区域。

用户看到的是一句问题和明确的 Accept/Reject 操作，不是一个聊天窗口。

“一句问题”是每个 IntentRevision 的内容约束，不是全局数量限制。用户快速连续点击 Intent Send 时，每次提交都会原子锁定一个新的历史窗口并形成新的 IntentRevision；多个 revision 的泡泡可以同时围绕主体或对应部件排列。系统必须禁止同一 revision 因模型 refine、轮询或重连重复弹问，但不能为了保持单泡泡而隐藏后续用户显式提交的意图。

多个泡泡可以并行确认；实际生成按 `intent_seq` 顺序写入 Solution Space。前一个批次完成后，后一个批次追加在其后，不清空、不覆盖前一批结果。

### 3.3 More Creative：用户拼合方向

More Creative 是右侧发散面板，不是 AI 对话区。

推荐的三个维度：

#### 形状

```text
[更弯曲] [更粗壮] [向外延伸] [贴近壶身]
```

#### 连接

```text
[一体化连接] [清晰的插接结构] [柔和过渡] [可折叠连接]
```

#### 表面

```text
[温润的木质感] [哑光金属] [细密防滑纹理] [柔软织物]
```

部件不同，维度可以变化。例如鼻子可以是“形状/功能/表面”，把手可以是“形状/连接/人体工学”，整体轮廓可以是“轮廓/比例/风格”。

### 3.4 Solution Space：6–8 个可比较结果

Solution Space 的职责是让用户比较，而不是让用户阅读模型解释。

每张卡片至少包含：

- 结果缩略图；
- 方向标签；
- 用户选中的关键词；
- `preserved_constraints` 摘要；
- identity/locality QA 状态；
- 选择、拒绝、拖入画布和 Make 3D 操作。

卡片不能显示破图；图片必须使用前端可访问的代理或签名 URL。

## 4. 统一数据契约

四阶段之间不得传递未校验的自由字典作为最终业务语义。至少保留以下对象：

### 4.1 SourceContext

```json
{
  "asset_id": "asset_xxx",
  "object_type": "snowman",
  "version_id": "ver_xxx",
  "source_image_ref": "/api/v1/assets/asset_xxx/viewport.png",
  "source_model_ref": "/files/.../source.obj",
  "target_part_id": "carrot_nose",
  "target_mask_ref": "/files/.../mask.png",
  "camera_ref": "camera_xxx"
}
```

### 4.2 ScopeGate

```json
{
  "gate_id": "gate_xxx",
  "intent_revision_id": "intent_rev_02",
  "intent_seq": 2,
  "target": "carrot_nose",
  "scope": "part",
  "question": "你想改变这个胡萝卜鼻子的形状吗？",
  "status": "pending | accepted | rejected | ignored",
  "user_action": "accept | reject | ignore"
}
```

### 4.3 DivergenceSelection

```json
{
  "intent_revision_id": "intent_rev_02",
  "scope": "part",
  "target_part_id": "carrot_nose",
  "selected_keywords": ["更弯曲", "木质纹理"],
  "keyword_mode": "append",
  "base_keywords": ["一体化连接"],
  "cumulative_keywords": ["一体化连接", "更弯曲", "木质纹理"],
  "user_text": "更像手工雕刻的胡萝卜",
  "dimensions": {
    "shape": ["更弯曲"],
    "connection": [],
    "surface": ["木质纹理"]
  }
}
```

关键词选择不得写回成新的行为 atom；它属于对应 IntentRevision 的 `DivergenceSelection` 和生成审计记录。前一 revision 已接受时，默认按 `base_keywords + selected_keywords` 去重追加；前一 revision 被拒绝时，被拒关键词只作为 negative evidence，不进入正向累计词。

### 4.4 GenerationSpec

```json
{
  "source": {
    "asset_id": "asset_xxx",
    "object_type": "snowman",
    "image_ref": "...",
    "mask_ref": "..."
  },
  "target": {
    "scope": "part",
    "part_id": "carrot_nose"
  },
  "selected_keywords": ["更弯曲", "木质纹理"],
  "preserve": [
    "preserve snowman identity",
    "preserve eyes, hat, scarf, body and camera",
    "preserve attachment to face"
  ],
  "candidate_count": 8,
  "seeds": [42, 143, 244, 345, 446, 547, 648, 749]
}
```

## 5. 修改策略

### P0：先切断错误成功路径

目标：没有具体对象、原图和目标上下文时，不得进入生成。

工作项：

- `IntentIR.target.object_type` 为空时停止，不用 `object` 或 `unknown` 兜底；
- run 创建时始终携带 `asset_id/object_type/version_id`；
- 失败阶段写入 `failed_stage` 和错误详情后，禁止继续 advance 或 gate；
- 删除前端 90 秒自动接受；
- Gate 前 Qwen-Image 调用数必须为 0；
- 统一生成 artifact URL，前端不再直接拼接后端相对路径。

验收：给一个只有 `glossiness` 的输入，系统必须要求补充具体对象/目标，不得生成 `unknown — ...`。

### P1：恢复 source identity 链

工作项：

- 前端 capture 当前 viewport screenshot；
- 2D annotation/3D brush 结束时，将行为、mask、截图和 asset context 作为一次事件提交；
- `EvidenceAssembler` 把 source image、局部 mask、part 语义和非目标约束送入 re-representation；
- Qwen-Image 改为 image-edit/conditioned 路径，至少支持 source image + mask + prompt；
- `GenerationSpec` 保存 source image hash、mask hash、camera、part id 和 model revision；
- 生成后执行 identity/locality QA。

验收：对雪人胡萝卜鼻子做局部改变时，帽子、眼睛、围巾、身体、镜头和背景保持；只允许鼻子变化。

### P2：Gate 降级为每 revision 一句话，并支持多泡泡

工作项：

- 后端 `DecisionIR` 可保留多假设，但增加 `gate_question`、`semantic_target` 和 `recommended_scope`；
- 前端为每个 IntentRevision 只渲染一句问题和 Accept/Reject，不同 revision 可同时显示；
- summary、rationale、confidence、prior case id 移到 debug/history，不进入主交互；
- 用户拒绝后记录 negative evidence；新一次显式 Intent Send 仍可创建新的 bubble；
- Gate 通过后才展开 More Creative。

验收：同一个 revision 只出现一个问题，不出现 2–4 个方向段落；两个显式提交的 revision 可以同时显示两个稳定、互不重叠的泡泡。

### P3：重接关键词发散

工作项：

- 关键词点击不再调用 `re_representation`；
- 引入 `DivergenceSelection`，与行为 atom 分离；
- 关键词按目标生成形状/连接/表面等维度；
- 用户选中的关键词必须逐项进入每个候选 prompt 或结构化 condition；
- GenerationSpec 记录“用户选择了什么”和“系统必须保留什么”；
- 取消发散温度/评分严谨度这类未接入生成契约的伪控制，或把它们正式加入可审计 spec。

验收：用户选中“更弯曲 + 一体化连接 + 哑光金属”后，8 个候选都能追溯到这三个词，并沿不同轴变化。

### P4：生成与质量 Gate

工作项：

- 前端 Solution Space 目标为 6–8 张合格结果；
- 后端默认 `4 directions × 2 candidates`，不够 6 张时只允许重试，不允许用占位图补齐；
- 质量 Gate 检查：identity、locality、用户关键词一致性、保留约束、候选多样性、URL 可访问性；
- 全部失败时状态为 retryable failed，不能 completed；
- 2D 结果被用户选中或拖入画布后，才触发 Hy3D。

验收：Solution Space 中显示 6–8 张真实可加载图片；每张都有 prompt/seed/source/QA 追踪信息。

### P5：CreativeFlow 完整主线

当用户选择 Make 3D 或 case 需要 3D 时，继续执行完整链路：

```text
concrete request JSON
  → pipeline_transfer_engine.py
  → retained_rationales / generated_targets 非空
  → pipeline_hunyuan3d_post.py
  → step4_mesh_worker_mv.py
  → multiview + mesh.glb + mesh.obj
  → OSS
  → case.json + report HTML + index
  → website sync
```

旧 `pipeline.py` 保留；不得为了四阶段 UI 看起来完成而跳过 3D、OSS、case library 或 website sync。

### P6：构建、部署和可观测性

工作项：

- 前后端源码、构建产物和运行服务记录同一个 git commit/build id；
- 部署后检查 `frontend/dist` 是否包含当前源码的 Gate/关键词逻辑；
- 统一 `/api/v1/remote-worker/artifact-file` 或签名 URL；
- 每个 run 页面可查看 event → IntentIR → retrieval → Gate → DivergenceSelection → GenerationSpec → artifact；
- 统计以下指标：
  - object identity missing rate；
  - source image/mask missing rate；
  - Gate accept/reject/ignore rate；
  - user keyword carry-through rate；
  - identity/locality QA pass rate；
  - 6–8 solution completion rate；
  - Hy3D non-empty mesh rate；
  - case/website sync rate。

## 6. UI 设计稿索引

以下设计稿是当前产品视觉和交互的参考基线。文件名保留原样，路径相对于仓库根目录。

### 6.1 整体流程与桌面布局

| 参考图 | 作用 | 应保留的产品含义 |
| --- | --- | --- |
| [Desktop - 16.png](<../UI Design/Desktop - 16.png>) | 初始整体观察 | Perception 只描述整体观察；右侧 More Creative 先按 Whole structure 展示维度 |
| [Desktop - 20.png](<../UI Design/Desktop - 20.png>) | Solution Space 展示 | 上方横向候选条；用户比较多张方案；当前产品目标为 6–8 个 solution |
| [Desktop - 21.png](<../UI Design/Desktop - 21.png>) | 候选切换/版本比较 | 候选结果与当前画布版本并行存在，不覆盖原始资产 |
| [Desktop - 23.png](<../UI Design/Desktop - 23.png>) | 多分支方案空间 | 保持 source identity，展示不同发散分支；不把分支说明塞进 Gate |
| [User Flow.png](<../UI Design/User Flow.png>) | 完整用户流程 | 白模/空白界面 → 行为操作 → 是否接受介入 → 发散方向选择 → 多样内容生成 → 选择 → 迭代/3D |

### 6.2 轮廓与局部发散

| 参考图 | 作用 | 当前修改后的解释 |
| --- | --- | --- |
| [轮廓发散.png](<../UI Design/轮廓发散.png>) | 整体轮廓发散 | Gate 只问“改变整体轮廓吗？”；接受后右侧展示形状/比例/表面关键词 |
| [局部发散.png](<../UI Design/局部发散.png>) | 局部目标与发散 | 目标附近有轻量确认；正式版本收敛为一句目标明确的问题 |
| [局部发散-1.png](<../UI Design/局部发散-1.png>) | 具体语义部件 | 证明 Gate 必须能说清楚“鼻子/围巾/把手”，而不是只说 part |
| [局部发散-2.png](<../UI Design/局部发散-2.png>) | 局部候选结果 | Solution Space 候选只改变目标部件，主体身份和非目标区保持 |
| [体积添加.png](<../UI Design/体积添加.png>) | 添加基础体积 | primitive add 是行为证据；它可以引发轮廓/体积相关发散，但不能直接等于生成意图 |
| [体积添加及发散.png](<../UI Design/体积添加及发散.png>) | 添加体积后的发散 | add primitive 后仍需识别目标范围，关键词选择和生成必须由用户确认 |

### 6.3 2D/3D 行为输入

| 参考图 | 作用 | 后端必须记录 |
| --- | --- | --- |
| [2d笔刷.png](<../UI Design/2d笔刷.png>) | 2D 外轮廓/区域标注 | stroke、bbox、projection、screenshot、mask/ref、asset id |
| [3d笔刷.png](<../UI Design/3d笔刷.png>) | 3D 局部区域和方向标注 | part/region、工具类型、方向向量、影响半径、mask、viewport |
| [drag.svg](<../UI Design/drag.svg>) | Drag 工具图标 | 只作为工具资产，不作为意图文本 |
| [smooth.svg](<../UI Design/smooth.svg>) | Smooth 工具图标 | 只作为工具资产，不作为意图文本 |
| [smooth.png](<../UI Design/smooth.png>) | Smooth 工具视觉稿 | 与前端按钮样式保持一致 |

### 6.4 设计交付包

| 参考包 | 用途 |
| --- | --- |
| [Flow-Studio-Handoff.zip](<../UI Design/Flow-Studio-Handoff.zip>) | 设计交付原包；用于查找组件、尺寸和原始导出，不替代仓库中的可追踪 PNG/SVG 参考图 |

## 7. 产品级验收清单

一条链路只有同时满足以下条件，才可以标记为 completed：

- [ ] source asset 存在且 `object_type` 具体；
- [ ] IntentIR 包含 asset、target、scope、source image 或 model ref；
- [ ] Retrieval 有可审计结果或明确 abstain；
- [ ] 每个 IntentRevision 的 Gate 只显示一句问题；
- [ ] 多个 IntentRevision 可以同时显示多个泡泡，同一 revision 不重复；
- [ ] 多批生成结果按 IntentRevision 顺序追加，不覆盖已有 Solution；
- [ ] Gate 前没有 Qwen-Image/Hy3D 生成；
- [ ] 用户关键词单独记录，未被写入行为 atom；
- [ ] GenerationSpec 包含原图、mask/part、用户关键词和 preserve constraints；
- [ ] 默认生成 6–8 个 Solution，少于 6 个时进入重试或失败，不用占位图；
- [ ] 每张图通过 identity、locality、关键词一致性和 URL 可访问性检查；
- [ ] 用户选择结果后才触发 Hy3D；
- [ ] 需要 3D 时得到非空 `mesh.glb` 与 `mesh.obj`；
- [ ] OSS、case library 和 website sync 状态可查询；
- [ ] 前端源码、dist 和远端运行服务具有同一 build id；
- [ ] 失败不会返回 HTTP 200 的假成功 run。

## 8. 修改优先级

```text
P0  identity/source context、unknown/object 禁止生成、失败状态封闭、URL 修复
P0  Gate 一句话 + 删除自动接受
P0  关键词与 Gate 解耦，用户关键词成为 GenerationSpec 主输入
P1  source image/mask 条件生成与 identity/locality QA
P1  Solution Space 6–8 个真实候选与选择/版本管理
P1  构建版本一致性、run trace 和指标
P2  contextual divergence、KG 扩展、候选排序和研究指标
P2  Hy3D/OSS/case library/website 的完整主线验收
```

任何实现分支都不得通过删除检索、使用通用 `object`、跳过原图条件、减少 Solution 数量、跳过 Hy3D 或返回占位图来“快速变绿”。
