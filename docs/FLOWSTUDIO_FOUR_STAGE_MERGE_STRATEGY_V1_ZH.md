# FlowStudio 四阶段单链路合并策略 V1

状态：策略稿（待用户确认后执行）
范围：前端交互链路清理与合并，最终只保留一条四阶段链路

## 1. 目标态：一条链，一个意图泡泡

用户与 3D 模型交互的那一刻起，整条四阶段链路就持续存在；所有 UI 都挂在这条链上，
不存在第二条"意图理解/发散/生成"路径。

```
交互行为(画笔/拖拽/雕刻/标注/文字)
  -> 阶段1 encoding 实时后台编码
  -> 阶段2 retrieval：意图泡泡冒出 "change silhouette?"
  -> 阶段3 点发散关键词：re-representation + Gate 泡泡(接受√/拒绝X)
  -> 阶段4 generation：8张候选逐张显示
  -> 点选拖入画布：Hy3D 生成模型
拒绝(X) -> request_revision -> 重新决策 -> 泡泡再弹
90s 超时 -> 自动接受推荐项
```

UI 承载关系（唯一）：

- 阶段1 encoding：无 UI（后台 `four-stage/runs` append 行为事件）
- 阶段2 retrieval：意图泡泡（`PlannerClarificationOverlay`），数据源 = 四阶段 run
  的 retrieval 证据 + 首轮决策摘要
- 阶段3 re-representation：发散关键词面板 + Gate 泡泡（同一个泡泡），数据源 =
  decision option 的 `divergence_seeds`；√=accept_option，X=request_revision
- 阶段4 generation：Solution Space 候选区，8 张逐张 WS 进度；拖入画布 → Hy3D

## 2. 现状盘点（两条链并存）

### 2.1 链 A（旧意图理解，仍活着）

```
composeAndInterpret(intentText 稳定后自动触发)
  -> POST /api/v1/interaction/interpret
  -> intentBubble -> PlannerClarificationOverlay("change silhouette?" + √/X)
  -> decidePlannerInterpretation 接受/拒绝
  -> runDirectionsSuggest -> POST /api/v1/directions/suggest -> 发散关键词面板
  -> 旧生成链路 requestGeneration / runCreativeSolutionSpace（已无 UI 入口，死代码）
```

证据（前端 `frontend/src/state/studioStore.ts`）：

- `composeAndInterpret`（约 L3163）：intentText 稳定后 450ms 自动调用
  `POST /api/v1/interaction/interpret`，返回值驱动意图泡泡。
- `decidePlannerInterpretation`（约 L3265）：泡泡 √/X 回调，走旧决策。
- `runDirectionsSuggest`（约 L3079）：interpret 成功后自动调用
  `POST /api/v1/directions/suggest`，生成关键词面板数据。
- `runCrossDomainDivergence`（约 L3596）：IntentComposer "Cross-domain Diverge"
  按钮入口，旧发散路径。
- `sendIntentDraft / saveIntentDraft / restoreIntentDraft / archiveIntentDraft`：
  intent-drafts 旧体系，IntentComposer 仍有 "Compose" 入口。
- `submitPlannerChat / requestGeneration / runCreativeSolutionSpace /
  runAssistanceSuggestion / continueSuggestedAction`：无 JSX 触发点，仅 store 导出。

证据（后端 `backend/app`）：

- `POST /api/v1/interaction/interpret`（`app/api/perception.py` L72）
- `POST /api/v1/directions/suggest`（`app/api/directions.py`，已标注 deprecated proxy）
- `POST /api/v1/prompt/compose`（`app/api/candidates.py`，旧提示词合成）

### 2.2 链 B（四阶段，已接一半）

```
recordActionAtom -> appendFourStageEvents（交互即编码）✅
  -> composeAndInterpret 成功后 advanceFourStageRun("retrieval") ⚠️
  -> togglePromptToken -> advanceFourStageRun（点关键词推进决策）✅
  -> awaiting_gate -> gateFourStage（accept_option / request_revision）✅
  -> generation 8张逐张 WS 进度 ✅
  -> dragCandidateIntoCanvas -> runFourStageHy3d ✅
```

证据：

- `recordActionAtom`（约 L557）每次行为 append 进四阶段 run ✅
- `composeAndInterpret` 成功后 `advanceFourStageRun("retrieval")`（约 L3212）⚠️：
  旧 interpret 完成后才推进，两链并行
- `togglePromptToken`（约 L3660）`advanceFourStageRun()` ✅，但关键词来自链 A
- Gate：`gateFourStage` + AIBehaviorPanel 选项卡 + 泡泡 gateMode（新增）
- 后端四阶段 API 完整：`four_stage_orchestrator.py`、`four_stage_retrieval.py`、
  `decision_service.py`（Gemini + rule fallback）；decision option 已带
  `divergence_seeds`（阶段3 关键词源，见 `decision_service.py` L185）

## 3. 问题本质

1. 阶段2 双源：泡泡显示链 A interpret 的结果；四阶段 retrieval 并行空转。
   同一个意图 planner/Gemini 被调用两次（一次 interpret、一次 encode+decide），
   结果可能不一致，两链无法对齐。
