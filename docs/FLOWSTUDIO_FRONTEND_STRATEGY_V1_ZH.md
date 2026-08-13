# FlowStudio 前端重整策略 V1（2D/3D 画笔 · hover 分割 · 四阶段状态管理）

- 版本：V1（策略稿，未进入实现）
- 日期：2026-08-04
- 状态：等待评审。评审通过后按阶段实现。
- 关联文档：`FLOWSTUDIO_FOUR_STAGE_DEEPSEEK_IMPLEMENTATION_STRATEGY_V1_ZH.md`（四阶段后端，已完成）、`FLOWSTUDIO_CURSOR_TO_CODEX_PERCEPTION_BEHAVIOR_HANDOFF_V1_ZH.md`

---

## 0. 一句话结论

前端不需要推倒重来：2D 画笔与 3D 雕刻**已有可用实现且已接入行为证据链**，缺的是「界面截图」这个多模态证据和「笔刷/拖拽结束后的统一提交」；hover 建议**从 3D 语义分割降级为 2D 视频图像分割模型（前端 ONNX / 后端 SAM2 双轨）**；`four_stage.*` 的 WS 事件后端已全部发出，前端只需要补订阅、Gate UI 和 run 生命周期。整体是「增强 + 补链」，不是重构。

---

## 1. 现状核验（代码级结论）

| 模块 | 现状 | 与目标的差距 |
| --- | --- | --- |
| 2D 画笔 | `AnnotationCanvasOverlay.tsx`（155 行）已实现铅笔标注；Done 后 `recordAnnotation` → `POST /api/v1/annotations` → `recordActionAtom("annotation")` → `sendEvent("annotation_commit")` | 只有单色等宽 polyline、无「毛笔类笔刷形状」；提交的只是 SVG 笔画快照（深色底 + 蓝色 polyline），**不是界面截图** |
| 3D 雕刻 | `sculptEngine.ts`（501 行）纯 three.js 自研：`sculptFalloff / sculptApplyOffset / grabDisplace / SculptSession / SculptPointerController`；UI 有 brush/drag/smooth + 半径/强度滑块；提交走 `onSculptAction` → `sendEvent("brush_end"/"drag_end")` → `recordActionAtom` | 已存在但功能偏基础；行为证据链已通，缺截图 |
| hover | ThreeViewport + sculptEngine 用 `THREE.Raycaster` + `onHoverPart`（250ms 节流）命中部件 | 纯 3D 几何命中，无 2D 分割加持 |
| 行为 → 意图推测 | `recordActionAtom`（brush/drag/annotation）→ `visibleBehaviorAtoms` → `live_signals`（brush_count/mask_coverage/annotation_count/tool_switch_count/semantic_distance）→ `POST /interaction/interpret`；`isObjectBehaviorAtom` 已过滤非行为事件 | 链路存在，但 evidence 里没有 `viewport_screenshot` 这类多模态输入 |
| 截图 | 全仓库无 `toDataURL / captureFrame / preserveDrawingBuffer` 逻辑 | **完全缺失**，这是最大缺口 |
| 四阶段前端状态 | `main.tsx` 只有旧 planner gate（`plannerGateStatus`）；`studioStore.ts` WS 处理 `stage_update / live_signals_updated / interaction_interpretation / planner_interpretation_decision` 等 | **完全没有** `four_stage.*` 事件、run API、awaiting_gate Gate UI、option 回传 |
| 后端四阶段 API | `POST /api/v1/four-stage/runs`（body 带 `run_hy3d`）、`GET runs/{run_id}`、`retry/cancel`、`GET .../intent-ir|retrieval|decision`、`POST decisions/{decision_id}/gate`、`POST runs/{run_id}/generation`；orchestrator 通过既有 `/ws/sessions/{session_id}` 广播 10 种 `four_stage.*` 事件 | 后端已完备，前端未消费 |

**行为证据链验证结论**：`recordActionAtom` 已经存在于 `studioStore.ts:506`，brush/drag/annotation 均会写入 atom 并带 `live_signals` 进入意图推测。也就是说「笔刷结束后是否有 behavior 给 intent planner 联合推测」——**答案是：已有**。缺的不是行为链，而是：

