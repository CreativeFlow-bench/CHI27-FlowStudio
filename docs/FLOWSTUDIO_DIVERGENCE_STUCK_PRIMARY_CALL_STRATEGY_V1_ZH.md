# FlowStudio 发散卡在 primary_call 诊断与更改策略 V1

日期：2026-08-11  
状态：P0/P0b 已落地（路由钉死 flash、超时、流式 phase-log、部分候选放行）；持续观察网关  
现象：Accept 后 UI 长时间停在 `Calling primary model gemini-3.6-flash`，`run.semantic_divergence` 一直为 `null`

---

## 0. 一句话结论

**两件事叠在一起，不是「前端信号不够」。**

1. **代码缺陷（主因）**：UI / `runtime.model=` 写的是 flash，但 `GatewaySemanticGenerator.generate()` 走 `route_for(SEMANTIC_DIVERGENCE)`，**实际先打 `gpt-5.5`（reasoning）**。  
2. **网关事实（放大器）**：同机探针下 `gemini-3.6-flash` ~4.6s 正常；`gpt-5.5` **30s 读超时**。再叠加 60s×重试×repair，体感可卡数分钟，且全程停在 `primary_call`。

---

## 1. 证据

### 1.1 实时探针（本机 → 当前 MODEL_API）

| 模型 | 结果 | 耗时 |
| --- | --- | --- |
| `gemini-3.6-flash` | OK（tiny JSON） | **~4.6s** |
| `gpt-5.5` | `TimeoutError: The read operation timed out` | **~30s**（单次探测上限） |

结论：网关对 **flash 可用**；对 **reasoning 当前慢/挂**。不是「整条网关全死」。

### 1.2 路由代码（实际 HTTP 模型）

`ModelApiProfile.route_for`：

- `INTENT` / `PERCEPTION` → fast 主 / reasoning 备  
- **其它 stage（含 `SEMANTIC_DIVERGENCE`）→ reasoning 主 / fast 备**

`GatewaySemanticGenerator.generate` 调用：

```text
gateway.complete_json(self.stage, ...)  # 按 stage 路由，忽略 self.model
```

`runtime.py` 虽把 `semantic_primary.model = fast_text`，**只影响 progress 文案**（`getattr(self.gemini, "model")`），不改变 HTTP。

### 1.3 超时配置未落到发散路径

| 配置 | 值 | 实际是否约束发散 primary |
| --- | --- | --- |
| `semantic_divergence_timeout_sec` | 25 | **否**（Gateway 路径不用） |
| `model_api_timeout_sec` | 60 | 是（transport 单次） |
| `model_api_max_retries` | 2 | 是（最多 3 次） |
| stage 内双模型 + validation repair | — | 再乘一层 |

粗算最坏墙钟：双模型 × (首轮+repair) × 3 次 × 60s → **可到数分钟～十分钟级**，UI 一直停在 `primary_call`，`semantic_divergence` 保持 `null`（persist 只在整段 `_diverge_once` 结束）。

### 1.4 「卡在 Calling primary + sd=null」是否预期？

| 问题 | 答案 |
| --- | --- |
| HTTP 未返回前显示 `primary_call`？ | **预期**（phase 已发，结果未落盘） |
| poll 看到 `semantic_divergence=null`？ | **预期**（同因） |
| 文案写 flash 实际打 gpt-5.5？ | **缺陷** |
| 超过 25s 仍无 `primary_failed` / fallback / error？ | **缺陷**（预算过大 + 超时未生效） |
| Accept SSE / worker 合流导致死锁？ | **非本次根因**（同 task join；会一起挂在 HTTP 上） |

### 1.5 网关冗余（已确认，多层叠乘）

主站一次「primary_call」里，实际可能串行叠了 **三层** 冗余，且文案不暴露内层切换：

```text
L1 transport          max_retries=2 → 同一 model 最多 3 次 × 60s
L2 TextModelGateway   complete_json(stage) → route 内 primary+fallback 两模型
                      + validation 失败再 repair 一轮（同 model 再 chat_json）
L3 SemanticDivergenceService
                      self.gemini (stage=SEMANTIC_DIVERGENCE) 失败/不够
                      → self.local_vlm (stage=PERCEPTION) 再整套 L1+L2
```

