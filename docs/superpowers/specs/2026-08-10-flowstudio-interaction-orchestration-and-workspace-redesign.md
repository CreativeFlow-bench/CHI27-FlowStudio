# FlowStudio 交互编排内核与工作区重构策略

日期：2026-08-10

状态：待用户复核的设计策略

范围：后端状态机、持久任务、事件一致性、前端交互协调、响应加速与工作区版面接入

## 1. 结论

本轮完整重写 FlowStudio 的交互编排内核，但不重写模型能力、3D 编辑算法和生成质量算法。

重写后的唯一产品主线为：

```text
持续观察用户行为
  → 锁定一次 IntentRevision
  → 后台规划出一句 Scope Gate
  → 用户接受或拒绝范围
  → 独立后台任务生成发散关键词
  → 用户选择并保存关键词
  → 用户显式点击 Generate
  → 独立后台任务生成 Solution Batch
  → 用户比较结果并创建版本分支
```

本策略同时解决以下已确认问题：

1. Active Editor 被版本节点的固定 `520×520` 尺寸限制，模型显示不完整；
2. Gate 泡泡点击后等待实验记录、Gate API 和关键词模型，表现为点不动；
3. AI Behavior 同时承担状态、Gate、模型详情、参数、关键词和生成，滚动与交互失效；
4. 关键词必须等待同步 Gate 请求和轮询，响应过慢；
5. Perception 视觉权重过高；
6. 多套前端状态互相覆盖，刷新、重连和并发 IntentRevision 时结果不稳定。

## 2. 产品依据与优先级

实现以以下文件为产品契约，按优先级解释冲突：

1. `docs/FLOWSTUDIO_PRODUCT_DEFINITION_AND_MODIFICATION_STRATEGY_V1_2_ZH.md`；
2. `UI Design/Flow-Studio-Handoff/02-Product-Spec/acceptance-criteria.md`；
3. `UI Design/Flow-Studio-Handoff/02-Product-Spec/interaction-spec.md`；
4. `docs/FLOWSTUDIO_REALTIME_OBSERVATION_MULTI_INTENT_MODIFICATION_STRATEGY_2026_08_05_ZH.md`；
5. `UI Design/Flow-Studio-Handoff/03-API-Spec/data-model.md` 与 `api-contract.yaml`。

不可破坏的产品约束：

- 四阶段是后台能力，不是四个要求用户阅读的前端步骤；
- Perception 只展示低阶、可验证的用户行为；
- 每个 IntentRevision 只有一句 Gate 问题；
- 不同 IntentRevision 可以同时存在和独立确认；
- Gate 只确认改变范围，不等待或展示细粒度发散方向；
- 用户关键词是生成方向的主导输入；
- 只有用户显式点击 Generate 才能进入生成；
- 慢任务不能锁住 3D 导航和其他 revision；
- 原始实验记录只追加、不可修改；权威审计与业务状态同事务快速写入，较慢的实验投影和资产整理不得阻塞主要交互；
- Solution Batch 按 `intent_seq` 追加，不能清空或覆盖先前结果。

## 3. 本轮范围

### 3.1 包含

- 统一的后端领域状态与合法转移；
- 数据库持久化任务队列、租约、重试、取消和恢复；
- transactional outbox 与领域事件推送；
- Gate acknowledgement 与 semantic divergence 解耦；
- divergence selection 与 Behavior/ActionAtom 解耦；
- Generate 与生成任务解耦；
- 多 IntentRevision 独立状态和结果排序；
- 前端 Interaction Coordinator、reducer、selectors 和恢复机制；
- 移除关键交互对 1.5 秒轮询和人工 typewriter 延迟的依赖；
- AI Behavior 固定 Dock、单一滚动容器和状态分区；
- Gate 泡泡的即时反馈、命中区、错误和重试；
- Active Editor 与 Version Graph 展示尺寸解耦；
- Perception 视觉降级；
- 兼容迁移、功能开关、故障注入和端到端验收。

### 3.2 不包含

