# FlowStudio 四阶段后端 DeepSeek 开发实施策略 V1

状态：Phase 0–4 已实现并已在双机拓扑真实部署验收（2026-08-04）：planner 在 `connect.weste.seetacloud.com:30320`（Qwen3-8B，transformers FastAPI :18084，隧道映射本机 :18085），主后端/Qwen-Image/worker 在 `connect.westd.seetacloud.com:34333`；teapot/snowman/water gun 三案例全部 Gate → 真实 Qwen 编码 + 真实 Gemini + 真实 Qwen-Image 产物；Hy3D 3D 链验收通过（teapot `run_hy3d=true`，132.8s 产出非空 `mesh.glb` 1.3MB / `mesh.obj` 2.6MB / PNG）。146 passed；3 个失败为环境相关既有问题。OSS/case/website 同步为 CreativeFlow 主线的独立环节，前端状态管理为下一阶段。  
适用仓库：`CHI27-FlowStudio`  
实施形式：由 DeepSeek 作为编码 Agent，在当前代码基础上分阶段修改、测试和交付  
目标运行环境：主后端/Qwen-Image `connect.westd.seetacloud.com:34333`；Qwen3 Planner 应运行在新 GPU 实例本机 `127.0.0.1:18084`（`qwen3.5-27b`，与 `backend/.env` 一致）。旧文档中 `connect.weste.seetacloud.com:30320` 已失效（该主机上无 planner 服务，2026-08-04 实测确认）。
修订：2026-08-04 V1.1 —— 按评审收敛：不引入向量库、Gemini 模型确认为 `gemini-3.5-flash`、持久化精简为三张表、GPU scheduler 为唯一开关、补充双盲审发布约束。

## 0. 必须完整保留的总体定义

以下文字是本轮开发的原始产品定义，实施时不得删减或改写：

> 整个后端分为四个大的模块，
> 第一个是用户意图的encoding，也就是所有用户的输入（视口旋转，文字输入，绘制等等）都是需要planner分开统一编码成为intermediate representation(ir)的，可以写成一个json形式，这个可以让planner也就是qwen3-8b来做。
> 然后第二个大模块是检索，拿用户现在写好的这个ir在我们的先验ir向量库里面匹配找文本匹配度高的，看先验经验的判断结果是什么，这个设计程序自动检索匹配。
> 第三个大模块是re-representation，根据先验和大模型对当下多模态上下文内容的推理，联合让api给出一个合理的判断，返回给前端进行gate询问，这个可以调用api让gemini-3.1-pro来做判断。调用文档提供了，api-key后提供。
> 第四个模块是进行关键词发散，用户点选以后进行多样化的生成，这个就是本地的qwen-image进行。

Gemini API 已知信息：

- Base URL：`https://128api.cn/v1`
- 目标模型：`gemini-3.5-flash`（2026-08-04 确认使用；产品定义原文中的模型名以实际配置为准）
- API key：已由用户提供（2026-08-04），但不写入仓库；仅通过本地 gitignore 的 `.env` 或服务端 secret file 注入
- 调用文档：<https://www.yuque.com/yuqueyonghujlk9m3/ny700k/uhwl59vt8nkcalk4?singleDoc#>
- 文档明确提示接口信息可能变化，因此联调时必须先做模型列表和最小请求探测，不把第三方中转站的可用模型 ID 当作永久常量。

## 1. 实施目标

将当前分散在 `interaction_understanding`、`design_state_ir`、方向发散、Gate 和 generation worker 中的能力，收敛成一条可观测、可回放、可恢复的四阶段状态机：

```text
raw_events
  -> encoding
  -> retrieval
  -> re_representation
  -> awaiting_gate
  -> generation
  -> completed | failed | cancelled
```

实施完成后，一次用户意图 Episode 必须可追踪到：

1. 原始事件与归一化事件。
2. Qwen3-8B 生成的 `IntentIR`。
3. 检索的先验 IR 及其分数。
4. Gemini 生成的 `DecisionIR`。
5. 用户在 Gate 中的选择。
6. 选中方向对应的关键词、prompt、seed 和 Qwen-Image 产物。
7. 可选的 Hunyuan3D、OSS、case library 和网站同步结果。

## 2. 不可破坏的现有基线