装配现状（`runtime.py`）：

| 服务层角色 | `stage` | `route_for` 真实顺序 | `self.model`（仅展示） |
| --- | --- | --- | --- |
| semantic_primary (`self.gemini`) | `SEMANTIC_DIVERGENCE` | **gpt-5.5 → flash** | flash |
| semantic_fallback (`self.local_vlm`) | `PERCEPTION` | **flash → gpt-5.5** | gpt-5.5 |

因此：

- UI 停在 `Calling primary model gemini-3.6-flash` 时，L2 **很可能正在打/重试 gpt-5.5**（已探针 30s 超时）。
- 即使 L2 最终落到 flash，前面的 reasoning 超时×重试已经把墙钟吃光。
- 若再进 L3 fallback，会 **再打一遍** PERCEPTION 路由（flash 主），看起来像「又在跑」，但用户仍可能以为卡在同一句 primary。

**冗余不是灾备写错了，是三层未做预算合并**：没有「整段发散总超时 / 禁止对已超时模型再试 / 内层 fallback 要发 phase」。

### 1.6 主站前端 vs sandbox 差异（你的直觉对）

| 维度 | Sandbox (`gate-diverge-sandbox.html`) | 主站 (`AIBehaviorPanel` + `studioStore`) |
| --- | --- | --- |
| 入口 | `POST /sandbox/diverge/stream` 直打 | Accept Gate → SSE `/four-stage/.../stream` + worker 等合流 |
| 进度 UI | 独立 `phase-log`，每条 phase 追加 | 单行 `semantic-keyword-status`，易被「同一句」盖住 |
| 模型计划 | defaults 展示 primary/fallback provider+model；body 可选 `model_choice` | 无 model_plan；无法选只打 flash |
| 校验门闸 | **无** `SemanticCandidateValidator`；generator 返回即当成功 | 有 collection 校验 → `needs_fallback` 易触发 L3 |
| Payload | 可编辑短 intent / 可关 KB | 完整 run 上下文 + evidence，更大更慢 |
| 失败可见 | stream `error` / 页面 throw 很直观 | 长等 + poll null；错误易被 loading/phase 吞或滞后 |
| 内层路由 | 同一个 `GatewaySemanticGenerator.complete_json` | 同左 —— **sandbox 也吃 L1+L2 冗余** |

Sandbox「体感更快」常见原因：

1. 默认/手动走到 **fallback generator**（`stage=PERCEPTION`）→ L2 **先打 flash**；或 primary 很快失败后切到它。  
2. 无校验门闸 → 少一轮 L3。  
3. phase-log 让你看见切换；主站只留一行，像「一直卡住」。  
4. 载荷更小。

**所以：前端逻辑确实和 sandbox 还有差异；同时网关冗余在两边底层是共享的，主站被 L3 校验 + 错误路由放大得更狠。**

历史日志另有 `ModelHttpError: chat completion contained invalid JSON` → **脏响应** 会再叠 L2 repair，策略里要一并防。

---

## 2. 根因分层

```text
UI: "Calling primary model gemini-3.6-flash"
        │
        ▼
progress 读 self.model (= fast)     ← 展示层（误导）
        │
        ▼
complete_json(SEMANTIC_DIVERGENCE)
        │
        ▼
route_for → primary = gpt-5.5      ← 代码路由（错误/过重）
        │
        ▼
transport 60s × retries (+ repair) ← 超时策略（过宽）
        │
        ▼
gpt-5.5 读超时 / 极慢              ← 网关事实（已探针）
```

---

## 3. 更改策略（分阶段）

### P0 — 对齐「快发散」契约 + 去掉叠乘冗余（必须，一个小 PR）

目标：Accept 后 **优先打 flash**，25s 级失败可切 fallback，文案 = 真实模型；**一层决策、禁止三层各试一遍 gpt-5.5**。

1. **路由**：`route_for(SEMANTIC_DIVERGENCE)` 改为  
   `ModelRoute(fast_text_model, reasoning_text_model)`  
   （与 INTENT/PERCEPTION 同形；或仅发散 stage 特例。）
