# FlowStudio 常驻 Observation 与多意图泡泡修改策略

日期：2026-08-05  
状态：产品规则冻结，GPU 定点部署完成；snowman 双 revision 的队列/继承/追加通过，但视觉 identity 与部件约束失败；C7 未完成  
上位产品定义：`docs/FLOWSTUDIO_PRODUCT_DEFINITION_AND_MODIFICATION_STRATEGY_V1_2_ZH.md`  
关联交付策略：`docs/FLOWSTUDIO_2026_08_05_PRODUCT_DELIVERY_MODIFICATION_STRATEGY_ZH.md`

## 1. 本次修订结论

FlowStudio 不是“点击按钮后才启动编码、检索和推理”的静态管线，而是：

```text
常驻 Observation
  → 持续记录 Behavior
  → 持续增量编码 Design State
  → 持续增量检索 Design-State IR
  → 用户点击 Intent Send 时锁定一个历史窗口
  → Planner 只推断该锁定窗口的目标部件/范围
  → 为该 IntentRevision 生成一个 Gate 泡泡
  → Gate 接受后进入关键词发散与生成
```

Observation 在 Planner、Gate、发散和生成期间均不中断。锁定点之后发生的新行为进入下一个 IntentRevision 的记录范围，不得反向修改已经锁定的版本。

多个用户显式提交的 IntentRevision 可以同时对应多个意图泡泡。产品限制的是“同一个 IntentRevision 不得重复弹问”，不是“画布全局只能有一个泡泡”。

## 2. UI 依据与本轮草图解释

视觉与交互基线仍以仓库目录 `UI Design` 和其中的 `Flow-Studio-Handoff` 为准。

本轮用户提供的“雪人主体周围同时排列 `Silhouette Change` 与 `Part Change?`”草图，作为以下交互规则的补充依据：

- 多个 IntentRevision 的泡泡可以同时围绕当前主体排列；
- 每个泡泡只对应一个目标范围和一句问题；
- 已接受的泡泡可收敛为无操作按钮的紧凑标签；
- 待确认泡泡保留 Accept/Reject；
- 泡泡通过锚点或引导线关联整体轮廓、部件或材质区域；
- More Creative 仍是唯一的细粒度关键词选择区；
- 多个意图产生的结果按 IntentRevision 顺序追加到 Solution Space。

该草图是交互语义补充，不替代 `UI Design` 中的组件尺寸、字体、颜色和版式规范。

## 3. 行为粒度：一次工具使用是一个 Behavior

不得继续采用“一笔 stroke 等于一个行为”的逻辑。

```text
tool_start
  → 多个 pointer/stroke/update 仅在当前工具会话内聚合
  → tool_end / tool_switch / explicit_commit
  → 提交一个 Behavior
```

每个 Behavior 至少保存：

```json
{
  "behavior_id": "beh_014",
  "sequence": 14,
  "tool": "drag",
  "asset_id": "asset_snowman",
  "target_part_id": "part_hat",
  "target_label": "帽子",
  "started_at": "...",
  "ended_at": "...",
  "stroke_count": 13,
  "start_views": {"front": "...", "side": "...", "top": "..."},
  "end_views": {"front": "...", "side": "...", "top": "..."},
  "operation_summary": {},
  "artifact_refs": []
}
```

原始 pointer/stroke 数据可以保存在调试或几何 artifact 中，但不作为主要行为历史中的独立圆点，也不逐笔触发 Planner、Gate 或完整模型编码。

前端历史区中：

- 一个圆点代表一个已完成 Behavior；
- 当前工具会话只显示一个 active 圆点；
- `13 笔`应显示为该 Behavior 的 `stroke_count=13`，不得产生 13 个圆点；
- 圆点位于工具/输入面板之外的历史轨道；
- 点击圆点可以查看工具、目标、开始/结束三视图、参数和撤销状态。

## 4. 常驻 Observation 的职责

### 4.1 三层状态

| 层 | 生命周期 | 职责 | 是否触发 Gate |
| --- | --- | --- | --- |
| `EventLedger` | 全 session 常驻 | 追加所有原始事件、Behavior、反馈和版本记录 | 否 |
| `LiveObservationState` | 全 session 常驻 | 增量编码当前设计阶段、目标假设、操作和检索结果 | 否 |
| `IntentRevision` | 每次 Intent Send 创建 | 锁定 cutoff 之前的一段历史，供 Planner 与 Gate 使用 | 是，每 revision 一个 |

