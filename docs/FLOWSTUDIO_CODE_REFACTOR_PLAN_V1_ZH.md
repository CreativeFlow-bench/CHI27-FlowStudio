# FlowStudio 代码结构重整规划 V1（结构化清理“屎山”）

日期：2026-08-03  
依据：当前代码审计（2026-08-03）+ 现有前后端交互契约 + 重设计文档
（`FLOWSTUDIO_PLANNER_TARGET_SUPERVISION_REDESIGN_V1_ZH.md`）

## 0. 目标

在不改变现有前后端交互契约、不重写生成主链的前提下，把代码结构从
“单体文件 + 复制粘贴 + 死代码”重整为“分层、单一职责、可测试”。

## 1. 现状证据（屎山清单）

| 问题 | 证据 | 危害 |
| --- | --- | --- |
| 前端单体 | `frontend/src/main.tsx` 8318 行（含类型/组件/状态/工具/视图） | 改动互相踩；难测试；上手成本高 |
| 后端单体 | `backend/app/main.py` 5582 行 | 路由与业务 helper 混在一起 |
| worker 单体 | `remote_worker/app.py` 3474 行 | job 编排全部堆一处 |
| 巨型闭包 | ThreeViewportInner 内单个 effect 约 725 行 | 场景/雕刻/指针/undo 全耦合，易出白屏类事故 |
| 复制粘贴 | `ZH_LABELS`/标签清洗逻辑在 3 个 service 各存一份 | 改语义名要改三处 |
| 死代码/遗留 | 25 处 TODO/legacy/stub/deprecated；`AAT_NOUN_BANK`、`buildLocalAnalogyDirections`、`visual_inspiration`（Pinterest 静态板）仍可渲染；`runBrushAction/runSculptPreview` 后端路径冗余 | 混淆“什么是真路径”；静态灵感板违反 More Creative 口径 |
| 状态域混乱 | undo 仍两套（editorScene 命令栈 + 部分组件快照）；sculpt/acceptTarget 等散在组件 state | 状态难还原、难测试 |

## 2. 不可破坏的交互契约（重构基线）

### 2.1 REST API（保持路径与语义不变）

```text
POST/GET /api/v1/sessions; PATCH /api/v1/sessions/{id}
POST /api/v1/assets; POST /api/v1/assets/upload; GET/PATCH /api/v1/assets/{id}
POST/GET /api/v1/assets/{id}/versions; GET /api/v1/assets/{id}/parts
POST /api/v1/sessions/{id}/actions; GET /api/v1/sessions/{id}/actions
POST /api/v1/annotations|brush-masks|smooth-operations|primitive-additions|drag-operations|focus-observations
POST/GET/PATCH /api/v1/intent-drafts; POST /api/v1/sessions/{id}/episodes
POST /api/v1/interaction/interpret; GET /api/v1/sessions/{id}/perception/latest
GET/PUT /api/v1/sessions/{id}/live-signals; GET /api/v1/sessions/{id}/snapshot
POST /api/v1/interpretations/{id}/decision
POST /api/v1/directions/suggest|cross-domain; GET/PATCH /api/v1/directions/{id}; GET /api/v1/sessions/{id}/directions
POST /api/v1/prompt/compose
POST /api/v1/generation/replace|drag|diverge; GET /api/v1/jobs/{id}; GET /api/v1/jobs/{id}/candidates
POST /api/v1/candidates/{id}/accept|reject|preview|commit|hy3d|fit
POST/GET /api/v1/cases; POST /api/v1/geometry/{op}; POST /api/v1/render/{op}
POST /api/v1/viewport-segmentation; GET/POST /api/v1/artifacts
```

### 2.2 WebSocket 事件（保持 type 不变）

```text
ack | perception_updated | interaction_interpretation | live_signals_updated
| action_atom_created | intent_draft_saved | intent_episode_submitted
| planner_interpretation_decision | cross_domain_directions | directions_updated
| prompt_tokens_composed | job_update | candidate_ready | stage_update
| case_saved | reference_image_attached | reference_model_attached
| asset_version_created | 各 tool committed 事件
```

