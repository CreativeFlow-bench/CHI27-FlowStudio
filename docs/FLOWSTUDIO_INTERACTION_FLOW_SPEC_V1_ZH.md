# FlowStudio Interaction Flow Spec v1

日期：2026-08-02  
目标：把 FlowStudio 的主动观察、轻量询问、类比发散和生成结果管理收束成一条可实现、可解释、可实验验证的交互闭环。  
关联文档：

- `FLOWSTUDIO_PROTOTYPE_FRONTEND_BACKEND_DEV_SPEC_V1_ZH.md`
- `FLOWSTUDIO_BACKEND_CONVERGENCE_STRATEGY_V1_ZH.md`
- `FLOWSTUDIO_CURSOR_BACKEND_CONTRACT_V1_ZH.md`
- `FLOWSTUDIO_IR_RUNTIME_USAGE_SPEC_V1_ZH.md`

---

## 1. 核心设计立场

FlowStudio 不是普通的“输入 prompt → 生成图片/3D”的工具。它的关键机制是：

```text
持续观察人的创意行为
→ 推测人的创意状态
→ 在可能 fixation / 需要帮助时轻量介入
→ 让人选择发散维度和关键词
→ 再生成候选方案
```

系统必须保持“不打扰”：

- 默认只观察，不急着判断；
- 不在用户刚开始操作时弹意图；
- 每次只问一个小问题；
- 用户可以忽略；
- 生成慢时不锁住主操作区；
- 所有 AI 建议必须由用户显式触发生成。

---

## 2. 三层 AI 前台角色

### 2.1 Perception：观察层

位置：左上角。  
职责：只说系统观察到了什么，不要求用户决策。

允许展示：

```text
User is moving the view.
User is hovering over a part.
User is drawing on the silhouette.
User is drawing on the part.
User added a primitive volume.
```

禁止展示：

```text
Change part?
Structural + Aesthetic?
explore_shape
```

Perception 可以有 history drawer，但 history 只展示：

- 最新低阶观察；
- signal 摘要；
- 真实 object/canvas behavior；
- 必要时展示 IR evidence 摘要。

Prompt chip / analogy keyword 不进入 Perception history。

### 2.2 Intent Bubble：轻确认层

位置：画布上靠近当前关注对象或右侧空白区域。  
职责：只确认用户当前想改的范围。

唯一允许的问题类型：

```text
Change contour?
Change part?
Change material?
```

细粒度意图，例如 `cute / fashion / organic / modular / structural / aesthetic`，不在 bubble 里问，放到 More Creative。

Intent bubble 行为：

```text
出现 → 用户接受 → More Creative 展示相应维度和 prompt chips
出现 → 用户拒绝 → 记录 negative evidence，短时间不再问同类问题
出现 → 用户不点 10 秒 → 自动消失，记录 ignored
```

### 2.3 AI Behavior / More Creative：发散层

位置：右侧面板。  
职责：不是聊天区，而是发散区。

它有两种展示形式：

#### A. 用户尚未输入明确意图时：视觉灵感流

展示 Pinterest-like inspiration stream：

- 当前 object 相似设计图；
- 同类产品参考；
- 跨领域形态/材质/结构参考；
- 当前 part 的视觉灵感。

此时面板主要激发灵感，不强迫用户读长文字。

#### B. 用户输入意图或接受 bubble 后：文字发散区

展示：

- 当前 context；
- 推荐发散维度；
- prompt chips；
- Generate 按钮。

示例：

```text
Aesthetic
- soft color rhythm
- cute proportion

Structural
- modular outline
- layered silhouette

Material
- translucent shell
- fluffy texture
```

More Creative 只负责帮助用户拼合 prompt，不自动生成。

---

## 3. Signal / Behavior / Intent / Prompt Chip 的边界

### 3.1 Signal：原始可计算信号

Signal 是后台观察证据，不直接等同于用户意图。

当前 6 类 computable behaviors / signals：

| 类别 | 示例字段 | 用途 |
|------|----------|------|
| 停留时间 | `dwell_ms`, `compare_dwell_ms` | 判断关注、犹豫、可能 fixation |
| 新 case 尝试率 | `new_case_attempt_rate` | 判断探索活跃度或卡住 |
| 空间操作 | pan / drag / canvas movement | 判断局部编辑或整体构图 |
| 视口缩放与旋转 | `viewport_orbit_count`, `viewport_zoom_count`, `local_zoom_count` | 判断全局观察、多视角检查、局部检查 |
| 语义距离 | `semantic_distance`, selected prompt tokens | 判断发散幅度 |
| 用户手绘内容 | `drawing_content`, `mask_coverage`, brush / annotation count | 判断轮廓、局部、材质相关编辑 |

