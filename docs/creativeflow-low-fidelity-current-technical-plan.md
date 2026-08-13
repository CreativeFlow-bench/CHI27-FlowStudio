# CreativeFlow Low Fidelity 当前技术方案

更新时间：2026-07-17  
状态：当前保留版本，作为 Low Fidelity 后续接 Hunyuan3D / PBR / 三视图渲染的基线方案。

## 1. 当前结论

Low Fidelity 暂时不走 ConceptNet / KG target noun 路线，也不做 phrase normalization。

当前保留方案是：

```text
source image
→ Qwen2.5-VL 只提取 source identity cues
→ macro silhouette primitive library 生成 raw shape prompt
→ Qwen-Image text2img 生成白底单体图
→ 合格图进入 Hunyuan3D / PBR / 三视图渲染
```

关键设计判断：

- Low Fidelity 的目标不是微小比例扰动，而是同一类 source object 下的宏观轮廓族变化。
- 允许帽子、围巾、表情、小装饰、局部比例、轻微配色和风格跟随新轮廓自然变化。
- 只要仍然可识别为同一个 source noun，就不需要像 Texture 那样严格锁死 identity。
- 不使用 source image 做强像素级结构控制；否则 Qwen-Image 会把轮廓拉回原图。
- 不做 normalize；raw shape phrase 必须原样进入 prompt，否则 “triangular / blocky / long vertical” 会被压成保守的“略收窄、略增加”。

## 2. 输入与输出

### 2.1 输入

Low Fidelity 输入：

```json
{
  "stage": "low_fidelity",
  "object_type": "snowman",
  "source_image_path": "/path/to/source.png",
  "user_prompt": "optional designer instruction"
}
```

`source_image_path` 只用于 Stage 1 的 VLM 观察，不直接作为 Stage 2 的强像素约束。

### 2.2 输出

Stage 1 输出 `stage1_result.json`：

```json
{
  "stage": "low_fidelity",
  "source_noun": "snowman",
  "identity_cues": [
    "black top hat with one red band",
    "orange carrot nose",
    "red scarf",
    "twig arms"
  ],
  "directions": [
    {
      "direction_id": "low_fidelity_01_blocky_square_body",
      "silhouette_delta": "把主体大轮廓改成更方块化的几何体量...",
      "transfer_spec": {
        "prompt": "生成一个snowman..."
      }
    }
  ]
}
```

Stage 2 输出：

```text
images_text2img/
  low_fidelity_01_blocky_square_body.png
  low_fidelity_02_triangular_cone_body.png
  ...
  stage2_result.json
```

## 3. Stage 1：Identity cues + raw silhouette primitives

实现文件：

- [`remote_worker/low_fidelity_stage1.py`](../remote_worker/low_fidelity_stage1.py)

Stage 1 做两件事：

1. 使用 Qwen2.5-VL 从 source image 中提取可迁移的身份线索。
2. 使用稳定的宏观轮廓原语库生成候选方向。

### 3.1 VLM 只负责 identity cues

VLM 需要观察 source image，提取：

- source noun；
- visible identity cues；
- current silhouette 描述，作为审计信息；
- 可选 style locks，仅用于记录，不作为强约束。

示例 snowman identity cues：

```json
[
  "black top hat with one red band",
  "orange carrot nose",
  "closed red neck scarf",
  "two brown twig arms",
  "two black coal eyes",
  "coal body buttons"
]
```

### 3.2 当前 macro silhouette primitive library

当前固定使用 8 个宏观形状方向：

| ID | 方向 | 目标 |
|---|---|---|
| `blocky_square_body` | 方块化 | 主体接近方形/立方块比例，边界更直，角保持圆润 |
| `triangular_cone_body` | 三角/圆锥 | 上窄下宽，底部更稳，顶部收窄 |
| `long_vertical_body` | 长条竖向 | 高度显著增加，宽度收窄 |
| `flat_wide_body` | 扁宽 | 高度降低，横向展开 |
| `cylindrical_body` | 圆柱/桶形 | 上下宽度接近，侧边更直，顶底更平整 |
| `hourglass_waisted_body` | 沙漏腰收 | 上下饱满，中部明显收窄 |
| `broad_base_body` | 宽底窄顶 | 下半部显著扩大，重心更低 |
| `broad_top_body` | 宽顶窄底 | 上半部显著扩大，下半部收窄 |

这些不是 donor object noun，而是可跨 source noun 使用的轮廓原语。

## 4. 不做 normalize

当前 `normalize_delta_text()` 只做空格清理：

```python
def normalize_delta_text(name: str, raw_delta: str) -> str:
    return _clean(raw_delta)
```

原因：

- normalize 会把强轮廓词翻译成保守比例词。
- 例如 `triangular_cone_body` 曾被改写成“上部略收窄，底部略扩大”，导致生成结果几乎仍是圆形雪人。
- Low Fidelity 需要保留 raw shape intent，尤其是 `blocky`、`triangular`、`long vertical`、`flat wide`、`hourglass` 等强意图。

## 5. Stage 2：raw shape prompt + identity cues + less pixel constraint

实现文件：

- [`remote_worker/variation_stage2_images.py`](../remote_worker/variation_stage2_images.py)

当前推荐 Stage 2 使用 `text2img`，不是 `img2img`。

