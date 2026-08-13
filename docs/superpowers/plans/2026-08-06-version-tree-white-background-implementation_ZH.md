# FlowStudio 白底候选与版本树实现计划

> **执行要求：** 在当前任务中使用 `superpowers:executing-plans`，按任务顺序逐项实现和验证。所有步骤使用复选框跟踪。

**目标：** 保证 Solution Space 中每张生成图都是纯白背景上的完整单体；用户把候选拖入画布后，立即出现图片版本节点，并在后台生成 3D，完成后在原节点、原位置升级为可编辑模型。

**架构：** 在四阶段生成协议中加入明确的白底、单体和完整构图约束，并由远端图片 QA 再次执行硬性筛选。使用现有四阶段 SQLite 存储持久化版本树，并通过实时快照和 API 提供给前端。前端不再根据 `acceptedCandidateIds` 临时推导版本布局，而是使用显式版本节点、确定性的树布局函数，以及鼠标拖拽和按钮共同调用的幂等版本创建操作。

**技术栈：** FastAPI、Pydantic、SQLite、React 19、TypeScript、原生 HTML Drag and Drop、Three.js、Node Test Runner、pytest、Pillow。

## 全局约束

- 不提交 Git，不推送 GitHub，不部署 GitHub Pages。
- 只有通过纯白底、完整单体 QA 的图片才能进入 Solution Space。
- 每批 Solution Space 展示 6–8 个合格候选。
- 拖入候选后 300ms 内必须出现图片版本节点，Hy3D 在后台异步执行。
- Hy3D 必须更新同一个 `node_id`，不能另建版本节点。
- 刷新页面或 WebSocket 重连后，版本树和活动节点必须恢复。
- 不破坏常驻 Observation、多意图 Gate、关键词继承和 Solution Space 追加逻辑。

---

## 文件职责

- `backend/app/models/four_stage.py`：生成图片硬约束字段。
- `backend/app/services/generation/four_stage_spec_builder.py`：白底和完整单体 prompt 协议。
- `backend/app/models/realtime_observation.py`：版本树模型和 API 请求模型。
- `backend/app/services/storage/four_stage_store.py`：版本树 SQLite 持久化。
- `backend/app/services/intent/realtime_observation.py`：幂等版本操作和快照聚合。
- `backend/app/api/realtime_observation.py`：创建、更新、激活版本节点的 API。
- `remote_worker/variation_stage2_images.py`：图片视觉 QA 硬门槛。
- `frontend/src/types.ts`：版本树前端类型。
- `frontend/src/utils/versionGraph.ts`：确定性的树状布局与活动路径计算。
- `frontend/src/state/studioStore.ts`：恢复、创建、激活、升级和重试版本。
- `frontend/src/components/panels/SolutionSpaceRail.tsx`：真实可拖拽候选卡片。
- `frontend/src/components/StudioCanvas.tsx`：画布 drop target、节点、连线、状态和重试。
- `frontend/src/main.tsx`：组件属性连接。
- `frontend/src/styles.css`：版本树、拖拽反馈和活动路径样式。

---

## 任务 1：把白底、单体和完整构图加入 GenerationSpec

**修改文件：**

- `backend/app/models/four_stage.py`
- `backend/app/services/generation/four_stage_spec_builder.py`
- `backend/tests/test_four_stage_generation.py`

**接口产出：**

```python
GenerationSpec.require_white_background: bool
GenerationSpec.require_single_object: bool
GenerationSpec.require_full_object: bool
```

- [ ] 先写失败测试，构造 part-scope spec 并断言三个字段均为 `True`。
- [ ] 断言每个 `prompt_candidates` 都包含：

```python
assert "pure white rgb(255,255,255) background" in prompt.lower()
assert "one complete object only" in prompt.lower()
assert "no crop" in prompt.lower()
```

- [ ] 运行测试确认 RED：

```bash
cd backend
.venv/bin/python -m pytest tests/test_four_stage_generation.py -k white_background -q
```

- [ ] 在 `GenerationSpec` 中加入三个默认值为 `True` 的字段。
- [ ] 在 `GenerationSpecBuilder` 的所有场景 prompt 最后统一追加一次固定构图协议：

```python
_IMAGE_FRAMING_CONTRACT = (
    "One complete object only, centered with at least 5% clear margin on every side; "
    "pure white RGB(255,255,255) background; no crop, no cut-off parts, no floor, "
    "no shadow, no scene, no text, no watermark, and no additional objects."
)
```

- [ ] 运行相邻测试确认 GREEN：

```bash
cd backend
.venv/bin/python -m pytest tests/test_four_stage_generation.py tests/test_four_stage_e2e.py -q
```

---

## 任务 2：远端 Worker 强制白底、安全边距和单主体 QA

**修改文件：**

- `remote_worker/variation_stage2_images.py`
- 新建 `remote_worker/tests/test_variation_stage2_images.py`

**QA 输出字段：**

```text
accepted
reasons
border_white_ratio
subject_bbox
safe_margin_ratio
component_count
nonwhite_ratio
```