1. 截图（界面证据）没有进 evidence；
2. 提交时行为与截图没有作为一次原子事件打包；
3. 没有把「2D 笔刷 → 精确 mask」这一步做出来（现在是 3D brush mask）。

---

## 2. 总体策略：增强三件套 + 补四阶段消费

```
[ 前端交互 ]                                    [ 后端四阶段 ]
 2D 画笔(带笔刷) ──┐
 3D 雕刻(增强)  ───┼─ 行为 atom + 截图 ─→ /api/v1/four-stage/runs
 hover 2D 分割   ──┘   (events 数组)        │
                                            ▼
  Gate UI ←─ four_stage.awaiting_gate ←─ re_representation
     │  accept_option / reject_all /
     │  request_revision / clarify
     ▼
  generation ←─ four_stage.generation_queued ─→ Qwen-Image / hy3d
```

原则：

- **不引入重型前端框架**；只加 2 个依赖（SAM ONNX 运行时 + 可选 brush 内核）。
- **保持现有 CSS 风格**（`.annotation-*`、`.sculpt-*`、`.gate-*` 沿用现有类体系）。
- **截图进证据**，但**截图理解放在后端**（Qwen3-8B 是文本版，多模态交给 Gemini-3.5-flash，key 只放服务器 `.env`）。
- **scheduler 是唯一开关**，Gate UI 只是运维覆盖（沿用既定决策）。

---

## 3. 2D 画笔：增强为「特定笔刷 + 截图 + 行为原子提交」

### 3.1 现状

`AnnotationCanvasOverlay` 已有：指针捕获、归一化坐标（0-1）、stroke 收集（上限 240 点）、Undo/Clear/Done、SVG 快照。提交链：

```
handleDone → onCommit(strokes) → recordAnnotation
  → POST /api/v1/annotations
  → recordActionAtom("annotation", …, {live_signals})
  → sendEvent("annotation_commit", …)
```

### 3.2 要补的三件事

1. **笔刷（关键项：笔刷形状，Procreate 风格钢笔）**：不是换颜色/透明度，而是**笔画本身是变宽度的钢笔笔触**。实现从「等宽 polyline」升级为「笔刷戳记（brush stamp）渲染」：
   - 笔画点集用 Catmull-Rom/贝塞尔平滑后，沿路径按距离采样（~2-4px 间隔）；
   - 每个采样点带**动态宽度**：笔尖半径 = 基础半径 × 压力（`PointerEvent.pressure`，笔/触屏）/ 速度衰减（鼠标无压力时用速度模拟） × **钢笔 taper 曲线（两头细、中间粗，且不过分粗）**；
   - 每个采样点贴一个**预渲染钢笔纹理戳记**（尖头、平滑边缘、无毛边，介于毛笔与圆头笔之间；中间段宽度控制在基础半径的 1.5-2.2 倍，避免笔迹臃肿），按运动方向旋转、按宽度缩放，用 `globalCompositeOperation` 叠加；
   - 画笔类型候选：**钢笔（pen，两头细中间粗，默认）、marker（半透明平头）、pencil（细颗粒）**，eraser 作为修正工具；
   - 渲染载体：Canvas 2D 覆盖层（纹理戳记天然支持），不再用 SVG polyline；提交给 planner 的 stroke 数据仍保持轻量 JSON（归一化点列 + 每点 pressure/t 与笔刷类型），宽度在渲染时推导、不存大体积位图。
2. **截图**：`handleDone` 时调用 `viewportCapture.captureJpeg()`（见 §6 截图基础设施），把压缩 JPEG（~640px、quality 0.7）与 SVG 笔画**一起**提交。
3. **原子提交**：`recordAnnotation` 的 evidence 增加 `viewport_screenshot_url / viewport_screenshot_data`（base64 走 POST body 或先传 `/api/v1/screenshots` 换 URL），`sendEvent("annotation_commit")` payload 同步带上。

