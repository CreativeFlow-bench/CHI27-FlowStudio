# FlowStudio 三阶段修补流程 V1

状态：可执行的修补计划（讨论稿）  
日期：2026-08-03  
依据：

- `docs/FLOWSTUDIO_PROTOTYPE_FRONTEND_BACKEND_DEV_SPEC_V1_ZH.md`（主规格 v1.2）
- `docs/FLOWSTUDIO_CONTEXTUAL_DIVERGENCE_FRAGMENT_PIPELINE_V1_ZH.md`（增量规格 v1.0）
- 2026-08-04 双服务器审计（主后端/Qwen-Image 服务器 `westd:50575`、Qwen3 Planner 服务器 `weste:30320`）

## 执行状态（2026-08-03 更新）

- **Phase 1 已完成**：backend(18000)/remote worker(18100)/Qwen-Image(18082)/Qwen3 planner
  (18084+tunnel 18085)/KG 代理(33210)/前端 dist(5173) 全部在线；planner smoke、真实
  图片候选、Zero123++→Hunyuan3D-2 mesh→OSS 均跑通（`hy3d_ready=true`）。
- **Phase 2 核心已完成**：contextual fragment 管线落地（models/services/路由/知识适配器/
  IR 清理/前端无评分呈现/prompt compose 冲突检测）；雪人整体与部件级词片带
  Wikidata→Getty/AskNature 溯源；单测 7 条通过。
- **Phase 3/交付已完成（核心）**：雪人全流程真实跑通并产出 PBR 结果
  （案例 `case_dd3d29e27f`，详见 `outputs/final_snowman_pbr_case/README.md`）。
- **剩余硬化项（已记录，不阻塞案例）**：PostgreSQL/Redis 持久化、WS `seq` 缺口检测、
  前端组件拆分（F1）、Getty 实时端点经跳板被 499（当前用本地缓存降级）。

## 手动测试修复记录（2026-08-03 晚）

用户手动测试反馈 4 个问题，均已定位并修复（代码已同步部署）：

1. **Getty 499**：`vocab.getty.edu/sparql` 在 Mac/跳板/Qwen 服务器三个网络全部 499
   （Qwen 侧返回 “Service temporarily degraded”）——是 Getty 端点全局降级，不是跳板故障。
   修复策略：KG 检索保持 cache-first，并把 worker 的 `allow_partial_graph` /
   `allow_rule_fallback` 默认改为 true、KB 超时默认 25s，Getty 挂掉时生成不再整体失败。
2. **Drag/Brush 不改模型**：根因是几何预览链路 403
   （源 mesh 在 worker 允许根目录外）+ 源为 GLB 时按 OBJ 解析失败 + 远程几何只做全局平移。
   修复：worker 允许根加入历史 variation 目录；backend `_read_mesh`/`_remote_mesh_path`
   同机直读 + GLB→OBJ（trimesh）；交互式预览（deform-preview/sculpt-*/add-primitive）
   优先走本地 Blender headless 真实局部雕刻（`sculpt_engine=blender_headless_local`）。
3. **笔刷后模型消失**：ThreeViewport 只加载预览 URL、失败即 `resetModel()`。
   修复：预览加载失败时回退加载基础资产 mesh，不再清空画布。
4. **接口无图片预览**：worker 进程缺 planner tunnel 环境变量（打到 18084 而非 18085），
   KG 属性规划全失败 → 生成 job 失败 → 无候选图。修复：worker 启动脚本导出
   `CF_TEXT_LLM_API_BASE/CF_VISION_LLM_API_BASE=http://127.0.0.1:18085/v1`；
   属性规划器加“校验失败→修正提示重试（6 次）”；前端带词片时 `skip_kg_expansion=true`
   （词片即 KG 结果，生成不再重复跑 KG）。实测词片路径与 KG 降级路径均返回真实图片候选。

---

## 0. 审计结论摘要（本计划的输入）

### 0.1 运行时现状

- 主服务器 `~/flowstudio_app` 部署了完整前后端，但整条链路当前全部停止：
  backend（18000）、remote worker（18100）、Qwen-Image（18082）均无监听进程；
  主服务器 GPU 空闲。
- 根 `.env` 的 `IUL_VLM_INTENT_URL=http://127.0.0.1:18085/v1/chat/completions`，
  但**没有 18085→Qwen 服务器 18084 的 SSH tunnel**；`backend/.env` 写的是 18084 直连，
  两处不一致（`config.py` 实际加载根 `.env`）。
