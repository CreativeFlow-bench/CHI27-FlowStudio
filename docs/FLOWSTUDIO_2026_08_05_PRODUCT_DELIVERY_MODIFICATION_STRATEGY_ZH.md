# FlowStudio 2026-08-05 修改策略（按产品定义交付物）

日期：2026-08-05  
状态：待按 Checkpoint 实施与验收  
产品基线：`docs/FLOWSTUDIO_PRODUCT_DEFINITION_AND_MODIFICATION_STRATEGY_V1_2_ZH.md`  
适用范围：FlowStudio 四阶段后端、前端交互、Qwen-Image 条件生成、Solution Space、远端部署与 CreativeFlow 3D 主线

交互补充策略：`docs/FLOWSTUDIO_REALTIME_OBSERVATION_MULTI_INTENT_MODIFICATION_STRATEGY_2026_08_05_ZH.md`。如本文件关于“全局只能显示一个泡泡”的旧表述与补充策略冲突，以补充策略为准：每个 IntentRevision 只有一个 Gate，但多个 IntentRevision 可以同时在主体周围显示多个泡泡；生成结果按 revision 顺序追加。

## 0.1 UI 参考源与错误案例边界（修订）

本策略的 UI 规范来源不是用户消息中附带的三张截图，而是项目目录：

`/Users/primav/Documents/博一/CHI27-FlowStudio/UI Design`

该目录中的 `Flow-Studio-Handoff` 是实现交接包，阅读优先级为：

1. `02-Product-Spec/acceptance-criteria.md`
2. `02-Product-Spec/interaction-spec.md`
3. `03-API-Spec/api-contract.yaml` 与 `data-model.md`
4. `01-Prototype/index-cn.html` / `index.html`
5. `04-Content/copy-zh.json` / `copy-en.json`

主要 UI 参考索引：

- `User Flow.png`：Import → Mark/Operate → Infer Intent → Confirm → Diverge → Select Direction → Generate 的主流程；
- `轮廓发散.png`：整体轮廓发散与方向面板；
- `局部发散.png`、`局部发散-1.png`、`局部发散-2.png`：部件/区域身份保持、局部发散和结果比较；
- `体积添加.png`、`体积添加及发散.png`：添加体积后再进入发散的操作关系；
- `Desktop - 16.png`：桌面工作区与右侧行为/发散面板；
- `Desktop - 20.png`、`Desktop - 21.png`、`Desktop - 23.png`：Solution Space、当前版本比较和版本分支；
- `2d笔刷.png`、`3d笔刷.png`、`smooth.png`、`drag.svg`：行为工具与空间标记参考。

早期用户附带的三张 `codex-clipboard-*.png` 只作为错误案例证据，具体用于记录：原始物体 identity 丢失、同一意图重复 Gate、关键词未成为生成主输入、Solution Space 破图/数量错误。它们不作为目标布局或交互规范。2026-08-05 后续提供的“多意图泡泡围绕雪人主体排列”草图是交互语义补充：允许多个用户显式提交的 IntentRevision 同时显示，但禁止同一 revision 重复弹问。

## 0. 8 月 5 日修改目标

本轮不以“接口能返回 200”或“模型能生成图片”为完成标准，而以产品定义中的用户闭环为完成标准：

```text
具体物体与用户行为
  → IntentIR 保留 asset/object/part/source context
  → Gate 只问一句范围问题
  → 用户在 More Creative 选择或输入关键词
  → 原图 + mask/part + 用户关键词 + 保持约束进入条件生成
  → Solution Space 展示 6–8 个合格结果
  → 用户选中后按需进入 Hy3D、OSS、case library 和网站同步
```

8 月 5 日修改的核心结果必须是：