- 更换 Gemini、本地 VLM、Qwen-Image 或 Hy3D；
- 优化模型提示词和关键词语义质量；
- 重写 mesh 编辑、brush、drag、smooth 或 Three.js 渲染算法；
- 重写 part segmentation、mask 或 identity/locality 算法；
- 完成 OSS、case library 和网站发布链路；
- 为第一版引入 Redis、Celery、Kafka 或额外微服务。

现有模型服务作为有延迟、可能失败、允许重试的黑盒任务处理器接入新内核。

## 4. 架构原则

### 4.1 不建立一个超级状态枚举

Intent、关键词任务、关键词选择和生成任务具有不同生命周期。将它们塞进一个状态机会继续制造耦合，因此拆成四个独立聚合，再由 Projection 组合成用户可见阶段。

### 4.2 命令与事件分离

- Command 表达用户请求系统做什么；
- Domain Event 表达系统已经发生什么；
- Task 表达需要后台执行的慢工作；
- Projection 表达前端当前应该显示什么。

组件不能通过检查多个布尔值自行推断业务阶段。

### 4.3 后端状态权威，前端即时反馈

前端可以立即展示 `submitting`、`saving` 等瞬时状态，但 accepted、completed 等持久状态必须来自后端带版本号的响应或事件。

### 4.4 关键交互不等待模型

以下请求必须快速完成，不得同步调用模型：

- Accept Gate；
- Reject Gate；
- Save Divergence Selection；
- Start Generation 的任务创建。

### 4.5 所有慢任务可恢复

后端或 Worker 重启后，queued/running 任务必须被重新领取或明确失败，不能永久卡住。

## 5. 领域状态模型

### 5.1 IntentRevision

负责一次被锁定的意图窗口及范围确认，不负责关键词生成状态。

```text
planning
awaiting_gate
accepted
rejected
cancelled
failed
```

合法转移：

```text
planning → awaiting_gate | failed | cancelled
awaiting_gate → accepted | rejected | cancelled
accepted → accepted
rejected → rejected
cancelled → cancelled
failed → failed
```

`accepted/rejected/cancelled/failed` 对该 revision 的 Gate 生命周期是终态。重复接受相同 Gate 返回当前资源，不创建重复任务；相反决策返回明确 conflict。

### 5.2 DivergenceTask

负责调用现有 semantic divergence 服务。

```text
queued
running
succeeded
failed
cancelled
superseded
```

当参数或 authoritative decision 改变时，旧任务可以继续完成审计，但必须标记 superseded，不能覆盖新结果。

### 5.3 DivergenceSelection

后端持久状态只有稳定快照：

```text
empty
saved
```

前端在此基础上增加瞬时投影：

```text
dirty
saving
save_failed
```

保存内容必须使用 candidate ID、原始 label、group、参数版本和 selection version。关键词选择不进入 Behavior、ActionAtom 或新 Gate 的证据窗口。

### 5.4 GenerationTask

```text
queued
running
quality_checking
succeeded
partial
failed
cancelled
```

没有 saved selection 或没有显式 StartGeneration command 时，不允许创建 GenerationTask。

### 5.5 前端阶段 Projection

四个聚合被投影为稳定的用户阶段：

```text
observing
planning_intent
awaiting_gate
preparing_keywords
choosing_keywords
ready_to_generate
generating
reviewing_solutions
needs_attention
```

Projection 只负责展示，不反向驱动领域状态。

## 6. Command 与 Domain Event 契约

### 6.1 Commands

```text
SubmitIntent
AcceptGate
RejectGate
RetryDivergence
UpdateDivergenceSelection
StartGeneration
CancelTask
```

每个 Command 必须包含：

```text
command_id
idempotency_key
project_id
session_id
revision_id（适用时）
expected_version（适用时）
actor
requested_at
payload
```

### 6.2 Domain Events

```text
IntentRevisionCreated
IntentPlanningStarted
GateProposed
GateAccepted
GateRejected
DivergenceQueued
DivergenceStarted
DivergenceCompleted
DivergenceFailed
DivergenceSuperseded
SelectionSaved
SelectionSaveFailed
GenerationQueued
GenerationStarted
GenerationProgressed
GenerationCompleted
GenerationPartiallyCompleted
GenerationFailed
TaskCancelled
```

每个事件必须包含：

