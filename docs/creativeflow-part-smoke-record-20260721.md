# CreativeFlow Part：3D-first 原位替换 smoke 记录（2026-07-21）

这份记录只对应当前中间结果，不视为最终 CreativeFlow Part variation。

## 当前结果定位

本轮结果验证的是“不用 2D mask，直接在 3D 里删除 SAM3D 选中的部件面片，并把 replacement mesh 原位塞回去”的工程可行性。

它不是完整 Part 链路，因为 replacement 目前仍是 procedural smoke mesh，不是经过“部件语义 → 属性/功能发散 → Qwen-Image 生成 → Hunyuan3D → PBR 材质 → 原位替换”的真实生成部件。

## 可视化结果

![CreativeFlow Part three-source smoke board](/Users/primav/Documents/博一/CHI27-FlowStudio/tmp/part_three_sources_20260721/creativeflow_part_three_sources_board.png)

## 已验证的三个 source/part

| Source | SAM3D 选中部件 | SAM3D label | 删除面数 | 保留面数 | 当前 replacement | 结论 |
|---|---|---:|---:|---:|---|---|
| snowman | nose | 0 | 969 | 39031 | wood procedural part | 局部性较好，主体未选中区域保持稳定 |
| teapot | lid knob | 3 | 4111 | 389209 | knurled procedural part | 壶身/把手/壶嘴保持稳定，局部替换边界较清楚 |
| toy water gun | grip/trigger union | 13,16 | 973 | 39027 | leather procedural grip | 能做 3D 局部替换，但 SAM3D 语义聚类只覆盖了部分 grip/trigger，不是完整把手 |

远端输出目录：

```text
/root/autodl-tmp/creativeflow_part_three_sources_20260721/
```

本地同步目录：

```text
/Users/primav/Documents/博一/CHI27-FlowStudio/tmp/part_three_sources_20260721/
```

## 当前可用规律

1. 对 Part 来说，真正有价值的约束不是 2D mask，而是 SAM3D 选中部件在 3D mesh 上形成的 socket。
2. 未选中 mesh faces 可以直接从 source mesh 复制，因此理论上能保证“其他部分基本不动”。
3. replacement part 应该先作为独立部件生成，再做 3D socket fitting；这样比 prompt-only 改整张图更适合“只改对应部分”。
4. SAM3D label 的语义质量很关键：如果选中 label 不完整，后续替换也只会替换局部碎片。

## 当前主要问题

1. 当前 replacement 不是 Qwen/Hunyuan/PBR 生成结果，因此颜色、材质和结构创新不足。
2. 没有知识图谱/类比迁移发散；只是工程 socket 验证。
3. water gun 把手的 SAM3D selection 还不够完整，需要更稳地选择完整 handle/grip semantic cluster。
4. 当前 merged mesh 的 PBR 材质合并尚未完成；更可靠的下一步是先输出 replacement part 的 PBR OBJ/贴图，再做 fitted mesh 和三视图渲染。

## 下一步真实 Part 链路

下一轮应按以下顺序跑：

1. 真实 SAM3D part selection：从 source mesh 读取部件聚类，选中待替换部件。
2. Part planner：根据 source identity、part name、part function、shape、attachment/interface、material affordance 提取可迁移属性。
3. 发散候选：围绕同功能/同连接关系/同形态语义做远距离类比迁移，生成多个 replacement part prompt。
4. Qwen-Image：生成单体 replacement part 图，要求白底、无场景、3D product render。
5. Hunyuan3D：将 replacement image 生成 GLB/OBJ。
6. PaintPBR：生成 PBR OBJ 和材质贴图。
7. 3D socket fitting：删除 SAM3D 选中部件，将 generated replacement part fitting 到原位。
8. Blender 三视图：输出 replacement part PBR 预览 + merged object 原位替换预览。

## 真实三源 Part probe 第一次完整结果

远端输出目录：

```text
/root/autodl-tmp/creativeflow_part_full_three_sources_20260721/
```

本地同步 board：

![CreativeFlow Part full-flow final board](/Users/primav/Documents/博一/CHI27-FlowStudio/tmp/part_full_three_sources_20260721/creativeflow_part_full_probe_final_board.png)

完成状态：

| Source | Part | Candidate | Qwen replacement | Hunyuan3D shape | PaintPBR | Socket fit | 三视图 |
|---|---|---|---|---|---|---|---|
| snowman | nose | translucent icicle-horn carrot nose | 完成 | 完成 | 完成 | 完成 | 完成 |
| teapot | lid knob | ridged acorn pull knob | 完成 | 完成 | 完成 | 完成 | 完成 |
| toy water gun | handle grip | braided rubber ergonomic handle | 完成 | 完成 | 完成 | 完成 | 完成 |

### 当前观察

1. 工程链路已经贯通：Qwen replacement image → Hunyuan3D mesh → PaintPBR OBJ/texture → SAM3D socket fitting → Blender three-view render。
2. Snowman nose 能较清楚体现 replacement part 原位替换，但生成部件偏大，socket fitting 需要更强的尺度/朝向控制。
3. Teapot lid knob 的 Qwen 图是可用的，但 Hunyuan3D/PBR 后变成薄片，说明“圆形小部件 + 细密装饰环”的单视图 3D 重建失败风险高。
4. Water gun handle 的 Qwen 图仍生成了“局部半枪”，不是干净的独立 handle part；但 Hunyuan/PBR 与 socket-fit 流程能跑完，merged preview 中未选中的主体相对稳定。
5. 下一版应在 Qwen 之前增加 replacement-part image gate：拒绝任何包含 full source object、半个 source object、薄片化/卡片化风险、非独立部件的图，再进入 Hunyuan3D。

### 下一轮改动重点

1. Prompt 要从 “replacement for source object” 改成更严格的 “only the detached part component, no parent object visible”。
2. 对小圆顶/旋钮类部件，优先生成更厚、更简单、更可重建的形体，例如 mushroom knob、rounded gem knob、gear knob，而不是复杂装饰环。
3. Hunyuan3D 前加 VLM/视觉 gate：是否单体部件、是否白底、是否不是完整 source object、是否有足够厚度。
4. Socket fitting 增加方向/尺度提示：按 selected part 的主轴、连接面、突出方向分开控制，避免外部 generated mesh 被 PCA 拉扁或转错。