- Qwen 服务器 `Qwen3-8B` 权重完整（约 16G）；`flowstudio_planner_server.py`
  （OpenAI 兼容 `:18084/v1/chat/completions`，模型名 `qwen3-planner`）之前跑通过，当前未启动。
- Qwen 服务器 vLLM 路径损坏（`vllm/_C.abi3.so` ImportError），
  `1-8B推理-API接口.sh`（llamafactory + vLLM，8000 端口）不可用；只使用自定义 FastAPI 服务。
- 本地仓库与线上部署字节一致（关键文件 md5 相同）；前端 `dist` 构建时间晚于 `main.tsx`，产物较新。

### 0.2 缺口层级总览（修补对象）

| 层级 | 主要缺口 | 对应规格 |
| --- | --- | --- |
| 运维/模型服务 | 链路未运行；tunnel 缺失；.env 端口不一致；vLLM 坏；planner 文本化（图片被丢弃） | 主规格 6.1、部署矩阵 |
| 前端 | 单体 `main.tsx`；静态方向/`AAT_NOUN_BANK`/分数排序；证据 drawer 死代码；部件级澄清缺失；behavior 无排序 UI；Send 语义矛盾；visual_inspiration 默认模式 | 主规格 F1/F3/F5、2.2；增量规格 13 |
| 后端 | contextual fragment pipeline 完全缺失；`AnalogyDirection.score` 不可空；无 `ContextualFragment` 等模型；WS 无 `seq`；部分事件名不一致；IntentDraft 无 `scope`；prompt compose 无冲突检测 | 主规格 6.3/6.4/6.6/B5；增量规格 11/12/14 |
| 发散推理/知识层 | 无 `knowledge_adapters/` 共享适配器；三知识源代码仍内嵌在 variation 管线 | 增量规格 12.4 |
| 数据 | IR retrieval `text` 含 task_group/software 硬案例身份；IR 分数被用于词片排序展示 | 主规格 1.2；增量规格 1.1/1.2 |
| 持久化/测试 | in-memory + JSON autosave，无 PostgreSQL/Redis；仅 3 个后端测试文件 | 主规格 7、B5；增量规格 18 |

### 0.3 Hunyuan3D 专项核查结论（2026-08-03）

主服务器 Hy3D 不是“没部署”，而是**权重与服务路径齐全、曾真实跑通、当前未运行**：

- 权重齐全：Hunyuan3D-2（`/root/Hunyuan3D-2/HuggingFaceHub/.../blobs`，42 个 blob，约 22G，
  dit/paint/delight 快照 symlink 有效）；Hunyuan3D-2mv fast（`/root/autodl-tmp/models/Hunyuan3D-2mv`，4.6G）；
  Hunyuan3D-2.1 dit-v2-1（6.9G）/ paintpbr-v2-1（6.5G）/ vae-v2-1（626M）；
  Zero123++ v1.2（unet 3.46G + text_encoder 680M，`du` 显示 0 是 overlay 的 symlink 统计假象，
  `ls` 实测文件在）。`hy3dpaint`（/root/models）只是纹理管线代码，权重在 paintpbr 子目录。
- 运行环境：worker 的 `PYTHON_BIN=/root/autodl-tmp/venvs/torch5090/bin/python`
  （torch 2.10.0+cu128、diffusers 0.37.0），在 `sys.path` 加入 `/root/Hunyuan3D-2` 后
  `import hy3dgen` 通过；`hunyuan3d21` conda env 用于手动 gradio（7860），两条路径互不依赖。
- 真实成功记录：`/root/autodl-tmp/flowstudio_worker_runs/rw_hy3d_from_staged_1444d1d7d4`
  （job_state `status=completed`、returncode 0），输出
  Zero123++ 多视图（mv_front/left/back/right + 扩展视图）→ `mesh.glb` + `mesh.obj`，
  证明“输入图 → Zero123++ → Hunyuan3D-2 → mesh”主链在这台机器上可跑。
- 运行形态：Hy3D 是**作业型 subprocess**（`/jobs/hy3d`、`/jobs/hy3d-from-staged` 调
  `pipeline_hunyuan3d_post.py` + `step4_mesh_worker_mv.py`），不是常驻服务；
  当前 `REMOTE_CREATIVEFLOW_AUTO_HY3D=false`，mesh 由前端 “Make 3D” 触发，图片候选先到、mesh 后到。

因此 Hy3D 的问题不是“缺模型”，而是**链路未运行 + 自动化开关 + 与增量词片管线的衔接**，
按 Phase 1/3 收口（见下）。

