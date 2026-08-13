# FlowStudio Cursor 前端联调后端契约 v1.3

日期：2026-08-02  
变更：
- v1.1 Phase A 契约止血（Canonical / Deprecated / Perception 广播统一）
- v1.2 Phase B Parts lifecycle 状态机
- v1.3 Phase C–E：IR/VLM 去重、router 拆分、`/candidates` 410、snapshot.solution_space

## 连接方式

```bash
ssh -p 50575 \
  -L 5173:127.0.0.1:5173 \
  -L 8000:127.0.0.1:8000 \
  root@connect.westd.seetacloud.com
```

- 前端预览：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000`
- 健康检查：`GET /health`
- WebSocket：`ws://127.0.0.1:8000/ws/sessions/{session_id}`

## Cursor 前端建议主链路

1. `POST /api/v1/sessions`
2. `POST /api/v1/assets` 或上传/加载白模
3. `POST /api/v1/sessions/{session_id}/actions`
4. `POST /api/v1/intent-drafts`
5. `PATCH /api/v1/intent-drafts/{draft_id}`，发送时可用 `{"status":"submitted"}`
6. `POST /api/v1/interaction/interpret`
7. `POST /api/v1/directions/suggest`
8. `GET /api/v1/sessions/{session_id}/snapshot`

如果前端已经在本地形成了完整 `behavior_atoms`，第 3 步可以省略，直接把
`behavior_atoms` 放入 `POST /api/v1/intent-drafts`。后端会自动把这些 atom 登记到
session action index，之后仍可从 `/actions` 和 `/snapshot.action_atoms` 恢复。

`POST /api/v1/sessions/{session_id}/episodes` 会在保存 episode 后直接运行一次
Planner，并在响应里返回：

- `planner_interpretation`
- `metadata.planner_interpretation_id`
- `metadata.planner_primary_intent`
- `metadata.planner_confidence`

因此 Cursor 前端可以先直接读 episode response 渲染确认门；如果需要手动重新解释某个
临时事件，再单独调用 `/api/v1/interaction/interpret`。

确认门接受时，如果希望后端顺手生成 More Creative 方向，可以调用：

```json
{
  "session_id": "sess_xxx",
  "decision": "accepted",
  "metadata": {
    "auto_suggest_directions": true,
    "source_summary": "confirmed cute whole snowman prompt expansion",
    "dimensions": ["aesthetic", "structural"],
    "direction_count": 2,
    "preserved_constraints": ["preserve snowman identity", "preserve face"],
    "live_signals": {
      "dwell_ms": 2300,
      "viewport_orbit_count": 2,
      "viewport_zoom_count": 1,
      "semantic_distance": 0.6,
      "annotation_count": 1
    }
  }
}
```

响应会额外包含：

- `suggested_directions`
- `direction_response`

不传 `auto_suggest_directions` 时，确认门仍保持轻量，只记录接受/拒绝。

## 已兼容开发文档字段

后端保留现有实现字段，同时兼容文档字段：

| 文档字段 | 后端实现字段/行为 |
| --- | --- |
| `action_id` | 可作为 `atom_id` 输入；响应同时返回 `atom_id` 和 `action_id` |
| `intent_draft_id` | 响应中作为 `draft_id` 的别名返回 |
| `action_ids` | 响应中由 `behavior_atoms[].atom_id` 自动派生 |
| draft `status: "submitted"` | 自动归一化为内部状态 `"sent"` |
| draft `status: "saved"` | 自动归一化为内部状态 `"draft"` |
| `direction_count` | 可代替 `candidate_count` |
| `preserved_constraints` | 可代替 `constraints` |
| `dimensions: ["aesthetic"]` | 自动归一化为 `["Aesthetic"]` |
| `scope` / `context_snapshot_id` / `minimum_semantic_distance` | 会进入并回显在 direction response metadata |

## IR 与用户状态信号

`/api/v1/interaction/interpret` 和 `/api/v1/directions/suggest` 都支持 `live_signals`：