DeepSeek 必须以增量改造为原则：

- 保留当前 `/api/v1/interaction/interpret`、Episode、Gate 和 generation API，新 API 稳定前不删除旧路由。
- 保留 `pipeline.py`，结构化传递流程与旧流程并存。
- 保留 `pipeline_transfer_engine.py -> pipeline_hunyuan3d_post.py -> step4_mesh_worker_mv.py` 完整链路。
- 不用通用 `object` 替代具体物体。
- 不为赶进度跳过检索、Gate、真实 Qwen-Image 生成或必要的质量检查。
- 不把 API key、SSH 密码或 Bearer token 写入 Python、TypeScript、Markdown、测试 fixture 或日志。
- 代码可提交到 GitHub，但存在双盲审约束：评审期间不得公开含身份信息的内容；公开发布前必须匿名化（作者、机构、用户名、路径、截图水印等）。具体发布方式（私有仓库/匿名镜像/camera-ready 后公开）由用户决定，实施过程中默认不写入身份信息。

## 3. 目标目录结构

不再将新逻辑堆入 `backend/app/main.py`。以精简为默认，新增以下边界（文件数量按需合并，四个服务边界和四个数据契约是唯一硬边界）：

```text
backend/app/
  api/
    four_stage.py
  models/
    four_stage.py
  services/
    pipeline/
      four_stage_orchestrator.py
    encoding/
      event_normalizer.py
      qwen_intent_encoder.py
    retrieval/
      retriever.py
      # 包装现有 DesignStateIRRetriever（稀疏），不引入向量库
    rerepresentation/
      evidence_assembler.py
      gemini_client.py
    generation/
      generation_spec_builder.py
      gpu_scheduler.py
      # 复用现有 generation_orchestrator.py 和 creativeflow_adapter.py

scripts/
  probe_gemini_api.py
  four_stage_smoke.py

backend/tests/four_stage/
  test_encoding.py
  test_retrieval.py
  test_rerepresentation.py
  test_gate.py
  test_generation.py
  test_end_to_end.py
```

不建向量库、不引入独立数据库、不做工业级基础设施；以“效果好、便于管理”为目标，能复用现有实现就不新建文件。

## 4. 四个阶段的公共数据契约

### 4.1 `IntentIR`

```json
{
  "schema_version": "flowstudio.intent-ir.v1",
  "ir_id": "ir_xxx",
  "run_id": "run_xxx",
  "session_id": "sess_xxx",
  "episode_id": "episode_xxx",
  "source_event_ids": ["evt_1", "evt_2"],
  "target": {
    "asset_id": "asset_xxx",
    "object_type": "teapot",
    "part_id": "lid_knob",
    "region": null
  },
  "observations": {
    "viewport": {},
    "interaction_summary": {},
    "text": "make the lid knob more organic",
    "image_refs": [],
    "model_refs": []
  },
  "intent": {
    "operation": "explore_variations",
    "scope": "part",
    "goal": "organic lid knob",
    "constraints": ["preserve socket", "keep manufacturable"],
    "preferred_axes": ["structural", "aesthetic"]
  },
  "hypotheses": [],
  "confidence": 0.78,
  "ambiguity": 0.22,
  "provenance": {
    "encoder": "qwen3-8b",
    "encoder_version": "qwen3-planner",
    "prompt_version": "intent-ir-v1"
  },
  "created_at": "ISO-8601"
}
```

### 4.2 `RetrievalBundle`

```json
{
  "schema_version": "flowstudio.retrieval.v1",
  "retrieval_id": "ret_xxx",
  "run_id": "run_xxx",
  "query_ir_id": "ir_xxx",
  "data_version": "design-state-ir-2026-08-v1",
  "retriever": "design-state-ir-sparse-v1",
  "matches": [
    {
      "prior_ir_id": "prior_xxx",
      "case_id": "case_xxx",
      "sparse_score": 0.63,
      "metadata_score": 1.0,
      "outcome_score": 0.0,
      "final_score": 0.79,
      "prior_judgement": {},
      "evidence": [],
      "outcome": {"accepted": true}
    }
  ],
  "abstained": false,
  "abstain_reason": null
}
```

### 4.3 `DecisionIR`

