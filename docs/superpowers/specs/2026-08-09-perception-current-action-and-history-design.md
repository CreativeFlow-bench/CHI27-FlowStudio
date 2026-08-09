# FlowStudio Perception 当前动作与操作历史设计规格

**日期：** 2026-08-09
**状态：** 待用户书面审阅
**范围：** Perception 面板展示层；不改变实验记录的原始数据保存规则

## 1. 目标

Perception 面板复刻参考图的“当前动作优先”表达：收起状态只显示一句自然语言，回答“用户此刻正在做什么”；展开状态显示经过归一化、去重和聚合的用户操作历史。

主面板不再直接显示 `design_phase · operation · scope` 机器字段。设计阶段、置信度、来源和内部证据不占据主视觉。

## 2. 已确认的隐私边界

- 用户输入文字在 Perception 面板中一律显示为 `Describing an intended change`。
- Perception 主句和操作历史均不得显示输入原文、截断原文、Prompt token 或输入摘要。
- 输入原文继续由实验文件的原始事件记录保存；本设计不改变其记录、导出或审计能力。
- 展示层只消费脱敏后的 `operation=describe_intent`，不得从实验事件 payload 反向读取原文。

## 3. 当前实现问题

当前 [PerceptionPanel.tsx](../../../frontend/src/components/panels/PerceptionPanel.tsx) 的展示优先级为：

1. 只要 `liveObservation` 存在，就渲染 `design_phase · operation · scope`。
2. 只有 `liveObservation` 不存在时，才渲染 `livePerception.summary`。

这导致以下已有能力通常无法成为最终显示：

- `livePerceptionSummary()` 已能生成自然语言动作句。
- 本地 `liveSignals` 能即时识别 orbit、zoom、hover、brush、annotation 和 view mode。
- 后端 supervisor 能融合 GUI、语言、IR 与 cognition 信号，判断 whole、silhouette、part、material region。

同时，当前历史列表混合 `SYS`、`INIT`、`PERCEPTION` 和 `ACTION`，并不是参考图语义下的“用户操作历史”。

## 4. 推荐架构

新增独立展示层，采用“前端即时事件 + 后端确认合并”策略：

```text
liveSignals / 本地交互
          │
          ├── 即时 provisional display event
          │
BehaviorSession / liveObservation / server perception
          │
          └── confirmed display event
                         │
                         ▼
              Perception presenter
              ├── 当前动作选择
              ├── 自然语言生成
              ├── 去重与时序保护
              └── 历史聚合
                         │
                         ▼
              PerceptionPanel
              ├── 一句当前动作
              └── 可展开操作历史
```

展示层不得改变识别服务、四阶段状态、Gate 判断或实验记录。它只负责把已有识别结果转换成稳定、可读、可审计的界面状态。

## 5. 统一展示事件

展示层使用以下逻辑结构：

```ts
type PerceptionDisplayOperation =
  | "add"
  | "draw"
  | "sculpt"
  | "reshape"
  | "smooth"
  | "inspect"
  | "focus"
  | "survey"
  | "compare"
  | "describe_intent"
  | "review"
  | "idle";

type PerceptionDisplayEvent = {
  id: string;
  behaviorSeq: number | null;
  operation: PerceptionDisplayOperation;
  scope: "whole" | "silhouette" | "part" | "material_region" | "unknown";
  targetLabel: string | null;
  sentence: string;
  source: "local" | "server";
  confidence: number | null;
  status: "provisional" | "confirmed";
  startedAt: string;
  endedAt: string | null;
  count: number;
};
```

`sentence` 必须由脱敏后的结构化字段生成，不能直接使用用户输入文本。

## 6. 当前动作优先级

从高到低选择当前主句：

1. 当前明确手势：add、draw、brush/sculpt、drag/reshape、smooth。
2. 最近 2.5 秒内提交的 `BehaviorSession`。
3. 当前持续注意行为：focus、inspect、survey、compare。
4. 后端确认的 `liveObservation` 或 `perception_updated`。
5. 8 秒内没有新操作时显示 review。
6. 没有模型和行为时显示 idle。

更新约束：

- 新事件必须比当前事件更新，旧的服务器结果不得覆盖更新的本地动作。
- 相同 `behaviorSeq` 的 server 事件原位确认 local 事件，不新增历史项。
- 明确结束事件可以立即替换；普通观察状态最少稳定展示 800ms。
- hover 停留不足 400ms 不进入主句或历史。
- 低置信度结果不得显示未经确认的部件名称。

## 7. 自然语言规则

主句固定使用英文陈述句，并以句号结束。