```text
event_id
event_type
project_id
session_id
revision_id
intent_seq
aggregate_type
aggregate_id
aggregate_version
correlation_id
causation_id
occurred_at
payload
```

前端按 `event_id` 去重，按 `aggregate_version` 丢弃旧事件。

## 7. 持久任务系统

### 7.1 数据结构

新增统一 `interaction_tasks`：

```text
task_id
task_type
project_id
session_id
revision_id
status
input_json
result_ref
progress
attempt
max_attempts
lease_owner
lease_expires_at
idempotency_key
created_at
started_at
completed_at
error_code
error_message
```

任务类型第一版只有：

```text
intent_planning
semantic_divergence
solution_generation
```

### 7.2 Worker 领取规则

- 使用数据库条件更新领取 queued 或 lease expired 的任务；
- running 任务定期续租；
- 进程退出后由新 Worker 重新领取；
- 相同 idempotency key 只能有一个有效任务；
- 每次 attempt 保存开始、结束和错误；
- 达到 max attempts 后进入 failed；
- 用户取消 queued 任务立即生效，running 任务设置 cancellation requested；
- 模型返回后再次检查 revision、decision、参数和 task 是否仍为当前权威版本。

### 7.3 第一版不引入外部队列

当前实验规模使用 SQLite/PostgreSQL 支持的数据库任务表即可满足持久化和恢复。只有实测吞吐或多机争用超出数据库任务表能力时，才评估 Redis/Celery。

## 8. Transactional Outbox 与实验记录

### 8.1 三类数据分开

1. Raw Experiment Event：用户原文、行为、参数、时间戳和资产引用；
2. Domain Event：业务状态已经发生的变化；
3. Outbox Record：等待投递到 WebSocket、实验导出或其他消费者的事件。

Raw Experiment Event 和 Domain Event 都只追加，不修改。

当前 FourStageStore 与 ExperimentProjectStore 使用两个独立 SQLite 连接，不能依赖跨库事务。V2 新增一个 InteractionStore，使用同一个数据库事务保存：

- IntentRevision 和任务等权威业务状态；
- `interaction_audit_events` 中与 Command 对应的权威原始审计记录；
- Domain Event；
- Outbox Record。

ExperimentProjectStore 继续负责实验项目、运行、资产引用和导出视图，但其 interaction event 明细由 outbox 异步复制。复制失败不会回滚已确认的业务状态；outbox 保留重试并在实验界面显示记录同步健康度。对一次交互命令而言，InteractionStore 中的 audit event 是不可修改的权威记录，ExperimentProject 是可重建的实验投影。

### 8.2 移除前端关键路径阻塞

当前前端先等待串行 `projectRecorder.record(..., critical)`，再发送 Gate 请求。重构后：

```text
前端发送 AcceptGate command
  → 服务端事务保存 GateAccepted + Raw Event + DivergenceTask + Outbox
  → 快速返回 revision/task projection
  → Outbox 异步推送与导出
```

InteractionStore 中权威 audit event 写入失败必须使本次服务端事务整体失败并返回可修复错误；ExperimentProject 投影复制失败不得阻塞或撤销 Gate。前端已有其他非关键记录的队列不能延迟 Gate。

## 9. API 策略

### 9.1 Gate

```text
POST /api/v1/intent-revisions/{revision_id}/gate
```

只执行：

- 校验 expected revision version；
- 保存 accepted/rejected；
- accepted 时创建或复用 DivergenceTask；
- 写入领域事件、实验事件和 outbox；
- 返回 revision projection 与 task summary。

禁止在请求内调用 knowledge router、Gemini 或本地 VLM。

### 9.2 Tasks

```text
GET  /api/v1/interaction-tasks/{task_id}
POST /api/v1/interaction-tasks/{task_id}/retry
POST /api/v1/interaction-tasks/{task_id}/cancel
```

### 9.3 Selection

```text
PUT /api/v1/intent-revisions/{revision_id}/divergence-selection
```

请求携带 `expected_selection_version`，返回新的稳定选择快照。

### 9.4 Generation

```text
POST /api/v1/intent-revisions/{revision_id}/generation-tasks
```

