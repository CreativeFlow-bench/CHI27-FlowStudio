# FlowStudio 雪人帽子局部发散与 Identity 在线验收

状态：**FAIL（数量与数据合同通过，局部性与具体 source identity 未通过）**  
验收日期：2026-08-05  
用途：C7 `part-local divergence + source identity + 6–8 solutions` 的 GPU 真实链路证据。

## 1. 固定输入

| 字段 | 值 |
| --- | --- |
| session | `sess_bcb3214bf8` |
| revision | `intent_e7494277a6` |
| run | `fsrun_c5e5237ee4` |
| batch | `batch_intent_e7494277a6` |
| generation | `gen_ef1b01c563` |
| source asset | `asset_329aa0683e` / `snowman` |
| source image | `/files/screenshots/art_b9a5a17157/viewport.jpg` |
| source model | `/files/white-models/christmas/snowman.obj` |
| Gate | `你想改变这个 hat 的形状或连接吗？` |
| scope / target | `part` / `hat` |
| 人选关键词 | `integrated hat-to-head connection`; `soft seamless transition` |
| 候选数 | 8 |

Gate 接受、关键词保存和 Generate 全部通过真实 GPU API 执行，未使用 mock、占位图或历史候选补数。

## 2. 验收规则

一个候选只有同时满足下列条件才计入 Solution Space：

1. URL 可访问，且为真实非空 PNG；
2. 显式携带 source image、`scope=part`、`target_part_id=hat` 和人选关键词；
3. 帽子与头部连接发生可见变化；
4. 头部非目标区、身体比例、两侧树枝手臂、相机/构图与白模风格保持；
5. 不得将整体轮廓、全局材质、脸部、围巾或装饰重绘当作帽子局部发散；
6. 至少 6 张通过 identity + locality QA；不足 6 张时 batch 必须进入 retryable quality failure，不能标记为可交付 `completed`。

## 3. 真实结果

- API 产物：8/8 张为 512×512 真实 PNG，URL 可访问；
- 数据链：Revision、Intent IR、SourceContext 和 GenerationSpec 均为 `part/hat`，两个人选关键词进入每个 prompt；
- source snapshot：非空，可辨识为当前两层雪人白模；
- mask：`target_mask_ref=null`，因此实际执行为整图 conditioned generation，不是局部 masked edit；
- prompt：仍轮换使用 `overall silhouette`、`material appearance`、`internal structure`、`ornament` 四类全局轴，与已确认的 `part/hat` 冲突；
- 人工严格视觉复核：候选普遍改变脸部、头/身比例、手臂、风格或增加围巾/装饰，未证明“同一个具体雪人”的非目标区保持；
- Qwen2.5-VL 二次 QA：`accept=1`、`maybe=4`、`reject=3`；即使将 maybe 全部放宽计入也只有 5 张，仍低于 6 张交付门槛。

8 个产物路径：

```text
/files/four_stage/gen_ef1b01c563/candidate_01.png
/files/four_stage/gen_ef1b01c563/candidate_02.png
/files/four_stage/gen_ef1b01c563/candidate_03.png
/files/four_stage/gen_ef1b01c563/candidate_04.png
/files/four_stage/gen_ef1b01c563/candidate_05.png
/files/four_stage/gen_ef1b01c563/candidate_06.png
/files/four_stage/gen_ef1b01c563/candidate_07.png
/files/four_stage/gen_ef1b01c563/candidate_08.png
```

## 4. 判定

| 验收项 | 结果 |
| --- | --- |
| 6–8 个真实产物 | PASS（8） |
| source / target / keyword provenance | PASS |
| Gate 与 GenerationSpec 一致 | PASS |
| 帽子局部修改 | FAIL（无 mask，prompt 含全局轴） |
| 具体 source identity 保持 | FAIL |
| 至少 6 个质量合格 Solution | FAIL（VLM 严格 accept 仅 1） |
| 当前 batch 标记 `completed` | FAIL（缺少生成后 quality Gate） |

因此 C7 不能标记完成。该 batch 只能作为失败证据，不应作为产品合格 Solution 展示。

## 5. 修复后重跑的硬条件

1. `part` 生成缺少真实 `target_mask_ref` 时不得直接完成；
2. `part` prompt 使用局部变体轴，禁止 `overall silhouette/material/global ornament` 轮换；
3. 每张生成后运行 identity/locality/keyword QA，并将结果写入 artifact metadata；
4. 只把 QA 通过图追加到 Solution Space；
5. 合格数少于 6 时只重试失败方向，最终不足 6 则明确失败。

## 6. 失败后修复记录

2026-08-06 已完成并定点部署第一个根因修复：