```json
{
  "schema_version": "flowstudio.decision-ir.v1",
  "decision_id": "decision_xxx",
  "run_id": "run_xxx",
  "intent_ir_id": "ir_xxx",
  "retrieval_id": "ret_xxx",
  "summary": "The user is exploring a part-level structural change.",
  "recommended_scope": "part",
  "options": [
    {
      "option_id": "opt_1",
      "label": "Organic gourd-like knob",
      "rationale": "...",
      "confidence": 0.79,
      "evidence_refs": ["prior_xxx", "image_ref_xxx"],
      "constraints": ["preserve socket"],
      "divergence_seeds": ["gourd shoulder", "soft taper", "celadon restraint"]
    }
  ],
  "needs_clarification": false,
  "clarification_question": null,
  "confidence": 0.79,
  "model": "gemini-3.5-flash",
  "prompt_version": "re-representation-v1"
}
```

### 4.4 `GenerationSpec`

```json
{
  "schema_version": "flowstudio.generation-spec.v1",
  "generation_id": "gen_xxx",
  "run_id": "run_xxx",
  "decision_id": "decision_xxx",
  "selected_option_id": "opt_1",
  "asset_id": "asset_xxx",
  "object_type": "teapot",
  "target": {"scope": "part", "part_id": "lid_knob"},
  "keywords": [],
  "prompt_candidates": [],
  "preserved_constraints": [],
  "candidate_count": 4,
  "model": "Qwen-Image-2512",
  "seeds": [42, 143, 244, 345],
  "run_hy3d": false
}
```

## 5. Phase 0：契约和状态机先行

本阶段不换模型，不动生成链，先建立四阶段的稳定边界。

### DeepSeek 任务

1. 在 `backend/app/models/four_stage.py` 建立上述四个 Pydantic model。
2. 新增 `FourStageRun`，保存当前 stage、各阶段 ID、error、时间戳和重试次数。
3. 建立 `FourStageOrchestrator`，本阶段只实现状态转移和 fake adapter。
4. 在新 router 中增加：
   - `POST /api/v1/four-stage/runs`
   - `GET /api/v1/four-stage/runs/{run_id}`
   - `POST /api/v1/four-stage/runs/{run_id}/retry`
   - `POST /api/v1/four-stage/runs/{run_id}/cancel`
5. 现有 `/api/v1/interaction/interpret` 不变，通过 adapter 进入新 EncodingService。
6. 所有阶段输出只能由 Pydantic model 持久化，不允许将未校验 dict 直接传到下一阶段。

### 退出标准

- 非法状态跳转被拒绝。
- 同一 `idempotency_key` 不会建立两个 run。
- 每个阶段均有 started/completed/failed 时间戳。
- 新老 API 回归测试均通过。

## 6. Phase 1：Encoding 完善

### 6.1 复用的现有能力

- `services/intent/interaction_features.py`：事件特征归一化。
- `services/intent/interaction_understanding.py`：规则、IR prior 和 predictor 串联。
- `services/intent/multimodal_intent_predictor.py`：OpenAI-compatible Qwen3 HTTP 边界。
- `ActionAtom`、`IntentDraft`、`IntentEpisode`：用户多种输入容器。

### 6.2 DeepSeek 任务

1. 实现 `EventNormalizer`：
   - 保留视口旋转、停留、选择、绘制、brush、drag、smooth、add、text、image/model ref。
   - 高频 viewport 事件按 300–500ms 窗口聚合，不将每一帧发给 Qwen3。
   - 绘制保留 artifact URL、bbox、投影和统计摘要，不直接嵌入无上限坐标/base64。
2. 实现 `QwenIntentEncoder`：
   - 输入为 normalized event bundle 和有界的 session context。
   - system prompt 明确要求只返回 `IntentIR` JSON。
   - `temperature=0`或极低值，以编码稳定性为主。
   - 输出必须通过 `IntentIR.model_validate` 。
3. 实现 JSON 修复路径：
   - 第一次解析失败，仅将 validation errors 发回模型修复一次。
   - 第二次失败即进入 `encoding_failed`，不伪造 IR。
4. 为 Qwen3 调用加入：
   - request body 大小限制。
   - tokenizer/context 长度限制。
   - 单机 semaphore。
   - timeout、有界重试和 OOM 降级。
   - 不记录原始图片/base64。
