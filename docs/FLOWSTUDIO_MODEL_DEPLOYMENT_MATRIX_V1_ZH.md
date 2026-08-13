# FlowStudio 原型模型部署与清理矩阵 V1

日期：2026-07-30  
依据：`FLOWSTUDIO_PROTOTYPE_FRONTEND_BACKEND_DEV_SPEC_V1_ZH.md`

## 1. 部署结论

本轮采用以下模型组合：

| 能力 | 模型/模块 | 处理决定 | 规格对应 |
|---|---|---|---|
| Planner、意图理解、发散词生成 | Qwen3 planner（当前部署：Qwen3-8B OpenAI-compatible service） | 已部署并通过文本 Planner smoke | 关注点推测、证据化解释、自然语言意图与发散词生成 |
| 文生图 | Qwen-Image-2512 | 已部署并通过真实生成 smoke | 类比发散候选图生成 |
| 图像编辑 | Qwen-Image-Edit-2511 | 已部署；普通编辑通过，语义遮罩可生成但非选区保真未达标 | 参考图编辑、语义局部编辑 |
| 单图多视图 | Zero123++ v1.2 | 保留 | 为当前 Hunyuan3D 多视图链提供输入 |
| 图像/多视图转 3D | Hunyuan3D-2mv / Hunyuan3D 2.1 | 保留 | 真实 mesh 生成和多视图后处理 |
| 3D 部件语义分割 | SAM3D / SAMPart3D | 保留 | Hover、Brush 部件命中、局部替换、socket fitting |
| 严格局部图像控制 | Qwen-Image ControlNet Inpainting | 保留 | Brush 需要严格保持非选区；Edit-2511 的语义遮罩测试出现取景漂移 |
| 冗余通用控制 | Qwen-Image ControlNet Union | 删除 | 当前规格和主链均无独立职责，不能替代 Inpainting 的严格局部保真 |
| 可选 VLM fallback | Qwen2.5-VL-7B-Instruct | 不作为主 planner；仅在需要图像理解 fallback 时单独启用 | 当前在线主链优先使用事件/IR/文本 planner，不再依赖重型常驻 VLM |
| 旧图像模型 | Qwen-Image | 已删除 | Qwen-Image-2512 真实生成 smoke 已通过 |

## 2. Zero123++ 与 SAM3D 不能二选一

两者处在不同阶段：

```text
源图片
  ├─ Zero123++：补全多视图 → Hunyuan3D → mesh
  └─ 已有 mesh → SAM3D：分割语义部件 → 命中/替换/装配
```

Zero123++ 解决“从一张图得到可用于 3D 生成的多视图”，SAM3D 解决“在已有 3D
对象里识别用户关注的部件”。当前结构化生成主链仍显式调用
`step4_mesh_worker_mv.py`，因此在新 3D 链完整回归通过前删除 Zero123++ 会破坏开发
规格中的真实图片到 mesh 路径；删除 SAM3D 则会直接破坏 Hover、Brush 与局部部件
替换能力。

## 3. 双 GPU 运行策略

当前推荐把 planner 与图像/3D 生成拆到两张卡，避免大语言模型和 Qwen-Image 同时常驻导致显存互相挤占：

1. 新 GPU：Qwen3 planner 提供 OpenAI-compatible `:18084/v1` 接口；旧 GPU 通过 SSH tunnel 映射为 `127.0.0.1:18085/v1`。
2. 旧 GPU：Qwen-Image 服务保留 `:18082` 契约，pipeline 延迟加载；生成模型与编辑模型按请求
   类型切换，不要求两套图像权重同时驻留显存。
3. Hunyuan3D、Zero123++、SAM3D 为作业型 worker；进入 3D 阶段前释放图像生成
   pipeline，不与大图像模型长期并驻。
4. 前端高频 hover、orbit、brush 事件先在本地聚合；Planner 只接收 500–1000ms
   窗口形成的结构化证据，不对每个指针事件发起模型调用。

当前在线配置：

- `CF_TEXT_LLM_API_BASE=http://127.0.0.1:18085/v1`
- `CF_TEXT_LLM_MODEL=qwen3-planner`
- `CF_VISION_LLM_MODEL=qwen3-planner`（文本 planner 兼容接口；图片内容由事件/IR/前端上下文摘要提供）
- `model_phase.sh planner|image|3d` 不再启动本机重型 planner；`planner` 阶段只检查远程 planner，并释放旧 GPU 图像 pipeline。

## 4. 切换与删除门槛

每个旧模型都遵循“新模型下载到 staging → 校验文件 → 启动 → 真实请求 smoke →
切换路径 → 删除旧模型”的顺序。

### Qwen3 planner

- `/v1/models` 返回 `qwen3-planner`；
- 纯文本请求能返回可解析的 Planner JSON；
- 发散词以名词/名词短语为主，必要时由服务层做 Getty AAT/词表规范化；
- CreativeFlow Planner 调用不走 fallback。

### Qwen-Image-2512

- `/health` 报告新模型路径；
- `/generate` 返回有效 PNG；
- 候选图可继续进入 Hunyuan3D 后处理。

### Qwen-Image-Edit-2511

- 参考图编辑请求返回有效 PNG；
- 语义遮罩编辑能改变白色目标区域，且 API 明确报告实际编辑模式；
- 黑色非选区必须满足局部保真阈值，否则保留 Inpainting ControlNet；
- 2026-07-30 实测能正确把帽子改为薄荷绿，但取景和非选区发生漂移，因此只删除
  Union，保留 Inpainting。

### 3D 主链

- Zero123++ 产生非空多视图资产；
- Hunyuan3D 产生真实 `mesh.glb` 与 `mesh.obj`；
- SAM3D 产生非空部件语义/面片选择；
- OSS 上传和 case 注册可由前端访问。

2026-07-30 使用同一雪人案例完成真实部署回归：

- Zero123++ 在禁止单视图 fallback 的条件下产出 348,108 字节多视图网格和四向视图；
- Hunyuan3D-2mv 以 8 步、192 octree 生成带纹理 mesh，GLB 1,797,064 字节，
  OBJ 2,824,338 字节；
- GLB、OBJ、多视图网格和两份元数据均逐项确认已存在于 OSS；
- 新 mesh 继续进入 SAM3D，产出 7 个面片部件、非空 face labels、分件 PLY，以及
  每个部件的 16 视图投影遮罩。

## 5. 明确不采用的方案

- 不在单 GPU 上本地部署 Kimi K3；其体量不符合当前服务器资源约束，可作为未来
  云 API 对照，不作为本地 Planner 主模型。
- 不把 Zero123++ 当成 SAM3D 的替代品，也不把 SAM3D 当成多视图生成器。
- 不因模型服务更新而绕开
  `pipeline_transfer_engine.py → pipeline_hunyuan3d_post.py →
  step4_mesh_worker_mv.py` 的结构化主链。
- 不在新模型未经真实 smoke 的情况下先删除旧权重。