- `part` GenerationSpec 不再轮换全局 `silhouette/material/structure/ornament` prompt；
- 改为局部形状、局部连接、局部表面和局部细节四类变体；
- 每个 prompt 强制写入 `change only <part>`、非目标部件保持、身体比例/姿态/相机/渲染风格保持；
- 结构质量 Gate 新增 `part_prompt_locality`，发现 `part` prompt 退化为全局轴时直接失败；
- 本地聚焦回归 23 passed，GPU 合并树 22 passed，后端/worker 健康。

该修复只关闭了 prompt locality 缺口。`target_mask_ref` 生成和候选图后的 VLM identity/locality Gate 尚未闭环，因此不重复浪费 GPU 生成无 mask 的第二批图，C7 继续保持 FAIL。

## 7. 白模 Identity 标准修订

用户选择的初始 source 是白模时，不得将“保持白色”当作 identity 验收条件。根据任务类型分开评估：

- `material/material_region`：锁定几何、轮廓、比例、部件关系、姿态和相机；颜色、材质、光泽、粗糙度和微结构必须允许明显发散；
- `part`：锁定非目标几何与已选定的 appearance baseline，只改目标部件/连接；
- `whole/silhouette`：可改整体外形，但保留用户已确认的部件和外观约束。

因此本文先前的“渲染风格改变”只能在 `part` 局部形状任务中作为越界证据，不能用于否定白模的语义材质着装。

## 8. 材质探索是条件路由，不是固定 Phase 0

材质探索不得成为每个模型的必经流程。上传模型已有可用贴图、PBR 材质、顶点色或用户已确认的 appearance baseline 时，系统必须继续原意图路由，不插入材质 Gate。

### 8.1 常驻观测输出

Asset 加载时先建立 `AppearanceProfile`：

```json
{
  "status": "authored | white_clay | unknown",
  "has_mtl": false,
  "has_texture_maps": false,
  "has_pbr_material": false,
  "has_vertex_colors": false,
  "render_is_uniform_white": true,
  "appearance_baseline_id": null,
  "evidence": []
}
```

这些是结构/渲染事实，不交给 VLM 猜测。Observation 持续编码用户文本、参考图、材质工具使用和已有资产状态，但不自动弹 Gate。

### 8.2 Send 时的路由规则

Send 只锁定当前 cutoff 之前的状态，再按以下优先级判断：

1. 用户明确要求材质、颜色、纹理、光泽或上传材质参考图：直接路由到 `material/material_region`；
2. 用户明确要求轮廓、部件、连接或结构：优先执行该明确意图，即使是白模也不强制先做材质；
3. 语义含糊/整体审美，且 `AppearanceProfile.status=white_clay`、无 baseline：生成一句材质范围 Gate；
4. 已有材质或 baseline：跳过该路由，除非用户显式要改材质；
5. 用户已拒绝本 revision 的材质建议：不重复询问，继续原意图路由。

建议的唯一 Gate 问句：

```text
这个模型目前没有材质，你想先探索它的材质和配色吗？
```

接受后才进入 material 关键词面板和 6–8 个语义着装候选；拒绝则返回原轮廓/部件/连接路由。新的 IntentRevision 仍可与已有 Gate 气泡并存，生成结果按 revision 顺序追加。

### 8.3 模型和规则的边界

VLM/LLM 只负责从用户语言和参考图提取“材质意图可能性”和生成解释；是否插入材质探索由上述可审计规则决定。模型不得覆盖“已有贴图”或“用户明确要改形状”等硬证据。

## 9. 2026-08-06 C7 四组 GPU 对照实验

### E1：白模 → 暖色针织/毛毡材质

- session: `sess_2467abad66`
- run: `fsrun_fd7ee11f40`
- generation: `gen_4770bd9b4e`
- 关键词：`warm red knitted wool`、`forest-green felt`、`tactile woven fibers`
- 产物：8/8 真实 PNG；颜色、针织和图案发散明显；
- 失败：生成器将“针织材质”解释成整只针织雪人重设计，新增围巾/纽扣并改变手臂或脸部，几何锁定未达 6/8。

### E2：白模 → 冰晶/蓝紫虹彩材质

- session: `sess_b45969eecb`
- run: `fsrun_157bdad5b6`
- generation: `gen_fbe7e8cf91`
- 关键词：`translucent icy glass`、`blue-violet aurora iridescence`、`frosted microtexture`
- 产物：8/8 真实 PNG；透明度、色彩和冰晶微结构语义成功；
- 失败：候选仍新增脸部细节/底座并改变局部比例，说明 img2img + prompt 不足以锁住原 mesh。

### E3：彩色 baseline → 帽子连接局部发散