### 4.2 增量而非重算

常驻 Observation 使用：

```text
previous_live_state + behavior_delta → next_live_state
```

不得每次从 session 全部原始事件重新计算。建议：

- pointer/viewport 高频信号在前端聚合；
- Behavior 完成后立即更新确定性 reducer；
- 每 500–1000ms 或 Behavior burst 稳定后运行一次增量编码；
- 仅当 `target/scope/operation/design_phase` 指纹变化时刷新检索；
- 相同查询指纹复用 retrieval cache；
- VLM/LLM 慢结果异步 refine，不阻塞新的 Observation；
- Observation 的 UI 更新时间目标小于 200ms，模型 refine 不影响用户继续操作。

### 4.3 设计阶段和后端阶段必须分离

用户设计阶段：

```text
Observe → Focus → Shape/Connect → Surface/Reference → Commit → Diverge → Compare
```

内部执行阶段：

```text
encoding → retrieval → re-representation → generation
```

内部阶段变化不得直接触发泡泡；只有用户点击 Intent Send 才创建 IntentRevision 和对应 Gate。

## 5. Intent Send 与历史窗口锁定

点击 Intent Send 时必须进行原子切分：

```text
cutoff_seq = 当前 EventLedger 最大 sequence
当前 open window = [window_start_seq, cutoff_seq]
下一 open window = [cutoff_seq + 1, ...]
```

创建：

```json
{
  "revision_id": "intent_rev_02",
  "intent_seq": 2,
  "parent_revision_id": "intent_rev_01",
  "window_start_seq": 15,
  "cutoff_seq": 23,
  "snapshot_behavior_ids": ["beh_015", "beh_018", "beh_023"],
  "snapshot_design_state": {},
  "snapshot_retrieval_refs": [],
  "user_text": "...",
  "status": "planner_pending"
}
```

Planner 优先复用锁定时的 `LiveObservationState` 和 retrieval cache，只对 cutoff 前尚未合入的 delta 做最终归并。提交后新产生的 Behavior 继续进入下一窗口，不能污染当前 Planner、Gate 或 GenerationSpec。

## 6. 多 Intent Bubble 规则

### 6.1 数量规则

- 一个 IntentRevision 恰好产生一个用户可见 Gate question；
- 同一个 revision 的模型 refine、重试、WebSocket 重连和轮询不得重复创建泡泡；
- 多个不同 revision 可以同时显示多个泡泡；
- 泡泡以 `revision_id` 作为稳定 key，不以 `decision_id` 或组件 render 次数作为 key。

### 6.2 空间布局

- 根据目标部件的 3D/屏幕投影位置计算 anchor；
- 整体轮廓泡泡锚定主体外轮廓；
- 部件泡泡锚定具体 part/region；
- 采用稳定的环形/象限槽位进行碰撞避让；
- 新泡泡选择距离目标最近的空闲槽位；
- 已显示泡泡位置保持稳定，禁止在模型旋转或状态轮询时频繁跳动；
- 泡泡不得遮挡主要目标、底部 Intent Composer 或右侧 More Creative；
- 当目标位于屏幕外时，泡泡降级为边缘指示标签，并保留回到目标的操作。

### 6.3 泡泡状态

| 状态 | UI |
| --- | --- |
| `planner_pending` | 可显示短暂计算状态，不出现空问题框 |
| `gate_pending` | 显示一句问题和 Accept/Reject |
| `accepted` | 收敛为紧凑彩色标签，可继续作为结果 provenance |
| `rejected` | 短暂显示拒绝状态后淡出；历史仍保留 |
| `generating` | 标签显示生成进度，不重新出现 Accept/Reject |
| `completed` | 标签保留为结果分组入口或按用户操作收起 |

不得使用 10 秒自动忽略来删除一个已显式提交的 IntentRevision，也不得自动接受。

## 7. 快速连续 Send 与并行 Gate

用户可以在前一个 Gate 未完成时再次点击 Send：

1. 立即锁定新的 cutoff；
2. 创建新的 IntentRevision；
3. Planner 独立推断该窗口；
4. 新泡泡可以与旧泡泡同时显示；
5. 每个泡泡独立 Accept/Reject；
6. Observation 始终继续记录下一窗口。

允许 Gate 并行，但生成任务进入 `DivergenceQueue`，按 `intent_seq` 保持确定顺序。已 resolve 且 accepted 的 revision 可以开始生成；前序 rejected revision 直接跳过。这样多个泡泡可以同时存在，同时避免多组候选并发写入导致 Solution Space 乱序。