只验证 selection 和 source context，创建任务并返回，不同步生成。

### 9.5 Recovery Projection

```text
GET /api/v1/sessions/{session_id}/interaction-projection
```

返回恢复 UI 所需的最小权威数据：

- IntentRevision 列表；
- 每个 revision 的当前 DivergenceTask；
- saved selection；
- GenerationTask 与 SolutionBatch 摘要；
- `last_event_cursor`。

## 10. WebSocket 与恢复

### 10.1 推送

Outbox dispatcher 按持久化顺序推送领域事件。消息包含 event cursor，客户端确认收到的最大 cursor。

### 10.2 断线恢复

```text
WebSocket 断开
  → UI 保留当前 projection 并显示连接状态
  → 重连后携带 last_event_cursor
  → 服务端补发可用事件
  → 若事件窗口不足，GET interaction-projection
  → reducer 按版本合并
```

1.5 秒 realtime observation 轮询可以保留为低频观察快照兜底，但不得再承担 Gate、关键词和生成任务的主要完成通知。

## 11. 前端 Interaction Coordinator

### 11.1 模块边界

从 `studioStore.ts` 抽出：

```text
frontend/src/interaction/
  commands.ts
  events.ts
  reducer.ts
  selectors.ts
  coordinator.ts
  recovery.ts
  types.ts
```

### 11.2 职责

- dispatch Command；
- 维护 submitting/saving 等瞬时状态；
- 合并 API acknowledgement；
- 消费 WebSocket Domain Event；
- 按 event ID 去重；
- 按 aggregate version 拒绝旧事件；
- 断线恢复 projection；
- 为组件生成只读 ViewModel；
- 将错误绑定到具体 revision/task，而不是全局面板。

### 11.3 组件约束

以下组件不能再直接读取多套底层业务状态并自行判断阶段：

- PlannerClarificationOverlay；
- AIBehaviorPanel；
- More Creative；
- Generate 控件；
- Solution Space。

组件只能：

```text
读取 ViewModel
  → 渲染
  → dispatch 用户 Command
```

### 11.4 废弃的前端模式

- 单一全局 `gateOpen` 表示多个 revision；
- `intentBubble + fourStage + uiBrief + interpretation` 共同决定同一控件；
- 模型请求完成前不改变按钮状态；
- 依赖固定轮询才能知道 task 完成；
- 700–2400ms planner debounce 后再逐字输出；
- 任何一个 revision 的成功清除其他 revision 的错误或选择。

## 12. 响应加速设计

### 12.1 用户感知预算

| 操作 | 目标 |
| --- | --- |
| 点击 Gate 后出现 submitting | 100ms 内 |
| Gate 本地服务 acknowledgement | p95 500ms 内，不含模型 |
| DivergenceTask queued 状态可见 | Gate acknowledgement 同一响应 |
| 关键词 loading skeleton | 100ms 内 |
| 关键词完成后的 UI 更新 | 收到事件后 200ms 内 |
| 关键词点击反馈 | 50ms 内 |
| selection 保存状态出现 | 100ms 内 |
| Generate 创建任务 | p95 500ms 内，不含生成 |
| 页面恢复出主要 UI | projection 返回后 300ms 内 |

### 12.2 加速手段

- Gate 与模型调用分离；
- 实验记录移入服务端事务和 outbox；
- 任务结果事件推送替代主要轮询；
- 去除人为 typewriter 延迟；
- selection 使用即时本地选择状态，后台版本化保存；
- 相同 request key 的已完成 divergence 结果可复用；
- in-flight 相同任务去重；
- 组件只订阅细粒度 selector，减少全局 rerender。

## 13. 多 IntentRevision 一致性

每个 revision 独立保存：

- Gate 状态；
- 当前 authoritative decision；
- DivergenceTask；
- DivergenceSelection；
- GenerationTask；
- SolutionBatch；
- error 与 retry；
- aggregate version。

一致性规则：