- session: `sess_4442c604ae`
- revision/run: `intent_3bc1d32654` / `fsrun_b8c8fcee6c`
- generation: `gen_064fb2b097`
- source: E1 `candidate_02.png`
- 产物：8/8；
- 严格 VLM：8/8 保持彩色 baseline 的 object identity 和非目标区，4/8 同时具备足够明显的帽子连接变化；
- 结论：“先确立 appearance baseline，再做局部发散”显著提升 identity，但有效变体仅 4 张，未达 6/8。

### E4：对 E3 不明显方向做强化文本重试

- revision/run: `intent_d0afe70d86` / `fsrun_aaf5d846a2`
- generation: `gen_a95d754a94`
- 新关键词：`wide integrated rolled collar`、`clearly changed hat-to-head junction`；
- 关键词继承：通过，保留 E3 的 2 个 base keywords 并追加 2 个 delta keywords；
- Solution 追加：通过，`append_index=2`、`parent_batch_id=batch_intent_3bc1d32654`、新增 8 张且未覆盖 E3；
- 严格 VLM：0/8；`collar` 被一致错译为脖子围巾/领圈，修改了错误部位；
- 结论：仅增强 prompt 不能代替局部 mask/anchor，失败方向重试必须携带真实部位定位。

### 附加规则缺陷与修复

E1 首次 Gate 将 `warm` 中的子字符串 `arm` 误判为手臂，产生错误问句。已将英文部件解析改为完整单词边界匹配，新 GPU 回归结果为：

```text
scope=material
target=snowman
你想改变这个 snowman 的表面或材质吗？
```

聚焦回归：本地 36 passed，GPU 33 passed；后端与 remote worker 健康。

### E5：携带雪人类别语义的材质发散

- session/run: `sess_741d94ca85` / `fsrun_8f5b77c6d1`
- 语义约束：蓝白积雪身体、橙色胡萝卜鼻、黑色煤块五官/纽扣、棕色树枝手臂、红色针织冬帽；
- 产物：8/8 均具有明确 snowman 语义，不再退化为统一红绿针织玩偶；
- 证明：材质计划必须是 `object semantic profile + part role -> regional material`，不能只使用全局 donor material；
- 仍未关闭：图像生成仍会重绘五官和局部比例，需要在原 mesh 上生成/投射 PBR 材质才能完成几何 identity 锁定。

同时修复 material Gate 的多部件聚合：只提到一个明确部件时询问局部材质；同一意图提到帽子、鼻子、纽扣和手臂等多部件时，Gate 目标回退为整体 `snowman`。GPU 在线问句已验证为：

```text
你想改变这个 snowman 的表面或材质吗？
```

最新聚焦回归：本地 37 passed，GPU 33 passed；后端与 remote worker 健康。

## 10. 2026-08-06 E6：常驻 Observation / 快速 Gate / 双批次追加复验

- session：`sess_3306d3cc1c`；
- 明确部件 Gate：服务端完整四阶段持久化耗时 `11.68 ms`，HTTP 创建到
  `awaiting_gate` 实测 `45.12 ms`；问句为“你想改变这个 帽子 的形状或连接吗？”；
- 明确材质 Gate：HTTP 创建到 `awaiting_gate` 实测 `45.60 ms`，scope 为
  `material`；问句为“你想改变这个 snowman 的表面或材质吗？”；
- 规则明确时使用独立 deterministic planner，不修改共享模型服务；规则无法确定范围时
  仍保留 Qwen 编码与 Gemini 重表征路径；
- material revision / run / batch：`intent_3209d7c428` /
  `fsrun_b37b0d513a` / `batch_intent_3209d7c428`；
- material generation：`gen_99e2c28f07`，8/8 真实 PNG；关键词为
  `glittering fresh snow`、`frosted ice crystals`、`soft knitted wool`；
- scarf revision / run / batch：`intent_b10ba5e0f7` /
  `fsrun_20f2a0a0d7` / `batch_intent_b10ba5e0f7`；
- scarf generation：`gen_76b4f32e27`，8/8 真实 PNG；继承前三个材质词并追加
  `wide integrated knitted scarf`；`append_index=2`，parent 指向 material batch；
- 前端真实 DOM：Solution Space 显示 `16 items`，意图 10 与意图 11 各 8 张，
  后一批未覆盖前一批。

复验结论：常驻 Observation、多 IntentRevision、单句 Gate、关键词继承、批次顺序追加和
6–8 张真实结果均通过。材质多样性与 snowman 类别 identity 通过；严格几何/非目标区
identity 仍未关闭：围巾批次中部分候选丢失脸部细节或改变非目标外观，因此不能将严格
C7 locality/identity 标记为 PASS。最终闭环仍需 mesh 上的 PBR 材质投射，或真实 part mask /
anchor 条件编辑及候选后视觉 QA。