---

## 1. 修补原则（三个阶段都遵守）

1. **不 mock、不静态兜底**：任何一步都不允许用静态词库、本地方向模板或假候选冒充真实结果
   （主规格 2.2、增量规格 13.2/16）。
2. **先恢复再改功能**：Phase 1 建立可验证的运行基线，之后的改动以真实 smoke 为准。
3. **契约优先**：先冻结数据契约（模型/接口/WS 事件），再改前端和服务，最后接知识检索。
4. **每阶段有明确退出条件**：只有验收标准通过才能进入下一阶段；不通过则回到本阶段修补。
5. **改动以审计发现的缺口为范围**：不重写既有的生成主链与旧 CreativeFlow 管线
   （增量规格 1.3、12.4）。

---

## 2. Phase 1：恢复运行基线（运维 + 模型服务）

目标：让 backend / remote worker / Qwen-Image / Qwen3 planner 全链路在线，
并跑通真实 smoke，证明“能运行”而不是“看起来能运行”。

### 2.1 任务

**Qwen3 Planner 服务器（weste:30320）**

1. 启动 Qwen3 planner：
   ```bash
   cd /root && nohup python3 flowstudio_planner_server.py \
     > /root/autodl-tmp/flowstudio_logs/flowstudio_planner_server.log 2>&1 &
   ```
   - 确认 `/v1/models` 返回 `qwen3-planner`，`/health` 报 GPU 可用、模型已加载。
2. 禁止使用 vLLM 路径：`qwen3-planner-vllm.log` 已有 `vllm/_C.abi3.so` ImportError。
   若确实要 vLLM，单独排障（重装匹配 torch 的 vllm 轮子）后再启用；本阶段不阻塞。

**主后端/Qwen-Image 服务器（westd:50575）**

1. 建立持久 tunnel（推荐 autossh 守护）：
   ```bash
   ssh -N -L 18085:127.0.0.1:18084 -p 10980 root@connect.weste.seetacloud.com
   ```
   统一 `.env`：根 `.env` 与 `backend/.env` 的 `IUL_VLM_INTENT_URL` 只保留一个口径
   （建议统一为 tunnel 后的 `http://127.0.0.1:18085/v1/chat/completions`）。
2. 启动 remote worker（18100）：
   ```bash
   cd /root/flowstudio_app/remote_worker
   nohup /root/autodl-tmp/venvs/torch5090/bin/uvicorn app:app \
     --host 127.0.0.1 --port 18100 > /root/flowstudio_app/logs/remote-worker.log 2>&1 &
   ```
3. 启动 Qwen-Image（18082）：
   ```bash
   /root/creativeflow_image_service/start_qwen_image.sh
   ```
4. 启动 backend（18000）：
   ```bash
   cd /root/flowstudio_app/backend && source .venv/bin/activate
   nohup uvicorn app.main:app --host 0.0.0.0 --port 18000 \
     > /root/flowstudio_app/logs/cloud-backend.log 2>&1 &
   ```
5. 核对 `scripts/cloud_start.sh` 的路径假设（`/root/flowstudio_backend`、
   `/root/flowstudio_remote_worker`）与当前 `/root/flowstudio_app` 布局不一致；
   要么修正脚本变量，要么按上面手动启动。前端 dist 用静态服务（5173）或接入 gateway。
6. **Hunyuan3D 链路 smoke**（不启动 gradio，直接验证作业链）：
   ```bash
   # 用旧成功 job 的输入图复跑一次，或走 frontend Make 3D：
   # POST /jobs/hy3d-from-staged（staged_result_path 指向一个真实 image candidate）
   # 期望：Zero123++ 多视图 → mesh.glb/mesh.obj → OSS 可读 URL
   ```
   - 确认 `pipeline_hunyuan3d_post.py` / `step4_mesh_worker_mv.py` 在
     `/root/creativeflow_pipeline/`（worker 默认 `PIPELINE_ROOT`），torch5090 venv 依赖可用；
   - 确认 `/preflight/creativeflow` 返回 `hy3d_ready=true`；
   - 手动 gradio（`1键启动.sh`，7860）只作人工预览用，不作为自动链验收依据。

### 2.2 验收标准（全部通过才算退出）

- [ ] `GET /health`（backend、worker、Qwen-Image）全部 200；
- [ ] `GET /api/v1/remote-worker/preflight` 返回 creativeflow/sam3d/partfield 就绪状态；
- [ ] Qwen planner `/v1/chat/completions` 对规划请求返回可解析 JSON
  （`scripts/cloud_planner_smoke.py` 通过）；