- [ ] 使用 Pillow 创建四类测试图片：合格白底单体、灰色背景、主体触边、两个独立主体。
- [ ] 运行测试确认当前逻辑不能满足新标准：

```bash
python3 -m pytest remote_worker/tests/test_variation_stage2_images.py -q
```

- [ ] 使用以下固定阈值：

```python
MIN_BORDER_WHITE_RATIO = 0.95
MIN_SAFE_MARGIN_RATIO = 0.05
MIN_SUBJECT_RATIO = 0.10
MAX_SUBJECT_RATIO = 0.70
```

- [ ] 从非白像素 mask 计算主体包围框和连通区域。
- [ ] 使用稳定的失败原因：

```text
background_not_pure_white
subject_touches_frame
multiple_large_subjects
subject_too_small
subject_too_large
```

- [ ] 只允许一个大型连通主体；小于最大区域 8% 的噪点可忽略。
- [ ] QA 失败图片保留诊断信息，但不能进入返回给 Solution Space 的 `items`。
- [ ] 继续使用有限次数的补生成逻辑，直到获得请求数量或达到上限。
- [ ] 验证：

```bash
python3 -m pytest remote_worker/tests/test_variation_stage2_images.py remote_worker/tests/test_variation_contracts.py -q
```

---

## 任务 3：持久化 Version Graph 和活动节点

**修改文件：**

- `backend/app/models/realtime_observation.py`
- `backend/app/models/__init__.py`
- `backend/app/services/storage/four_stage_store.py`
- `backend/app/services/intent/realtime_observation.py`
- `backend/app/api/realtime_observation.py`
- `backend/tests/test_realtime_observation.py`

**新增 API：**

```text
POST  /api/v1/sessions/{session_id}/version-nodes
PATCH /api/v1/sessions/{session_id}/version-nodes/{node_id}
PUT   /api/v1/sessions/{session_id}/active-version/{node_id}
```

**核心模型：**

```python
class VersionNodeStatus(StrEnum):
    image_ready = "image_ready"
    generating_3d = "generating_3d"
    mesh_ready = "mesh_ready"
    mesh_failed = "mesh_failed"

class VersionGraphNode(BaseModel):
    node_id: str
    session_id: str
    version_number: int
    parent_node_id: str | None
    candidate_id: str | None
    label: str
    preview_url: str | None
    mesh_url: str | None
    obj_url: str | None
    status: VersionNodeStatus
    hy3d_job_id: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
```

- [ ] 先写以下失败测试：同一 parent/candidate 创建幂等、mesh 升级保持 node id、快照恢复活动节点、从旧节点建立兄弟分支。
- [ ] 运行确认 RED：

```bash
cd backend
.venv/bin/python -m pytest tests/test_realtime_observation.py -k version_graph -q
```

- [ ] 新建 `version_graph_nodes` 与 `version_graph_states` 两张表。
- [ ] `(session_id, parent_node_id, candidate_id)` 设置唯一约束。
- [ ] Store 新增：

```text
save_version_node
get_version_node
list_version_nodes
set_active_version_node
get_version_graph_state
```

- [ ] 创建节点时验证 parent 属于同一 session，并分配递增 `version_number`。
- [ ] PATCH 只允许修改状态、mesh URL、job id 和 error，不能改变 parent 或版本号。
- [ ] `RealtimeObservationSnapshot` 增加 `version_graph`。
- [ ] 运行完整 Observation/Gate/Solution 测试：

```bash
cd backend
.venv/bin/python -m pytest tests/test_realtime_observation.py -q
```

---

## 任务 4：实现确定性的从左到右版本树布局

**新增文件：**

- `frontend/src/utils/versionGraph.ts`
- `frontend/tests/versionGraph.test.ts`

**修改文件：**

- `frontend/src/types.ts`

**接口：**

```ts
layoutVersionGraph(nodes, activeNodeId): {
  nodes: VersionCanvasNode[];
  links: VersionCanvasLink[];
}

activePathNodeIds(nodes, activeNodeId): Set<string>
```

- [ ] 先测试祖先位于活动节点左侧、兄弟分支纵向分开、活动节点固定在主编辑锚点、每个非根节点只有一条父连线。
- [ ] 运行确认 RED：

```bash
cd frontend
node --experimental-strip-types --test tests/versionGraph.test.ts
```

- [ ] 活动节点固定为 `(640,0)`、尺寸 `520×520`。
- [ ] 历史节点尺寸 `220×220`，深度间距 `280`，兄弟行间距 `240`。
- [ ] 通过 parent 遍历计算深度、活动祖先路径与分支位置。
- [ ] 验证：

```bash
cd frontend
node --experimental-strip-types --test tests/versionGraph.test.ts tests/*.test.ts
```

---

## 任务 5：加入真实候选拖拽和统一版本创建 action

**修改文件：**