## 8. 接受、拒绝与关键词继承

### 8.1 上一 IntentRevision 被拒绝

- 拒绝不会停止常驻 Observation；
- 被拒绝的 target/scope/direction 作为 negative evidence 保存；
- 下一 revision 继续从最近一次已接受的设计分支或当前 source version 发散；
- 被拒关键词不得作为正向条件继承；
- 新 revision 生成的结果仍追加在已有 Solution Space 后面。

### 8.2 上一 IntentRevision 被接受

下一 revision 接受后默认采用增量关键词策略：

```text
cumulative_keywords[n]
  = dedupe(cumulative_keywords[n-1] + delta_keywords[n])
```

- 旧关键词保留原顺序；
- 新关键词追加在末尾；
- 同义重复词去重，但不擅自改写用户原词；
- 新 GenerationSpec 使用累计关键词；
- 旧候选和旧关键词 provenance 不被覆盖；
- 只有用户显式选择“重置方向”时才允许 `keyword_mode=replace`。

### 8.3 关键词不属于 Observation Behavior

More Creative keyword：

- 不创建 ActionAtom/Behavior；
- 不修改 Intent Composer 的原始 `user_text`；
- 不重新触发 Planner 或新的 Gate；
- 只进入对应 revision 的 `DivergenceSelection` 和 GenerationSpec。

## 9. Solution Space 追加策略

每个已接受 revision 形成一个独立结果批次：

```json
{
  "batch_id": "solution_batch_02",
  "intent_revision_id": "intent_rev_02",
  "append_index": 2,
  "parent_batch_id": "solution_batch_01",
  "keyword_mode": "append",
  "base_keywords": ["soft silhouette"],
  "delta_keywords": ["integrated connection"],
  "cumulative_keywords": ["soft silhouette", "integrated connection"],
  "candidate_ids": []
}
```

规则：

- 每个批次生成 6–8 个通过 QA 的 Solution，产品默认值为 8；
- 第一个泡泡的结果先写入，第二个泡泡的结果随后追加；
- 前一批结果不清空、不覆盖、不重新编号；
- 前端以 IntentRevision/关键词摘要分组，批次内部保留候选顺序；
- 候选必须追溯到 source、revision、Gate、关键词、seed 和 QA；
- 多批次共用具体 source identity，但各自保留 target/mask 和 cumulative keyword provenance；
- 用户选择候选后，Hy3D、OSS、case library 和 website sync 仍按完整 CreativeFlow 主线执行。

## 10. 前端修改范围

### `frontend/src/state/studioStore.ts`

- 将全局单一 `fourStage.gateOpen` 改为 `intentRevisions[]`；
- 移除文本稳定自动提交；
- Intent Send 创建原子 cutoff；
- Observation 独立于 revision/generation 生命周期；
- tool session 聚合为一个 Behavior；
- keyword selection 不再写回 `intentText`；
- generation progress 按 `revision_id/batch_id` 路由；
- Solution Space 使用 append，不用 replace。

### Bubble overlay

- 使用数组渲染多个 revision bubble；
- 增加 anchor 投影、槽位分配、碰撞检测和稳定位置缓存；
- 每个 bubble 独立 accept/reject/busy；
- accepted bubble 收敛为标签，不占用重复操作按钮。

### Behavior history

- 从每 stroke 一个圆点改为每 tool session 一个圆点；
- 圆点轨道移出工具面板；
- 支持查看 start/end 三视图、target、参数、撤销状态。

## 11. 后端修改范围

### 数据契约

新增：

- `BehaviorSession`；
- `LiveObservationState`；
- `IntentRevision`；
- `IntentRevisionGate`；
- `DivergenceContext`；
- `SolutionBatch`。

关键唯一约束：

```text
UNIQUE(session_id, intent_seq)
UNIQUE(intent_revision_id, gate_id)
UNIQUE(intent_revision_id, solution_batch_id)
```

### 已落地 API

```text
POST /api/v1/sessions/{session_id}/behaviors/start
POST /api/v1/sessions/{session_id}/behaviors
DELETE /api/v1/sessions/{session_id}/behaviors/{behavior_id}
GET  /api/v1/sessions/{session_id}/realtime-observation
POST /api/v1/sessions/{session_id}/intent-revisions
POST /api/v1/intent-revisions/{revision_id}/gate
PUT  /api/v1/intent-revisions/{revision_id}/divergence-selection
POST /api/v1/intent-revisions/{revision_id}/generation
```