```json
{
  "live_signals": {
    "dwell_ms": 2200,
    "new_case_attempt_rate": 2,
    "mask_coverage": 0.18,
    "viewport_orbit_count": 2,
    "viewport_zoom_count": 1,
    "semantic_distance": 0.6,
    "drawing_content": "closed_contour",
    "hover_count": 1,
    "brush_count": 1,
    "annotation_count": 1
  }
}
```

响应里重点读：

- `features.design_state_ir.matches[].confidence`
- `features.design_state_ir.axis_scores`
- `features.design_state_ir.query_signals`
- `metadata.retrieved_design_state_ir`
- `directions[].metadata.ir_recommended_axes`
- `directions[].metadata.prompt_tokens`

## 最小 suggest 请求示例

```json
{
  "session_id": "sess_xxx",
  "asset_id": "asset_xxx",
  "intent_draft_id": "draft_xxx",
  "preserved_constraints": ["preserve snowman identity", "preserve face"],
  "dimensions": ["aesthetic", "structural"],
  "direction_count": 2,
  "scope": {"type": "whole_object", "part_id": null},
  "context_snapshot_id": "ctx_current",
  "minimum_semantic_distance": 0.55,
  "metadata": {
    "live_signals": {
      "dwell_ms": 2200,
      "viewport_orbit_count": 2,
      "viewport_zoom_count": 1,
      "semantic_distance": 0.6,
      "annotation_count": 1,
      "drawing_content": "closed_contour"
    }
  }
}
```

`/api/v1/directions/suggest` 只返回类比方向和 prompt tokens，不直接生成图片或 3D。

## Perception 实时环

1. 前端上报路径  
   - 高频鼠标/相机信号先在前端聚合为 `live_signals`，不要逐帧上报。  
   - 如只想保存最新实时信号，可调用 `PUT /api/v1/sessions/{session_id}/live-signals`。  
   - 工具完成态用 `POST /api/v1/sessions/{session_id}/actions` 保存 `ActionAtom`。后端会同步创建 `UserEvent(type="action_atom_created")`，并立刻进入 `InteractionUnderstandingService + DesignStateIRRetriever`。  
   - 纯观察态用 `POST /api/v1/interaction/interpret`，推荐 `type="camera_observation_ended"`，用于静默刷新 Perception。

2. 后端主模块名  
   - 行为记录主模块：`ActionAtom` store。  
   - 推理主模块：`InteractionUnderstandingService`。  
   - 真实 IR 匹配模块：`DesignStateIRRetriever`，读取 `intentdatabase/cleaned/design_state_ir_retrieval.jsonl`。

3. 读取路径  
   - `GET /api/v1/sessions/{session_id}/perception/latest`
   - `GET /api/v1/sessions/{session_id}/live-signals`
   - `GET /api/v1/sessions/{session_id}/snapshot` 中也会返回 `live_signals`
   - 关键字段：
     - `perception.summary`
     - `perception.behavior_label`
     - `perception.confidence`
     - `perception.evidence`
     - `perception.evidence_summary`
     - `perception.features.live_signals`
     - `perception.features.design_state_ir.query_signals`
     - `perception.features.design_state_ir.matches`
     - `perception.features.design_state_ir.axis_scores`

4. WebSocket 事件  
   - `live_signals_updated`: `{session_id, live_signals, updated_at, source}`  
   - `action_atom_created`: `{event_id, action_atom_id, atom}`  
   - `interaction_interpretation`: 完整 `InteractionInterpretation`  
   - `perception_updated`: `GET /perception/latest` 中的 `perception` 对象  
   - `stage_update`: 最新 `StageState`

5. 推荐防抖窗口  
   - 相机/鼠标聚合：前端本地即时更新 UI。  
   - 静默 interpret：约 `900ms` 防抖。  
   - VLM 可能慢于规则，但后端会先返回当前 interpretation；前端可用 `perception_updated` 覆盖本地观察。

