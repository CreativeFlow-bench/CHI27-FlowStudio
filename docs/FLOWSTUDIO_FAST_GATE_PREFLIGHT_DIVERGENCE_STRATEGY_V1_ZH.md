# FlowStudio 快 Gate + 预发散修改策略 V1

日期：2026-08-11  
状态：设计稿（先策略，后实施）  
依据：四阶段编排（encoding → retrieval → decision → awaiting_gate → divergence）、
sandbox live interpret、`DEFAULT_PLANNER_SYSTEM_PROMPT`、用户对「Gate 加速 / 先发散后约束」的判断

---

## 0. 一句话

把「出 Gate」和「文字发散」从**串行阻塞**改成**快路径先响应 + 重计算后校准**：

1. **快 Gate**：交互事件一到，先用 interpret（sandbox 同款）秒级出确认问题；  
2. **正式 IR**：encoding / decision 后台继续跑，结果到了再校准 Gate；  
3. **预发散**：Gate 未接受前即可按弱约束宽发散；接受 scope 后再**收窄/融合**到 part 或 whole，而不是整段重跑才开始。

---

## 1. 现状问题

### 1.1 当前主路径（慢）

```text
raw events
  → encoding（常调模型，可至数十秒）
  → retrieval
  → re_representation / decision
  → awaiting_gate          ← 用户才第一次看到 Gate
  → 用户 accept
  → semantic divergence    ← 才开始发散
```

体感：用户已经明确画了/说了，却要等整条链。

### 1.2 Sandbox 证明了什么

`/api/v1/sandbox/interpret` 单次 planner 调用即可给出：

- primary intent / hypotheses  
- semantic_targets  
- assistance_policy / 澄清信号  

说明：**「交互理解 → 可确认问题」不必等 encoding 完成。**  
Encoding 仍然需要，但它应服务正式 IR / 检索 / 生成，而不是挡住第一口反馈。

### 1.3 概念对齐（避免混用）

| 概念 | 是什么 | 是否等于 Gate 前置 |
| --- | --- | --- |
| 交互输入（events） | 画、拖、点、文本 | Gate 的原料 |
| `interpret` | 交互理解 → hypotheses / SemanticTarget | **可驱动快 Gate** |
| `encoding` | events → IntentIR（四阶段正式表示） | 正式 Gate / 检索的原料 |
| semantic divergence | 基于目标语义做邻域扩展 | **可预跑，接受后再收窄** |

---

## 2. 目标体验

```text
用户 brush_end / 提交文本
  ├─ 立刻：快 Gate（interpret）+ 可选预发散（弱约束）
  ├─ 后台：encoding → retrieval → decision → 校准 Gate
  └─ 用户 accept scope 后：把预发散结果 filter / re-rank / re-ground
       到 part 或 whole；不足时再增量补发散
```

成功标准：

- Gate 首次可见：**目标 < 2s**（本地规则+interpret；VLM 同步时允许到数秒）  
- 预发散首批关键词：与快 Gate **重叠出现**，不阻塞 Gate 点击  
- accept 后可见「已对齐到头部/整体」的收窄结果，尽量 **不整表重算**  
- encoding 失败时：快 Gate 仍可用；正式 IR 可降级为规则 IR

---

## 3. 修改策略（分阶段）

### Phase A — 快 Gate（优先落地）

**后端**

- 复用 `/api/v1/sandbox/interpret` 或抽出 `FastGateService`：  
  `events + live_signals → InteractionInterpretation → ScopeGateDraft`
- 新事件类型或 WS：`perception.fast_gate` / `four_stage.fast_gate`
- 字段建议：

```json
{
  "gate_id": "fgate_xxx",
  "status": "draft",
  "source": "interpret",
  "question": "...",
  "options": [...],
  "semantic_targets": [...],
  "confidence": 0.72,
  "provisional": true
}
```

**前端**