5. 将规则 predictor 保留为 prior/fallback，但要在 `provenance` 中区分 Qwen 输出和 rule fallback。
6. 修正当前测试环境泄漏：测试不得隐式读取开发机 `.env` 中的 VLM endpoint。

### 6.3 必测样例

- 仅旋转视口：输出 observation，不得确定为生成意图。
- 旋转 + 局部停留 + 绘制：能定位 part/region。
- 文字 + brush mask：正确编码 operation、scope 和 constraints。
- 拖拽向量：保留坐标系、方向和 influence radius。
- 中文、英文与中英混合文本。
- 超大坐标数组、超大 base64 和恶意 JSON。

### 6.4 退出标准

- 固定 fixture 的 `IntentIR` schema 通过率 100%。
- 连续运行 100 次无非法 JSON。
- 输入超限返回可理解的 4xx，不得将 GPU 打 OOM。
- 规则 fallback 被清晰标记，不得伪装成 Qwen 结果。

## 7. Phase 2：Retrieval 完善

### 7.1 复用的现有能力

- `intentdatabase/cleaned/design_state_ir_retrieval.jsonl`：207 条已清洗先验。
- `DesignStateIRRetriever`：信号、词项、scope 和稀疏 cosine 评分。
- `recommend_target` 与 `recommend_axes`：已有先验聚合边界。

### 7.2 DeepSeek 任务

1. 保留现有稀疏检索（`DesignStateIRRetriever` 的稀疏 cosine 评分）作为唯一检索通道。**不引入向量库、不引入 dense/embedding 通道、不做 repository/引擎抽象**；207 条先验的稀疏检索已经足够快，速度不是瓶颈。
2. 实现最终打分：

```text
final_score = w_sparse * sparse_score
            + w_metadata * metadata_score
            + w_feedback * outcome_score
```

   初始权重可作为配置，不得作为未经评测的研究结论。
3. metadata filter 至少包括：`object_type`、`scope`、`target_level`、`operation`、`design_state`、`language`。
4. 先取 top-20，再 rerank 得到 top-5；数据量较小时可用确定性 reranker，不强制再增加一个 LLM。
5. 增加 abstain：最高分不足或 top-1/top-2 过于接近时，输出“无可靠先验”，不强行引用案例。
6. 将 Gate 结果、最终 accept/reject/undo 写入轻量 feedback store（与四阶段共用 SQLite），但不立即改写原始 207 条数据。
7. 检索数据（207 条 JSONL）为 source of truth，缺失或版本变化时明确失败，不静默降级。

### 7.3 离线评测

建立至少 30 条 query fixture，标注：

- 期望 scope/target level。
- 可接受 case ID 集合。
- 不应匹配的 negative cases。
- 是否应 abstain。

报告 Recall@5、MRR、scope accuracy、abstain precision，不只测“有没有返回结果”。

### 7.4 退出标准

- 相同输入在相同数据版本下返回可重现结果。
- 每个 match 包含分项分数（sparse/metadata/outcome）、最终分数、case ID 和可审计证据。
- 检索数据缺失或版本不匹配时明确失败，不静默返回空结果或伪向量。
- 检索评测报告纳入仓库。

## 8. Phase 3：Re-representation 与 Gemini Gate 完善

### 8.1 配置

在 `.env.example` 中新增，但不写真实 key：

```dotenv
GEMINI_REREPRESENTATION_ENABLED=false
GEMINI_API_BASE=https://128api.cn/v1
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash
GEMINI_TIMEOUT_SEC=60
GEMINI_MAX_RETRIES=2
GEMINI_MAX_IMAGES=4
GEMINI_MAX_IMAGE_BYTES=5242880
```

`GEMINI_API_KEY` 只能通过环境变量或服务端 secret file 注入。

### 8.2 联调前置

拿到 key 后，先运行 `scripts/probe_gemini_api.py`：

1. `GET {base_url}/models`，保存脱敏后的可用模型 ID。
2. 发送一次纯文本最小 `chat/completions` 请求。
3. 发送一次小图多模态请求。
4. 验证是否支持 `response_format/json_schema`。
5. 验证 timeout、429、5xx 和空回处理。
6. 探测输出不得包含 API key、Authorization header 或完整用户图片。