1. 不再生成 `object`、`unknown` 或与原始对象无关的结果；
2. Gate 不再展示模型长解释和多个方向；
3. 用户关键词不再触发第二次 Gate，也不会被 Gemini 覆盖；
4. Qwen-Image 接收原始图像或 viewport 条件，局部任务接收 mask/part；
5. Solution Space 稳定展示 6–8 个真实、可加载、可追踪的候选；
6. 失败状态、构建版本和 3D 后续链路都能被真实验收；
7. Observation 全程常驻并增量编码/检索，Intent Send 只负责锁定 cutoff；
8. 一次工具使用形成一个 Behavior，多 stroke 不拆成多个行为圆点；
9. 多个 IntentRevision 可并行显示泡泡，多批发散结果按顺序追加而不覆盖。

## 1. 交付原则

### 1.1 产品原则

- 具体物体优先：`snowman`、`teapot`、`water gun` 等具体名词必须贯穿全链路；
- 原始对象身份优先：不得用纯文本生成假装完成局部编辑；
- 人在回路：Gate 只确认范围，细粒度方向由用户在 More Creative 选择；
- 常驻观察：编码与检索持续增量运行，用户点击 Send 只创建可审计的历史快照；
- 多意图并行：每个 revision 一个 Gate，不同 revision 可同时显示；
- 先确认再生成：Gate 前 Qwen-Image 和 Hy3D 调用数必须为 0；
- 6–8 个 Solution：默认 `4 directions × 2 candidates = 8`，质量过滤后至少返回 6 个合格结果；
- 无假成功：空对象、空产物、破图、空 mesh 或失败阶段不得标记 completed。

### 1.2 工程原则

- 先改数据契约和状态约束，再改 UI；
- 关键词选择与用户行为事件分开存储；
- 后端负责构建 GenerationSpec，前端不得拼接最终生成 prompt；
- 每个 Checkpoint 单独测试、单独部署、单独保留回滚点；
- 前端源码、`dist` 和远端运行服务必须具有相同 build id；
- 保留旧 `pipeline.py`，结构化 CreativeFlow 主线与旧流程并存。

## 2. 交付物总览

| ID | 交付物 | 用户可见结果 | 优先级 | 前置依赖 |
| --- | --- | --- | --- | --- |
| D0 | 产品契约冻结包 | 团队对 Gate、关键词和 6–8 Solution 不再有歧义 | P0 | 无 |
| D1 | SourceContext 与失败状态封闭 | 不再出现 `unknown` 生成或失败后继续 Gate | P0 | D0 |
| D2 | 单句、多 IntentRevision Gate | 每个 revision 只出现一句问题；不同 revision 的泡泡可同时围绕主体排列 | P0 | D1 |
| D3 | More Creative 关键词选择契约 | 用户点关键词不会再次触发 Gate | P0 | D0、D2 |
| D4 | 保持 identity 的条件生成 | 原始物体和非目标部件保持稳定 | P0 | D1、D3 |
| D5 | 6–8 Solution 与视觉质量 Gate | Solution Space 有 6–8 张合格可比较结果 | P1 | D4 |
| D6 | 前端 URL、状态与构建一致性 | 无破图，线上 UI 与源码一致 | P0 | D2、D3、D5 |
| D7 | 产品级端到端验收包 | snowman/teapot/water gun 三案例全链可追踪 | P1 | D1–D6 |
| D8 | 选中方案后的 3D 主线交付 | 非空 mesh、OSS、case 和网站同步可查 | P1 | D5、D7 |

## 3. D0：产品契约冻结包

### 目标

把产品定义转成前后端都能直接实现和测试的唯一契约，解决旧文档中“Gate 展示 2–4 options”和新产品定义“Gate 只问一句”的冲突。

### 修改内容

- 将 `ScopeGate`、`SourceContext`、`DivergenceSelection` 和新版 `GenerationSpec` 定为产品层公共契约；
- 明确 `DecisionIR.options` 仅供后台推理、审计和 debug，不直接进入主 UI；
- 明确 Solution Space 数量为 6–8；
- 明确关键词点击不属于 ActionAtom，不触发 re-representation；
- 明确显式 Send 创建的 Gate 不自动接受，也不因超时删除 revision；
- 明确多个 IntentRevision 可并行显示 Gate，生成结果按 revision 顺序追加；
- 明确只有用户显式 Generate 才能进入 generation。

