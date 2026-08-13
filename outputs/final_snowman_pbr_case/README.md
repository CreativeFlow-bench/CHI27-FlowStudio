# FlowStudio 雪人上下文发散 PBR 案例（Phase 1–3 验收交付）

日期：2026-08-03  
案例 ID（后端）：`case_dd3d29e27f`  
会话 / 资产 / 候选 / 作业：
`sess_a896bed533` / `asset_d85e4af4b2` / `cand_45b883e638_stage_01` / `job_45b883e638`

## 1. 完整链路（真实运行，无 mock）

```text
雪人资产（source.png）
  → /api/v1/directions/suggest（contextual_fragments_v1，whole scope）
      Wikidata grounding Q483985 → first-hop（P366/P527/P279）
      → Getty AAT / AskNature 二阶 → 硬门 → 3 个无分数词片
  → 用户选择词片 → /api/v1/prompt/compose（full_phrase_zh + provenance）
  → /api/v1/generation/diverge → remote worker creativeflow_low_fidelity
      → Qwen-Image-2512 真实图片候选
  → /api/v1/candidates/{id}/hy3d → Zero123++ 多视图 → Hunyuan3D-2mv → mesh.glb/obj（带 Hy3D-2 纹理）
  → Hunyuan3D-2.1 PaintPBR（no-bpy 路径）→ mesh_pbr.obj + diffuse/metallic/roughness 贴图 + MTL
  → Blender 5.0 转 mesh_pbr.glb + 渲染 preview_pbr.png
  → OSS 上传（creativeflow/flowstudio/final_snowman_pbr_case/）
  → /api/v1/cases 注册案例（evidence chain + PBR URL）
```

## 2. 上下文发散词片（Phase 2 验收点）

提问：你想如何改变这个雪人的整体？

| 词片 | 完整短语 | 溯源 |
| --- | --- | --- |
| 防滑握持纹理 | 防滑握持纹理的雪人 | snowman → ice and snow activities (P366) → AskNature "Fur And Feathers Get Grip On Ice" |
| 更矮 | 更矮的雪人 | snowman → snowball (P527) → AskNature "Flowers Accommodate Short Growing Season" |
| 更富装饰 | 更富装饰的雪人 | snowman → decoration (P527) → Getty AAT "decorative coating" (300451608) |

无偏好分数、无预选、硬门全部通过；Getty 实时端点被跳板代理挡（499）时自动走本地缓存真实 AAT 记录，
AskNature 实时可用（`partial_sources` 记录在 retrieval_audit 中）。

## 3. 最终 prompt（prompt/compose 输出）

```text
Make this snowman more playful and refined, keep snowman identity, top hat, red scarf, carrot nose, twig arms and coal buttons recognizable.
Analogy keywords: 防滑握持纹理的雪人, 更富装饰的雪人
```

## 4. 交付物（本地 outputs/final_snowman_pbr_case/ + OSS）

| 文件 | 本地 | OSS |
| --- | --- | --- |
| PBR mesh GLB（含材质贴图） | `mesh_pbr.glb`（6.97MB） | [mesh_pbr.glb](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/mesh_pbr.glb) |
| PBR mesh OBJ | `mesh_pbr.obj`（2.68MB） | [mesh_pbr.obj](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/mesh_pbr.obj) |
| MTL（引用三张贴图） | `mesh_pbr.mtl` | [mesh_pbr.mtl](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/mesh_pbr.mtl) |
| Diffuse 贴图 | `mesh_pbr.jpg` | [mesh_pbr.jpg](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/mesh_pbr.jpg) |
| Metallic 贴图 | `mesh_pbr_metallic.jpg` | [metallic](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/mesh_pbr_metallic.jpg) |
| Roughness 贴图 | `mesh_pbr_roughness.jpg` | [roughness](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/mesh_pbr_roughness.jpg) |
| 预览渲染图 | `preview_pbr.png`（1024²） | [preview_pbr.png](https://creativeflow.oss-cn-beijing.aliyuncs.com/creativeflow/flowstudio/final_snowman_pbr_case/preview_pbr.png) |
| 发散图片候选 | `candidate_image.png` | — |

## 5. 证据链（规格 §14.18 可反查）

```text
case_dd3d29e27f
  → candidate cand_45b883e638_stage_01（decision=accepted，mesh_url 已设置）
  → generation job job_45b883e638 → remote rw_creativeflow_low_fidelity_74b4306d1f
  → directions（session snapshot 保存 6 条 contextual directions）
  → contextual_fragments（fragment_id + provenance_path 存于 case metadata）
  → prompt/compose（final_prompt + selected_prompt_tokens）
  → Hy3D rw_hy3d_from_staged_21c8084aeb（mesh.glb/obj，textured=true）
  → PaintPBR final_snowman_pbr/（mesh_pbr.* + 贴图）
  → OSS creativeflow/flowstudio/final_snowman_pbr_case/
```

## 6. 环境状态（修复文档 Phase 1 验收）

- 主服务器：backend 18000 / remote worker 18100 / Qwen-Image 18082 / 前端 dist 5173 全部在线；
  KG 代理 33210 在线（Wikidata/AskNature 实时，Getty 实时被挡→缓存降级）；
  Qwen3 planner tunnel 18085→18084 在线。
- Qwen 服务器：flowstudio_planner_server.py（18084）在线，`/v1/models` 返回 qwen3-planner。
- `hy3d_ready=true`；真实 Hy3D 与 PaintPBR 均在本机跑通。

## 7. 已知残余项（非本案例阻断）

- Getty `vocab.getty.edu` 经 DatabaseMart 跳板返回 499：已用本地缓存真实 AAT 记录降级；
  后续可换代理/直连恢复实时检索。
- PaintPBR 依赖 custom_rasterizer 内核：已用 `.pre_torch211` 构建 + torch5090 环境跑通；
  若重建内核需用 CUDA 12.8 + `TORCH_CUDA_ARCH_LIST="12.0"`。
- PostgreSQL/Redis 持久化未做（当前 JSON autosave + session snapshot 恢复）；WS `seq`
  缺口检测未实现——按修复文档 Phase 3 剩余项处理。