- [ ] Qwen-Image `/generate` 返回真实 PNG（`scripts/qwen_image_2512_edit_smoke.py` 通过）；
- [ ] `scripts/cloud_creative_solution_smoke.py`、`cloud_frontend_case_smoke.py` 通过；
- [ ] 前端 WS 可连接，`ack` 正常，Perception 面板能收到 `perception_updated`。
- [ ] Hy3D 作业链 smoke 通过：从真实图片候选生成至少一个 `mesh.glb`（或明确标记
  `3D failed` 并保留 image candidate，符合主规格 §10），OSS URL 可读。

---

## 3. Phase 2：增量规格落地 + 主规格缺口收敛（前后端 + 知识层）

目标：实现“上下文相关发散词片 Pipeline”（增量规格全部要求），并收敛审计中列出的
前端/后端/IR-RAG 缺口。本阶段不做持久化架构替换（留 Phase 3）。

### 3.1 后端（backend/app）

1. **models.py（增量规格 11、12.1）**
   - 新增 `ContextualFragment`、`TargetRef`、`ProvenancePath`、`HardGates`。
   - `AnalogyDirection.score` 改为 `float | None = None`；contextual 模式返回 `null`。
   - `PromptToken` 增加 `full_phrase_zh`、`group_key`、`target_ref`、`operation`、
     `attribute_delta`、`provenance_path`（兼容旧字段，`weight` 可空且不参与排序）。
   - `IntentDraft` 增加 `scope` 字段（主规格 6.3 契约）。
2. **api/directions.py（增量规格 12.2）**
   - 保留 `/api/v1/directions/suggest`；按 `metadata.suggestion_mode == contextual_fragments_v1`
     路由到新服务；`/cross-domain` 保持 deprecated proxy，不加逻辑。
3. **新增 services（增量规格 12.3）**
   - `contextual_divergence.py`：3D Semantic State 组装（asset_id、可信对象名、scope、
     target、operations、locks、证据引用）+ Wikidata grounding + first-hop + 二阶并行 +
     词片解码编排 + 缓存/审计。
   - `contextual_graph_policy.py`：scope/operation → 关系白名单（版本化配置，测试 fixture 锁定）。
   - `fragment_decoder.py`：受约束解码 `display_label_zh/full_phrase_zh` + 硬门
     （`entity_resolved/first_hop_verified/second_hop_verified/target_exists/scope_match/
     operation_compatible/locks_preserved/physically_expressible/phrase_grounded`）+
     同义去重（target+operation+canonical attribute_delta）。
4. **main.py（增量规格 12.3）**
   - `create_direction_suggestions()` 委托新服务；contextual 模式不得再调用
     `_qwen_cross_domain_response()` / `_analogy_prompt_tokens()` 静态兜底。
   - `/api/v1/prompt/compose` 增加冲突检测：互斥词片（如“贴近壶身”+“向外大幅延伸”）
     返回 `needs_resolution`，不静默选一个（增量规格 14）。
5. **WebSocket（主规格 6.6、B5）**
   - `WebSocketMessage` 增加单调 `seq`；重连后前端据此做缺口判断。
   - PATCH draft 时广播 `intent_draft_updated`；对齐事件名
     （如 `cross_domain_directions_updated`）、补 `planner_clarification_requested`、
     `intervention_updated`、`solution_space_updated`、`memory_updated`。

### 3.2 发散推理/知识层（remote_worker）

- 从 `variation_graph_directions.py` 与 `/root/creativeflow_pipeline/scripts/kb_semantic_distance.py`
  抽取共享 adapter：`remote_worker/knowledge_adapters/wikidata.py`、
  `getty_aat.py`、`asknature.py`（增量规格 12.4）。
- 旧结构迁移管线与新 contextual 管线各自保留编排顺序，共用 adapter；
  不重写 `variation_graph_directions.py` 的完整生成链。
- Wikidata grounding 顺序：缓存 QID → label+parent+role 搜索 → instance of/subclass/part of
  消歧 → 硬门拒绝（媒体作品/软件/泛类）后进入 first-hop（增量规格 6）。

### 3.3 IR-RAG 数据与逻辑

- 清理 `intentdatabase/cleaned/design_state_ir_retrieval.jsonl` 的 `text`，
  去掉 `Task group`、software、原始 observed actions 等硬案例身份字段；
  检索向量只由 `design_state/signals/route/scope_hint/recommended_axes` 构成
  （主规格 1.2）。
