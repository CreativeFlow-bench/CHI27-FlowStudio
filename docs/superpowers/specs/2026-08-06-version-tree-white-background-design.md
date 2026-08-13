# FlowStudio 白底候选与版本树画布设计规格

日期：2026-08-06  
状态：已确认的交互设计，等待实现

## 1. 目标

FlowStudio 的每个生成候选必须是纯白背景上的完整单体。用户把候选从 Solution Space 拖入画布后，系统立即创建下一版图片节点，同时在后台启动 Hy3D；3D 完成后在同一节点、同一位置升级为可编辑模型。旧版本向左排列，并以父子连线形成可回溯、可分支的版本树。

## 2. 非目标

- 不把所有候选自动转换为 3D。
- 不允许一次拖入同时创建多个活动版本。
- 不在本轮实现任意自由布线、多人协作或版本合并。
- 不提交或推送 GitHub，不部署 GitHub Pages。

## 3. 图片生成硬约束

每个进入 Solution Space 的候选必须同时满足：

1. 背景为纯白 `RGB(255,255,255)`，无渐变、地面、环境、卡片边框和背景阴影。
2. 画面只包含一个设计主体；帽子、手臂、底座等所有外轮廓完整可见。
3. 主体居中，四边均有安全边距，不允许触边或裁切。
4. 无文字、水印、图例、分屏和额外道具。
5. 主体仍符合当前对象语义与 identity 约束。

生成规格必须显式传递 `require_white_background: true`、`require_single_object: true`、`require_full_object: true`。提示词约束和生成后 QA 同时生效；仅靠提示词不算验收。

### 3.1 QA 门槛

- 边缘白色像素比例不低于 `0.95`。
- 主体非白像素包围框不得接触图像边缘，并至少保留图像短边 `5%` 的安全边距。
- 大型前景连通区域只能有一个；允许与主体接触的细小部件，不允许第二个独立主体或卡片。
- 主体占画面比例应处于 `0.10–0.70`。
- 不合格结果标记具体原因并从 Solution Space 排除；系统继续补生成，直到得到 6–8 个合格候选或达到重试上限并向用户报告缺口。

## 4. Version Graph 数据模型

前端使用显式版本节点，而不是从 `acceptedCandidateIds` 临时推导布局。

```ts
type VersionNodeStatus = "image_ready" | "generating_3d" | "mesh_ready" | "mesh_failed";

type VersionGraphNode = {
  nodeId: string;
  versionNumber: number;
  parentNodeId: string | null;
  candidateId: string | null;
  label: string;
  previewUrl: string | null;
  meshUrl: string | null;
  objUrl: string | null;
  status: VersionNodeStatus;
  createdAt: string;
};
```

源模型是 Version 1，`parentNodeId=null`。用户从当前活动节点拖入候选时，新节点的 `parentNodeId` 等于当前活动节点。若用户先激活旧节点再拖入候选，则从旧节点创建兄弟分支，而不是覆盖既有后代。

版本图随 session 快照持久化；刷新、WebSocket 重连或前端重新 bootstrap 后应恢复节点、父子关系和活动版本。

## 5. 拖放与异步升级

1. Solution 卡片设置真实 HTML drag payload，包含 `candidateId`。
2. 整个版本画布是可访问的 drop target；“拖入画布”按钮调用同一 action，作为键盘与触屏替代路径。
3. drop action 在 300ms 内创建 Version 2 图片节点，状态为 `generating_3d`，立即设为活动节点并显示候选图片。
4. 同一 action 异步请求 Hy3D，不阻塞节点创建。
5. Hy3D 返回 mesh 后，以 `nodeId` 更新原节点为 `mesh_ready`；位置、版本号、父节点和连线保持不变。
6. 生成失败时节点保留图片，状态改为 `mesh_failed`，提供“重试 3D”；不得删除历史或回退活动节点。
7. 同一个 candidate 在同一个 parent 下重复 drop 必须幂等，不创建重复节点或重复 Hy3D 任务。

## 6. 自动树状布局

- 当前活动节点使用主编辑尺寸，位于画布视觉中心偏右。
- 当前节点祖先按版本深度逐列向左排列，Version 1 位于最左侧。
- 同一父节点的兄弟分支按创建顺序纵向排列。
- 父子之间使用平滑曲线或折线连接；活动路径使用更清晰的描边，非活动分支降低对比度。
- 新节点加入时整体世界坐标自动平移，使主编辑节点保持在可操作区域；旧节点不覆盖 Perception、Solution Space、AI Behavior 或 Intent Composer。
- 点击历史节点将其设为活动版本；只有 `mesh_ready` 节点启用 3D 编辑工具，图片/生成中节点只能查看和继续建立分支。

## 7. 界面状态

图片节点必须显示：

- `Version N`；
- 来源候选标签；
- `正在生成 3D`、`可编辑 3D` 或 `3D 失败`；
- 失败时的重试按钮。

拖拽悬停时画布显示明确 drop 高亮和“创建下一版本”提示。拖放完成后 Solution 卡片保留在候选区，并标记其已经用于哪个版本。

## 8. 错误处理

- 无预览 URL 的候选不能拖入，并在卡片上显示原因。
- 后端创建节点失败时不启动 Hy3D，前端显示非阻塞错误。
- Hy3D 超时或失败只影响对应节点。
- 恢复 session 时发现 `generating_3d` 节点，应查询对应任务状态，而不是重新提交任务。
- 图片 QA 不合格时保存失败原因供调试，但不把失败图暴露为可选候选。

## 9. 验收测试

1. 候选 prompt/spec 始终包含三项硬约束，QA 会拒绝非白底、裁切或多主体图片。
2. Solution Space 仅展示 QA 通过的 6–8 张完整白底单体。
3. 鼠标拖拽和“拖入画布”按钮创建完全相同的版本节点。
4. Version 2 在 300ms 内以图片出现，Version 1 左移并连线。
5. Hy3D 完成后 Version 2 原位升级为可编辑 3D。
6. Hy3D 失败后图片节点和历史树仍存在，重试不会创建 Version 3。
7. 从 Version 1 再拖入另一个候选会创建兄弟分支。
8. 刷新后版本号、父子关系、活动节点和异步任务状态恢复。
9. 桌面端和窄屏下均能访问版本节点、拖入替代按钮和状态文本。

