# FlowStudio 后端收敛修改策略 v1

日期：2026-08-02  
作者侧：Cursor（前端联调视角）  
读者：Codex（后端 / AutoDL `/root/flowstudio_app`）  
关联：`FLOWSTUDIO_CURSOR_BACKEND_CONTRACT_V1_ZH.md`、`FLOWSTUDIO_PROTOTYPE_FRONTEND_BACKEND_DEV_SPEC_V1_ZH.md`  

**状态（2026-08-02）**：Phase A–E 已在本地落地并同步 AutoDL；契约见 v1.3。

---

## 0. 目标与非目标

### 目标

在 **不打断当前前端联调** 的前提下，把后端从「多入口补丁堆」收敛成 **一条可解释的主链路**：

```text
Session → Asset/Parts → ActionAtom / live_signals
       → Interpret（Perception）
       → Planner 确认门
       → Directions（More Creative）
       → Generation（CreativeFlow / Hy3D）
       → Snapshot / Solution Space
```

让前端只需要认 **少数 canonical API**，后端内部可以保留实现细节，但对外行为必须一致。

### 非目标（本轮不做）

- 不重写整个 CreativeFlow / remote_worker 研究脚本库
- 不追求一次拆完 `main.py` 到「完美微服务」
- 不改前端视觉主路径（除非契约变更要求前端跟着换 endpoint）
- 不删除历史脚本文件本身；优先 **标记废弃 + 路由层收敛**

### 成功标准（给 Codex 验收）

1. 文档中的 Canonical 表与服务器实际路由行为一致  
2. Perception 只有一条「观察刷新」路径 + 一条「工具完成」路径，行为可测  
3. Directions 对外只保留一个主 endpoint（另一个变薄代理或标注 deprecated）  
4. Generation 只走 `/generation/*`；`/candidates` stub 路径不再被新代码依赖  
5. Parts 有明确状态：`tentative | obj_group | viewport_2d | segmented_3d`，不互相假装成同一层  
6. Prompt chip / analogy keyword 不污染 `ActionAtom` 或 Perception history  
7. Generation 请求先返回 `job_id`，不因 Qwen-image / Hy3D 慢而阻塞前端  
8. Cursor 前端按契约联调，无需猜「这次会不会更新 perception」

---

## 1. 现状诊断（给 Codex 对齐事实）

服务器路径：`/root/flowstudio_app`

| 症状 | 证据 |
|------|------|
| 上帝文件 | `backend/app/main.py` ~5431 行，~71 路由 |
| 生成编排过大 | `generation_orchestrator.py` ~1809 行 |
| Worker 巨石 | `remote_worker/app.py` ~3263 行 |
| 双生成体系 | `studio_store.jobs` vs `legacy_job_store` + stub `CreativeFlowAdapter` |
| 方向重复 | `/directions/suggest` ≡ `/directions/cross-domain`（同 builder） |
| Interpret 多入口 | `/interpret`、`/actions`、`/episodes`、WS 子集、candidate 决策，broadcast 不一致 |
| 分割未贯通 | OBJ fallback / SAM3D / viewport-sam 结果不进统一 part 状态机 |
| 状态散落 | stage / live_signals / memories / candidate_memory / snapshot / solution-space 重叠 |
| 演进方式 | 根目录多个 `*.tgz` 补丁包，像持续打补丁而非模块演进 |

**判断**：不是「完全不可用」，而是 **原型联调补丁态**。策略应是 **收敛对外契约 + 渐进拆分**，不是推倒重来。

---

## 2. Canonical API（请 Codex 以此为准，其余降级）

### 2.1 前端主链路（保留并强化）

| 步骤 | Canonical | 说明 |
|------|-----------|------|
| 建会话 | `POST /api/v1/sessions` | |
| 资产 | `POST /api/v1/assets` / benchmark load / upload | |
| 工具完成态 | `POST /api/v1/sessions/{id}/actions` | **唯一**写入 ActionAtom 并触发「完成态 interpret」的入口 |
| 草稿 | `POST/PATCH /api/v1/intent-drafts` | Send = status submitted |
| 静默观察 | `PUT .../live-signals` + `POST /interaction/interpret`（`camera_observation_ended`） | 不替代 actions |
| 确认门 | planner decision endpoint（现有 accept/reject） | accept 可带 `auto_suggest_directions` |
| 方向 | **`POST /api/v1/directions/suggest`** | 唯一对外主入口 |
| 读状态 | **`GET /api/v1/sessions/{id}/snapshot`** | 单一真相源优先 |
| 生成 | **`POST /api/v1/generation/*`** | replace / drag / diverge 等 |
| 部件发现 | `POST /api/v1/parts/discover` | 写 `asset.parts` |
| 2D 辅助分割 | `POST /api/v1/viewport-segmentation` | 明确只是 2D evidence，不冒充 3D part |