Signal 不直接进 behavior history；它作为 Creative State Observer 和 IR 的证据。

### 3.2 Behavior：用户对对象的可解释动作

Behavior 是用户对 object / part / canvas 的真实操作，会进入 history，也可以被合并成 intent。

算 behavior：

- hover commit 某个 part；
- 2D 笔刷画轮廓；
- 3D brush 画局部；
- annotation 标注；
- drag / smooth / add；
- 上传参考图 / 参考模型。

不算 behavior：

- 点 More Creative 关键词；
- 切换视角；
- 单纯移动鼠标；
- 打开 menu；
- prompt chip 选择。

### 3.3 Intent：多个 behavior + 语言 + prompt chips 的组合

Intent 是用户希望系统后续生成/发散时遵循的设计意图。

它可以由以下内容组成：

```text
natural language text
+ object behaviors
+ selected prompt chips
+ reference image / model
+ current part / object context
```

多个 behavior 可以在底部 panel 中压缩成小圆点，并被保存为一个 intent draft。

### 3.4 Prompt Chip：发散词材料

Prompt chip 是 More Creative 给出的词汇材料，不是行为证据。

它只进入：

- prompt compose；
- generation metadata；
- case report trace。

禁止写入 ActionAtom。

---

## 4. Creative State Observer

### 4.1 模块职责

Creative State Observer 是后台一直运行的观察模块。它接收 signals、behaviors、IR evidence 和近期 history，输出当前创意状态。

建议状态：

```text
idle
exploring
focused_editing
refining
comparing
possible_fixation
ready_for_help
```

### 4.2 第一版最小规则

先用可解释规则，不急着上复杂模型。

```text
idle:
  没有模型或没有任何 meaningful input

exploring:
  new_case_attempt_rate 高
  或 semantic_distance 增加
  或正在浏览多个候选

focused_editing:
  hover / brush / annotation / drag 集中在同一 part

refining:
  smooth / small brush / repeated micro edit 增加

comparing:
  compare_dwell_ms 高
  或 candidate hover / preview 多

possible_fixation:
  已有明确行为
  且 8–15 秒内没有新方案或明显进展
  且 dwell / hover / orbit / zoom 集中在同一对象或部件
  且 new_case_attempt_rate 低

ready_for_help:
  possible_fixation 持续约 2 秒
  且最近没有 ignored / rejected 同类 bubble
```

### 4.3 Bubble 触发门槛

Intent bubble 只由 `ready_for_help` 或明确用户输入触发。

禁止触发 bubble 的情况：

- 页面刚打开；
- 用户只是在移动视角；
- 用户刚开始输入文字；
- 上一个 bubble 刚被忽略或拒绝；
- 正在生成中；
- Solution Space 已展开且用户正在比较候选。

建议冷却时间：

```text
bubble ignored → 30 秒内不再弹同类问题
bubble rejected → 45 秒内不再弹同类问题
bubble accepted → 本轮 More Creative 完成前不再弹
```

### 4.4 Bubble 生命周期

```text
appear
→ accepted
→ rejected
→ ignored after 10s
```

`ignored` 是重要实验信号，表示系统没有打断用户。

---

## 5. IR 的角色

IR 不是给用户看的硬检索结果。IR 是后台 planner 的证据库。

IR 应该用于：

- 判断用户当前创意阶段；
- 判断是否可能 fixation；
- 推荐下一步发散维度；
- 给 More Creative 提供 axis priors 和 prompt token source。

IR 不应该用于：

- 直接告诉用户“你想要 X”；
- 把检索字段原样展示在前台；
- 单独决定 bubble 出现；
- 覆盖用户明确选择。

推荐输出：

```text
creative_state_confidence
recommended_axes
scope_hint
evidence_summary
confidence
```

---

## 6. 主交互闭环

```text
用户操作
→ Signal Collector 聚合 6 类信号
→ Perception 更新低阶观察
→ Creative State Observer 判断状态
→ IR 作为后台证据参与状态和维度判断
→ 如果 ready_for_help：
     显示一个 Intent Bubble，只问 contour / part / material
→ 用户接受：
     More Creative 切换成对应维度和 prompt chips
→ 用户选择 prompt chips：
     拼合 prompt
→ 用户点击 Generate：
     Solution Space loading strip
→ 生成完成：
     Solution Space 展开
→ 用户接受/拒绝/忽略候选：
     进入 canvas / history / solution record
```

---

## 7. Solution Space 生命周期

