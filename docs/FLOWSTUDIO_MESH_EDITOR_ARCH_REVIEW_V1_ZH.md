# FlowStudio 网格编辑工具架构评估 V1

日期：2026-08-03  
背景：以“合格的 mesh editing 工具”为标准，评估当前 FlowStudio 的编辑架构；
区分渲染层问题与架构层问题；回答是否要转向 Qt。

## 1. 结论（先说答案）

1. **不需要 Qt。** Blender 的编辑能力来自 BMesh 数据模型、操作符（Operator）系统、
   统一撤销栈和依赖图（Depsgraph），不是来自 Qt。Qt 只提供桌面 UI 外壳。
   当前 web/Three.js 路线完全能承载同等架构；真正缺的是“编辑数据模型 + 命令 +
   提交”这一层，而不是渲染后端。
2. 目前暴露的编辑问题里，**大部分是架构层缺口，少部分是渲染实现细节**：
   - 渲染层：笔刷衰减边界、法线更新、缩放中心、模型中途消失（effect 生命周期）。
   - 架构层：没有独立的“场景/网格数据模型”、撤销栈与几何分离、工具状态机不完整、
     雕刻结果与资产版本没有正式绑定、无统一的“编辑 → 提交”命令。

## 2. 渲染问题（已修/可修，属实现细节）

| 问题 | 归类 | 处理 |
| --- | --- | --- |
| Drag 拉出一整块硬边 | 渲染/几何 | 改为固定选区 + 初始衰减权重，边界软过渡（已修） |
| Smooth 过渡生硬 | 渲染/几何 | 固定选区 + 权重化质心平滑（已修） |
| 模型编辑中途消失 | 渲染/生命周期 | 去掉 effect 对 `parts.length` 的依赖；雕刻笔触 try/catch（已修） |
| 缩放朝向画布左上角 | 渲染/交互 | `transform-origin:0 0` + 以视口中心补偿 pan（已修） |
| 笔刷无对位提示 | 渲染/交互 | 模型上投影笔刷圈 + 大小/力度滑杆（已修） |

这些属于“画得好不好看、稳不稳定”，不是结构性问题。

## 3. 架构问题（真正的差距）

### 3.1 缺一个独立“编辑场景”数据模型

现在网格几何藏在 ThreeViewport 的 effect 闭包里（`interactive` 数组、BufferGeometry），
撤销快照、雕刻状态、资产状态分散在组件 state 里。合格的 DCC 工具应该有一个
`EditorScene`：

```text
EditorScene
├── mesh: BufferGeometry（唯一事实来源）
├── editStack（几何 undo/redo，存顶点快照）
├── selection / activePart
├── toolState（当前工具、笔刷配置）
└── history（编辑操作日志，供后端行为证据）
```

当前 `ThreeViewportHandle`（exportMeshOBJ/capturePositions/applySculptSnapshot）
已经是这个方向的雏形，但仍是“ref 接口”，不是数据模型。

### 3.2 撤销栈与编辑状态分离

- 现在有两套栈：编辑器快照栈（React state）与雕刻几何栈（positions）。
- 合格做法：**统一命令（Command）模式**——每次编辑（雕刻笔触/添加体/删除/参数）
  都是 `{execute(), undo(), redo(), label}`，一个全局 CommandStack 管理，
  Ctrl+Z / Ctrl+Shift+Z 天然统一，且每个命令可写行为日志。

### 3.3 工具状态机不完整

Blender 的工具循环是：

```text
选择工具 → 配置笔刷(半径/强度/对称) → 开始笔触(选中受影响顶点) →
持续笔触(衰减位移) → 结束笔触(压入撤销栈/写历史) → 提交或继续
```

我们已经实现笔触本身；还缺“工具配置对象”（radius/strength/symmetry 可持久化）、
“笔触完成 → 写入行为证据（已做 ActionAtom）→ 触发后续意图判断”的完整闭环
（现在笔触结束只记一条 ActionAtom，没有主动触发 Perception/Planner 更新）。

### 3.4 雕刻结果与资产版本没有正式绑定