6. `live_signals` 标准字段

```json
{
  "dwell_ms": 2200,
  "compare_dwell_ms": 2100,
  "new_case_attempt_rate": 2,
  "mask_coverage": 0.18,
  "viewport_orbit_count": 3,
  "viewport_zoom_count": 1,
  "local_zoom_count": 1,
  "semantic_distance": 0.62,
  "drawing_content": "closed_contour",
  "tool_switch_count": 4,
  "reference_match_count": 1,
  "hover_count": 1,
  "brush_count": 1,
  "annotation_count": 1
}
```

7. observed facts 与 evidence 边界  
   - `observed_facts`: 工具完成态、选择对象/部件、brush mask 覆盖率、annotation stroke、viewport/orbit/zoom/dwell 聚合值。  
   - `evidence/live_signals`: `semantic_distance`、`new_case_attempt_rate`、`tool_switch_count`、`compare_dwell_ms`、`reference_match_count` 等推理证据。  
   - 后端不会把 IR case 当作硬检索结果直接展示为“用户目标”；IR 只用于推理当前创意阶段与下一步发散维度，并返回置信度。

## Prompt chips 保存

`POST /api/v1/prompt/compose` 用于保存用户从右侧 More Creative 词片段中选择并拼合出的最终 prompt，不触发生图。

请求：

```json
{
  "session_id": "sess_xxx",
  "asset_id": "asset_xxx",
  "base_prompt": "make this snowman cuter",
  "selected_prompt_tokens": [
    {"label": "fluffy", "dimension": "Aesthetic", "role": "texture"},
    {"label": "rounded silhouette", "dimension": "Structural", "role": "shape"}
  ],
  "direction_ids": ["dir_xxx"],
  "intent_draft_id": "draft_xxx"
}
```

响应包含 `final_prompt`、`analogy_prompt_package`、`event_id`、`memory_id`。后端会写入 `working` memory，类型为 `prompt_chip_composition`。

前端在用户选择了 More Creative prompt chips 并触发生成前，应先调用该接口；随后把响应中的 `event_id` / `memory_id` 写入 generation metadata 的 `prompt_compose_evidence`，这样最终 case report 可以追溯“人选择了哪些词片 → 如何拼成 final prompt → 哪次生成使用了它”。

## 白模库

`GET /api/v1/benchmark-assets` 会同时返回 CreativeFlow/Design DB 模型和本地白模。前端可用：

- `metadata.source === "local_white_model"` 判断本地白模；
- `metadata.category` 分组，目前为 `bakery`、`christmas`、`toy_animals`；
- `obj_url` 作为可加载源模型；
- `POST /api/v1/benchmark-assets/{benchmark_id}/load` 把白模加载为当前 session 的 active asset。

当前 GPU 已放置 36 个本地白模：

- `bakery`: 15
- `christmas`: 20
- `toy_animals`: 1

加载后的 asset metadata 会带：

- `white_model_category`
- `white_model_collection`
- `storage_path`

白模部件发现：

- 优先走远端 SAMPart3D/SAM3D；
- 如果远端分割 checkpoint 不可用，后端会读取 OBJ 内部真实 `o` / `g` object-group 作为可编辑 part fallback；
- fallback 响应中 `metadata.adapter === "obj_group_fallback"`，part 的 `type === "obj_group"`，`metadata.source_part_id` 和 `metadata.face_count` 来自 OBJ 文件本身；
- 这不是语义分割结果，前端展示时可标成 “OBJ group fallback / temporary editable groups”。

## Hover 语义与混合图像分割 v0

当前联调口径分三层，不要在 UI 上混淆：