### 2.3 数据对象（保持字段兼容）

Session/Asset(+versions)/Part/ActionAtom/IntentDraft/IntentEpisode/InteractionInterpretation
（含 semantic_targets/supervision_votes）/SemanticTarget/AnalogyDirection/
CrossDomainDivergenceResponse（metadata.question/groups/contextual_fragments）/
ContextualFragment/Candidate/Job/Case。

## 3. 重构原则

1. **行为优先**：先抽文件、后改逻辑；每步“移动即编译通过”。
2. **契约冻结**：REST 路径、WS type、字段名、前端状态域入口不变（§2）。
3. **小步可验证**：每阶段有构建 + 无头渲染 + pytest + 关键 API smoke 回归。
4. **删除要证据**：删死代码前先确认无引用（`rg`）。
5. **不顺手重写**：生成主链、CreativeFlow KG 管线、模型部署不动。

## 4. 目标结构

### 4.1 前端 `frontend/src/`

```text
src/
├── main.tsx                 # 入口 + 组装（目标 <500 行）
├── types.ts                 # 全部共享类型（Asset/Interpretation/SemanticTarget/…）
├── editorScene.ts           # 已有：几何数据模型 + 命令栈
├── api.ts                   # api()/WS 封装、API_BASE/WS_BASE、端点常量
├── labels.ts                # ZH/EN 语义标签映射（前端需要时）
├── components/
│   ├── StudioShell.tsx      # 布局（header/perception/canvas/sidebar/composer）
│   ├── ThreeViewport.tsx    # 渲染器入口（瘦壳）
│   ├── viewport/
│   │   ├── scene.ts         # 场景/相机/灯光/GLB-OBJ-PLY 加载
│   │   └── sculptEngine.ts  # 笔刷/抓取/平滑算法 + 投影圈（从 725 行 effect 抽出）
│   ├── panels/
│   │   ├── PerceptionPanel.tsx
│   │   ├── AIBehaviorPanel.tsx
│   │   ├── MoreCreativePanel.tsx
│   │   ├── SolutionSpaceRail.tsx
│   │   └── IntentComposer.tsx
│   ├── overlays/
│   │   ├── PlannerClarificationOverlay.tsx
│   │   ├── IntentBeadOverlay.tsx
│   │   └── SculptGLModal.tsx
│   └── menu/StudioMenu.tsx
├── state/
│   ├── studioStore.ts       # session/asset/actionAtoms/drafts/directions/candidates/jobs
│   └── perceptionStore.ts   # liveSignals/perception/creativeState
└── hooks/
    ├── useWebSocket.ts
    └── useGeneration.ts
```

说明：是否引入 Zustand 由 P1 拆件时评估；若引入，只替换内部状态实现，
对外（组件 props/context）接口不变。

### 4.2 后端 `backend/app/`

```text
app/
├── main.py                  # 组装 app + 静态挂载 + 精简路由（目标 <1500 行）
├── api/                     # 已拆：directions/perception/perception_flow/solution_space/generation
│   └── assets.py            # 新增：assets/versions/parts 从 main.py 迁出
├── models.py                # 保持单文件（拆域可选，P2）
└── services/
    ├── signals/             # cognition_supervisor / gui_interaction_supervisor /
    │                        # semantic_language_supervisor / target_fusion
    ├── intent/              # interaction_understanding / multimodal_intent_predictor / design_state_ir
    ├── divergence/          # contextual_divergence / contextual_graph_policy /
    │                        # fragment_decoder / knowledge_adapters / semantic_labels(新共享)
    ├── generation/          # generation_orchestrator / creativeflow_adapter /
    │                        # geometry_worker / render_preview_worker / part_lifecycle / autopartgen_adapter
    ├── storage/             # studio_store / job_store / websocket_manager
    └── shared/              # mesh_utils / labels
```

## 5. 分阶段执行计划