- `frontend/src/components/panels/SolutionSpaceRail.tsx`
- `frontend/src/components/StudioCanvas.tsx`
- `frontend/src/state/studioStore.ts`
- `frontend/src/main.tsx`
- `frontend/tests/interactionReliability.test.ts`

**统一 action：**

```ts
dropCandidateIntoVersionGraph(candidate: Candidate): Promise<void>
```

- [ ] 先写失败测试，要求候选卡片可拖拽、设置 FlowStudio MIME payload、画布实现 `onDragOver/onDrop`，按钮调用同一个 callback。
- [ ] 运行确认 RED。
- [ ] bootstrap 和实时快照恢复 `version_graph`；每个 session 只创建一个 Version 1 源节点。
- [ ] drop action 按以下顺序执行：

1. 验证候选存在预览 URL。
2. 立即 POST 版本节点，parent 为当前活动节点。
3. 合并返回节点、设为活动节点并显示候选图片。
4. 不等待 Hy3D，先把控制权返回前端。
5. 后台调用 `runFourStageHy3d` 或 `generateCandidateHy3d`。
6. 成功后 PATCH 同一节点为 `mesh_ready`，失败后 PATCH 为 `mesh_failed`。

- [ ] 若同一节点已经 `generating_3d` 或 `mesh_ready`，不重复启动 Hy3D。
- [ ] 卡片原生拖拽 payload：

```tsx
draggable={Boolean(previewUrl)}
onDragStart={(event) => {
  event.dataTransfer.effectAllowed = "copy";
  event.dataTransfer.setData(
    "application/x-flowstudio-candidate",
    JSON.stringify({ candidateId: candidate.candidate_id }),
  );
}}
```

- [ ] “拖入画布”按钮直接调用同一个 `dropCandidateIntoVersionGraph`。
- [ ] 验证：

```bash
cd frontend
node --experimental-strip-types --test tests/*.test.ts
npx tsc --noEmit
```

---

## 任务 6：渲染版本历史树、状态和原位重试

**修改文件：**

- `frontend/src/components/StudioCanvas.tsx`
- `frontend/src/state/studioStore.ts`
- `frontend/src/styles.css`
- `frontend/tests/interactionReliability.test.ts`

- [ ] 先测试 Version N、候选名称、中文状态、失败重试按钮、drop target 无障碍名称和活动路径 class。
- [ ] 删除基于 `acceptedCandidateIds` 的临时版本布局。
- [ ] 使用任务 4 的节点和连线渲染真实持久化版本树。
- [ ] 当前活动节点使用 520×520 主视口；历史节点在左侧显示为 220×220。
- [ ] 父子连接使用 SVG 曲线；活动祖先路径高亮，其他分支降低对比度。
- [ ] `image_ready`、`generating_3d`、`mesh_failed` 节点显示 `<img>`，禁用雕刻和部件操作。
- [ ] `mesh_ready` 节点把 mesh URL 传入 `ThreeViewport` 并开放编辑。
- [ ] `onRetryVersionNode(nodeId)` 只更新现有节点，不能 POST 新版本。
- [ ] 增加拖拽悬停、状态徽标、活动路径、历史缩略图和失败重试样式。
- [ ] 遵守 `prefers-reduced-motion`。
- [ ] 验证：

```bash
cd frontend
node --experimental-strip-types --test tests/*.test.ts
npx tsc --noEmit
npm run build
```

---

## 任务 7：同步 GPU 并完成真实端到端验收

- [ ] 本地运行：

```bash
backend/.venv/bin/python -m pytest backend/tests/test_four_stage_generation.py backend/tests/test_realtime_observation.py -q
python3 -m pytest remote_worker/tests/test_variation_stage2_images.py remote_worker/tests/test_variation_contracts.py -q
cd frontend
node --experimental-strip-types --test tests/*.test.ts
npx tsc --noEmit
npm run build
```

- [ ] 只同步本次修改文件和 `frontend/dist/` 到 `/root/flowstudio_app`。
- [ ] 重启进程前先验证 PID 与命令，只重启受影响的后端、前端和图片 Worker。
- [ ] 所有服务健康检查必须返回 HTTP 200。
- [ ] 真实生成一批 6–8 张候选，并记录每张图的白底比例、主体边距、连通区域数量和尺寸。
- [ ] 任意图片不是纯白底、发生裁切或包含额外主体，都不能通过验收。
- [ ] 实际拖拽候选，确认 Hy3D 完成前 Version 2 图片已经出现，Version 1 已左移并连线。
- [ ] 确认“拖入画布”按钮产生完全相同的版本操作。
- [ ] 等待 Hy3D，确认同一 `node_id` 从 `generating_3d` 变为 `mesh_ready`，位置不发生变化，雕刻工具可用。
- [ ] 刷新页面后确认版本树、活动节点和状态恢复。
- [ ] 从 Version 1 再拖入另一候选，确认生成纵向分开的兄弟分支。
- [ ] 最终报告测试数量、服务健康、真实 node id、状态变化、图片 QA 数据和界面截图。

只有真实图片和刷新恢复均通过证据验证后，才能报告本功能完成。

