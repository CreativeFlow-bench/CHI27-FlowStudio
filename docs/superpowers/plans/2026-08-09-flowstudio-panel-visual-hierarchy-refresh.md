# FlowStudio 左右面板视觉层级轻量重排计划

> 目标：在不改变实验记录、生成流程和画布交互的前提下，明显重排左侧 Menu 与右侧 AI Behavior，继续使用现有点阵画布、蓝粉渐变、Manrope 与少量手写标题。

## 设计边界

- 左侧按“实验文件 → 输入素材 → 输出 → 系统状态”排序；文件状态始终优先。
- Runtime 与 Services 合并为原生可折叠的“系统状态”，减少常驻噪声。
- 右侧只把“当前现象”和“下一步”作为首屏结论；详情和创意控制均可折叠。
- 泡泡继续承担画布上的即时决策，右侧只做摘要和控制，二者不复制相同的视觉语言。
- 不新增 UI 框架，不调整 API、Store 或实验记录 Schema。

## Task 1：锁定层级与可访问交互

**Files**
- Add: `frontend/tests/panelVisualHierarchy.test.ts`
- Modify: `frontend/src/components/menu/StudioMenu.tsx`
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx`

1. 新增针对可观察结构的测试：Menu 有清晰的导航分区，系统状态使用可键盘操作的 `details/summary`；AI 面板的下一步是独立卡片，完整输出与创意控制分别可折叠。
2. 运行测试并确认它因新结构尚不存在而失败。
3. 在不改变 props 与事件处理的前提下，重排两个组件的语义结构。
4. 重新运行测试并确认通过。

Run:

```bash
node --experimental-strip-types --test frontend/tests/panelVisualHierarchy.test.ts
```

## Task 2：统一视觉 Token 与响应式层级

**Files**
- Modify: `frontend/src/styles.css`

1. 左侧 Rail 改为轻微磨砂底，项目文件使用顶部强调条；各区用小号 eyebrow 标签分隔。
2. Source 保持主要工作区；Output 使用紧凑卡片；System 使用折叠容器。
3. AI Behavior 增加克制的蓝粉环境色头部；现象卡保持白色，下一步卡使用低饱和渐变。
4. More Creative 仅在折叠标题中保留手写字体；展开内容恢复统一的白色表面和紧凑参数行。
5. 为 `summary` 增加可见焦点、足够触控区域，并在窄屏保持现有收起/展开机制。

## Task 3：回归与浏览器验收

1. 运行面板、可访问性和交互可靠性测试。
2. 运行全部前端 Node 测试与 Vite production build。
3. 在 `127.0.0.1:5173` 检查桌面和窄屏：左侧顺序、右侧首屏结论、折叠交互、溢出与可读性。
4. 只修复本次改动引入的问题，不扩展到后端或历史数据逻辑。