如果 `/models` 中的真实 ID 与 `gemini-3.5-flash` 不同，只修改运行时 `GEMINI_MODEL`，不改业务逻辑。

### 8.3 `EvidenceAssembler`

发送给 Gemini 的证据必须有界、可审计：

- 完整 `IntentIR`。
- top-5 `RetrievalBundle.matches`，不发整库。
- 当前 viewport 最多 1 张。
- annotation/mask/reference image 合计最多 3 张。
- 对应的 asset/part 语义、用户硬约束和近期 Gate 反馈。
- 所有图片要么是有效的 signed URL，要么是受限的 data URL；不向第三方发送本地私有路径。

先验检索文本必须包裹为“不可信的证据数据”，不得与 system prompt 拼接在同一指令层。

### 8.4 `GeminiClient`

- 对上层暴露 `decide(evidence) -> DecisionIR`，不泄漏第三方 response shape。
- 优先使用服务支持的 JSON schema response。
- 如果不支持，则使用 JSON-only prompt + 本地 parse/validate + 最多一次修复。
- 只重试 429、502、503、504 和网络超时；不对 schema 错误无限重试。
- 记录 request ID、latency、model ID、token usage 和错误类型，不记录 key。
- 纯读的相同 evidence hash 可使用短期 cache，Gate 修改后必须失效。

### 8.5 Gate 扩展

复用当前 `POST /api/v1/interpretations/{id}/decision`，但新增方向级 Gate：

```text
POST /api/v1/four-stage/decisions/{decision_id}/gate
```

请求支持：

```json
{
  "action": "accept_option | reject_all | request_revision | clarify",
  "selected_option_id": "opt_1",
  "user_revision": null,
  "reason": null
}
```

规则：

- Gate 之前不得调用 Qwen-Image。
- `accept_option` 必须指定有效 option ID。
- `request_revision` 生成新 `DecisionIR` revision，不覆盖历史。
- `reject_all` 记入 retrieval feedback，但不自动把先验数据删除。
- Gate 选择后再创建 `GenerationSpec`。

### 8.6 失败策略

- Gemini 不可用：返回 `rerepresentation_unavailable`，前端可选择稍后重试或显式使用本地 Qwen fallback。
- 本地 fallback 必须在 UI 和 provenance 中标记，不得显示为 Gemini 判断。
- 如果模型置信度低或证据冲突，应生成澄清问题，而不是自动选方向。

### 8.7 退出标准

- Gemini 纯文本和多模态 smoke 都成功。
- Gemini 输出 100% 通过 `DecisionIR` 校验或明确失败。
- Gate 前 Qwen-Image 调用数为 0。
- accept/reject/revise/clarify 四条路径均有 API 和 WebSocket 回归测试。
- API key 不出现在 Git diff、log、exception body 或前端 bundle。

## 9. Phase 4：关键词发散与 Qwen-Image 生成完善

### 9.1 复用的现有能力

- `contextual_divergence.py`、Wikidata/Getty/AskNature 检索和 planner enrichment。
- `GenerationOrchestrator` 异步 job API。
- `remote_worker/app.py` 的 staged image generation。
- Qwen-Image-2512、Qwen-Image-Edit-2511 和 masked/conditioned endpoint。
- 当前图片 QA、多次 seed 尝试和 pairwise diversity。
- 可选 Hunyuan3D 后处理、OSS 和 case library 链路。

### 9.2 职责边界

第四阶段拥有“关键词发散 + 生成”整体业务边界，但内部分工为：

- 发散器：将用户选中的 `DecisionIR.option` 扩展成带约束的多个 prompt candidates。
- Qwen-Image：只负责按选定语义生成图像，不得擅自改变用户在 Gate 中选定的设计方向。

### 9.3 DeepSeek 任务

1. 实现 `GenerationSpecBuilder`：
   - 必须同时接收 `DecisionIR`、`selected_option_id` 和原始 asset context。
   - 将选中 option 的 constraints 写入每一个 prompt，不只放在顶层 metadata。
   - 保存“发散了什么”和“必须保留什么”两类字段。