2. **或**（二选一即可，优先改 route）：`GatewaySemanticGenerator.generate` **强制**  
   `transport.chat_json(model=self.model, ...)`，stage 仅用于审计；`runtime` 的 primary/fallback `model=` 才真正生效。  
   → 这样 L2 不再暗中再套一套 route，服务层 L3 才是唯一 fallback。
3. **超时**：发散路径套 `asyncio.wait_for(..., timeout=semantic_divergence_timeout_sec)`，或给该 stage 传入独立 `timeout_sec=25` + `max_retries<=1`。  
   Primary 超时 → 发 `primary_failed` → 立刻 fallback。  
   **已对某 model 超时的，同一次 diverge 禁止再试该 model**（砍掉 L1×L2×L3 对 gpt-5.5 的重复轰炸）。
4. **Progress**：显示实际 HTTP model + attempt；内层 route fallback / repair 也要发 phase（或至少改文案），对齐 sandbox `phase-log` 的可见性。

验收：

- 探针级：主站 Accept 后 phase 文案出现真实模型名（应为 `gemini-3.6-flash` 且 HTTP 一致）。  
- 墙钟：正常路径多数 **< 15–25s** 出首批 candidates 或明确 `primary_failed`。  
- 人为让 reasoning 超时：不得再堵死整段数分钟无 phase 更新；同一次请求最多打 reasoning **1 次**。

### P0b — 主站前端对齐 sandbox 体验（可同 PR 或紧随）

5. More Creative 关键词区增加可滚动 **phase 列表**（或至少保留最近 3 条），不要只留一行被盖住。  
6. 展示 `model_plan`（primary/fallback 真实 model），可选「仅 flash」调试开关（对标 sandbox `model_choice`）。  
7. 超过总预算仍无 candidates → 明确错误/重试 CTA，而不是无限 skeleton。

### P1 — 可观测与失败可见（小改）

8. `_call_model` 等待中每 5–10s heartbeat：`primary_call` + `elapsed_ms` + `attempt` + `model`。  
9. 可选：persist `status=running` 中间态，避免 poll 长期 `null` 被误判为「没跑」。  

### P2 — 契约与载荷（防脏响应拉长）

10. Gateway `max_tokens=3600` 与 `build_payload`（可到 ~8000）对齐，按 `candidate_count` 设上限，降低截断 → invalid JSON → repair。  
11. 主路径校验过严时：首轮允许「部分合格 candidates」先 SSE 推送，不足再补，避免整段等 L3。  
12. 文档：sandbox vs main 的校验/超时/冗余差异写进 runbook。

### 明确不做（本轮）

- 不为「补前端交互信号」改发散。  
- 不重写 SSE/worker 合流（非根因）；P0 落地后再评估是否简化 worker 为纯等待。  
- 不把 reasoning 从产品里删掉；只是 **发散首跳禁止依赖当前已超时的 gpt-5.5**，且禁止多层重复试它。

---

## 4. 推荐落地顺序

```text
Day 0（已完成）: 探针确认 flash OK / gpt-5.5 超时 + 路由错位
Day 1: P0 路由 + 超时 + 真实 model 文案
Day 1–2: P1 heartbeat + 前端超时提示
Day 2+: P2 max_tokens / 部分候选早推（若仍见 invalid JSON / repair 风暴）
```

---

## 5. 回滚与风险

| 改动 | 风险 | 回滚 |
| --- | --- | --- |
| SEMANTIC_DIVERGENCE 改 fast 主 | 发散质量可能略降 | route 改回 reasoning 主 |
| 25s 硬超时 | 偶发慢成功变 fallback | 调到 35–40 或仅 primary 25s |
| 强制 `self.model` | 与全局 stage 路由分裂 | 改回 `complete_json(stage)` |

---

## 6. 相关文件

- `backend/app/services/model_api/config.py` — `route_for`  
- `backend/app/services/divergence/semantic_model_clients.py` — `GatewaySemanticGenerator.generate`  
- `backend/app/services/model_api/runtime.py` — primary/fallback 装配  
- `backend/app/services/divergence/semantic_divergence_service.py` — phase / persist  
- `backend/app/config.py` — `semantic_divergence_timeout_sec` vs `model_api_timeout_sec`  
- `frontend/src/state/studioStore.ts` / `semanticDivergenceStream.ts` — phase UI（展示层，非根因）