2. 阶段3 双源：关键词由链 A `directions/suggest` 生成；点关键词却推进链 B 决策。
   发散词与决策输出互不相干。
3. Gate 双 UI：AIBehaviorPanel 选项卡 + 泡泡 gateMode；而 "change silhouette?"
   泡泡本体仍由链 A `intentBubble` 驱动。同一个 Gate 呈现两处、数据源不同。
4. 死代码残留：旧生成函数无 UI 入口但仍导出，容易误接。

## 4. 合并计划

### P0 — 切断旧链的 UI 触发（纯前端，先做）

- `IntentComposer`：移除 "Cross-domain Diverge" 按钮绑定与 `runCrossDomainDivergence`
  调用；移除 intent-drafts "Compose" 入口（save/restore/archive/sendIntentDraft）。
- `PlannerClarificationOverlay`：`onDecide` 不再走 `decidePlannerInterpretation`，
  泡泡只承载四阶段 Gate（accept_option / request_revision）。
- 删除无 UI 入口的旧导出：`submitPlannerChat`、`requestGeneration`、
  `runCreativeSolutionSpace`、`runAssistanceSuggestion`、`continueSuggestedAction`。
- 保留 `dragCandidateIntoCanvas -> runFourStageHy3d`（属于阶段4，不是旧链）。

### P1 — 阶段2/3 数据源切换（核心合并）

- 阶段2：删除 `composeAndInterpret` 对 `POST /api/v1/interaction/interpret` 的
  自动调用。意图泡泡由四阶段 WS 事件驱动：
  - `four_stage.retrieval_completed` / `four_stage.decision_completed` 到达时，
    用 run 的 retrieval 摘要 + decision 的 `recommended_scope` / `summary` 组装
    "change silhouette?" 泡泡（level/scope 来自四阶段 decision）。
  - `interpretation` 状态不再由链 A 填充，改由四阶段 decision 派生。
- 阶段3：删除 `runDirectionsSuggest` 与 cross-domain 调用。关键词面板数据源 =
  `fourStage.decision.options[].divergence_seeds`（后端已输出）。
  `togglePromptToken` 后 `advanceFourStageRun("re_representation")`，让决策
  显式带上用户点选的 token 再进入 Gate。
- Gate：泡泡为唯一决策 UI；AIBehaviorPanel 选项卡降级为只读阶段指示（或移除）。
  90s 自动接受保留；X = `request_revision` -> 重新决策 -> 泡泡再弹。

### P2 — 后端收敛

- `/api/v1/interaction/interpret`：前端不再调用后标记 410（API 兼容，不删路由文件），
  确认无外部调用后移除。
- `/api/v1/directions/suggest`：同上；`prompt/compose` 视使用情况保留。
- 四阶段 API 补齐泡泡所需字段：`GET /runs/{id}` 返回 retrieval 摘要
  （top matches 的 prior_ir_id / case 描述 / score），供阶段2 泡泡展示。
- `intent_vlm`（qwen2.5-vl）接入后，阶段1 encode 使用 VLM 多模态编码，
  Gemini 仅作 fallback；`interaction/interpret` 的 VLM 部分并入 encode，不再单独暴露。

### P3 — 验证与回归

- 端到端：2D 画笔 -> 泡泡冒出（四阶段 retrieval+decision）-> 关键词出现
  （divergence_seeds）-> 点关键词 -> Gate 泡泡 -> 接受 -> 8 张逐张显示 -> 拖入 -> Hy3D。
- 拒绝路径：X -> request_revision -> 新 decision -> 泡泡再弹 -> 90s 未操作自动接受。
- 后端回归：147 tests + ruff（3 个既有环境失败除外）。
- 前端构建：`npm run build` 零新增错误。

## 5. 验收标准

1. 全流程只出现一条链：交互 -> 泡泡（阶段2）-> 关键词（阶段3）-> Gate 泡泡 -> 生成。
2. 同一意图 planner/Gemini 只被调用一次（后端日志可查，无并行 interpret+encode）。
3. UI 上没有任何旧入口：cross-domain diverge、intent-drafts、planner chat。
4. 拒绝走 request_revision 并重新弹 Gate；90s 超时自动接受推荐项。
5. 生成 8 张候选逐张显示进度，点选拖入才启动 Hy3D。

## 6. 部署状态（2026-08-05）

- 后端四阶段链（v14）已部署 westd :18000，全链路冒烟通过
  （创建 -> 编码 -> 检索 -> 决策 -> Gate -> 8张图）。
- 前端最新改动（进度计数 + Gate 泡泡）尚未部署（同步中断），远端为旧包。
- 合并完成后：前端 build -> 同步 dist -> 重启 http.server 5173 即生效。

## 7. 执行状态（2026-08-05 晚）

### 已完成

- P0 完成：移除 Cross-domain Diverge / intent-drafts Compose / planner chat /
  旧生成按钮的 UI 与函数；`IntentBeadOverlay` 移除；旧函数与 state 全部删除。