- Gate 可以并行确认；
- 每个 revision 只渲染一个 Gate；
- 当前 active revision 高亮，但不是唯一可运行 revision；
- A 的成功不能清除 B 的失败；
- B 的完成不能覆盖 A 的关键词；
- selection 保存只校验对应 revision 的 selection version；
- GenerationTask 可以并行执行，SolutionBatch 按 `intent_seq` 稳定追加；
- 同一 revision 的旧 task 完成只能进入 superseded 审计状态。

## 14. Workspace UI Integration

交互内核重写必须包括前端版面接入，否则架构正确但用户问题仍未解决。

### 14.1 Active Editor 与 Version Graph 解耦

当前 Active Editor 被版本树的固定 520px 活动节点包裹。改为两个视图：

#### Active 模式

- 3D 编辑器占据完整 workspace safe area；
- 不受版本树 node width/height 影响；
- 自动避开顶部版本栏、右侧 Dock、Perception 和底部 Composer；
- 容器变化后重新 fit-to-view；
- 模型必须完整显示，允许用户主动 zoom；
- 版本树只保留轻量导航提示。

#### Overview 模式

- 所有版本使用 220px 缩略节点；
- 使用现有祖先向左、兄弟向下的图布局；
- 点击版本进入 Active 模式；
- 不在 Overview 中挂载完整 ThreeViewport。

建议使用 CSS safe-area variables 描述布局，而不是将 UI 尺寸写入版本图算法：

```text
--workspace-safe-top
--workspace-safe-right
--workspace-safe-bottom
--workspace-safe-left
```

### 14.2 Gate Bubble

- 问题保持一句；
- Accept/Reject 命中区域不小于 40×40px，目标 44×44px；
- 点击后 100ms 内显示 submitting；
- 禁止重复点击；
- acknowledgement 后显示已确认并退出决策态；
- divergence 失败不让 Gate 回退；
- 错误给出重试或转到右侧面板；
- 画布 Bubble 与右侧 Gate 卡 dispatch 同一个 Command；
- Bubble 布局避让 Active Editor 关键目标和固定 Dock；
- 多 revision 使用稳定槽位和碰撞避让。

### 14.3 AI Behavior 固定 Dock

移除任意高度拖动和隐藏式 16px resize handle，改为固定右侧 Dock。桌面目标宽度 380–420px，窄屏进入明确的抽屉模式。

结构：

```text
固定 Header
当前阶段与一句状态
条件式 Gate 操作卡
────────────────
唯一滚动内容区
  More Creative
  参数（默认收束）
  关键词
  Generate
────────────────
折叠的完整模型详情
```

规则：

- `height: calc(100dvh - safe top - safe bottom)`；
- 使用 `grid-template-rows: auto auto minmax(0, 1fr) auto`；
- 只有一个 `.ai-panel-scroll` 拥有 `overflow-y: auto`；
- `scrollbar-gutter: stable` 并提供可见滚动条；
- `overscroll-behavior: contain`；
- Composer 不得覆盖 Dock 内容和操作；
- Gate 问题只显示一次；
- model details 默认折叠；
- 参数与关键词不建立第二个垂直滚动容器；
- loading、failed、retry 不仅通过颜色表达。

### 14.4 AI Behavior 状态布局

```text
awaiting_gate       → Gate 操作卡，More Creative 锁定
preparing_keywords  → 范围已确认 + skeleton，3D 可操作
choosing_keywords   → 关键词和参数可操作
ready_to_generate   → Generate 可用
generating          → 进度和取消，不锁 3D
needs_attention     → 当前 task 的错误与重试
```

不再同时展示四阶段 mini、重复 Gate summary、当前现象和下一步中的同义内容。

### 14.5 Perception

Perception 是辅助观察层：

- 标题 10–11px；
- 当前动作 13–14px；
- 最大两行；
- 内容区最小高度 58–64px；
- 默认宽度约 300–340px；
- 历史 11–12px；
- 不显示内部 phase、scope token、模型原文或用户输入原文；
- 与 Gate、AI Behavior 保持明确视觉层级差。

## 15. 错误处理

错误必须绑定具体资源：