### Phase P0：止血（约 0.5–1 天）

目标：消除复制粘贴与明显死路径，降低“屎味”不碰结构。

1. 新建 `backend/app/services/shared/labels.py`：合并 3 份 ZH_LABELS +
   `_zh_label/_clean_part_label`，三个 supervisor/contextual_divergence 改为 import。
2. 删除/禁用 `visual_inspiration`（Pinterest 静态板）及其 `visualInspirationItems`；
   More Creative 默认只走 contextual 词片。
3. 清理 `AAT_NOUN_BANK`/`aatNounPromptTokens`/`buildLocalAnalogyDirections`
   （contextual 已接管；旧方向 UI 分支若保留则标注 legacy 并仅作降级）。
4. 删除 `runBrushAction`/`runSculptPreview` 冗余后端几何调用（按钮已走前端雕刻；
   `createPrimitive`（Add）保留后端路径）。
5. 运行 `rg` 确认无引用后删除死代码；加 `pytest` 覆盖 labels 共享。

验收：构建通过；无头渲染无 JS 错误；`/interaction/interpret` +
`/directions/suggest`（semantic_target）smoke 通过；无未使用 import 告警。

### Phase P1a：前端拆分（约 1–2 天）

目标：main.tsx 从 8300 行降到 <1000 行；ThreeViewport effect 从 725 行降到 <200 行。

1. `types.ts`：搬出全部共享类型（含 SemanticTarget/ContextualFragment/EditorSnapshot）。
2. `api.ts`：搬出 `api()`/WS 封装、API_BASE/WS_BASE、端点常量与上传 helper。
3. `viewport/scene.ts`：搬出场景/相机/灯光/加载/resetModel/fitLoadedModel。
4. `viewport/sculptEngine.ts`：搬出笔刷/抓取/平滑/投影圈/指针状态（从 effect 闭包抽为
   可注入的类，接口：`begin/continue/finish(pointer, mesh)`）。
5. `panels/overlays/menu`：按 JSX 区块机械搬移（不改渲染逻辑）。
6. `state/`：评估用 Zustand 收敛 studio 状态；若引入，保持对外接口。

验收：每步 `npm run build` + `node --check` + 无头渲染；关键交互 smoke
（加载模型→雕刻→保存版本→生成）。

### Phase P1b：后端收敛（约 1–2 天）

1. 新建 `api/assets.py`：把 assets/versions/parts/upload/reference 路由从 main.py 迁出。
2. `main.py` 内业务 helper 归组：`create_direction_suggestions` 迁入
   `services/divergence/contextual_divergence.py`（或 `planner.py`）；
   geometry/artifact/export helper 迁入 `services/shared/`。
3. `services/` 目录化（signals/intent/divergence/generation/storage/shared），
   import 路径同步更新。
4. 消除剩余重复（`_request_image_ref_count` 等跨模块复制）。

验收：pytest 全绿；API smoke 全通（§2.1 端点抽样）；启动无 ImportError。

### Phase P2：收敛与去重（可选，约 1–2 天）

1. `models.py` 按域拆分（session/asset/intent/planner/direction/generation/case），
   保留 re-export 兼容。
2. `interaction_understanding.py`（1008 行）拆 features 提取 /
   creative-state / supervision 装配。
3. editorScene 全面接管 undo：编辑器状态命令化，删除残留组件级快照栈。
4. `remote_worker/app.py` 内 job 编排按域抽函数（不动 KG 管线本体）。

## 6. 验证与回归策略

| 阶段 | 验证 |
| --- | --- |
| P0 | `pytest`（含新 labels 测试）+ 构建 + 无头渲染 |
| P1a | 构建 + `node --check` + 无头渲染 + 前端交互 smoke |
| P1b | `pytest` 全量 + §2.1 API smoke 脚本 + 启动健康检查 |
| P2 | 全量回归 + 行为对比（关键流程录制/断言） |

关键 API smoke（每阶段必须过）：

