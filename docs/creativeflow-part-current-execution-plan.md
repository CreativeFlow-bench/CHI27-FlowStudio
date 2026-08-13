# CreativeFlow Part 当前执行计划

更新时间：2026-07-17  
状态：已接入 SAM3D 局部语义 → Part 候选 → Qwen-Image 图像验证；Stage2 局部编辑稳定性仍在优化。

## 1. Part 的目标

Part variation 的目标是：

```text
source image + SAM3D selected part semantic + 3D semantic context
→ 只改变 selected part 的局部形态/语义
→ 保持 source noun、整体姿态、全局结构、未选中部件不变
→ 输出完整单体图
→ 合格图进入 Hunyuan3D / PBR / 三视图渲染
```

Part 不是全局重设计，也不是像素拼贴。brush mask / SAM3D 只用于得到“选中了哪个部件”和该部件的 3D 语义上下文，不用于 ControlNet、不用于二维合成、不用于生成后贴图。

核心约束不是“换一个物体词”，而是：

```text
同一个 3D 局部角色 / 同一个连接 socket / 兼容尺度与朝向
+ 新的局部形态
+ 仍然能作为 source 的该 part 被阅读
```

例如 snowman 的 nose：候选必须仍然“可以成为鼻子”，而不是 pepperoni、贴纸、装饰片或任意语义相关物。

## 2. 当前 Part 链路

```text
Stage 0: source image + brush mask / SAM3D
       → selected_part_semantic
       → canonical_name / semantic_role / shape / attachment / bbox3d / confidence

Stage 1: selected_part_semantic + source context
       → 可作为同一局部角色的 candidate concepts
       → part_affordance_mapping / socket_compatibility / scale_orientation_constraints
       → part-only prompt plan

Stage 2: source image + part-only prompt
       → Qwen-Image native img2img
       → 完整 source object，只有 selected part 变化

Stage 3: accepted images
       → Hunyuan3D
       → GLB / OBJ / PBR texture
       → Blender front / side / three-quarter renders
```

## 3. Stage 0：Part semantic

生产目标：

```json
{
  "canonical_name": "nose",
  "semantic_role": "central facial protrusion",
  "shape": "short tapered cone",
  "visible_color": "orange",
  "material": "carrot",
  "attachment": "center front of head",
  "scale_constraint": "small facial part"
}
```

当前 smoke test 已使用 `sam3d_part_semantic_resolver.py` 的 snowman nose 解析结果：

```json
{
  "canonical_name": "nose",
  "semantic_role": "facial feature",
  "shape": "short, pointed, carrot-like",
  "attachment": "attached to the snowman's face",
  "confidence": 0.945,
  "face_count": 5644
}
```

后续正式版本使用：

- `sam3d_part_semantic_resolver.py`
- 输入：SAM3D manifest + brush mask + source image
- 输出：selected part noun / semantic role / attachment / shape / material / confidence

## 4. Stage 1：Part-only expansion

实现文件：

- [`remote_worker/part_relation_stage1.py`](../remote_worker/part_relation_stage1.py)

当前 Stage 1 要求：

- 候选必须针对 selected part，而不是 whole object。
- 候选必须有 `part_affordance_mapping`：说明为什么它仍然能作为这个 part。
- 候选必须有 `socket_compatibility`：说明如何保持同一 3D 连接位置/接触界面。
- 候选必须有 `scale_orientation_constraints`：说明尺度和朝向如何兼容，但允许局部形态明显变化。
- 候选不能要求改变未选中部件。
- 候选不能只是装饰物、贴纸、场景或额外物体。
- 输出 prompt 必须明确“替换原 selected part，不保留新旧两个 part”，并排除旧局部外观。

当前 snowman nose 的 v6 方向：

```text
bulbous nose
button-like nose
flattened nose
knob/peg-like nose
nozzle-like nose
```

这些只是 smoke test 的局部形态方向，不是未来所有 source 的固定词库。未来对任意 selected part，应先根据 part 的 role / shape / socket / scale 生成候选。

## 5. Stage 2：Qwen-Image part-only generation

实现文件：

- [`remote_worker/variation_stage2_images.py`](../remote_worker/variation_stage2_images.py)

推荐使用：

```text
mode = img2img
strength = 0.78 ~ 0.90
```

原因：

- Part 需要保持整体 source，所以不能像 Low 那样完全 text2img。
- 但 strength 太低会不改变 selected part；strength 太高会漂移整体结构。
- 当前 smoke test 会比较一版中高 strength。

Prompt 必须包含：

```text
基于这张 [source] 图，SAM3D 选中的局部部件是 [part_name]。
目标不是贴图或装饰，而是测试这个 3D 局部语义是否能迁移。
请只把这个 [part_name] 替换成 “[target]” 形态。
新的局部必须仍然能作为 [source] 的 [part_name] 来阅读，保持同类功能/感受。
保持同一个 3D 连接位置、接触界面和朝向逻辑。
局部大小要和原部件兼容，但允许明显看出形态已经改变。
彻底替换原来的 [part_name]，不要保留原部件外观，不要出现两个 [part_name]。
除这个 [part_name] 外，其它部分尽量保持原图。
```

Stage2 当前已修复：`variation_stage2_images.py` 的 Part 分支会优先使用 Stage1 的 `transfer_spec.prompt`，不再丢掉 SAM3D/3D 语义 prompt。

## 6. 成功标准

一张 Part 结果只有满足以下条件才进入 Hunyuan3D：

1. source noun 仍然清楚。
2. selected part 发生了可见变化。
3. 未选中部件没有大规模漂移。
4. 没有新旧两个 selected part 同时存在。
5. 没有贴图/拼图痕迹。
6. 单体完整、白底、适合 single-view 3D。

## 7. 当前服务器验证目标

本轮在 27774 上已跑：

```text
source noun: snowman
selected part: nose
candidate count: 5
Stage 1: part_relation_stage1.py
Stage 2: variation_stage2_images.py with Qwen-Image img2img
```

当前输出：

- v6 Stage1: `/root/autodl-tmp/creativeflow_variations_20260717/part_snowman_nose_v6_semantic/stage1_result.json`
- v6 filtered Stage1: `/root/autodl-tmp/creativeflow_variations_20260717/part_snowman_nose_v6_semantic/stage1_result_shape_filtered.json`
- v6 image board, strength 0.82: `/Users/primav/Documents/博一/CHI27-FlowStudio/tmp/part_snowman_nose_v6_semantic/contact_part_nose_s082.png`
- v7 image board, strength 0.88: `/Users/primav/Documents/博一/CHI27-FlowStudio/tmp/part_snowman_nose_v6_semantic/contact_part_nose_s088.png`

当前观察：

1. Stage1 候选已经从“随机物体/贴片”收敛到“可作为 nose 的局部形态”。
2. Stage2 使用纯 Qwen-Image img2img 时，局部替换可见但不稳定；strength 低时旧胡萝卜外观保留，strength 高时整体服饰/视角漂移。
3. 下一步应优先寻找 Qwen-Image 是否有更合适的 edit/inpaint 接口；如果没有，则需要在 prompt 侧进一步减少全局重写，并把 source image 作为弱 identity reference，而不是强像素控制。