- “保存雕刻为新模型”只是上传成一个新 asset（已实现），但没有“版本”语义：
  父资产 → 编辑版本 → 发散版本的关系链不完整（SolutionGraph 有雏形）。
- 合格做法：`assetVersion { parent, mesh, edit_ops, applied_at }`，
  提交时把编辑命令列表一并存，便于回放与案例证据。

### 3.5 前后端职责边界

- 笔触/雕刻：**前端实时**（正确方向，同 Blender）。
- 提交/持久化：**后端**（上传新 mesh 版本）。
- 发散/生成：**后端 worker**（Qwen-Image → Hy3D → PBR）。
- 行为理解：**前端聚合信号 → 后端 IR/Planner**。

这个边界是对的，不需要 Qt 或 native 渲染来改变它。

## 4. 关于 Qt 的评估

| 维度 | 结论 |
| --- | --- |
| 需要吗 | 不需要。当前问题都是架构层，换 Qt 不解决 |
| 性能 | WebGL/Three.js 对原型级雕刻足够；百万面以上才需要 GPU 雕刻内核，届时可选 Three.js 之外的方案，而不是换 UI 框架 |
| 分发 | web 便于研究评审与远程部署；Qt 桌面版会丢掉浏览器直开 |
| 什么时候再考虑 | 如果要做 Blender 级高面数雕刻、复杂 DCC 插件生态或本地文件系统深度集成，再评估（Qt/原生或 Godot/Unity 都不是唯一解） |

## 5. 演进路径（按 Blender 参考）

1. **P0 稳定笔触**（已完成）：固定选区、衰减、法线、投影圈、Ctrl+Z。
2. **P1 编辑数据模型**：抽出 `EditorScene`（geometry + editStack + toolState），
   把 ThreeViewport 变成“渲染器”，把组件 state 收敛进去。
3. **P2 命令栈**：统一 `CommandStack`，雕刻/Add/删除/参数全部走命令，行为日志从命令派生。
4. **P3 工具配置**：笔刷预设（radius/strength/symmetry/mirror），工具架 UI。
5. **P4 资产版本**：`assetVersion` + 编辑命令回放；提交时后端存版本链。
6. **P5 编辑→意图闭环**：笔触结束 → 更新 Perception scope/证据 → 必要时触发
   Planner 澄清 → 方向/生成。

## 6. 一句话

FlowStudio 现在“能雕、能撤销、能提交”；要成为合格的 mesh editing 工具，
下一步不是换 Qt，而是把几何编辑从组件闭包里提升为一个正式的
`EditorScene + CommandStack + assetVersion` 架构，渲染层问题按 §2 清单继续打磨即可。

## 7. 实施状态（2026-08-03 已落地）

按用户要求把上述架构升级落地（已部署并验证）：

- **P1 几何数据模型**：新增 `frontend/src/editorScene.ts` 的 `EditorScene`（几何引用、
  统一命令栈、编辑操作日志）；ThreeViewport 通过 `onGeometryReady` 把当前网格几何
  注册进 EditorScene，不再只藏在组件闭包。
- **P2 统一 Command 栈**：`pushGeometryEdit`（几何前后快照）与 `pushEditorCommand`
  （编辑器状态 before/after 快照）共用一个栈；Ctrl/Cmd+Z、Shift+Z、按钮撤销全部走
  `EditorScene.undo()/redo()`；旧的独立雕塑栈已删除。
- **P4 资产版本**：后端新增 `AssetVersionRecord` + `POST/GET /api/v1/assets/{id}/versions`，
  store 持久化扩展；前端“保存为资产版本”把雕刻 OBJ + 编辑命令日志提交为版本链
  （当前资产 obj_url/current_version_id 更新，版本文件互不覆盖）。API smoke 验证通过。
- **P5 编辑→Perception/Planner 闭环**：每次雕刻笔触结束立即更新本地 Perception
  （含 part/scope 证据），并通过 ActionAtom 同步后端 `interaction/interpret`
  （规则+IR 判定 → WS perception_updated → 澄清泡泡/方向可继续触发）。
- 验证：前端构建通过、无头 Chrome 渲染正常、后端测试 79 通过
  （5 个失败为服务器环境性断言：配置了远端 worker/planner 与白模目录为空）。