```text
sessions → assets(+versions) → actions/interpret → semantic_targets
→ directions/suggest(semantic_target) → fragments → prompt/compose
→ generation/diverge → job → candidates → hy3d → case
```

## 7. 明确不做（YAGNI）

- 不重写 CreativeFlow 生成主链与 `variation_graph_directions.py` KG 管线；
- 不换前端框架（React/Three 保持）；
- 不做 UI 视觉重构（只拆文件、不动样式语言）；
- 不引入重型状态库（除非 P1a 评估确有必要且接口不变）。

## 8. 执行顺序与依赖

```text
P0（止血，无结构风险）→ P1a（前端拆件）→ P1b（后端收敛）→ P2（去重/深化）
每阶段独立可合入、可回滚；P0 先行是因为它能立即降低后续拆件的噪音。
```

---

## 9. 执行状态（2026-08-03 更新）

> 状态标注：✅ 已完成并部署验证 ｜ ◐ 部分完成 ｜ ⬜ 未开始

### P0 止血 ✅

- `backend/app/services/shared/labels.py`：合并 3 份 `ZH_LABELS` +
  `_zh_label/_clean_part_label`，三个 supervisor/contextual_divergence 改为共享 import。
- 删除前端 `visualInspirationItems` / `AAT_NOUN_BANK` / `aatNounPromptTokens` /
  `buildLocalAnalogyDirections` / `runBrushAction` / `runSculptPreview` / `sculptBusy`。
- 删除 8 个无人引用的健康摘要死函数；`Main` 从 7886 → 6445 行。

### P1a 前端拆分 ✅

- `types.ts`（659 行共享类型）、`api.ts`（API/WS 封装与端点常量）、
  `utils/format|scope|session|appHelpers`、`components/ui/primitives`、
  `components/viewport/scene|sculptEngine`、`components/ThreeViewport.tsx`（641 → 348 行）。
- JSX 面板按块抽组件：`panels/AIBehaviorPanel`、`panels/IntentComposer`、
  `panels/PerceptionPanel`、`panels/SolutionSpaceRail`、`menu/StudioMenu`、
  `overlays/*`、`StudioCanvas`（VersionCanvas/SculptControlsPanel/SculptGLModal/CanvasNav）。
- **状态层**：`state/studioStore.ts`（`useStudioStore()`，322 个状态/处理器统一出口，
  不引入 Zustand，符合 §7 YAGNI）。
- **结果**：`main.tsx` 8318 → 777 行（-91%）；ThreeViewport 主 effect 725 → 153 行。
- **类型安全**：补装 `@types/react` / `@types/three` / `vite/client`，`tsc --noEmit` 全绿
  （此前 vite 构建不做类型检查，掩盖了 69 处类型错误与 3 处真实运行期 bug）。
- **修复重构引入的真实 bug**：
  1. `ThreeViewport` 重构时误删 5 个 ref 同步 effect（sculptTool/radius/strength/
     onSculptAction/onGeometryReady + 选择/悬停 refs）→ 笔刷点击后雕刻无响应；
  2. 抽取时丢失 `useImperativeHandle`（applySculptSnapshot / capturePositions /
     exportMeshOBJ）→ 雕刻无法写入 undo 栈、SculptGL 导出失效；
  3. P0 残留 `setSculptBusy` 调用（createPrimitive 路径 ReferenceError）；
  4. `candidateStage/candidatePreviewUrl/candidateFidelity` 被 P0 误删但仍在调用。
- **交互 smoke**：CDP 真实输入管线验证 加载 Design DB 模型 → 笔刷 → 画一笔 →
  `editorScene.editOps()` 计数增长且可撤销，全程零 JS 错误。

### P1b 后端收敛 ✅（含 2 项遗留）

- 新增 `app/api/assets.py`（`create_assets_router`）：assets / versions / parts /
  upload / reference-images|models / benchmark-assets / export 全部迁出 `main.py`；
  `main.py` 5582 → 4974 行；路由注册无重复（82 条）。