### 2.2 降级 / 废弃（不要再扩展）

| API / 模块 | 策略 |
|------------|------|
| `POST /directions/cross-domain` | 保留 1 个版本作薄代理 → 内部转 `suggest`，响应加 `deprecated: true`；文档标明勿新用 |
| `POST /api/v1/candidates` + `CreativeFlowAdapter` stub | **冻结**：新功能禁止依赖；下一步删除或返回 410 |
| `legacy_job_store` | 只读兼容；新 job 只进 `studio_store` |
| WS 内随意 interpret | 收紧白名单；观察态统一走 HTTP interpret / actions |
| `/memory` vs `/memories` vs `/solution-space` | 短期：`snapshot` 聚合齐全；中期：solution-space 变为 snapshot 的 view 字段 |

所有 deprecated endpoint 必须在响应 `metadata.deprecated = true`，并写 server warning：

```text
DEPRECATED_API_USED endpoint=... session_id=...
```

新测试或新前端代码不应依赖 deprecated endpoint；兼容代理只保留一个联调迭代。

### 2.3 Episode 与 Interpret 的分工（必须写死）

| 场景 | 走哪条 |
|------|--------|
| 用户点工具完成（Hover commit / Brush / Annotate…） | `POST .../actions`（ActionAtom）→ 后端自动 interpret + `perception_updated` |
| 相机/悬停观察（未完成） | 前端聚合 → `PUT live-signals` → 防抖 `POST /interpret`（silent） |
| 用户点 Send 提交意图草稿 | intent-drafts submitted；需要 Planner 时由 draft/episode **一条路径**完成，不要再强制前端连打 3 个 interpret |
| 手动重解释 | 仅调试用 `/interpret` |

**原则**：同一用户动作禁止要求前端「又 actions 又 interpret 又 episode」三重调用才能看到 Perception。

### 2.4 ActionAtom 与 Prompt Chip 的边界（必须写死）

`ActionAtom` 只记录用户对 object / part / canvas 的真实操作：

```text
hover_commit / brush / annotation / drag / smooth / add / image_reference / model_reference
```

More Creative 里点击的 analogy keyword / prompt chip **不是** ActionAtom。它只能进入：

```text
POST /api/v1/prompt/compose
generation.metadata.selected_prompt_tokens
generation.metadata.prompt_compose_evidence
```

禁止把 prompt chip 选择写成 `text · whole object` 或 `whole_part` 行为；它不参与：

- Perception interaction history
- `pending_behavior_count`
- IR 用户状态匹配中的「用户操作」
- 多个 behavior 合并 intent 的行为列表

### 2.5 Clarification Bubble 的职责边界

Planner clarification bubble 只确认当前用户想改的范围：

```text
contour | part | material
```

不要在气泡里直接问 `Structural + Aesthetic?`、`Functional?` 这类发散维度。  
确认 `change_scope` 后，`/directions/suggest` 再结合 IR、当前 object、part lifecycle、live_signals，在 More Creative panel 里给出具体维度和 prompt chips。

### 2.6 Generation 的异步契约

`POST /api/v1/generation/*` 必须快速返回 `job_id`，不得阻塞到 Qwen-image / Hy3D 完成。前端 loading 依赖以下 WS 顺序：

```text
job_update(status=queued/running)
candidate_ready(candidate_ids=[...])
job_update(status=succeeded/failed)
```

前端行为：

1. 收到 generation 请求响应或 `job_update running` 后，Solution Space 先显示 compact loading strip  
2. 收到 `candidate_ready` 后，自动展开 Solution Space 并加载 candidates  
3. 失败时用 `job_update failed` 释放 loading，不让界面卡死

---

## 3. 分阶段改造（建议 Codex 按 Phase 执行）

### Phase A — 契约止血（1–2 天，优先）

**目的**：行为可预期，前端少踩坑。少做大拆文件。

1. **统一 Perception 广播**  
   - 抽出 `_publish_perception(session_id, interpretation)`  
   - `/actions`、`/interpret`、episode planner、candidate 决策凡产生 interpretation，一律走同一函数  
   - `_publish_perception` 统一负责 `interaction_interpretation`、`perception_updated`，如 stage 变化再发 `stage_update`  
   - 禁止各 endpoint 手写不同版本的 perception payload / broadcast 顺序  
   - 明确：哪些 artifact endpoint **不**自动 interpret（viewport-sam、纯文件保存）→ 写进契约