1. `3D raycast hover`：前端在当前 mesh 上实时命中 part，毫秒级更新 tentative label。命中名称可按 `part_id`、`label`、`metadata.source_part_id` 解析到后端 part。
2. `projected semantic hover`：前端把 hover part、屏幕点、相机/viewport、可选截图或局部 mask 作为 `live_signals` / `focus-observations` 证据上报；Perception 可以立即显示 “User is hovering over X”。这是混合 2D/3D 方案的当前可测层。
3. `real 3D segmentation`：后台 SAMPart3D/SAM3D 或 PartField 生成真正 3D parts；完成后替换/增强 tentative parts。失败时继续使用 OBJ group fallback，不阻塞 hover/brush。

推荐前端行为：

- pointer move 不要逐帧上报后端；本地 200–300ms 节流更新 tentative label 即可。
- 900ms 防抖后通过 `/api/v1/interaction/interpret` 静默刷新 Perception，payload 带：

```json
{
  "type": "camera_observation_ended",
  "payload": {
    "selected_part_label": "Branch",
    "live_signals": {"hover_count": 3, "dwell_ms": 1200},
    "signals": {
      "interaction": {"mode": "projected_semantic_hover"},
      "semantic": {
        "part_label": "Branch",
        "semantic_source": "projected_hover_tentative"
      }
    }
  }
}
```

- 用户明确点击 Hover 工具或停留结束时，再保存 `ActionAtom(tool="hover")` 或 `POST /api/v1/focus-observations`。
- 如果接入 2D image segmentation，截图/mask 作为 `focus-observations.metadata.viewport_image_artifact_id` 或 `mask_url` 证据保存；不要把 2D mask 直接称作稳定 3D part，除非已投影回 mesh 并有 face/vertex 对应关系。

### Viewport SAM endpoint

后端已提供真实 2D point-prompt segmentation：

```http
POST /api/v1/viewport-segmentation
```

请求：

```json
{
  "session_id": "sess_xxx",
  "asset_id": "asset_xxx",
  "part_id": "obj_group_01",
  "label": "Branch",
  "image_data_url": "data:image/png;base64,...",
  "point": {"x": 0.52, "y": 0.41},
  "viewport": {"width": 1280, "height": 720, "camera": "..."},
  "metadata": {
    "source": "hover_tentative_label",
    "semantic_source": "projected_hover_tentative"
  }
}
```

`point.x/y` 可以是 0–1 归一化坐标，也可以是像素坐标。响应：

```json
{
  "status": "completed",
  "adapter": "viewport_sam",
  "mask_url": "/api/v1/remote-worker/artifact-file?path=...",
  "overlay_url": "/api/v1/remote-worker/artifact-file?path=...",
  "artifact_id": "art_xxx",
  "worker_job_id": "rw_viewport_sam_xxx",
  "result": {
    "mask_coverage": 0.17,
    "score": 1.01,
    "note": "2D viewport mask only; project to mesh before treating it as a stable 3D part."
  }
}
```

实测 GPU 上 warm 后约 9 秒返回；前端仍应先用 raycast tentative label 即时反馈，SAM mask 回来后再增强 evidence/overlay。

`viewport-segmentation` **不会**自动触发 interpret / `perception_updated`；它只写 artifact + event。需要 Perception 时由前端继续走 `/actions`（Hover commit）或静默 `/interpret`。

---

## Canonical vs Deprecated（v1.1）

### Canonical（前端请只认这些）

| 用途 | Endpoint |
|------|----------|
| 工具完成态 ActionAtom | `POST /api/v1/sessions/{id}/actions` → 统一 `_publish_perception` |
| 静默观察 | `PUT .../live-signals` + `POST /interaction/interpret` |
| More Creative 方向 | **`POST /api/v1/directions/suggest`**（可带 `interpretation_id` 复用 IR） |
| Prompt chip 保存 | `POST /api/v1/prompt/compose` |
| 生成 | `POST /api/v1/generation/replace\|drag\|diverge`（立即返回 `job_id`） |
| 读状态 | `GET /api/v1/sessions/{id}/snapshot` |
| 2D 视口分割证据 | `POST /api/v1/viewport-segmentation`（非 3D part） |

### Deprecated（兼容一个联调迭代，勿新用）