| 错误 | 保留状态 | 用户操作 |
| --- | --- | --- |
| Gate command conflict | 保留服务端 revision | 刷新当前 revision |
| InteractionStore 权威审计事务失败 | Gate 不提交 | 重试 Gate，原始操作仍在本地输入状态 |
| ExperimentProject 投影同步失败 | Gate 与任务保持原状态 | Outbox 自动重试，实验界面显示记录同步异常 |
| DivergenceTask failed | Gate 保持 accepted | Retry Keywords 或补充意图创建新 revision |
| Selection save failed | 本地选择保持 dirty | Retry Save，不允许 Generate |
| GenerationTask failed | selection 保持 saved | Retry Generation |
| WebSocket 断开 | projection 保持 | 自动重连并补拉 |
| 旧事件到达 | 当前状态不变 | 静默记录 stale event |
| Worker 重启 | task 恢复 queued/running | 显示恢复中，无需用户重复提交 |

禁止用全局错误清空所有关键词、关闭所有 Bubble 或重置整个 AI Behavior。

## 16. 可观测性

在切换前增加以下指标：

```text
command_received_at
command_acknowledged_at
task_queued_at
task_started_at
model_started_at
model_completed_at
event_published_at
event_received_at
projection_rendered_at
```

核心指标：

- Gate acknowledgement p50/p95；
- task queue wait p50/p95；
- divergence execution latency；
- generation execution latency；
- stale event count；
- duplicate command count；
- recovered task count；
- WebSocket reconnect/recovery count；
- selection save failure rate；
- UI command-to-feedback latency。

日志使用 correlation ID 串联 Command、Domain Event、Task 和模型调用，不记录未脱敏的用户原文到通用应用日志。

## 17. 测试策略

### 17.1 状态机单元测试

- 每个合法转移；
- 每个非法转移；
- terminal state 不可回退；
- 相同 Command 幂等；
- expected version conflict；
- superseded task 不覆盖结果。

### 17.2 任务系统测试

- queued → running → succeeded；
- Worker 在 running 时退出，lease 过期后恢复；
- 重试次数与退避；
- 相同 idempotency key 去重；
- cancel queued/running；
- 模型超时和 fallback；
- task 完成与 outbox 持久化原子性。

### 17.3 前端 reducer 测试

- event ID 去重；
- aggregate version 防旧写；
- acknowledgement 与 WebSocket 乱序；
- A/B revision 隔离；
- disconnect/recovery merge；
- selection dirty/saving/saved/error；
- Gate accepted 后 divergence failed 不回退。

### 17.4 交互测试

- Bubble Accept/Reject 键盘与指针操作；
- 100ms 内反馈；
- 右侧单滚动容器；
- Composer 不覆盖 Dock；
- Active Editor 在参考桌面尺寸完整展示模型；
- 关键词 loading 时 3D 仍可旋转；
- Generate 前置条件；
- Perception 字号与两行限制。

### 17.5 故障注入

- InteractionStore 权威事务写入失败；
- ExperimentProject 投影复制失败后恢复；
- WebSocket 断线；
- Worker 重启；
- Gemini 超时；
- fallback 失败；
- selection 保存返回冲突；
- GenerationTask 部分成功；
- 同一按钮快速点击两次；
- 两个 revision 先后响应倒序。

### 17.6 产品案例

使用 snowman、teapot、water gun 验证交互编排，不把模型图像质量作为本轮完成条件。每个案例验证：

- 具体 source/version/part 上下文保留；
- Gate 单句且可即时确认；
- 关键词任务异步；
- 用户选择可靠保存；
- 显式 Generate 创建任务；
- 刷新与重启后状态恢复；
- 多 revision 不覆盖。

## 18. 迁移与发布 Checkpoints

### C0：契约、基线测试与耗时观测（3–4 工程日）

- 冻结 Command/Event/Task/Projection schema；
- 为旧链路增加端到端时间点；
- 建立旧状态到新状态映射；
- 保存当前交互回归 fixture；
- 不改变用户行为。

验收：可以量化当前 Gate 和关键词等待分别耗时在哪里。

### C1：Task Store、Worker 与 Outbox（5–7 工程日）

- 建表和迁移；
- 实现任务租约、重试、取消和恢复；
- 实现 transactional outbox；
- 旧 UI 暂时仍可运行。

验收：模拟进程退出后任务可以恢复，不重复执行已完成请求。