### 5.1 为什么不用强 img2img

实验中发现：

- `img2img` 能保持 source identity，但会强烈复制 source 的原始圆轮廓。
- 对 Low Fidelity 来说，这会让大轮廓迁移不明显。
- 因此当前 Low 图像生成使用 text2img，把 source image 的作用前移到 VLM identity extraction。

### 5.2 最短 prompt 模板

当前效果最稳定的是短 prompt，而不是长英文补充 prompt。

模板：

```text
生成一个[source noun]，主体身体的大轮廓是：[raw silhouette delta]。
保留[source noun]的核心身份线索：[identity cues]。
允许帽子、围巾、表情和小配件跟随新轮廓自然变化。
单体完整三维资产，四分之三视角，完整主体居中，产品渲染，有真实体积和材质，
纯白背景，无地面，无投影，无环境。
```

示例：

```text
生成一个雪人，主体身体的大轮廓是：主体大轮廓改成明显上窄下宽的三角形或圆锥形体量：
底部更宽更稳，顶部逐渐收窄。
保留雪人的核心身份线索：黑色礼帽和红色帽带、橙色胡萝卜鼻子、红围巾、树枝手、煤球眼睛和纽扣。
允许帽子、围巾、表情和小配件跟随新轮廓自然变化。
单体完整三维玩具模型，四分之三视角，完整身体居中，纯白背景，无地面，无投影，无环境。
```

### 5.3 Negative prompt

当前 negative prompt：

```text
colored background, gradient background, floor, ground, sky, scene, landscape,
shadow, crop, close-up, cut off, duplicate, text, watermark, 2d,
flat illustration, line art
```

注意：Qwen-Image 仍可能生成浅灰或轻微渐变背景。后处理阶段可再做白底清理，但 Low 的核心优先级是轮廓有效。

## 6. 当前验证结果

### 6.1 Snowman

当前保留版：

- 本地总览图：[contact_minprompt.png](../tmp/low_raw_identity_v2e_minprompt/contact_minprompt.png)
- 远端目录：`/root/autodl-tmp/creativeflow_variations_20260716/low_raw_identity_v2e_minprompt`

观察：

- `blocky_square_body`、`triangular_cone_body`、`long_vertical_body`、`flat_wide_body`、`cylindrical_body` 已出现明显轮廓变化。
- `broad_base_body` 和 `broad_top_body` 仍偏弱，后续可以改成更直接的“梨形/倒梨形”或“下宽上窄/上宽下窄”中文描述，但仍不需要 normalize。

### 6.2 Teapot + Robot Toy

当前跨 source noun 验证：

- 本地总览图：[contact_two_nouns_combined.png](../tmp/low_two_noun_style_v1/contact_two_nouns_combined.png)
- 远端目录：`/root/autodl-tmp/creativeflow_variations_20260716/low_two_noun_style_v1`

观察：

- `teapot` 的方形、锥形、长条、扁宽、圆柱、沙漏都成立，且仍保留壶嘴/把手/壶盖。
- `robot toy` 的方块头、锥形头/身体、长条身体、扁宽躯干、圆柱躯干、沙漏躯干都成立。
- 风格可以自然变化，例如陶瓷、金属、玩具模块、彩色机械感等。

## 7. 当前代码路径

关键文件：

```text
remote_worker/low_fidelity_stage1.py
remote_worker/variation_stage2_images.py
```

当前服务器路径：

```text
/root/autodl-tmp/data/flowstudio/opt-flowstudio/app/remote_worker/
```

当前模型服务：

```text
Qwen-Image:  http://127.0.0.1:18082
Qwen2.5-VL:  http://127.0.0.1:18084/v1/chat/completions
```

## 8. 后续接 Hunyuan3D 的执行标准

只有满足以下条件的 Low 图像才进入 Stage 3：

1. 仍可识别为 source noun。
2. 大轮廓变化在缩略图尺度明显。
3. 单体完整，主体居中。
4. 没有明显 2D 平面插画感。
5. 没有大面积复杂背景、地面、投影或环境。
6. 适合作为 single-view 3D reconstruction input。

建议优先从每个 source noun 选择 4 个方向进入 Hunyuan3D：

```text
blocky_square_body
triangular_cone_body
long_vertical_body
flat_wide_body
```

如果需要 8 个方向，再加入：

```text
cylindrical_body
hourglass_waisted_body
broad_base_body
broad_top_body
```

## 9. 当前不做的事情

Low 当前明确不做：

- 不使用 ConceptNet。
- 不使用 KG target noun。
- 不使用 near / far semantic distance。
- 不做 phrase normalization。
- 不做 image geometry / mask / edge extraction。
- 不用 ControlNet。
- 不用 SDXL。
- 不用 source image 的强 img2img 像素约束。
- 不把 donor object 当成生成目标。

这些约束只适用于当前 Low Fidelity 基线版本。Part 和 Texture 后续仍按各自 variation 逻辑设计。

## 10. 一句话版本

当前 Low Fidelity 是：

```text
用 VLM 从 source 图里读出“它是谁”，
用固定的宏观轮廓原语决定“它变成哪种大形状”，
再用短 prompt 让 Qwen-Image 生成“仍然是这个 source noun、但大轮廓明显不同”的白底单体 3D 风格图。
```