### 调度

- Observation reducer 单独常驻，不受 FourStageRun 终态限制；
- Planner 输入必须带 `window_start_seq/cutoff_seq/snapshot_hash`；
- Gate idempotency key 使用 `revision_id`；
- Generation job 带 `intent_seq/append_index`；
- scheduler 串行写入同一 session 的 Solution Space；
- 后到的 generation result 不得覆盖早期 batch。

## 12. 验收场景

### 场景 A：13 笔 Drag

- 用户进入 Drag 工具并连续编辑 13 笔；
- 历史只新增一个 Behavior 圆点；
- `stroke_count=13`；
- 保存开始和结束三视图；
- 不产生 Gate。

### 场景 B：一次 Send

- 用户完成三个 Behavior 后点击 Send；
- cutoff 锁定三个 Behavior；
- Planner 输出具体 snowman/hat/nose 等目标，不得显示 `obj_group_02`；
- 只为该 revision 产生一个 Gate；
- Observation 继续接收新行为。

### 场景 C：快速两次 Send

- 第一次 Send 创建 `intent_rev_01`；
- 用户继续操作并立即第二次 Send，创建 `intent_rev_02`；
- 两个泡泡同时围绕主体排列且不重叠；
- 每个泡泡独立接受/拒绝；
- 同一个 revision 不因轮询再生成第二个泡泡。

### 场景 D：两个泡泡均接受

- `intent_rev_01` 生成 6–8 个结果；
- `intent_rev_02` 继承第一版已接受词，并追加第二版新词；
- 第二批 6–8 个结果接在第一批后面；
- 第一批不被清空或覆盖；
- 每张候选可追溯到对应 revision 和累计关键词。

### 场景 E：第一版拒绝、第二版接受

- 第一版记录 negative evidence，不生成；
- 第二版使用新的目标/范围继续发散；
- 不继承第一版被拒关键词；
- 第二批结果追加到现有 Solution Space；
- Observation 和之后的 IntentRevision 不受阻塞。

## 13. 实施顺序

| Checkpoint | 交付物 | 退出标准 |
| --- | --- | --- |
| C0 | 契约与迁移 | Behavior/Revision/Batch schema、seq/cutoff/idempotency 完成 |
| C1 | 常驻 Observation | 行为期间持续编码检索；无 Send 不产生 Gate |
| C2 | Tool-session Behavior | 多 stroke 聚合为一个圆点，start/end 三视图可查 |
| C3 | IntentRevision | Send 原子锁定窗口；提交后事件进入下一窗口 |
| C4 | 多泡泡布局 | 两个及以上 revision 泡泡可并行显示、稳定锚定、无重复 |
| C5 | 关键词继承 | accepted=append；rejected=negative，不污染正向词 |
| C6 | Solution append | 多批结果按 intent_seq 追加，不覆盖旧批次 |
| C7 | 端到端验收 | snowman/teapot/water gun 多 revision 全链通过 |

本策略取代此前“前一个 Gate 未处理时，新 IntentRevision 只能排队且不能显示第二个泡泡”的限制。正确规则是：**Gate 可以并行显示，生成结果按顺序追加。**

## 14. 2026-08-05 实现对照

| 产品交付物 | 实现位置 | 当前验收 |
| --- | --- | --- |
| Behavior/Observation/Revision/Batch 数据契约 | `backend/app/models/realtime_observation.py` | Pydantic + SQLite 序列化通过 |
| 常驻编码与检索 | `backend/app/services/intent/realtime_observation.py` | Behavior commit 后后台 refine，不生成 Gate |
| Send 原子 cutoff | 同上 + `frontend/src/state/studioStore.ts` | 测试覆盖已预留下一工具会话的排除 |
| 一次工具使用一个 Behavior | `studioStore.ts` + `ThreeViewport.tsx` | 多 stroke 聚合，保存 start/end 前、侧、顶视图 |
| 多 Gate 泡泡 | `PlannerClarificationOverlay.tsx` | GPU 页面验收 2 个 revision 同时显示、稳定槽位、独立 accept/reject |
| Gate 问句压缩 | `four_stage_encoding.py` + `decision_service.py` | 轮廓、部件/连接、表面分类；每 revision 一句 |
| 关键词继承 | `RealtimeObservationService.save_selection` | GPU 在线：第一版 `soft silhouette`；第二版继承并追加 `outward extension` |
| Solution Space 追加 | `advance_generation_queue` + `solutionBatches` | GPU 雪人双批真实生成：`append_index=1,2`，每批 8 个，旧批不覆盖；追加契约通过 |
| 原物体 identity | `SourceContext` + `GenerationSpecBuilder` | 契约已实现，但本轮 Send 快照为空白，视觉验收失败，不能计为通过 |