### 3.3 交互策略（可选增强，不阻塞主线）

参考 SAM / ScribblePrompt 的「先涂鸦后精修」范式：2D 画笔结束后，把笔刷区域转成提示（scribble 点集）发给分割模型（见 §5），得到精确 mask 后前端高亮，并把 mask 一并放入行为 atom。这样 planner 收到的不是一个「随手画了笔」，而是「用户在 X 部件上画了轮廓/涂了区域」。

**验收标准**：画 2 笔 → Done → 网络面板出现 1 次 annotation POST + 1 次 screenshot POST + 1 次 interpret；planner 侧能看到 `viewport_screenshot_url` 与 mask。

---

## 4. 3D 画笔（雕刻）：不集成 SculptGL，增强现有自研引擎

### 4.1 调研结论（开源方案）

| 候选 | 许可/形态 | 适配度 | 结论 |
| --- | --- | --- | --- |
| **SculptGL / SculptNG**（`Microtome/sculpt_ng`） | MIT，浏览器雕刻，维护活跃 | 高（同一领域），但**整站式**：自带场景管理、文件 IO、UI | 借鉴 brush 算法与平滑/膨胀内核，不整站嵌入 |
| **Chili3D**（`npm chili3d`） | MIT，OpenCascade WASM + three.js 浏览器 CAD | 低-中：强在布尔/硬表面，雕刻类弱 | 仅当后续需要 CAD 特征编辑时考虑；当前阶段不引入（体积大，~10MB+ WASM） |
| **marmelab/sculpt-3D** | React + three.js 原型 | 中：思路参考 | 参考其 pointer/brush 交互写法，无维护价值 |
| **Sculpt+ / D3D Sculptor** | 移动端 | 不适用桌面 | 排除 |

**决策**：保留并增强 `sculptEngine.ts`（它就是「自研轻量雕刻」，且已与行为链打通）。增强方向按性价比排序：

1. **SculptNG 内核借鉴**（唯一值得抄的）：拉入其 brush 算法思路（inflate/crease/flatten/rotate），在现有 `SculptSession` 里加 `crease`、`flatten` 两种 falloff 变体（纯数学，不依赖其仓库）；
2. **撤销/重做**：`editorScene.pushGeometryEdit` 已存在（`studioStore` P5），补齐快照级 undo；
3. **对称/镜像画笔**（可选）：雕塑常用，实现简单（x 镜像应用同一 offset）；
4. **不引入**：SculptGL 整站、Chili3D、任何 WASM 雕刻库。理由：现有实现 501 行已覆盖核心；引入整站库会破坏我们的事件/行为注入点，收益与集成成本不成比例。

### 4.2 行为提交增强

现状：`handleSculptAction(tool, evidence)` 已写 `recordActionAtom(tool, …)`，且 `positionsBefore/After` 进 `editorScene.pushGeometryEdit`。增强点：

- 提交时携带 `viewport_screenshot`（雕刻前后的各一张，可选）与 `stroke_count / duration_ms`；
- `sendEvent("brush_end"/"drag_end")` 与 `recordActionAtom` 的 evidence 字段对齐（现在 brush 走 `sendBrush` 一次、drag 走 `sendDrag` 一次，语义一致）；
- 雕刻提交后把「本次雕刻网格差量」摘要（受影响顶点数、平均位移）写进 atom，避免把几何数据整个发给 planner。

---

## 5. hover：3D 语义分割 → 2D 视频图像分割（前端 ONNX + 后端 SAM2 双轨）

### 5.1 为什么降级合理

3D 语义分割（如 PointNet++ / OpenMask3D 级别）需要：3D 语义标签体系、训练/标注数据、GPU 推理接口；且与现有 `obj_group_fallback` 的部件投影 hover 是两套体系。而**前端已有截图**后，2D 分割直接消费同一张截图，链路最短、演示效果最直观（鼠标移到哪，哪里高亮）。

### 5.2 开源方案检索结论