### 交付文件

- `docs/FLOWSTUDIO_PRODUCT_DEFINITION_AND_MODIFICATION_STRATEGY_V1_2_ZH.md`
- 本文件；
- `backend/app/models/four_stage.py` 中对应 Pydantic schema；
- `frontend/src/types.ts` 中一一对应的 TypeScript 类型；
- `backend/tests/test_four_stage_product_contract.py`。

### 验收证据

- Python 和 TypeScript 字段可一一映射；
- `candidate_count` 接受 6–8，默认 8；
- Gate 数据只有一个 `question`；
- 用户关键词有独立 `selected_keywords` 和 `dimensions`；
- schema fixture 中不存在通用 `object` 测试冒充具体案例。

## 4. D1：SourceContext 与失败状态封闭

### 目标

保证每个 run 从创建开始就绑定具体 asset、具体 object、当前版本、原始图像/模型和目标部件；任何阶段失败后不能继续推进。

### 后端修改范围

- `backend/app/models/four_stage.py`
  - 增加 `SourceContext`；
  - `FourStageRun` 持久化 source context；
  - `IntentIR.target.object_type` 在生成路径上变为硬门；
- `backend/app/services/encoding/event_normalizer.py`
  - 从所有行为事件保留 `asset_id/object_type/version_id/part_id`；
- `backend/app/services/encoding/four_stage_encoding.py`
  - 通过 asset lookup 补齐具体对象；
  - 补不齐时进入 `encoding_failed`，不允许 `unknown/object`；
- `backend/app/services/pipeline/four_stage_orchestrator.py`
  - `failed/cancelled/completed` 作为终态；
  - `failed_stage` 存在时拒绝 advance、gate 和 generation；
  - 阶段异常返回明确 4xx/5xx，不再用 200 包装假成功；
- `backend/app/services/storage/four_stage_store.py`
  - 保存 source context、failed stage 和完整 error provenance。

### 前端修改范围

- `frontend/src/state/studioStore.ts`
  - 创建 run 时始终发送 `asset_id/object_type/version_id`；
  - 首个文本事件也必须带 asset context；
  - run 失败后停止轮询 Gate/Generation，并显示可重试错误。

### 验收用例

1. 只有 `glossiness`、无 asset：返回 `missing_source_context`，不生成；
2. asset 有具体 `snowman`：IntentIR 必须保留 `snowman`；
3. retrieval 抛出异常：run 停在 failed，Gate API 被拒绝；
4. 已 failed run 再 advance：返回非法状态，不覆盖历史错误；
5. 100 个 run 的 object identity missing rate 为 0。

### 完成证据

- 新增 schema/state tests；
- SQLite 查询结果显示 completed run 的 `object_type/source_image_ref` 均非空；
- 日志中不再出现 `unknown — Change ...` prompt。

## 5. D2：单句、多 IntentRevision Gate

### 目标

Gate 从“模型方向说明区”收敛为“用户范围确认器”。“单句”约束作用于每个 IntentRevision，不是全局泡泡数量限制。

### 后端修改范围

- `DecisionIR` 增加：
  - `semantic_target`；
  - `recommended_scope`；
  - `gate_question`；
  - `gate_reason_debug`（仅 debug）；
- `GeminiClient` 的系统 prompt 改为：后台可以推理多假设，但必须输出唯一 gate question；
- Rule fallback 使用确定性模板生成一句问题；
- prior case id、rationale 和 confidence 不进入 Gate 公共响应。

### 前端修改范围