2. 四个候选必须沿不同轴变化，例如 silhouette/material/structure/ornament，而不是只替换形容词。
3. 设置可重现 seed，保存 model revision、steps、size、prompt、negative prompt 和 input asset hash。
4. 将 worker 的 job 存储补一层可恢复的轻量恢复层：
   - 最低可用 SQLite job table + lease（与四阶段状态共用同一 SQLite 文件，不引入独立数据库）。
   - 以追加式恢复层实现，不整体替换现有内存 job store 的旧路径。
   - API 进程重启后要能恢复 queued/running job，无 lease 的 running job 可重新入队。
5. 新增全局 GPU scheduler：
   - Qwen-Image 同时只运行 1 个生成 job。
   - Hunyuan3D 与 Qwen-Image 默认不同时常驻/运行。
   - model phase switch 也必须在同一把锁内执行。
   - GPU scheduler 是 model phase switch 的**唯一开关**；UI 面板的显式启动降级为运维覆盖（operator override），不得在运行时与 scheduler 并行抢锁。
   - cancel 时终止后续候选，不删除已完成的产物。
6. 增加质量 Gate：
   - 单图与选中意图一致性。
   - 必须保留约束。
   - 候选之间多样性。
   - 局部任务的非目标区保持度。
7. 只有通过质量 Gate 的图像才返回前端。全部失败时返回可重试失败，不返回伪占位图。

### 9.4 与完整 CreativeFlow 主线的关系

当 `run_hy3d=true` 或属于需要 3D 资产的 case 时，不能停在图片生成，必须继续：

```text
concrete request JSON
  -> pipeline_transfer_engine.py
  -> non-empty retained_rationales/generated_targets
  -> pipeline_hunyuan3d_post.py
  -> step4_mesh_worker_mv.py
  -> multiview + mesh.glb + mesh.obj
  -> OSS
  -> case.json + report HTML + index
  -> website sync
```

不允许为了四阶段 API 看起来成功而跳过上述用户已请求的 3D 链路。

### 9.5 退出标准

- 未 Gate 选中的 option 无法创建 generation job。
- 同一 `GenerationSpec` 可重现相同 seed 的运行参数。
- 并发提交两个 Qwen-Image job 时实际 GPU 生成串行。
- worker/backend 重启后 queued job 可恢复。
- 每个候选都能追踪到 decision/option/prompt/seed/model version。
- 完整 3D case 能产生非空 mesh，并完成指定的 OSS/case/website 链路。

## 10. Canonical API 和前端交互

### 10.1 后端 API

```text
POST /api/v1/four-stage/runs
GET  /api/v1/four-stage/runs/{run_id}
GET  /api/v1/four-stage/runs/{run_id}/intent-ir
GET  /api/v1/four-stage/runs/{run_id}/retrieval
GET  /api/v1/four-stage/runs/{run_id}/decision
POST /api/v1/four-stage/decisions/{decision_id}/gate
POST /api/v1/four-stage/runs/{run_id}/generation
POST /api/v1/four-stage/runs/{run_id}/retry
POST /api/v1/four-stage/runs/{run_id}/cancel
```

### 10.2 WebSocket 事件

```text
four_stage.encoding_started
four_stage.encoding_completed
four_stage.retrieval_completed
four_stage.decision_completed
four_stage.awaiting_gate
four_stage.gate_resolved
four_stage.generation_queued
four_stage.generation_progress
four_stage.completed
four_stage.failed
```

事件必须包含 `run_id`、`session_id`、`stage`、`occurred_at`、`schema_version`，不得将整张 base64 图片通过 WebSocket 广播。

### 10.3 前端 Gate

前端展示：

- Gemini summary。
- 2–4 个 options。
- 每个 option 的 rationale、confidence 和简化证据。
- Accept、Revise、Reject all、Clarify。
- 当使用本地 fallback 时显示明确标识。

前端不能自己拼装生成 prompt；必须将 option ID 返回后端，由后端建立 `GenerationSpec`。

## 11. 持久化与可观测性

### 11.1 最小持久化表

- `four_stage_runs`：主表，含 run_id、session_id、idempotency_key、当前 stage、各阶段输出（`IntentIR`/`RetrievalBundle`/`DecisionIR`/Gate 选择/`GenerationSpec` 以 Pydantic 序列化后的 JSON 列保存）、error、重试次数和时间戳。
- `generation_jobs`：SQLite job 表 + lease，重启后恢复 queued/running job（无 lease 的 running job 重新入队）。
- `model_call_audits`：模型调用审计（模型 ID、latency、token usage、错误类型），驱动指标，不含 key。