| 方案 | 形态 | 适用 |
| --- | --- | --- |
| **MobileSAM**（`sam-web` npm 包 / ONNX） | 浏览器 WASM，一次编码多次点选，~40MB 模型缓存 | 首选：hover 实时响应（编码一次，单点解码 <100ms） |
| **EfficientSAM** | ONNX / 浏览器 demo 已有 | 备选：编码更快，精度略低 |
| **ScribblePrompt**（BMVC 2023） | 交互式 scribble 分割 | 借鉴交互范式：先画 2D 笔刷再精修 mask（配合 §3.3） |
| **SAM2（HF 官方）** | 服务端 Python（GPU） | 后端双轨：重试/更高精度/批量 mask 生成 |
| **ATOM / SegDrawer** | 静态 web SAM 遮罩 | 参考实现，不直接采用 |

### 5.3 双轨设计

```
鼠标 hover（节流 150-250ms）
  → 前端 MobileSAM（ONNX, WASM）: 截图 + 光标点 → mask → 高亮部件
      失败/超时（>500ms）→ 降级：3D Raycaster 部件命中（现状）→ 兜底不阻塞
  → 后端 SAM2（备选）: POST /api/v1/segment/hover {image, point}
      返回 mask + 伪标注 → WS broadcast segment_updated
```

- 前端优先：MobileSAM 编码一次（切换视角/模型时重新编码），点选解码毫秒级，完全本地，无 GPU 成本；
- 后端兜底：SAM2 接口做成可选（`SEGMENTATION_MODE=local|server|off`），默认 `local`，`off` 时退回 Raycaster；
- 数据：hover mask **进意图推测**（`hover_focus` 行为 atom 已进 `visibleBehaviorAtoms`，再补 mask 与 dwell），用于给 planner 判断在哪个维度发散；但 **hover 是非阻塞信号**——意图推测主触发（打字/画笔/拖拽提交）不等 hover 的推理结果：hover 的 interpret 单独异步跑（沿用现有 `camera_observation_ended` + `interpret_silently` 通道，`syncId` 防乱序），慢就晚到合并，主链路照常推进；主触发 payload 始终带上**当前最新的 hover 上下文**（最近 hover 部件/dwell），即使 hover 推理尚未返回；
- 交互：hover 点击（非移动）才把「点 + mask」作为一次轻量行为 atom（`hover_focus` 已存在，补 mask）。

### 5.4 与画笔的关系

同一套截图 + ONNX 模型可复用给 2D 画笔：笔刷结束 → scribble 点集 → 同模型出精确 mask。这样 §3.3 与 §5 共用一份模型加载（一个 `Segmenter` 单例，`setImage` 一次）。

---

## 6. 截图基础设施（跨功能共用）

现状：three.js renderer 未开 `preserveDrawingBuffer`，`toDataURL` 会拿到空白帧。实现：

1. `viewportCapture.ts`：`captureJpeg(renderer, scene, camera, {width=640, quality=0.7})`——渲染一帧后 `renderer.domElement.toDataURL("image/jpeg", …)`，失败时回退 `toBlob`；
2. 提交策略：**前端截图 → POST `/api/v1/screenshots` → 返回 artifact URL → 放进 evidence/atom/event**。base64 不进 WS（体积大），只传 URL；
3. 触发时机：画笔 Done、雕刻提交、拖拽提交、意图推测触发前（`hasMeaningfulIntentEvidence` 为 true 时）各截一张；
4. 多模态理解放后端：`POST /api/v1/four-stage/screenshot-interpret {image_url, context}` → 调 Gemini-3.5-flash（视觉）产出结构化观察（看到什么、用户在画什么）→ 并入 intent IR 的 evidence。Qwen3-8B 是文本版，不做本地视觉。

---

## 7. 前端状态管理：`four_stage.*` 事件 + Gate UI + option 回传

### 7.1 事件契约（后端已实现，直接消费）

沿用 `/ws/sessions/{session_id}`（无需新连接），消息类型：