2. **Directions 单入口**  
   - `suggest` = canonical  
   - `cross-domain` = proxy + deprecated 标记  
   - planner `auto_suggest_directions` 内部只调同一函数（已接近，补 metadata 统一）
   - `suggest` 支持 `interpretation_id`；有 `interpretation_id` 时优先复用该 interpretation 的 `features.design_state_ir`

3. **Generation 冻结遗留轨**  
   - `/candidates` 打日志 + 文档废弃  
   - `GET /jobs/{id}` 仍可 fallback，但新代码禁止写 legacy store
   - `/generation/*` 必须先返回 job，不等待图片完成

4. **更新契约文档**  
   - 与 Cursor 共同改 `FLOWSTUDIO_CURSOR_BACKEND_CONTRACT_V1_ZH.md`  
   - 加一节「Deprecated」

**验收**：用白模跑一遍：hover 静默 → Hover commit → Perception 更新 → Accept → suggest tokens → 不出现「有时更新有时不更新」。

---

### Phase B — Parts 状态机（2–3 天）

**目的**：分割层不再互相假装。

建议在 part / asset metadata 中固定：

```text
part.lifecycle:
  tentative_raycast      # 前端 raycast，可不落库
  obj_group_fallback     # 当前白模默认可编辑组
  viewport_2d_mask       # 2D SAM 证据，挂 artifact_id
  segmented_3d           # SAMPart3D / PartField 真 3D
```

规则：

1. `viewport-segmentation` 只写 artifact + 可选 `part.evidence.viewport_mask_*`，**不**把 2D mask 标成稳定 3D part  
2. `/parts/discover` 成功后升级 lifecycle，替换或标注 obj_group  
3. Hover / focus-observations 引用 `part_id` + `lifecycle`，前端可区分「临时标签 vs 真分割」

**验收**：白模 hover 显示 tentative；viewport-sam 返回后 Perception evidence 增加 mask，但 parts 列表不突然变成「假 3D」；真分割可用时 lifecycle 升级。

---

### Phase C — 理解栈去重（2–4 天）

**目的**：Rule / VLM / IR 别各跑各的、重复检索。

1. Interpret 内 IR retrieve **一次**，结果放入 `features.design_state_ir`  
2. Directions 默认 **复用** 最近 interpretation 的 IR（可用 `interpretation_id` 入参），禁止无缓存再打一遍全量 retrieve  
3. VLM：  
   - 观察态 / 完成态：先返回 rule(+IR) interpretation，再异步 VLM 覆盖并 `perception_updated`（对齐契约「先返回再覆盖」）  
   - Directions 的 Qwen 调用与 Intent VLM **任务分离**（不同 prompt/adapter 名），即使同 URL 也要在 metadata 标 `task=direction_suggest|intent_predict`  
4. `rule_fallback` 只用于「模型不可用」，不要和「IR 匹配偏弱」混成同一个 label

**验收**：一次 Accept→Suggest，日志里 IR retrieve ≤ 1；VLM 慢时前端仍先看到 rule perception。

补充规则：IR 结果只作为「创意阶段 / 下一步发散维度」的证据，不把 IR case 的硬检索字段直接展示为用户意图。对外必须返回置信度、证据摘要、推荐维度，而不是把检索文本当结论。

---

### Phase D — 拆 `main.py`（并行可做，风险中）

**目的**：可维护，不是换协议。

建议拆成 routers（不必一次完美）：

```text
app/
  api/
    sessions.py
    perception.py      # live-signals, interpret, perception/latest
    actions_artifacts.py
    directions.py
    generation.py
    parts.py
    benchmarks.py
  services/            # 已有，继续下沉
```

搬迁顺序：`directions` → `perception/actions` → `parts` → `benchmarks` → `generation` 胶水。  
`create_app()` 只负责 include_router + 依赖注入。

**验收**：行为不变的回归测试（现有 `backend/tests`）全绿；路由列表与 Phase A 契约一致。

---

### Phase E — 生成与 Job 单轨（视联调进度）

1. 删除或 410：`CreativeFlowAdapter` stub 路径  
2. Hy3D：明确 `auto` vs `manual` 互斥/去重（同一 candidate 不重复提交）  
3. `solution-space` 改为 `snapshot.solution_space` 的视图，避免第二套聚合逻辑长期分叉  
4. Qwen-image / Hy3D 慢任务只通过 job 状态推进，不允许同步阻塞 API response

---

## 3.1 最小回归测试（每个 Phase 至少保这些）