本轮页面验收使用 `UI Design` 为视觉基线；用户提供的红框截图仅用于复现错误，不作为 UI 参考。

## 15. GPU 在线验收记录

2026-08-05 已在 `/root/flowstudio_app` 完成定点部署，未整目录覆盖 GPU 重构代码。当前后端 `:18000` 与前端 `:5173` 健康；Qwen、Planner、worker 与 CreativeFlow 主线保持原运行边界。

雪人双 IntentRevision 实际链路：

```text
intent 1: soft silhouette
  → batch 1 / append_index 1 / completed / 8 artifacts

intent 2: base=[soft silhouette] + delta=[outward extension]
  → batch 2 / append_index 2 / parent=batch 1 / completed / 8 artifacts
```

这证明场景 D 的 GPU 双批追加、关键词 provenance 与“不覆盖旧批”成立。它不证明视觉
identity：复核发现两批的源 `viewport.jpg` 都是空白深色图；第二个 revision 虽然用户文本为
“change the hat connection”，但 `target_part_id=null`、`gate_scope=whole`，因此 8 个结果主要是
整体彩色/轮廓变化，不是帽子连接的局部发散。场景 E 的拒绝不继承已由 GPU 在线 API 通过；
常驻 Observation 在 Gate 与生成期间不被锁住已由并发行为测试和在线更新时间证明。

尚未关闭的 C7 项：

- 修复并验证非空、可辨识的 Send source snapshot；
- 用户文本指向具体部件但行为 target 缺失时，Gate 必须确认冲突，不能静默降级为 whole；
- 将确认后的 part id、mask/anchor 一直传入 GenerationSpec，并验证局部变化；
- 重新完成 snowman identity-preserving 双 revision 全链；
- teapot 多 revision 全链；
- water gun 多 revision 全链；
- 用户侧确认关键词面板可点击、已接受泡泡切换后选中态恢复；
- 完整清理阶段统一移除仍保留的 legacy single-run UI 兼容代码。

## 16. 当前信号到 Design State 的真实规则与缺口

当前实现是“两层推断”，不是一个完整的阶段状态机：

1. Behavior commit 后立即用工具类型更新状态：hover/select→focus，brush/clay/drag/move/add→shape_connect，smooth/annotation/image/model→surface_reference，save/version→commit，generate→diverge，compare→compare。
2. 每次规则更新直接写入最近工具、target、scope；存在 `part_id` 即 part，否则 whole；置信度只由 stroke 数从 0.45 累加并封顶 0.92。
3. 后台仅处理尚未编码的 Behavior delta，经 Qwen 编码；不可用时使用规则 fallback。编码可修正 goal、operation、scope、target、confidence。
4. scope/operation/target 的 fingerprint 变化时才刷新 top-5 检索；Observation 本身永远不创建 Gate。
5. Intent Send 原子锁定 cutoff；Planner 只读取该窗口与用户文本，然后压缩为每 revision 一句 Gate。

现有 feature extractor 已采集 drag vector、brush coverage、dwell、同部件近期编辑、undo、accept/reject、视图与 mask 等信号，但常驻 Design State reducer 并未充分使用这些信号。下一版必须补充：

- 状态持续性与迟滞：不能由最后一个工具直接覆盖阶段；应按时间窗累计证据并保留置信度；
- 序列模式：观察、反复编辑、撤销、比较、接受/拒绝应分别推断探索、调整、不确定、收束；
- 有效行为：零 stroke、取消、仅打开工具不得算一次有效修改；
- 目标冲突：用户说“帽子”但没有 part id 时必须 Gate 澄清并保留文本候选；
- 视觉证据质量：空白/过暗/透明快照不得进入 planner/generation；
- 字段级证据：phase、scope、operation、target、readiness 各自保存 evidence/confidence，而非一个总 confidence；
- 局部约束闭环：part id、mask、camera、source identity 必须从 Send 快照传到每个候选；
- 发散轴约束：Gate 与选词为轮廓/部件时，不应默认轮换 material/ornament 稀释关键词。