| 事件 | 触发时机 | 前端动作 |
| --- | --- | --- |
| `four_stage.encoding_started` | run 创建 | 显示进度条「编码中」 |
| `four_stage.encoding_completed` | 编码完成 | 更新阶段徽章 |
| `four_stage.retrieval_completed` | 检索完成 | 显示命中条目数（可折叠） |
| `four_stage.decision_completed` | 方向决策完成 | 缓存 decision（options 等） |
| `four_stage.awaiting_gate` | **决策待确认** | 弹出 Gate UI（唯一用户打断点） |
| `four_stage.gate_resolved` | 用户已操作 Gate | 收起 Gate，进入生成 |
| `four_stage.generation_queued` | 生成排队 | 显示「生成中」+ 进度 |
| `four_stage.completed` | 全部完成 | 展示产物画廊（4 张 / mesh） |
| `four_stage.failed` | 失败 | 显示错误 + Retry 按钮 |
| `four_stage.cancelled` | 取消 | 灰化进度 |

payload 固定含：`run_id / session_id / stage / schema_version` + 事件附加字段（如 `decision_id`、`artifact_count`）。

### 7.2 状态模型（studioStore 新增）

```ts
type FourStageRunState = {
  runId: string | null;
  stage: "raw_events" | "encoding" | "retrieval" | "re_representation"
        | "awaiting_gate" | "generation" | "completed" | "failed" | "cancelled";
  decision: DecisionIR | null;        // options / clarification_question / confidence
  selectedOptionId: string | null;
  gateOpen: boolean;
  generationArtifacts: Array<{url: string; kind: "png" | "glb" | "obj"}>;
  error: {code: string; message: string; retryable: boolean} | null;
};
```

### 7.3 Gate UI（沿用既有 CSS，scheduler 是唯一开关）

`awaiting_gate` 时前端展示后端 decision 的 3 个方向 option（label/rationale/confidence）+ clarification 场景显示问题输入框。操作映射：

| 按钮 | `GateAction` | 请求 |
| --- | --- | --- |
| 采用选项 i | `accept_option` | `POST /decisions/{id}/gate` `{run_id, action, selected_option_id}` |
| 都不满意（拒绝） | `request_revision`（**拒绝统一走重决策链路**，不再用 `reject_all`） | `POST …gate` `{run_id, action: "request_revision", reason}`（后端重新决策并再次发 `decision_completed` + `awaiting_gate`，前端刷新 decision 面板，用户可看到新方向选项） |
| 改一下 | `request_revision` | `POST …gate` `{run_id, action: "request_revision", user_revision}`（同上，携具体修改意见；「拒绝」与「改一下」走同一条 `request_revision` 链路，只是带不带修改文本的区别） |
| 澄清 | `clarify` | `POST …gate` `{run_id, action, user_revision}`（保留已选方向） |

Gate 是**唯一**在前端出现的决策点；其余阶段只展示进度，不做选择（scheduler 自动推进）。

**超时策略（已定）**：Gate 弹出后 90s 内无用户操作，前端自动以**推荐选项**（confidence 最高者，前端排序后取第一）提交 `accept_option`，与手动点击走同一条链路；**拒绝则走 `request_revision` 链路**（重新决策并再次弹 Gate），不做「超时即拒绝」，也不做终止。用户操作优先于超时。

**后端兼容说明（已改代码）**：`reject_all` 保留为 API 兼容与检索反馈语义（V1.1 起记 deprecation warning），前端不再发送它；正式路径只有 `accept_option` / `request_revision` / `clarify`。

**推荐项展示**：Gate 面板把 confidence 最高的 option 标记为「推荐」，默认高亮；超时自动提交的就是这一项。

### 7.4 run 生命周期动作

- 创建：行为提交（§3/§4）后，前端把最近 1-2 个行为 atom + 截图 URL 组装 `events` 数组 → `POST /api/v1/four-stage/runs`（`{session_id, idempotency_key, events, run_hy3d}`）；
- 轮询兜底：WS 断线时 `GET /runs/{run_id}` 每 2s 拉一次（复用现有 `refreshJob` 轮询模式）；
- Retry/Cancel：`POST /runs/{id}/retry|cancel`；
- 生成启动：`awaiting_gate` 解决后若后端未自动进 generation，前端可 `POST /runs/{id}/generation` 兜底触发。