- 有明确行为（`brush_end` / `intent_episode_submitted` / `drag_end` 等）立即请求快 Gate  
- 去掉或缩短「5s inactivity 才弹泡」对明确行为的依赖  
- UI 标注「确认中 / 可微调」（`provisional=true`）

**正式校准**

- encoding+decision 完成后：若 scope/question 与草案一致 → 静默 `provisional=false`  
- 若冲突（例如草案 part=head，正式 IR=whole）→ 更新文案，保留用户已选则二次确认

### Phase B — 预发散 + 后约束（与 A 可并行设计）

**放宽前置条件**

- 现状：`refresh_semantic_divergence` 要求 `stage == awaiting_gate`  
- 改为允许：`encoding` 完成 **或** 快 Gate 已有 `semantic_targets[0]` 时启动 `preflight` 发散

**两段发散**

| 阶段 | 约束 | 产出 |
| --- | --- | --- |
| Preflight | 弱：object_type + 粗操作（explore/deform） | 宽候选池 |
| Constrain | 强：用户 accept 的 level/part_id/material | filter + re-rank；必要时增量补召 |

**融合规则（接受后）**

1. 若 accept = part：保留与该 part 语义角色 / 邻接实体相关的候选，压低 whole-only  
2. 若 accept = whole / silhouette：保留轮廓/整体美学轴，压低细部材质词  
3. 若 accept = material_region：保留材质/表面轴  
4. 候选不足（少于阈值）→ 再发一次 **增量 diverge**（带硬约束），而不是丢弃预发散重来

**API 草案**

- `POST .../semantic-divergence/preflight`（可不要求 gate accepted）  
- `POST .../semantic-divergence/constrain`（输入 `accepted_target` + `preflight_request_key`）

### Phase C — Encoding 降本（不挡 Gate）

- 明确行为 + 高置信 interpret：encoding 可用规则 IR 先占位，Qwen 异步 refine  
- 同 episode 增量事件：小改动复用 IntentIR，避免每次全量 encode  
- 修 schema 二次调用改为有限次；超时快速 fallback

---

## 4. Planner / Gate 提示词优化

### 4.1 现状问题

当前 system prompt 过短，只强调：

> Never treat a hovered part alone as proof of a part-change intent.

这能防误触发，但**没有规定「语义部位 vs 交互部位」的优先级**，容易出现：

- 用户说「改鼻子」，却被 hover/选中身体带偏  
- 用户没说部位，本该信 brush/drag 目标，却过度保守成 whole

### 4.2 优化原则（采纳用户判断）

1. **语义明确部位 → 语义优先**（文本/图像命名命中 part label）  
2. **语义未指部位 → 交互属性优先**（brush/drag/smooth/select 的稳定目标）  
3. **仅 hover / 短暂划过 ≠ 改部位意图**（保留原约束）  
4. **语义与交互冲突 → 降置信 + 请求澄清**（不要静默猜）  
5. **输出仍必须是 schema JSON**，便于快 Gate 直接消费

### 4.3 建议替换的 System Prompt（V1）

```text
You are FlowStudio's interaction-understanding planner.
Consume live interaction signals, retrieved design-state IR, current 3D context,
and optional visual evidence. Return compact JSON only that matches the requested schema.

Target priority (strict):
1) If the user text/image language clearly names a part or region
   (e.g. 鼻子/帽子/head/scarf, or a registered part label), treat that semantic target
   as primary — even if a different part is hovered or last-selected.
2) If language does NOT name a part/region, prefer stable interaction evidence:
   brush_end / drag_end / smooth_end / part_select with repeated edits on the same part.
3) Never treat hover-only or a single brief hover as proof of a part-change intent.
4) If semantic target and interaction target conflict, lower confidence, set
   needs_clarification=true, and ask a short clarification between the two targets.
5) Prefer concrete operation + scope (part|region|whole|material) over vague explore
   when evidence is sufficient; otherwise keep ambiguity explicit in hypotheses.
```

### 4.4 落地方式