- `frontend/src/components/overlays/IntentBeadOverlay.tsx`
  - 使用 `revision_id` 渲染多个 bubble；同一 revision 只渲染一个；
  - 泡泡围绕主体/目标部件稳定排列并避让碰撞；
  - 文案包含具体部件或整体轮廓；
  - 只保留接受/拒绝；
- `frontend/src/components/panels/AIBehaviorPanel.tsx`
  - 移除方向 options、长 summary 和 confidence；
  - Gate 等待期只显示简短状态；
- `frontend/src/state/studioStore.ts`
  - 删除 90 秒自动接受；
  - 删除显式 IntentRevision 的 10 秒自动隐藏；
  - 将单一 `gateOpen` 改为 revision 集合，每个泡泡独立 accept/reject；
  - accept 后进入 More Creative，reject 后记录 negative evidence；Observation 始终常驻。

### UI 参考

- `UI Design/轮廓发散.png`：整体轮廓单句确认；
- `UI Design/局部发散-1.png`：必须识别“鼻子/围巾”等语义部件；
- `UI Design/局部发散.png`：目标附近的轻量空间化介入。

本轮用户草图确认：不同 IntentRevision 的多个泡泡可以同时围绕主体排列。每个泡泡仍只能展示一句问题，不得把一个 revision 的多个模型假设拆成多个泡泡。

### 验收证据

- 同一个 `revision_id` 的 Gate bubble 数量恰好为 1；
- 快速连续提交两个 Intent 时可同时看到两个不同 `revision_id` 的泡泡，布局不重叠；
- 问句长度建议不超过 24 个中文字符；
- UI 不显示 prior case、2–4 options、rationale 或 confidence；
- 未接受的 revision 不会触发任何生成；
- Gate 前 Qwen-Image 调用计数为 0。

## 6. D3：More Creative 关键词选择契约

### 目标

让具体迁移方向真正由用户在发散面板中决定，关键词成为生成主输入，而不是新的行为证据或新的 Gate 输入。

### 数据与 API

新增或扩展：

```text
GET  /api/v1/four-stage/runs/{run_id}/divergence-options
PUT  /api/v1/four-stage/runs/{run_id}/divergence-selection
POST /api/v1/four-stage/runs/{run_id}/generation
```

`DivergenceSelection` 至少包含：

```json
{
  "target_part_id": "handle",
  "selected_keywords": ["更弯曲", "一体化连接", "哑光金属"],
  "user_text": null,
  "dimensions": {
    "shape": ["更弯曲"],
    "connection": ["一体化连接"],
    "surface": ["哑光金属"]
  }
}
```

### 后端修改范围

- 新增/调整 divergence option builder；
- 按具体 target 动态返回形状、连接、表面、功能、比例等维度；
- 保存用户原始选择，不让 Gemini 改写；
- `GenerationSpecBuilder` 只读取已保存的 Gate + DivergenceSelection；
- 用户关键词逐项进入所有候选的结构化条件或 prompt；
- 系统扩展词与用户词分字段保存。

### 前端修改范围

- 关键词点击只更新本地选择并保存 `DivergenceSelection`；
- 删除 `toggle keyword → submitIntentTextToFourStage(..., re_representation)`；
- More Creative 中按维度展示 chips；
- 支持用户输入新关键词、取消选择和清空；
- Gate 未接受前不显示可生成状态；
- Generate 按钮显式触发 generation。

### UI 参考

- 用户提供的关键词结构参考：形状、连接、表面；
- `UI Design/轮廓发散.png`：More Creative 分组布局；
- `UI Design/体积添加及发散.png`：添加体积后的结构/功能发散；
- `UI Design/Desktop - 16.png`：初始右侧发散面板层级。

### 验收证据

- 点击关键词不会产生新的 Gate 或 DecisionIR revision；
- ActionAtom/Perception history 中不出现 prompt chip；
- 选中 3 个关键词后，GenerationSpec 中 3 个词均原样存在；
- 用户取消词后，新一轮生成不再包含该词；
- 模型补充词与用户选择词可区分审计。

