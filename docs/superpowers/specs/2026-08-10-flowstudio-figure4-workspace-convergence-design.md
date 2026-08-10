# FlowStudio Figure 4 工作区收敛设计

日期：2026-08-10

状态：用户已确认

范围：桌面工作区布局、信息归属、前端状态投影与 `UiBrief` Gate 去重

## 1. 结论

本轮以用户提供的 Figure 4 为桌面工作区视觉与信息层级目标，采用“定向架构收敛”，不继续在现有布局上追加零散 CSS 补丁，也不重写全部前端。

唯一主线是：

```text
左侧轻量感知
  + 中央主模型/版本空间
  + 右侧紧凑 AI Behavior
  + 底部意图编辑器
  + 结果出现后展开的顶部 Solution Space
```

桌面首屏必须在 `1280×720` 下完整容纳核心界面，不允许通过浏览器页面滚动找回 Composer 或核心操作。

## 2. 已确认的布局行为

### 2.1 尚无 Solution Space

- `AI Behavior` 停靠在右侧，但不贴右上角；
- 面板位于右侧可用空间的中上段，为中央模型保留主视觉优先级；
- 顶部中央不显示空结果容器。

```text
┌ Brand ──────────────────────────────────────┐
│ Perception      中央主模型 / 版本画布       │
│                                      │ AI Behavior
│                                      │
│             Composer                 │
└────────────────────────────────────────┘
```

### 2.2 Solution Space 出现

- `Solution Space` 展开为顶部横向结果带，从 Brand/Perception 右侧延伸至右边界；
- `AI Behavior` 自动下移到 Solution Space 下方；
- 中央模型的可用矩形随之收缩，但模型使用 `object-fit: contain`/对应 3D 适配策略保持完整；
- Composer 始终在首屏底部中央可见。

```text
┌ Brand/Perception │        Solution Space         ┐
│                  └──────────────────────────┤
│       中央主模型 / 版本画布       │ AI Behavior
│                                      │
│             Composer                 │
└────────────────────────────────────────┘
```

## 3. 信息归属与去重

每类信息只能有一个主展示位置。

| 信息 | 唯一主展示位置 | 不允许出现的位置 |
| --- | --- | --- |
| 当前可验证的用户行为 | Perception | AI Behavior 的同义复述 |
| Gate 问题与接受/拒绝 | 画布 `PlannerClarificationOverlay` | AI Behavior、状态芯片、UiBrief |
| AI 当前简短行为说明 | AI Behavior | Gate 气泡、Perception |
| 发散关键词与参数 | AI Behavior / More Creative | 画布 Gate 气泡 |
| 生成进度、候选结果 | Solution Space | AI Behavior 的重复卡片 |
| 运行细节与模型原始输出 | AI Behavior 折叠详情 | 默认首屏文本 |

### 3.1 Perception

- 默认只显示一句当前观察，最多两行；
- 不展示解释、意图推断、后端阶段或历史；
- 历史进入现有 Timeline/History 入口。

### 3.2 AI Behavior

默认内容顺序为：

1. 一段简短 AI 行为说明；
2. `More Creative?` 入口与已锁定对象；
3. 展开后的发散参数和关键词；
4. 末尾折叠的模型详情/调试输出。

以下元素从 AI Behavior 默认界面移除：

- `four-stage-mini` 可视阶段条；
- `four-stage-gate` Gate 问题副本；
- “当前现象 / 下一步”双卡片；
- 与 Solution Space 重复的生成进度和候选摘要。

## 4. 状态与后端投影收敛

### 4.1 Gate 唯一事实来源

`IntentRevision` 是 Gate 的唯一事实来源，包括：

- revision 范围；
- Gate 问题；
- awaiting/accepted/rejected 状态；
- 接受和拒绝操作。

前端不再将以下全局布尔值组合成 Gate 文案：

```text
fourStage.gateOpen
fourStage.scopeAccepted
fourStage.decision
```

`fourStage` 可继续用于后端运行能力、审计和调试，但不直接投影成用户需要阅读的四阶段界面。

### 4.2 UiBrief

- 当存在 pending `IntentRevision` 时，后端不再把 `gate_question` 写入 `UiBrief.next_question`；
- `UiBrief` 可保留字段以兼容旧客户端，本轮不做破坏性 schema 删除；
- 非 Gate 的系统提示可继续使用 `next_question`，但前端 presentation selector 必须明确区分。

### 4.3 前端 Presentation Selector

新增纯函数 selector，将 store/API 原始状态整理为组件可直接消费的视图模型：

```ts
type WorkspacePresentation = {
  hasSolutionSpace: boolean;
  perception: { text: string; tone: string };
  gate: { revisionId: string; question: string; status: string } | null;
  aiBehavior: {
    narrative: string;
    creativeState: "locked" | "loading" | "ready" | "error";
    details: string | null;
  };
};
```