### C2：Gate 与 Divergence 解耦（5–7 工程日）

- Gate 快速返回；
- accepted 同事务创建 DivergenceTask；
- Worker 调用现有 semantic divergence；
- WebSocket 发布任务事件；
- 保留旧接口 adapter 和 feature flag。

验收：Gate API 无模型调用；模型失败不撤销 Gate。

### C3：Frontend Interaction Coordinator（6–8 工程日）

- 新 reducer、selectors、commands、recovery；
- Bubble、AI Behavior、More Creative 和 Generate 接入；
- 删除关键路径的人工 typewriter 延迟；
- 旧、新 projection 双读对比。

验收：多 revision、事件乱序、刷新和断线恢复通过。

### C3B：Workspace UI Integration（3–5 工程日）

- Active Editor 与版本树尺寸解耦；
- 固定右侧 Dock 与单滚动区；
- Bubble 命中区和反馈；
- Perception 视觉降级；
- 统一 safe area 与 z-index；
- 1440×900、1920×1080 和宽屏视觉验收。

验收：用户提出的四个前端问题逐项关闭。

### C4：全量切换、清理与部署验收（6–8 工程日）

- 新内核成为默认路径；
- 保留一个发布周期的只读兼容 adapter；
- 清理旧 `gateOpen`、单体 `intentBubble` 和任务完成轮询；
- 完成故障注入和三案例验收；
- 同步本地、部署源码、dist 和 build ID。

验收：旧内核关闭后全部交互、恢复和审计测试通过。

预计总量：28–39 工程日。两名熟悉代码的工程师可在存在顺序依赖的前提下压缩为约 4–6 个自然周。

## 19. 功能开关与回滚

使用 project/session 级功能开关：

```text
interaction_orchestrator_v2
workspace_layout_v2
```

发布顺序：

1. 数据库 schema 向前兼容；
2. 后端同时支持旧读路径和新 projection；
3. 内部项目开启 V2；
4. 三案例通过；
5. 新项目默认 V2；
6. 旧项目迁移；
7. 停止旧路径写入；
8. 一个发布周期后删除旧代码。

回滚只切换读写入口，不删除 V2 已写入的任务、事件和 projection。回滚后仍可审计 V2 期间发生的全部用户命令和任务结果。

## 20. 完成定义

只有以下条件全部成立，本轮才算完成：

### 后端

- Gate API 不同步调用模型；
- 任务可持久化、重试、取消和重启恢复；
- Command 幂等且有版本冲突保护；
- Domain Event 与业务状态原子保存；
- 多 revision 不互相覆盖；
- 没有显式 Generate 时生成调用数为 0。

### 前端交互

- Gate 点击 100ms 内反馈；
- 关键词 loading 立即可见；
- task 失败可局部重试；
- 断线和刷新后恢复；
- 旧事件不能覆盖新状态；
- 一个 revision 的结果不清除其他 revision。

### 前端版面

- Active Editor 使用完整安全工作区并显示完整模型；
- AI Behavior 只有一个可操作滚动容器；
- Composer 不覆盖 Dock；
- Gate Bubble 命中区满足要求；
- Gate 内容不重复；
- Perception 保持辅助层字号和内容密度；
- 参考桌面尺寸无关键控件遮挡。

### 实验记录

- 用户原文、行为、参数和选择按时间顺序完整保存；
- 原始记录不可修改；
- 记录链路不因前端串行队列阻塞 Gate；
- 每个 Command、Task 和结果可以用 correlation ID 追溯。

## 21. 决策摘要

- 选择完整重写交互编排内核，不重写模型能力；
- 选择多个小状态机与 Projection，不选择超级状态枚举；
- 选择数据库持久任务队列，不立即引入额外基础设施；
- 选择 transactional outbox 保证状态、审计和通知一致；
- 选择后端权威状态与前端瞬时反馈并存；
- 选择事件推送作为任务完成主通道，轮询只做恢复兜底；
- 选择 Active Editor 与 Version Graph 分离；
- 选择固定右侧 Dock 和单一滚动所有权；
- 将用户提出的版面问题纳入本轮完成定义，而不是留作无验收的后续美化。