| Endpoint | 行为 |
|----------|------|
| `POST /api/v1/directions/cross-domain` | 薄代理到 suggest；`metadata.deprecated=true`；打 `DEPRECATED_API_USED` 日志 |
| `POST /api/v1/candidates` | **410 Gone**；请改用 `/generation/*` |

### ActionAtom 边界

`ActionAtom.tool` 仅用于真实操作：`hover/brush/annotation/drag/smooth/add/image/model/text(用户正文)`。  
More Creative keyword / prompt chip **禁止**写入 `/actions`（后端返回 400）；只进 `/prompt/compose` 与 `generation.metadata.selected_prompt_tokens`。

### Perception 广播契约

凡产生 interpretation 的主路径（`/actions`、`/interpret`、episode、candidate 决策、窄 WS 白名单）统一调用 `_publish_perception`，顺序固定为：

1. `interaction_interpretation`
2. `perception_updated`
3. `stage_update`（若 stage 有更新）

纯 artifact 写入（annotation / brush-mask / focus-observations / viewport-sam 文件保存）**不**自动 interpret。

---

## Parts lifecycle（v1.2 / Phase B）

每个 `PartRecord` 带：

```text
lifecycle:
  tentative_raycast      # 前端 raycast，可不落库
  obj_group_fallback     # OBJ o/g 可编辑代理组
  viewport_2d_mask       # 已挂 2D SAM 证据，仍非稳定 3D part
  segmented_3d           # SAM3D / SAMPart3D / PartField 真分割
```

规则：

1. `/parts/discover`  
   - OBJ fallback → `obj_group_fallback`  
   - 远端真分割成功 → `segmented_3d`（可在 metadata 里保留 `previous_part_lifecycles`）
2. `/viewport-segmentation`  
   - 只写 artifact + `part.metadata.evidence.viewport_mask_*`  
   - 若原 lifecycle 不是 `segmented_3d`，升为 `viewport_2d_mask`  
   - **禁止**把 2D mask 标成 `segmented_3d`
3. `/focus-observations` 与 `/sessions/{id}/actions`  
   - 响应/事件携带 `part_lifecycle`（从 asset.parts 解析）  
   - 前端可用它区分「临时标签 / OBJ 组 / 2D 证据 / 真 3D」

`metadata.lifecycle_summary` 会出现在 discover 响应中，便于 UI 显示当前部件层。

---

## 理解栈与生成单轨（v1.3 / Phase C–E）

### Interpret：Rule 先返回，VLM 异步覆盖

- `/interaction/interpret`、`/actions`、episode、窄 WS 白名单：先返回 rule(+IR) interpretation
- 若配置了 Intent VLM：metadata 含 `task=intent_predict`、`vlm_pending=true`，随后异步 refine 再发一次 `perception_updated`
- `rule_fallback` **仅**表示模型/传输不可用，不表示 IR 弱匹配
- Directions Qwen 调用 metadata/payload 标 `task=direction_suggest`，与 Intent VLM 任务分离
- `directions/suggest` 带 `interpretation_id` 时复用该 interpretation 的 IR（不二次全量 retrieve）

### Snapshot 聚合 Solution Space

- `GET /sessions/{id}/snapshot` 含 `solution_space`（与 `GET .../solution-space` 同一 builder）
- 前端优先读 snapshot；独立 solution-space 仍可用

### Generation / Hy3D

- 慢任务只走 `/generation/*` → `job_id` + WS `job_update` / `candidate_ready`
- `POST /candidates` 已移除（410）
- Hy3D：`auto` 与 `manual` 互斥去重；同一 candidate 已有 `hy3d_status=queued|running|completed` 时不重复提交

### 后端模块（Phase D，协议不变）

```text
backend/app/api/
  perception.py      # live-signals / interpret / perception/latest / solution-space
  directions.py      # suggest + cross-domain proxy
  generation.py      # generation/* / jobs/* / candidates 410
  solution_space.py
  perception_flow.py # rule-first + async VLM refine
```