- P1 完成：
  - 阶段1：`recordActionAtom` 在无 run 时自动创建四阶段 run（交互即编码）。
  - 阶段2：意图文本稳定后自动追加 `intent_text_changed` 并 advance(retrieval)；
    interpretation / 意图泡泡 / 发散关键词全部由四阶段 run 派生
    （`deriveFourStageInterpretation` + `refreshFourStageUiFromRun`）。
  - 阶段3：`togglePromptToken` 把带关键词的意图文本追加进 run 并
    advance(re_representation)；Gate 泡泡（√/X）为唯一手动决策 UI，
    AIBehaviorPanel 选项卡降级为只读；90s 自动接受保留。
  - 阶段4：8 张候选逐张 WS 进度显示，点选拖入画布才启动 Hy3D（不变）。
- P2 部分完成：
  - `advance_run(target=re_representation)` 修复：重新编码（最新事件/关键词）
    -> 重新检索 -> 决策 -> 停在 awaiting_gate（`_reencode_to_gate`）。
  - `GET /runs/{id}` 已返回 retrieval 完整证据（matches/prior_judgement），
    前端直接使用，无需新增字段。
  - 偏差：`/interaction/interpret`、`/directions/suggest` 保留为兼容路由
    （后端测试仍断言其存在），前端已完全不再调用；待外部调用确认后按 410 移除。
- P3：前端 `tsc --noEmit` + `npm run build` 通过；后端 148 passed /
  3 个环境既有失败；新增 `test_advance_to_re_representation_stops_at_awaiting_gate`。
- Qwen2.5-VL 接入（阶段1 多模态编码）：
  - weste 下载 Qwen2.5-VL-7B-Instruct（16G）完成；补齐 torchvision 0.26+cu128、
    qwen-vl-utils。
  - `flowstudio_vl_planner_server.py` 部署 weste :18084（OpenAI 兼容、图文推理），
    经 westd 隧道 18085 对外；`intent_vlm` 服务定义改为可启动并纳入 auto-bootstrap。
  - 后端 `IUL_VLM_MODEL=qwen2.5-vl-planner`；编码器增加受限图片支持
    （image_refs → data URL，最多 2 张，失败跳过）。
  - 验证：阶段1 编码真实走 qwen2.5-vl-planner（fallback=False）；决策走
    Gemini-3.5-flash；全链路 retrieval → Gate → generation 通过。
- Hy3D PBR 材质（进行中）：新增 `run_hy3d_with_pbr.py` 包装脚本
  （hy3d 后逐 candidate 跑 PaintPBR OBJ + Blender GLB 转换，mesh_glb/mesh_obj
  升级为 PBR 产物），`/jobs/hy3d-from-staged` 已切到该包装；e2e 验证中。
- 初始化自动拉起（修正）：`.env` 原键名 `FLOWSTUDIO_AUTO_BOOTSTRAP_SERVICES`
  未被读取；改为 `SYSTEM_SERVICES_AUTO_BOOTSTRAP=true` +
  `SYSTEM_SERVICES_ENABLED=true`。实测：杀掉前端 http.server -> 重启后端 ->
  前端被 auto-bootstrap 自动拉起（HTTP 200）。planner_llm / qwen_image /
  intent_vlm / frontend 均在初始化 infra 列表。
- 健壮性修复：`advance(re_representation)` 从 raw_events 直接调用时
  `_reencode_to_gate` 缺少 raw_events 起始转移；已补并新增测试
  `test_advance_to_gate_from_raw_events`。
- 拒绝链路实测：request_revision -> 新 decision -> 重新弹 Gate（awaiting_gate），
  decision_id 更换。

### 验收证据（2026-08-05 深夜）

- 前端 dist JS 扫描：`interaction/interpret`=0、`directions/suggest`=0、
  `intent-drafts`=0；`four-stage/runs` 存在。旧链调用在产物层面清零。
- 后端 150 passed / 3 个环境既有失败；ruff 干净。
- 四阶段真实 e2e（run_hy3d=true）：VL 编码 -> Gemini 决策 -> Gate -> 生成，
  产物含 `mesh_pbr.glb` / `mesh_pbr.obj`（PBR 材质已接入）。
- PBR worker e2e：PaintPBR 产出 diffuse/metallic/roughness 三张贴图 +
  GLB 转换成功，summary items 升级为 PBR 路径。
- auto-bootstrap 实测、拒绝链路实测均通过。
- 部署：前端 dist（index.html + 新 JS/CSS，wasm 复用）已同步远端并清空旧 bundle；
  后端 orchestrator 已同步并重启；远端全链路手工验证通过
  （raw_events -> encoding -> retrieval(5 matches) -> awaiting_gate(3 options
  + divergence_seeds) -> gate -> generation）。

### 验收对照

1. 全流程单链：交互 -> 泡泡（阶段2）-> 关键词（阶段3）-> Gate 泡泡 -> 生成 ✅
2. 同一意图后端只走一次四阶段（无并行 interpret+encode）✅
3. UI 无旧入口（cross-domain / intent-drafts / planner chat）✅
4. 拒绝走 request_revision 并重弹 Gate；90s 自动接受 ✅（后端 resolve_gate 已支持）
5. 8 张逐张进度 + 拖入才启动 Hy3D ✅