组件不得再通过检查多个布尔值推断阶段或自行组装同义文案。

## 5. 前端布局架构

### 5.1 单一布局合同

`main.tsx` 在工作区根节点输出 `has-solution-space` 状态类或 data attribute，布局根据该状态计算一次。

建议使用一组集中变量：

```css
--workspace-gap: 16px;
--workspace-edge: clamp(12px, 1.4vw, 24px);
--perception-width: clamp(280px, 24vw, 340px);
--solution-left: clamp(360px, 34vw, 440px);
--solution-height: clamp(176px, 23vh, 220px);
--ai-width: clamp(292px, 22vw, 340px);
--composer-width: min(720px, calc(100vw - 48px));
--composer-reserve: 116px;
```

具体数值可在浏览器回归中微调，但只允许在这一处布局合同内调整。

### 5.2 停止内联尺寸竞争

- Perception、Solution Space 和 AI Behavior 不再使用通用 `ResizableShell` 的 React 尺寸 state 作为默认布局来源；
- 若仍保留 `ResizableShell`，必须增加不写入内联 width/height 的 static/layout-owned 模式；
- 不得用新的 `!important` 覆盖解决尺寸竞争；
- 将工作区最终布局规则收敛到独立样式区域/文件，删除或失效化旧的重复选择器。

### 5.3 主模型安全区

主模型/活动编辑器的可用矩形由以下保留区一次计算：

- 顶部：Brand 与可选 Solution Space；
- 左侧：Perception 的轻量占位；
- 右侧：AI Behavior 宽度与 gap；
- 底部：Composer 与导航控件。

版本节点缩略图尺寸与活动编辑器尺寸解耦，不允许固定节点尺寸继续限制活动模型。

## 6. 响应式与可达性

### 6.1 桌面验收档

- `1280×720`：核心验收下限；
- `1440×900`：默认产品视图；
- `1920×1080`：宽屏视图。

三档必须同时满足：

- 无水平页面滚动；
- Composer 全部可见；
- AI Behavior 不覆盖 Solution Space 或 Composer；
- 活动模型完整可见；
- 只有面板内部详情区可以独立滚动。

### 6.2 窄屏

`< 900px` 时，不强行维持 Figure 4 桌面布局：

- Perception 折叠为单行状态；
- AI Behavior 收起为可展开抽屉；
- Solution Space 使用顶部横向滚动；
- Composer 继续固定可见。

### 6.3 可访问性

- 交互控件保持明确 `:focus-visible`；
- 移动/窄屏主操作命中区不小于 44px；
- 文本截断需保留完整内容的可达途径；
- 动画遵守 `prefers-reduced-motion`；
- 不使用 `transition: all`。

## 7. 加载、错误与空状态

- 无候选结果时不渲染空 Solution Space 大框；
- 生成中由 Solution Space 显示单一进度状态；
- Gate 失败在 Gate 气泡原位显示简短原因和重试；
- More Creative 失败在该区域显示一个明确下一步，不在 AI Behavior 顶部另外复制错误；
- 错误不同时以 banner、toast、card 三种形式重复。

## 8. 测试与验收

### 8.1 后端

- pending revision 时 `UiBrief.next_question` 不复制 Gate 问题；
- Gate 问题继续在 `IntentRevision` 上完整可用；
- 兼容字段和非 Gate 提示不受影响。

### 8.2 前端单元测试

- selector 在冲突的 `scopeAccepted/gateOpen` 布尔值下仍以 revision 为准；
- Gate 问题只投影到画布气泡；
- `hasSolutionSpace` 在 loading/candidates/reviewing 状态下输出正确；
- AI Behavior 只保留一段主叙事。

### 8.3 浏览器验收

对每个桌面视口验证无 Solution Space 和有 Solution Space 两种状态：

1. 获取工作区根节点的 `scrollWidth/clientWidth` 与 `scrollHeight/clientHeight`；
2. 检查 Brand、Perception、Solution Space、AI Behavior、Active Editor 和 Composer 的 bounding boxes；
3. 检查任意两个主区域不存在非设计重叠；
4. 搜索可见 Gate 问题，断言出现次数为 1；
5. 截图与 Figure 4 的层级、占比和空白感对照。

## 9. 非目标

本轮不：

- 改变生成模型、语义发散算法或提示词质量；
- 重写 Three.js 交互和 mesh 编辑器；
- 移除原始审计数据或试验记录；
- 在桌面首屏展示后端四阶段细节；
- 引入新 UI 依赖。

## 10. 实施边界

为避免与现有用户改动冲突，实施时遵循：

- 仅修改本设计直接涉及的前端组件、selector、工作区样式、`UiBrief` 生成逻辑与对应测试；
- 不回滚或覆盖工作区内无关的未提交变更；
- 先为重复投影和布局状态写失败测试，再修改实现；
- 完成后以单元测试、构建、API 回归和真实浏览器截图共同验证。