## 7. D4：保持 identity 的条件生成

### 目标

从纯文本生成改为基于当前物体的条件编辑，解决发散后原物体 identity 消失的问题。

### 输入条件

每个 GenerationSpec 必须包含：

- 具体 `asset_id/object_type/version_id`；
- 当前 viewport 或 canonical source image；
- 局部任务的 `part_id/mask_ref`；
- 用户选中的关键词；
- 非目标区域、连接、相机和构图保持约束；
- source image hash、mask hash、模型版本和 seed。

### 后端修改范围

- `backend/app/services/generation/four_stage_spec_builder.py`
  - 合并 SourceContext、ScopeGate 和 DivergenceSelection；
  - 删除 `unknown` goal 和固定无上下文轴 prompt；
  - 每个候选显式保存 `change` 与 `preserve`；
- `backend/app/services/generation/qwen_image_client.py`
  - 增加 image-edit/conditioned endpoint；
  - 支持 source image + mask + prompt + seed；
  - 纯文本 `/generate` 仅保留给明确的新建对象，不用于编辑已有 asset；
- `backend/app/main.py`
  - 四阶段编辑任务统一走 conditioned generation；
  - source context 缺失时拒绝 dispatch；
- `remote_worker/app.py`
  - 返回输入/输出 hash、模型版本和本地产物路径；
  - 保持局部编辑与现有 CreativeFlow staged endpoints 的兼容。

### 保持约束示例

```text
preserve snowman identity
preserve hat, eyes, scarf, body proportions and camera
change only carrot nose mask
preserve nose-to-face attachment
apply: more curved + warm wood grain
```

### 验收案例

- snowman：只改 carrot nose；
- teapot：只改 lid knob 或 handle，保留 socket；
- water gun：只改 grip 或 nozzle，保留 trigger、body、tank 和 camera。

### 完成证据

- worker request 中存在真实 source image 和 mask；
- 输出与 source 的 object category 一致；
- 非目标区域的视觉保持度通过 QA；
- 不存在只传 prompt/seed 的已有资产编辑任务。

## 8. D5：6–8 Solution 与视觉质量 Gate

### 目标

Solution Space 只展示真实可加载、保持身份且方向有差异的 6–8 个结果。

### 生成数量策略

```text
CF_MAX_DIRECTION_PATHS=4
CF_GENERATION_CANDIDATES_PER_RATIONALE=2
最大输出 = 4 × 2 = 8
前端合格输出 = 6–8
```

若首轮合格结果少于 6：

1. 只重试失败方向；
2. 使用新 seed；
3. 保持同一个 SourceContext、Gate 和用户关键词；
4. 达到重试上限仍不足 6 时标记 retryable failed；
5. 不用占位图、旧批次图片或不合格图片补数。

### 质量 Gate

每张候选必须检查：

- `source_identity_preserved`；
- `target_change_visible`；
- `non_target_region_preserved`；
- `attachment_preserved`；
- `selected_keywords_satisfied`；
- `camera_and_composition_preserved`；
- `artifact_url_accessible`；
- `duplicate_or_near_duplicate`。

建议复用/扩展 `remote_worker/part_image_vlm_gate.py`，将 identity/locality 结果写回 artifact metadata，而不是只在后端做 URL/字符串检查。

### 前端修改范围

- `SolutionSpaceRail.tsx` 显示 6–8 张候选；
- 每张卡片显示方向和用户关键词；
- 支持 preview、select、reject、drag into canvas、Make 3D；
- 生成期间逐张流式出现，但未通过 QA 的图不进入正式卡片；
- 原始 asset 始终可回看，不被候选覆盖。

### UI 参考

- `UI Design/Desktop - 20.png`：横向 Solution Space；
- `UI Design/Desktop - 21.png`：候选与当前画布版本比较；
- `UI Design/Desktop - 23.png`：多分支方案空间；
- `UI Design/局部发散-2.png`：局部候选只改变目标部件。