---

## 8. 实施阶段（每阶段可独立验收）

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| P1 截图基础设施 | `viewportCapture.ts` + `POST /api/v1/screenshots` + 画笔/雕刻/拖拽提交带截图 | 网络面板可见 screenshot URL；planner evidence 含截图 |
| P2 2D 画笔增强 | 钢笔/marker/pencil 笔刷（brush-stamp 渲染，两头细中间粗）+ 原子提交 + scribble→mask（ONNX） | 2 笔画→1 次原子提交含 screenshot+mask；笔画呈现两端细中间粗的钢笔笔触 |
| P3 hover 2D 分割 | MobileSAM ONNX 前端 + Raycaster 兜底 + `hover_focus` 带 mask（**进意图但非阻塞，低优先级放后做**） | hover 高亮 <150ms；hover 推理慢不阻塞主意图触发 |
| P4 雕刻增强 | SculptNG 内核借鉴（crease/flatten）+ undo 快照 + 行为摘要 | 雕刻提交行为 atom 含 stroke 摘要 |
| P5 四阶段状态 | WS 事件订阅 + run 状态机 + Gate UI + option 回传 + 断线轮询 | 全链路走通：画笔→编码→检索→Gate→4 图 |
| P6 后端 SAM2 兜底（可选） | `/api/v1/segment/hover` + `SEGMENTATION_MODE` 开关 | local 不可用时可切 server |

建议顺序：**P1 → P5（打通四阶段主链路 + Gate，优先验收完整闭环）→ P2（2D 笔刷）→ P4（雕刻增强）→ P3（hover）→ P6（SAM2 兜底）**。P2/P3 共用 ONNX 模型，但 P3 优先级低于 P2/P4，可最后做；若想省一次集成，P3 也可与 P2 一起实现。

---

## 9. 风险与边界

- **MobileSAM 包体积**：模型 ~40MB 需缓存；演示机首次加载会慢。缓解：`crossorigin` 预取 + 加载进度条 + 失败自动降级 Raycaster。
- **截图隐私/体积**：截图只在本地会话使用，上传后端后即转 artifact URL；未登录态不开启。JPEG 640px 单张 ~80-150KB，可接受。
- **Qwen3 是文本模型**：截图理解只能走 Gemini-3.5-flash（后端，key 不入仓）；若 Gemini 不可用，前端截图层级降级为「无截图、仅行为」，不阻塞主流程。
- **Gate 默认超时策略**需要用户确认默认值（建议 90s 自动 accept 推荐项）。
- **SculptNG 借鉴边界**：只抄算法思路（falloff 曲线、算子数学），不复制其 UI/场景代码，避免许可证与集成复杂度。
- **双盲审**：实现阶段的仓库提交前做一次全仓扫描（去除服务器地址/端口/密钥），提交为私有 GitHub 仓库，发布前匿名化。

---

## 10. 已确认决策（v1 评审）

1. 2D 笔刷 = **Procreate 类钢笔笔刷形状**（两头细、中间粗、不过分粗、平滑无毛边，压力/速度驱动），非颜色/透明度切换；
2. Gate 超时 90s **自动 accept 推荐项**；拒绝与「改一下」统一走 `request_revision`（重新决策并再次弹 Gate），`reject_all` 废弃；
3. hover **进意图推测但非阻塞**——主意图触发不等 hover 推理，慢就晚到合并；hover 优先级低于主线；
4. 截图理解走 **Gemini-3.5-flash**（后端，key 不入仓）。

以下为实施时仍需微调的项（不阻塞开工）：
- 钢笔笔刷的具体纹理素材（程序化尖头渐变 vs 预渲染 stamp 贴图）与中间段宽度系数（建议 1.5-2.2×）；
- hover 推理的合并策略细节（晚到结果与主解释的优先级、去重窗口）。