| 测试名 | 要守住的行为 |
|--------|--------------|
| `test_action_creates_single_perception_broadcast` | `POST /actions` 后保存 interpretation，并广播一次标准 `perception_updated` |
| `test_prompt_chip_does_not_create_action_atom` | prompt chip 只进入 prompt compose / generation metadata，不进入 action history |
| `test_suggest_reuses_interpretation_ir` | `directions/suggest` 带 `interpretation_id` 时不重复全量 IR retrieve |
| `test_cross_domain_proxy_marks_deprecated` | `cross-domain` 代理响应兼容 suggest，且 `metadata.deprecated = true` |
| `test_generation_returns_job_before_candidates` | `/generation/*` 快速返回 job；candidate 后续通过 WS / poll 出现 |
| `test_viewport_mask_is_not_segmented_3d_part` | 2D mask 只作为 evidence，不把 lifecycle 冒充成 `segmented_3d` |

这些测试比完整端到端便宜，但能挡住当前最容易回潮的冗余：多入口 perception、prompt chip 污染行为、Directions 重复 IR、旧生成 stub 复活。

---

## 4. 明确不要碰 / 延后

| 区域 | 原因 |
|------|------|
| `remote_worker` 里大量 variation_* / low_fidelity_* 研究脚本 | 研究资产，与联调主链解耦即可 |
| 根目录历史 `.tgz` | 可归档到 `archive/`，别在热路径解压覆盖 |
| 前端大改 | 等 Phase A 契约冻结后再由 Cursor 跟 |
| 一次重写 IR jsonl 格式 | 先复用，后优化 |

---

## 5. 分工建议

| 角色 | 负责 |
|------|------|
| **Codex** | Phase A–E 后端；更新契约 Deprecated 段；服务器行为与测试 |
| **Cursor** | 前端只打 Canonical API；Hover/Perception/Composer 跟契约；联调验收 |
| **共同** | 每完成一个 Phase，同步改 `FLOWSTUDIO_CURSOR_BACKEND_CONTRACT_V1_ZH.md` 版本日期 |

Cursor 侧当前假设（请 Codex 确认或纠正）：

- 静默观察：`PUT live-signals` + 防抖 `/interpret`  
- 工具完成：`ActionAtom` via `/actions`（或等价封装）  
- More Creative：只打 `/directions/suggest`（Accept 后）  
- 生成：只打 `/generation/*`  
- 读状态：优先 `/snapshot`

---

## 6. 给 Codex 的启动 Prompt（可直接粘贴）

```text
请阅读仓库 docs/FLOWSTUDIO_BACKEND_CONVERGENCE_STRATEGY_V1_ZH.md
以及 docs/FLOWSTUDIO_CURSOR_BACKEND_CONTRACT_V1_ZH.md。

按 Phase A 先做「契约止血」，不要一开始大拆 main.py：
1) 统一 perception 广播函数；
2) directions/suggest 为唯一主入口，cross-domain 变薄代理并标记 deprecated；
3) 冻结 /candidates + legacy_job_store 写入；
4) 确保 prompt chip 不写入 ActionAtom，只进入 prompt/compose 与 generation metadata；
5) /generation/* 快速返回 job_id，candidate 通过 candidate_ready / job_update 异步到达；
6) clarification bubble 只判断 contour / part / material；
7) 更新契约文档的 Canonical / Deprecated 表；
8) 用白模会话写最小回归：actions → perception_updated；suggest 复用 interpretation IR；cross-domain 响应结构兼容且 deprecated；generation 先返回 job。

服务器目录：/root/flowstudio_app
完成后用简短 changelog 说明：改了哪些文件、前端是否需要改调用。
```

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 前端仍在打 `cross-domain` | 代理保持兼容 1 个迭代 |
| 去掉某次自动 interpret 导致 Perception 空 | Phase A 先「补齐广播」而不是「乱删触发」 |
| 拆 router 引入循环导入 | Phase D 单独分支；先搬纯函数再搬路由 |
| VLM 异步化改变时序 | 用 `perception_updated` 覆盖；前端已支持 WS 覆盖本地 summary |

回滚：每个 Phase 单独 commit；服务器可用现有 tgz/git 回退；契约版本号 `v1 → v1.1` 递增，不静默改语义。

---

## 8. 建议排期（示意）

| 顺序 | Phase | 预估 | 对前端影响 |
|------|-------|------|------------|
| 1 | A 契约止血 | 1–2 天 | 几乎无；可把 cross-domain 换成 suggest |
| 2 | B Parts 状态机 | 2–3 天 | 小：展示 lifecycle / 勿把 2D 当 3D |
| 3 | C 理解栈去重 | 2–4 天 | 体验更好（先 rule 后 VLM） |
| 4 | D 拆 main | 并行 | 无协议变化 |
| 5 | E Job 单轨 | 视进度 | 删除旧 candidates 调用 |

---

## 9. 一句话给 Codex

> 先让 **对外只剩一条主链路、Perception 行为一致、Directions/Generation 单入口**；再拆文件、再清理 remote_worker。  
> **收敛行为 > 炫技重构。**