- 新增 `app/services/divergence/direction_suggestions.py`
  （`create_direction_suggestion_builder`）：`create_direction_suggestions` 迁出 main.py。
- `app = create_app()` 移至模块底部，避免“工厂调用早于模块级 helper 定义”的 NameError。
- pytest：91 passed（3 个既有环境性失败：white-model manifest 缺 toy_animals 数据、
  两个 VLM predictor 环境相关，均与本次重构无关）。
- 后端已部署主服务器（18000）并 smoke：sessions → assets → versions →
  benchmark-assets → directions/suggest 全通。
- 遗留（◐）：services/ 完整目录化（signals/intent/divergence/generation/storage/shared
  全部落位，目前仅 divergence/ 与 shared/labels 落位）；`_request_image_ref_count`
  等剩余跨模块重复清理。

### P2 去重/深化 ✅

- ✅ 编辑器 undo 全面收敛：前端雕刻/画布编辑已统一走 `editorScene` 命令栈
  （`pushGeometryEdit` + `pushEditorCommand` + capture/restore 快照），
  组件级快照栈已清空。
- ✅ `models.py`（1103 行）按域拆分为 `app/models/` 包（base/semantic/session/
  asset/direction/planner/intent/generation/case/store 十个模块），
  `app/models/__init__.py` 全量 re-export，`from app.models import X` 全部兼容；
  去掉 `from __future__ import annotations` 后 pydantic 即时求值，规避跨域
  ForwardRef 命名空间问题。
- ✅ `interaction_understanding.py`（1008 行）拆出 `intent/interaction_features.py`
  （340 行，纯特征提取）与 `intent/creative_state.py`（58 行，创意状态观测），
  服务类降至 647 行并委托调用。
- ✅ `remote_worker/app.py`（3474 行）job 编排核心迁至
  `remote_worker/job_orchestration.py`（263 行：WorkerJob/PersistentJobStore/
  jobs/processes/_create_job/_run_job/_v1_job_response/_find_result 等），
  app.py 只保留 FastAPI 装配与处理器，KG 管线本体未动。

### 追加收敛（P1b 收尾 ✅）

- 新增 `api/actions.py`（878 行：intent-drafts/actions/annotations/brush-masks/
  smooth/primitive/drag/focus/episodes）、`api/sessions.py`（401 行：sessions/
  memory/snapshot/artifacts/admin/interpretations-decision）、
  `api/candidates.py`（442 行：geometry/render/directions-patch/prompt-compose/
  candidates/cases）。
- `main.py` 5582 → 2650 行（-52%），`@app.` 路由仅剩 9 个（index/health/ops）。
- benchmark 发现簇（~920 行）迁至 `services/storage/benchmark.py`；
  `_request_image_ref_count` 与 `interaction_features.unique_ref_count` 重复消除。
- 追加：跨域响应构建簇（~730 行）迁至 `services/divergence/cross_domain.py`；
  perception payload 助手（172 行）迁至 `services/intent/perception_helpers.py`；
  case 报告/索引（~230 行）迁至 `services/storage/cases.py`；
  prompt chip 包（114 行）迁至 `services/divergence/prompt_chip.py`。
- **`main.py` 5582 → 1467 行（-74%），达成目标结构 <1500 行**；
  仅保留 create_app 组装、index/health/ops 与少量内聚 helper。

### 验收口径（当前基线）

- 前端：`npm run build` + `node --check dist/assets/*.js` + `tsc --noEmit` 0 错误 +
  无头 Chrome 渲染无 JS 错误 + 雕刻链路 CDP smoke 通过；已部署主服务器 5173。
- 后端：`pytest` 91 passed（3 环境性失败） + API smoke（资产/版本/方向/会话）通过；
  已部署主服务器 18000。
- 后端 P2：models 包拆分 / services 六域目录化 / actions·sessions·candidates 路由 /
  benchmark 迁移全部部署 18000 并 smoke（sessions → assets → actions → directions）。
- worker：`job_orchestration.py` 已部署 18100，/health 与 /jobs/transfer dry-run 通过。