```text
生成开始
→ Solution Space 收成上方 loading strip

生成完成
→ Solution Space 展开

用户 hover / click 某个结果
→ 保持展开

用户 10–20 秒无交互
→ 自动收起为 history bead

用户点手动收起
→ 立即向上收起

用户接受某结果
→ 结果进入 canvas / history

用户拒绝全部
→ 清空 Solution Space，但保留生成记录
```

必须提供手动收起按钮。

---

## 8. 前端实现要求

### 8.1 需要有的前端状态

```ts
creativeState: CreativeState
bubbleState: {
  visible: boolean;
  scope: "contour" | "part" | "material" | null;
  status: "pending" | "accepted" | "rejected" | "ignored" | null;
  shownAt: number | null;
}
moreCreativeMode: "visual_inspiration" | "prompt_tokens"
solutionSpaceMode: "hidden" | "loading" | "expanded" | "collapsed_history"
```

### 8.2 面板显示规则

```text
Perception:
  永远只展示观察，不展示决策。

Intent bubble:
  只在 ready_for_help 或明确输入稳定后出现。
  10 秒无操作自动 ignored。

AI Behavior / More Creative:
  无明确 intent → visual inspiration
  有 intent 或 bubble accepted → prompt token cards

Solution Space:
  generation running → compact loading strip
  candidate_ready → expanded
  idle timeout → collapsed history bead
```

---

## 9. 后端实现要求

### 9.1 Canonical 输入

后端应接收：

- `live_signals`
- `ActionAtom`
- `intent_draft`
- `selected_prompt_tokens`
- `interpretation_id`
- `scope`

### 9.2 Canonical 输出

后端应返回：

- `perception_updated`
- `creative_state` / `state_confidence`
- `change_scope`
- `recommended_axes`
- `prompt_tokens`
- `job_update`
- `candidate_ready`

### 9.3 不要重复检索 IR

如果 `/directions/suggest` 带 `interpretation_id`，应复用该 interpretation 的 IR features。

---

## 10. 当前实现对照与待改清单

### 已基本具备

- 前端已有 `liveSignals` 聚合、900ms 静默 interpret、本地 Perception summary。
- 前端已有 `PlannerClarificationOverlay`，问题已经收敛到 `Change contour? / Change part? / Change material?`。
- 前端已有 More Creative prompt chips 和 `visualInspirationItems(...)`。
- 前端已过滤 prompt chip，不再写入 ActionAtom。
- 前端已有 Solution Space loading strip 和 18 秒自动释放逻辑。
- 后端已有 `_publish_perception(...)`、deprecated endpoint 标记、`interpretation_id` 复用 IR 的接口痕迹。
- 后端 IR retriever 已经能从 dwell、compare、orbit、zoom、mask、semantic_distance、new_case_attempt_rate 等信号生成 state codes。

### 需要改

1. **加入 Creative State Observer**
   - 前端先做轻量规则版即可。
   - 输出 `creativeState` 和 `readyForHelp`。
   - bubble 不再只看 `interpretation.confidence >= 0.68`。

2. **Bubble 10 秒自动消失**
   - 记录 `ignored`。
   - ignored 后 30 秒冷却。

3. **More Creative 双模式**
   - `intentText` 为空、没有 accepted bubble 时，只展示视觉灵感流。
   - 有文字意图或 accepted bubble 后，展示 dimension cards + prompt chips。

4. **Solution Space 手动收起按钮**
   - 当前已有 18 秒自动释放，但缺显式 collapse 按钮。

5. **Signal / Behavior / Intent 文案清理**
   - Perception history 默认不要展示太多 signal 行。
   - `whole object` 只作为 fallback，不应频繁出现。

6. **后端补 creative_state 字段**
   - 当前 IR codes 可用，但尚未形成统一 `creative_state` 输出。
   - 可以先在 `/interaction/interpret` metadata/features 中增加。

---

## 11. 最小验收脚本

1. 打开白模，不操作：  
   - Perception 显示 waiting / observing；
   - 不出现 bubble。

2. 只旋转视角：  
   - Perception 显示 moving view；
   - 不出现 bubble。

3. hover 同一 part + 停留 + 无新动作：  
   - Creative State 进入 possible_fixation / ready_for_help；
   - 出现一个 bubble；
   - 只问 contour / part / material。

4. bubble 不点击 10 秒：  
   - 自动消失；
   - 30 秒内不再弹同类问题。

5. 输入文字意图：  
   - More Creative 从视觉灵感流切换为 prompt chips。

6. 点击 Generate：  
   - Solution Space 先显示 loading strip；
   - candidate ready 后展开；
   - 10–20 秒无交互后收起；
   - 手动按钮可以立即收起。