### 验收证据

- Solution Space 真实显示 6–8 张；
- 每张 URL 在前端 origin 下返回 200 image；
- 每张有 source、direction、keywords、seed、model、QA metadata；
- 任意两张重复度超阈值时至少一张被替换；
- 每个批次内的候选都能追溯到同一个 IntentRevision、Gate 和 DivergenceSelection；多个批次按 revision 顺序追加且不覆盖。

## 9. D6：前端 URL、状态与构建一致性

### 目标

解决后端文件存在但前端破图、远端源码与 `dist` 不一致、旧 UI 继续对外服务的问题。

### 修改内容

- 统一 `resolveArtifactUrl()`，所有 `/files/*` 和 `/api/v1/remote-worker/artifact-file` 都通过 API base 或同源代理；
- WebSocket progress 和 run refresh 使用相同 artifact normalization；
- 生成缩略图加载失败时显示明确错误，不静默显示破图；
- `frontend/dist` 由当前源码重新构建；
- 构建注入 `VITE_BUILD_ID`、git commit 和构建时间；
- `/health` 返回 backend build id、frontend build id、worker build id；
- build id 不一致时 UI 显示运维警告，端到端验收不通过。

### 交付证据

- 前端源码中不再包含多 option Gate 和 90 秒自动接受；
- 对外 `dist` 同样不包含旧逻辑；
- 6–8 张候选和 progress thumbnails 均可加载；
- 本地、远端源码和运行 bundle 的 hash/build id 对齐；
- 部署前后 smoke 结果归档。

## 10. D7：产品级端到端验收包

### 固定案例

| 案例 | 输入行为 | Gate | 用户关键词 | 必须保持 |
| --- | --- | --- | --- | --- |
| snowman | viewport + brush/annotation carrot nose | 改变胡萝卜鼻子的形状吗？ | 更弯曲、木质纹理 | 帽子、眼睛、围巾、身体、镜头 |
| teapot | select lid knob/handle + text | 改变壶盖旋钮/把手吗？ | 更圆润、一体化连接、哑光陶瓷 | 壶身、壶嘴、socket、镜头 |
| water gun | brush grip/nozzle + drag | 改变握把/喷嘴吗？ | 更粗壮、防滑纹理、柔和过渡 | trigger、body、tank、颜色、镜头 |

### 每个案例必须输出的证据

- 原始 events 和 SourceContext；
- IntentIR；
- RetrievalBundle 或 abstain；
- 每个 IntentRevision 的唯一 Gate question 与用户 action；
- DivergenceSelection；
- GenerationSpec；
- 6–8 张候选及 QA；
- 用户选择、拒绝和拖入画布记录；
- API/WS 时序；
- build id；
- 错误和重试记录。

### 负向用例

- 缺失 asset/object；
- 只有 viewport orbit；
- 用户忽略 Gate；
- 用户拒绝 Gate；
- 关键词为空；
- source image 404；
- mask 与 asset 不匹配；
- Qwen-Image 超时；
- 只有 5 张通过 QA；
- frontend/backend build id 不一致；
- retrieval 阶段异常后继续 gate。

### 验收阈值

- schema 通过率 100%；
- completed run 的 object/source missing rate 为 0；
- Gate 前 generation count 为 0；
- user keyword carry-through 为 100%；
- 每案例 6–8 张合格候选；
- artifact URL 可访问率 100%；
- 失败状态继续推进率为 0；
- 三案例均能完整回放。

## 11. D8：选中方案后的 3D 主线交付

### 触发原则

2D 候选生成完成不自动运行 Hy3D。只有用户选择候选、拖入画布或点击 Make 3D 后，才启动 3D 主线。

### 完整链路

```text
具体 request JSON
  → pipeline_transfer_engine.py
  → graph expansion / relation / rationale / pruning
  → retained_rationales 与 generated_targets 非空
  → pipeline_hunyuan3d_post.py
  → step4_mesh_worker_mv.py
  → multiview
  → mesh.glb + mesh.obj
  → OSS
  → case.json + report HTML + index
  → website sync
```

