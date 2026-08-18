# Cursor → Codex：Perception 实时信号与前端行为记录模块交接

日期：2026-08-01  
发起：Cursor 前端  
对象：Codex 后端  

## 当前问题

1. 左侧 **Perception** 没有实时反映前端界面信号（orbit / dwell / hover / brush / annotation 等）。
2. 需要确认：后端“记录前端行为”的**主模块名称、接口与推送事件**是什么，前端应对齐哪一套。

## 规格里我们认为的主模块（请 Codex 确认或纠正）

开发规格 `FLOWSTUDIO_PROTOTYPE_FRONTEND_BACKEND_DEV_SPEC_V1_ZH.md` 与服务器现有实现，前端理解为：

| 层级 | 模块 | 作用 | 已有接口（服务器上看到的） |
| --- | --- | --- | --- |
| A. 行为原子 | **ActionAtom** | 记录 Hover/Brush/Annotation/Drag/Smooth/Add 等完成态操作 | `POST /api/v1/sessions/{id}/actions`、`GET .../actions` |
| B. 实时信号袋 | **live_signals** | 高频聚合后的标量信号，给 IR / Perception / suggest 用 | 挂在 interpret / suggest / draft metadata 里 |
| C. 观察快照 | **PerceptionSnapshot** | 低阶观察文案 + evidence + confidence | `GET /api/v1/sessions/{id}/perception/latest` |
| D. 会话恢复 | snapshot | 恢复 actions / interpretation / candidates | `GET /api/v1/sessions/{id}/snapshot` |

规格时序（§8.1）期望：

```text
camera / pointer 聚合
→ POST behavior episode / actions
→ 规则或 VLM 出 Perception
→ WS perception_updated
→ 左上 Perception 刷新（1s 内规则，3–8s VLM 可异步覆盖）
```

请 Codex 明确回答：

1. **主模块正式名称**是 `ActionAtom` store，还是另有 `EventCollector` / `BehaviorEpisode`？
2. 实时 Perception 应由前端：
   - 调 `POST /api/v1/interaction/interpret`（`type=camera_observation_ended` 等）静默刷新，还是
   - 只 `POST .../actions` + 读 `GET .../perception/latest`，还是
   - 另有专用 endpoint？
3. WebSocket 事件名是否已有 / 计划有：`perception_updated`、`action_atom_created`？payload 字段是什么？
4. `live_signals` 是否应独立持久化为 session 级最新快照（例如 `PUT /sessions/{id}/live-signals`），还是仅随 interpret/actions 附带？

## 前端现状（Cursor）

- 本地已聚合 `liveSignals`：`dwell_ms`、`viewport_orbit_count`、`viewport_zoom_count`、`hover_count`、`brush_count`、`annotation_count`、`mask_coverage`、`drawing_content`、`semantic_distance` 等。
- 工具完成会 `recordActionAtom` → `POST .../actions`。
- **缺口**：Perception 面板目前几乎只绑 `interpretation`（Send 之后才有），没有把 `liveSignals` / `perception/latest` / WS 接成实时刷新。
- Cursor 会先做前端侧：Perception 展示 live signals + 防抖静默 interpret（若你们确认用 interpret）+ 监听 WS。

## 请 Codex 返回的最小契约

请在 `docs/FLOWSTUDIO_CURSOR_BACKEND_CONTRACT_V1_ZH.md` 增补一节，至少包含：

```text
### Perception 实时环

1. 前端上报路径：...
2. 后端主模块名：...
3. 读取路径：GET /perception/latest 字段定义
4. WS 事件：type / payload
5. 推荐防抖窗口：相机聚合 ms；静默 interpret 间隔
6. 哪些信号算 observed_facts，哪些只能进 evidence / live_signals
```

## 联调环境

```bash
ssh -p 50575 \
  -L 5173:127.0.0.1:5173 \
  -L 8000:127.0.0.1:8000 \
  root@connect.westb.seetacloud.com
```

前端本地 Vite：`http://127.0.0.1:5173`  
后端隧道：`http://127.0.0.1:8000`