- IR 只用于判断上下文/栏目（scope、recommended_axes），不再用于词片排序或分数展示。

### 3.4 前端（frontend/src/main.tsx、styles.css）

1. **More Creative 增量呈现（增量规格 13）**
   - 读取服务端 `metadata.question`、`groups`、`contextual_fragments[]`；
     栏目按 scope 动态生成（形状/连接/表面等），不再固定 Aesthetic/Functional/Structural。
   - 移除 `AAT_NOUN_BANK` / `aatNounPromptTokens()` / `scoreLabel` / 分数排序；
     contextual 模式完全禁用静态词库。
   - chip 显示 `display_label_zh`；`buildAnalogyPromptPackage()` 提交
     `full_phrase_zh` + 完整 target/provenance，而不是只有 label/weight。
   - 移除 `visual_inspiration` 默认模式与本地静态方向
     `buildLocalAnalogyDirections()`（主规格 2.2 禁止静态 chip 冒充 AI）。
2. **认知面板（主规格 F3）**
   - 复活证据 drawer：渲染 `evidenceSummaryItems()`（Next axes、IR state、行为证据），
     支持“为什么这样判断”与低置信度措辞（可能/似乎）。
   - 部件级澄清：由 interpretation target 生成“Nose Change? / Scarf Change?”式泡泡。
3. **Intent Composer（主规格 F5）**
   - 修正 Send 语义：存在未保存 behavior 时由 `sendIntentDraft()` 询问后一并发送，
     而不是只保存草稿。
   - 增加 behavior 排序 UI（`moveActionAtom` 接线：上移/下移）。
4. **组件拆分（主规格 F1）**：把单体 `main.tsx` 拆为 Header/Viewport/
   IntelligenceSidebar/IntentComposer 等模块（至少 render 级组件文件化）。
5. **错误态**：`needs_clarification / retrieving / partial_sources /
   no_grounded_fragments / stale_context / needs_resolution` 全部有对应 UI。

### 3.5 测试（增量规格 18）

- 单元：scope/target/operation 推断优先级；Wikidata 消歧拒绝；relation 白名单；
  decoder 完整性；hard gate 任一失败不展示；同义去重不依赖 score；prompt compose 冲突检测。
- 固定场景：水壶把手（形状/连接/表面，拒绝 golden hour/anime/architecture）、
  音箱网罩、雪人整体、灯罩轮廓、壶身局部表面。
- 集成：选中 part → `/directions/suggest` 返回 question/groups/fragments →
  词片带 target 与可打开 provenance → 无 score 且无预选 →
  `/prompt/compose` 收到 `full_phrase_zh` → Generate 走既有 job。

### 3.6 验收标准（全部通过才退出）

- [ ] 增量规格 §19 每条满足（任取已命名对象/部件/表面，问题指向当前目标；
      词片可溯源 Wikidata→first-hop→Getty/AskNature；无证据词片不展示；
      无偏好评分；选择前不生成；既有 `/directions/suggest` 与生成 API 继续工作）。
- [ ] 主规格 §1.2：IR 检索字段纯净，UI 只显示 Next axes + 低调 source case。
- [ ] 主规格 §2.2：静态 chip/本地方向/假候选全部移除。
- [ ] 前端不再显示任何分数，初始无预选词片。
- [ ] 新单元/固定场景/集成测试全绿。

---

## 4. Phase 3：研究版本硬化与 v1 验收（持久化 + 恢复 + 全链证据）

目标：达到主规格 §14 v1 验收标准与增量规格 §17 性能预算，
把“能跑”变成“能作为研究版本交付”。

### 4.1 持久化与恢复（主规格 7、B5）

1. PostgreSQL：session、asset、part、action_atom、intent_draft、intent_episode、
   perception_snapshot、planner_interpretation、planner_intervention、analogy_direction、
   generation_job、candidate、candidate_artifact、candidate_decision、solution_node、case。
2. Redis：WebSocket 在线状态、短期 event buffer、job progress。
3. WebSocket `seq` 缺口恢复：断线重连时前端用 snapshot + solution-space 对齐，
   不依赖遗漏消息（主规格 6.6）。
4. 候选全链反查：candidate → job → direction → intervention → interpretation →
   episode → action atoms（主规格 §7 关系图）做成可导出的 case 报告。

### 4.2 失败与降级（主规格 §10）