### 交付证据

- transfer requests completed/total；
- retained rationales 数量；
- generated target images 数量；
- Hunyuan3D post items 数量；
- successful meshes 数量与文件大小；
- OSS 上传状态；
- case registration 状态；
- website sync 状态；
- 前端 mesh URL 可读取；
- source OBJ 如存在则注册；缺失时作为 follow-up，不阻塞具体对象主线。

### 禁止捷径

- 不把具体对象改成 `object`；
- 不把 `4 × 2` 降为只生成 1–2 张并声称完成；
- 不跳过 3D、OSS、case 或网站同步；
- 不用空 mesh 或旧产物补位；
- `hy3d_post` 零 item 不能标记成功。

## 12. Checkpoint 实施顺序

### Checkpoint A：安全与契约

包含 D0、D1。退出标准：具体对象和 source context 成为生成硬门；失败状态封闭。

### Checkpoint B：常驻观察与多意图交互

包含 D2、D3 和多意图补充策略 C1–C6。退出标准：Observation 常驻；Send 原子锁定窗口；每 revision 一个 Gate；多个 revision 泡泡可并行显示；关键词不再触发 Gate；Generate 显式触发；多批结果按顺序追加。

### Checkpoint C：identity 与 Solution

包含 D4、D5。退出标准：条件生成生效；snowman 局部案例返回 6–8 张合格结果。

### Checkpoint D：前端与部署

包含 D6。退出标准：无破图；源码、dist 和远端服务 build id 一致。

### Checkpoint E：产品与主线验收

包含 D7、D8。退出标准：三个具体案例完整回放；选中案例得到非空 3D 和同步结果。

每个 Checkpoint 必须独立提供：

- 修改文件清单；
- schema/API 变化；
- 自动化测试；
- 真实 smoke 记录；
- UI 截图；
- 数据库/run trace；
- 已知限制；
- 回滚方式；
- 下一 Checkpoint 的前置条件。

## 13. 8 月 5 日交付清单

产品定义层：

- [x] 产品定义 V1.2；
- [x] UI 设计稿索引；
- [x] 6–8 Solution 数量定义；
- [x] 单句 Gate 与关键词职责边界；
- [x] 常驻 Observation、tool-session Behavior、IntentRevision cutoff、多泡泡与结果追加契约；
- [x] SourceContext / ScopeGate / DivergenceSelection / GenerationSpec 概念契约；
- [x] D0–D8 修改策略与验收要求。

代码实施层（按 Checkpoint 逐项完成）：

- [ ] D0 schema 与类型落地；
- [ ] D1 source context 和失败状态封闭；
- [ ] D2 单句 Gate；
- [ ] D3 关键词选择解耦；
- [ ] 常驻 Observation 与增量检索；
- [ ] tool-session Behavior 和开始/结束三视图；
- [ ] IntentRevision cutoff、多泡泡布局和 Solution batch append；
- [ ] D4 Qwen-Image 条件生成；
- [ ] D5 6–8 Solution 与视觉 QA；
- [ ] D6 URL、状态和构建一致性；
- [ ] D7 三案例产品验收；
- [ ] D8 3D/OSS/case/website 主线验收。

## 14. 最终 Definition of Done

8 月 5 日修改只有在以下结果同时成立时才算完整交付：

```text
Gate 是一句话
+ 用户关键词由人选择
+ 原图与局部条件进入生成
+ 物体 identity 保持
+ Solution Space 有 6–8 个合格结果
+ 失败不假成功
+ 前端无破图且 build 一致
+ 用户选中后 3D/OSS/case/website 主线可完成
```

其中任何一项缺失，都只能标记为对应 Checkpoint 的局部 smoke，不得标记为 FlowStudio 产品主线完成。