三张表都保存 `schema_version`、created/updated timestamps 和 provenance。不引入迁移框架；Phase 0 先建 `four_stage_runs` 即可，其余按 checkpoint 递增。

### 11.2 指标

- Encoding latency / JSON repair rate / Qwen fallback rate。
- Retrieval top score / abstain rate / 数据版本。
- Gemini latency / token usage / retry rate / invalid JSON rate。
- Gate accept/revise/reject rate。
- Qwen-Image queue wait / generation latency / QA pass rate。
- Hy3D success rate / non-empty mesh count。

## 12. 分阶段交付方式

DeepSeek 不得一次性修改四个阶段后再统一测试。必须按以下顺序交付：

1. **PR/Checkpoint 0：契约与状态机**
2. **PR/Checkpoint 1：Encoding**
3. **PR/Checkpoint 2：Retrieval**
4. **PR/Checkpoint 3：Gemini Re-representation + Gate**
5. **PR/Checkpoint 4：Generation 队列与 GPU 调度**
6. **PR/Checkpoint 5：真实端到端验收**

每个 checkpoint 要提供：

- 修改文件。
- API/schema 变化。
- 新增测试。
- 全量回归结果。
- 已知限制。
- 回滚方式。
- 本 checkpoint 的真实 smoke 证据。

## 13. 端到端验收用例

至少选三个具体物体，不能用 `object`：

1. `teapot`：文字 + lid knob 局部选择。
2. `snowman`：视口观察 + carrot nose 绘制/批注。
3. `water gun`：brush mask + grip 材料/结构发散。

每个 case 必须证明：

- `IntentIR` 非空且 schema 有效。
- Retrieval 有可审计 top-k 或正确 abstain。
- Gemini 返回有效 `DecisionIR`。
- 前端 Gate 能选中指定 option。
- Qwen-Image 只在 Gate 后运行。
- 多个候选方向有明显多样性且保留硬约束。
- 需要 3D 时生成非空 `mesh.glb` 和 `mesh.obj`。
- 输出能追溯回 event -> IR -> retrieval -> decision -> option -> generation。

## 14. DeepSeek 启动 Prompt

以下内容可直接交给 DeepSeek：

```text
你要在现有 CHI27-FlowStudio 仓库中实施
docs/FLOWSTUDIO_FOUR_STAGE_DEEPSEEK_IMPLEMENTATION_STRATEGY_V1_ZH.md。

先完整阅读该策略以及：
- docs/FLOWSTUDIO_BACKEND_CONVERGENCE_STRATEGY_V1_ZH.md
- docs/FLOWSTUDIO_MODULE_DATAFLOW_V1_ZH.md
- docs/FLOWSTUDIO_REMEDIATION_PLAN_3PHASE_V1_ZH.md
- backend/app/services/intent/
- backend/app/services/divergence/
- backend/app/services/generation/
- remote_worker/app.py

只实施当前 checkpoint，不跨 checkpoint 大规模重构。
不删除旧 API、pipeline.py 或完整 CreativeFlow/Hunyuan3D 主线。
不写入任何 API key 或 SSH 密码。
开始修改前先报告当前代码映射和预计修改文件。
修改后运行新增测试与全量 backend 回归。
如果发现策略与真实代码冲突，先提供证据和最小修正建议，不要自行缩减四阶段目标。
```

## 15. 建议的实施优先级

```text
P0  四个 schema + run 状态机 + 密钥边界
P0  Qwen Encoding 输入限制、JSON 校验、并发保护
P0  Gemini adapter + DecisionIR + Gate-before-generation
P1  稀疏检索 + metadata 过滤 + abstain + 反馈记录
P1  持久 job queue + GPU 串行调度 + 重启恢复
P1  端到端三个具体 case
P2  检索权重调优、成本 cache、研究指标仪表盘
```

实施上不建议先单独“把 Gemini 调通”或“先搭建检索基建”。第一个交付物应是四个稳定 schema 和端到端状态机，否则各模型的输出仍会继续通过无约束 dict 相互传递。