- API Gateway 离线 / WS 断开 / VLM 不可用 / graph lookup 失败 / 图像失败 / Hy3D 失败 /
  OSS 失败 / PartField 失败 / fit 失败：按表格实现 UI 行为，全部真实错误，
  不出现 mock 成功。

### 4.3 安全、隐私与研究记录（主规格 §11）

- 同意流程；只存稀疏 snapshot；每条 AI 推断保存模型/提示词版本与置信度；
  用户可查看并纠正 Perception（纠正写为新 evidence，不覆盖原记录）；
  case 匿名导出；日志不落 API key/OSS secret/本地凭证路径。

### 4.4 性能预算（增量规格 §17）

- 已缓存 grounding <100ms；Wikidata first-hop P95 <1.5s；
  Getty/AskNature 二阶并行 P95 <3.5s；解码+硬门 P95 <2s；
  首组 chips 冷启动 <6s；>2s 显示可取消检索状态。

### 4.5 端到端验收（主规格 §14，雪人资产 20 条）

- 真实 GLB/OBJ 加载可旋转缩放；Hover 部件语义；Brush+Annotation+Add 形成 3 条 ActionAtom；
  Compose/Save 保存且不调 Planner；刷新后可恢复/排序/删除/补充；
  Send 才提交 IntentEpisode；Planner 返回 ≥2 个带证据假设；Silhouette Change? 可接受/拒绝；
  拒绝不介入；Cross-domain Diverge 返回 ≥3 个跨领域方向且不直接生成；
  右侧只显示本轮相关维度；选择方向后创建真实 job；图片候选先到、真实 mesh 后到；
  预览不覆盖源对象；接受后 active asset 更新、拒绝项保留；
  case 可反查完整证据链；远端失败显示真实失败；刷新/断线后全状态可恢复。

### 4.6 验收标准（全部通过才算完成）

- [ ] §14 的 20 条 checklist 以真实运行逐条通过并留证据（case 报告 + 日志）。
- [ ] §17 性能预算抽样达标（冷启动与缓存命中各测一组）。
- [ ] 故障注入（worker 停、OSS 断、graph 失败）下 UI 表现符合 §10。
- [ ] 全链 case 反查导出成功；匿名化字段生效。
- [ ] §14.15：Solution Space 先真实图片候选、后真实 mesh 状态（经 Make 3D 或 auto_hy3d）；
      §14.17：接受 mesh 后 active asset 更新、拒绝项保留。
- [ ] 故障注入 Hy3D 失败时：image candidate 保留并标记 `3D failed`，不出现假 mesh
      （主规格 §10）。

---

## 5. 缺口 → 阶段映射表

| 审计缺口 | 修补阶段 |
| --- | --- |
| 链路停止、tunnel 缺失、.env 不一致、vLLM 坏 | Phase 1 |
| Hunyuan3D/Zero123++ 链路未运行、`hy3d_ready` 未验证、auto_hy3d 开关与 Make 3D 衔接 | Phase 1（恢复 smoke）、Phase 3（§14.15 mesh 验收） |
| planner 图片内容被丢弃（多模态融合不足） | Phase 2（后端语义状态）或按部署矩阵启用 Qwen2.5-VL fallback |
| contextual fragment 模型/服务/路由/硬门/无评分 | Phase 2 |
| knowledge_adapters 抽取 | Phase 2 |
| IR retrieval text 清理、IR 不参与排序 | Phase 2 |
| 前端动态 question/groups/词片、去 AAT_NOUN_BANK/分数/静态方向 | Phase 2 |
| 证据 drawer、部件级澄清、behavior 排序、Send 语义、组件拆分 | Phase 2 |
| WS seq、事件名对齐、IntentDraft.scope、prompt compose 冲突检测 | Phase 2 |
| PostgreSQL/Redis、重连恢复、性能预算、隐私/匿名、§14 全链验收 | Phase 3 |

---

## 6. 执行顺序与依赖

```text
Phase 1（基线在线）→ Phase 2（契约 + contextual pipeline + 前端收敛）
                  → Phase 3（持久化 + 硬化 + §14 验收）

Phase 2 内部顺序：
后端 models/契约 → directions 路由 + 三个 service → knowledge_adapters
→ IR 数据清理 → 前端呈现与选择 → prompt compose/生成闭环 → 测试
```

每一阶段结束提交一次状态文档（本文件对应节打勾 + 证据链接），
并把新增 smoke 结果追加到 `FLOWSTUDIO_PROGRESS.md`。