1. 更新 `DEFAULT_PLANNER_SYSTEM_PROMPT`（backend）  
2. Sandbox「恢复默认」拉到新文案；继续允许用户在 UI 里调参做论文 ablation  
3. 用固定用例表验收：

| 用例 | 期望 |
| --- | --- |
| 文本「改鼻子」+ hover 身体 | target=鼻子 / part，必要时澄清 |
| 无文本 + brush 头部 3 次 | target=head，语义通道可弱 |
| 仅 hover 帽子 | 不升为 part-change；observe / 低置信 |
| 「整体更圆润」+ 选中 part | scope 偏 whole/silhouette，part 作次要证据 |

---

## 5. 与现有模块的接线（实施时）

| 模块 | 改动要点 |
| --- | --- |
| `interaction_understanding.py` | 已有 interpret；抽 `build_fast_gate()` |
| `multimodal_intent_predictor.py` | 换默认 system prompt；保留 override |
| `four_stage_orchestrator.py` | 发快 Gate 事件；放宽 preflight diverge；accept 后 constrain |
| `semantic_divergence_service.py` | 增加 weak/strong constraint 模式 |
| `studioStore.ts` | 明确行为 → 快 Gate；预发散并行；accept → constrain |
| `intent-ir-sandbox.html` | 继续作为 prompt / 融合实验台 |

**不在本策略范围：** 3D/图像生成提前狂跑（成本高）；取消 encoding（正式 IR 仍要）。

---

## 6. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 快 Gate 与正式 IR 不一致 | provisional 标记 + 冲突时二次确认 |
| 预发散浪费 token | 限制候选数；仅高置信交互触发；可关开关 |
| 语义优先误匹配（「头」匹配到 header） | 仅对 registered part_labels / 词典命中 |
| 用户接受草案后正式结果翻转 | 保留 draft_accepted 快照，翻转需显式提示 |

---

## 7. 建议实施顺序

1. **Prompt V1 替换**（低成本，sandbox 立刻可测）  
2. **快 Gate 接线到主前端**（体感收益最大）  
3. **Preflight 发散 API + 前端并行**  
4. **Accept 后 constrain / 增量补召**  
5. **Encoding 异步化与缓存**

---

## 8. 验收清单

- [ ] 明确行为后 Gate 草案 < 2s 可见  
- [ ] 仅 hover 不弹 part-change Gate  
- [ ] 「改鼻子」不被身体 hover 带偏  
- [ ] 无文本时 brush 目标能驱动 part Gate  
- [ ] 预发散与 Gate 可同时进行  
- [ ] accept part 后候选明显收窄到该部件语义  
- [ ] encoding 慢/失败时快 Gate 仍可用  

---

## 9. 决策记录

- 采纳：语义明确部位优先；否则交互属性优先；hover-only 不算意图。  
- 采纳：Gate 可加速出现；发散可先宽后窄。  
- 暂缓：生成阶段预跑。  

## 10. 实施进度（2026-08-11）

已落地（第一刀）：

- [x] Prompt V1 默认文案（`DEFAULT_PLANNER_SYSTEM_PROMPT`）  
- [x] `IntentRevision.gate_provisional` + `create_revision` 即时快 Gate 草案（`_apply_fast_gate_draft`）  
- [x] 正式 `plan_revision` 完成后 `gate_provisional=false`  
- [x] 前端泡泡展示「草案·正在校准正式范围」；idle 触发 5s→2s  
- [x] `SemanticDivergenceParams.preflight` + orchestrator/store 放宽 pending Gate 发散  
- [x] 前端在 `awaiting_gate` 到达时自动 preflight 发散；accept 复用缓存、不清空已有关键词  

未完成（后续）：

- [ ] accept 后按 part/whole 做 constrain / 增量补召（真正「先宽后窄」过滤）  
- [ ] Encoding 异步化与 IntentIR 缓存  
- [ ] 快 Gate 与正式 IR 冲突时的二次确认 UI  