| 结构化动作 | 展示句 |
|---|---|
| add + silhouette/whole | `User is adding to the silhouette.` |
| draw + silhouette | `User is drawing on the silhouette.` |
| sculpt + part/region | `User is sculpting the selected region.` |
| reshape + named part | `User is reshaping the {part}.` |
| reshape + unknown target | `User is reshaping the selected part.` |
| smooth + part/region | `User is smoothing the selected region.` |
| focus + trusted part | `User is focusing on the {part}.` |
| inspect + detail | `User is inspecting a local detail.` |
| inspect + low confidence | `User is inspecting the object.` |
| survey + whole | `User is surveying the whole structure.` |
| compare | `User is comparing design alternatives.` |
| describe_intent | `User is describing an intended change.` |
| review | `User is reviewing the current form.` |
| idle | `Waiting for the user's next move.` |

目标选择顺序：

1. 后端确认的语义部件名称；
2. 当前选中或持续停留的注册部件；
3. mask 对应的 material/local region；
4. silhouette；
5. whole structure；
6. object 兜底。

## 8. 操作历史规则

### 8.1 面板行为

- 默认收起，只显示标题、状态点和当前动作句。
- 使用现有右侧箭头按钮展开或收起，保留 `aria-expanded` 和明确的 accessible name。
- 展开后面板宽度可增至现有的 420px 上限，历史区域独立滚动。
- 操作历史默认显示最近 12 条，界面内最多保留 50 条。

### 8.2 历史内容

历史只显示用户操作，不显示：

- `SYS`；
- `INIT`；
- AI 生成进度；
- 四阶段内部状态；
- 用户输入原文；
- Prompt token 或输入摘要。

每行默认显示：

```text
HH:mm:ss  OPERATION ×N  Human-readable action
```

例如：

```text
10:42:18  ADD       Adding to the silhouette
10:42:13  ORBIT ×4  Surveying the whole structure
10:42:08  SELECT    Focusing on the hat
10:42:02  INTENT    Describing an intended change
```

### 8.3 合并与去重

- orbit、zoom、hover 等连续观察在 1.5 秒窗口内合并，并增加 `count`。
- start/end 属于同一 `behaviorSeq` 时只保留完成记录。
- provisional 项收到 server 确认后原位升级为 confirmed。
- operation、scope 和 target 相同且间隔小于 1.5 秒时合并。
- 明确的 add、draw、sculpt、reshape、smooth 操作不跨 behavior sequence 合并。
- UI 的 50 条限制不删除实验文件中的原始事件。

## 9. 识别来源的使用边界

| 来源 | 展示职责 |
|---|---|
| `liveSignals` | 即时 provisional 动作、view mode 和注意行为 |
| `BehaviorSession` | 已完成操作及稳定 behavior sequence |
| `liveObservation` | 后端确认的 operation、scope、phase 和置信度 |
| `perception_updated` | 语义 target 与 supervisor/VLM 确认 |
| 实验事件记录 | 原始输入和完整研究审计；不得直接用于 UI 文案 |

`design_phase` 只作为内部确认或未来详情字段，本版本不在主句和默认历史行显示。

## 10. 错误与降级

- 后端离线：继续显示本地 provisional 事件，不标记为错误文案。
- 服务器结果迟到：按事件时间和 behavior sequence 丢弃过期覆盖。
- 无法判断 scope：使用 object，不猜测 silhouette 或 part。
- 无法判断 operation：保持上一条未过期状态；超过 8 秒进入 review。
- 部件标签不可信：显示 selected part、selected region 或 object。
- 历史为空：显示 `No user operations yet.`。

## 11. 测试要求

- operation/scope/target 到英文句子的表驱动测试。
- `describe_intent` 永远不包含输入原文的隐私测试。
- local provisional 被相同 behavior sequence 的 server 结果原位确认。
- 旧 server 事件不能覆盖新 local 事件。
- orbit/zoom/hover 在 1.5 秒内正确聚合。
- 明确几何编辑不跨 behavior sequence 合并。
- 低置信度部件降级到 object。
- 800ms 最小展示时间与 8 秒 review 降级使用可注入时间测试。
- 展开按钮的键盘操作、`aria-expanded` 和历史滚动区域测试。
- 桌面与窄屏无水平溢出。

## 12. 非目标

- 不重写 GUI、semantic language、cognition supervisor 或 target fusion。
- 不修改四阶段、Gate、Solution Space 或 AI Behavior。
- 不将用户输入原文暴露给 Perception UI。
- 不删除或压缩实验文件中的原始记录。
- 不在本版本增加完整证据详情面板。
