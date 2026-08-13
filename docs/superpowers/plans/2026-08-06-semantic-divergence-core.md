# FlowStudio Semantic Divergence Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Gate 接受后，以 Gemini 为主、本地 Qwen2.5-VL 为模型 fallback，并按 `scope × temperature × intent` 动态使用 Wikidata/Getty AAT/AskNature，稳定输出 9–15 个可追溯的短语义关键词，供用户选择并生成 6–8 个 Solution。

**Architecture:** 保留常驻 Observation、IntentRevision、多 Gate 和四阶段状态机；将关键词生成从 `DecisionIR.divergence_seeds` 中拆出为独立 Semantic Divergence 服务。服务端组装可信上下文、路由知识源、调用主备模型并统一强校验；前端只提交参数和候选 ID，只显示短标签，生成阶段使用服务端保存的完整 prompt phrase。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLite、pytest、OpenAI-compatible Gemini/Qwen HTTP API、Wikidata API/WDQS、Getty AAT、AskNature、React 19、TypeScript、Vite、Node test runner。

## Global Constraints

- 本阶段不进行 GitHub 提交、推送或部署。
- Qwen2.5-VL 继续承担常驻 Observation 编码；Gemini Planner 只负责 target、scope 和一句 Gate 问句。
- Gate 接受前不得启动 Semantic Divergence；Gate 拒绝后不得发散。
- Gemini 是语义发散主模型；GPU 本地 Qwen2.5-VL 使用相同 schema 作为模型 fallback。
- Wikidata、Getty AAT、AskNature 是条件启用、允许降级的知识增强层，不能成为交互的强阻塞依赖。
- 前端显示中文 2–8 字或英文 1–4 词的短标签；后台保留完整 target、operation、semantic anchor、prompt phrase、scores 和 provenance。
- `Aesthetic / Structural / Functional / Cross-domain` 只能作为类别，禁止作为用户可选关键词。
- 正常返回必须包含 9–15 个合格候选；用户选择后生成 6–8 个 Solution。
- 多 Gate 可以并存；Observation 在发散期间继续记录，新行为进入下一个 intent 窗口。
- 新 intent 的结果追加到对应版本，继承已接受关键词但不重复。
- 双模型失败时显示真实错误并保留继承词，禁止用固定泛词补齐。

## File Map

**Create**

- `backend/app/models/semantic_divergence.py`：请求参数、知识路由、候选、校验报告和响应 schema。
- `backend/app/services/divergence/semantic_knowledge_router.py`：纯路由决策与现有知识适配器的条件调用。
- `backend/app/services/divergence/semantic_model_clients.py`：Gemini 主生成器和 Qwen2.5-VL fallback，共用结构化 Prompt 契约。
- `backend/app/services/divergence/semantic_validator.py`：禁词、长度、scope、identity、阈值、去重和集合配额。
- `backend/app/services/divergence/semantic_divergence_service.py`：主备调用、知识降级、一次 repair、幂等和审计编排。
- `backend/tests/test_semantic_divergence_models.py`：schema 和参数边界测试。
- `backend/tests/test_semantic_knowledge_router.py`：知识路由与局部降级测试。
- `backend/tests/test_semantic_divergence_service.py`：主备模型、质量 fallback、幂等和强校验测试。
- `frontend/tests/semanticDivergence.test.ts`：前端请求入链、分组、禁用旧 seeds 和 settled-slider 测试。

**Modify**

- `backend/app/models/__init__.py`：导出新 schema。
- `backend/app/models/four_stage.py`：在 run 和 selection 中保存语义发散结果与候选 ID。
- `backend/app/models/realtime_observation.py`：Gate 请求携带发散参数；revision 暴露发散状态。
- `backend/app/config.py`：Semantic Divergence 启用、超时、候选数和知识路由配置。
- `backend/app/services/storage/four_stage_store.py`：持久化 `semantic_divergence` JSON。
- `backend/app/services/pipeline/four_stage_orchestrator.py`：Gate 后调用服务、刷新参数、校验选中候选。
- `backend/app/services/intent/realtime_observation.py`：canonical revision Gate、继承词和多 intent 同步。
- `backend/app/api/four_stage.py`：Gate 参数和语义发散刷新端点。
- `backend/app/api/realtime_observation.py`：revision Gate 参数契约。
- `backend/app/main.py`：组装知识路由、主备模型、validator 和 service。
- `backend/app/services/generation/four_stage_spec_builder.py`：使用保存的完整 prompt phrase，不再退回 Decision seeds。
- `backend/tests/test_four_stage.py`：直接四阶段 API 契约。
- `backend/tests/test_four_stage_rerepresentation.py`：Planner 与 Semantic Divergence 解耦。
- `backend/tests/test_realtime_observation.py`：revision Gate、继承和并发 intent。
- `backend/tests/test_four_stage_generation.py`：候选 ID 到生成 Prompt 的可信解析。
- `frontend/src/types.ts`：新响应、候选、状态和 selection 类型。
- `frontend/src/state/studioStore.ts`：Gate 后取词、slider settle 刷新、候选选择和继承。
- `frontend/src/components/panels/AIBehaviorPanel.tsx`：四组短词、加载/降级状态和参数提交。
- `frontend/src/main.tsx`：传入参数提交 callback 与发散状态。

---

### Task 1: 定义 Semantic Divergence schema 与持久化边界

**Files:**

- Create: `backend/app/models/semantic_divergence.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/four_stage.py`
- Modify: `backend/app/models/realtime_observation.py`
- Modify: `backend/app/services/storage/four_stage_store.py`
- Test: `backend/tests/test_semantic_divergence_models.py`

**Interfaces:**

- Produces: `SemanticDivergenceParams`, `SemanticDivergenceRequest`, `KnowledgeRoute`, `KnowledgeEvidence`, `SemanticCandidate`, `SemanticDivergenceResponse`。
- Produces: `FourStageRun.semantic_divergence: SemanticDivergenceResponse | None`。
- Produces: `DivergenceSelection.selected_candidate_ids` 和 `resolved_prompt_phrases`。
- Consumed by: Tasks 2–8。

- [ ] **Step 1: 写参数边界、短标签和序列化失败测试**

```python
import pytest
from pydantic import ValidationError

from app.models import (
    SemanticCandidate,
    SemanticDivergenceParams,
    SemanticDivergenceResponse,
)


def test_semantic_divergence_params_are_bounded() -> None:
    params = SemanticDivergenceParams(temperature=0.6, strictness=0.8)
    assert params.candidate_count == 13
    with pytest.raises(ValidationError):
        SemanticDivergenceParams(temperature=1.1, strictness=0.8)


def test_candidate_keeps_short_label_and_full_prompt_separate() -> None:
    candidate = SemanticCandidate(
        candidate_id="kw_1",
        display_label_zh="熔岩流线",
        label_en="lava flow lines",
        group="semantic_transfer",
        target_ref={"asset_id": "asset_1", "type": "part", "id": "support"},
        operation="deform",
        semantic_anchor="cooling lava",
        prompt_phrase="reshape only the support with solidified lava-flow contours",
        attribute_delta={"attribute": "contour", "change": "solidified flow ridges"},
        scores={"identity": 0.9, "scope": 0.9, "relevance": 0.9, "specificity": 0.9, "novelty": 0.8},
        provenance={"generator": "gemini", "mode": "model_only"},
    )
    assert candidate.display_label_zh == "熔岩流线"
    assert "support" in candidate.prompt_phrase
```

- [ ] **Step 2: 运行测试并确认 schema 尚不存在**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_models.py`

Expected: collection fails because the new models are not exported.

- [ ] **Step 3: 实现明确的 Pydantic 类型**

`SemanticDivergenceParams` 使用以下唯一映射，不在其他文件重复计算：

```python
class SemanticDivergenceParams(BaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    strictness: float = Field(default=0.6, ge=0.0, le=1.0)
    candidate_count: int | None = Field(default=None, ge=9, le=15)
    inherited_keywords: list[str] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def derive_candidate_count(self) -> "SemanticDivergenceParams":
        if self.candidate_count is None:
            self.candidate_count = max(9, min(15, round(9 + 6 * self.temperature)))
        return self

    @property
    def model_temperature(self) -> float:
        return round(0.15 + 0.75 * self.temperature, 3)

    @property
    def thresholds(self) -> dict[str, float]:
        return {
            "identity": 0.55 + 0.35 * self.strictness,
            "scope": 0.55 + 0.40 * self.strictness,
            "relevance": 0.45 + 0.40 * self.strictness,
        }
```

`SemanticCandidate.group` 只允许 `shape | connection | surface | semantic_transfer`。`SemanticDivergenceResponse.status` 只允许 `completed | failed`，并包含 `request_key`、`fallback_used`、`fallback_reason`、`knowledge_route`、`validation_counts`、`latency_ms` 和 `candidates`。

- [ ] **Step 4: 把响应挂到 run，并扩展 selection**

```python
class DivergenceSelection(BaseModel):
    scope: str = "whole"
    target_part_id: str | None = None
    selected_candidate_ids: list[str] = Field(default_factory=list, max_length=12)
    selected_keywords: list[str] = Field(default_factory=list, max_length=12)
    resolved_prompt_phrases: list[str] = Field(default_factory=list, max_length=12)
    user_text: str | None = None
    dimensions: dict[str, list[str]] = Field(default_factory=dict)
    system_keywords: list[str] = Field(default_factory=list, max_length=12)
```

给 `FourStageRun` 增加 `semantic_divergence`，给 `RevisionGateRequest` 增加 `divergence_params: SemanticDivergenceParams | None`。IntentRevision 只增加 `semantic_divergence_status` 和 `semantic_divergence_error`，避免复制候选正文。

- [ ] **Step 5: 增加 SQLite JSON 列并完成旧库兼容**

在建表、兼容 `ALTER TABLE`、`save_run()` 和 `_row_to_run()` 四处加入 `semantic_divergence`。旧行的 `NULL` 必须反序列化为 `None`。

- [ ] **Step 6: 运行模型与存储回归**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_models.py backend/tests/test_four_stage.py`

Expected: all tests pass; an existing in-memory run round-trips with and without `semantic_divergence`.

- [ ] **Step 7: Reviewer checkpoint**

检查 schema 名称、字段类型和默认值与批准设计一致；不进行 Git 操作。

---

### Task 2: 实现按 scope、temperature 和 intent 的知识路由

**Files:**

- Create: `backend/app/services/divergence/semantic_knowledge_router.py`
- Modify: `backend/app/services/divergence/knowledge_adapters.py`
- Test: `backend/tests/test_semantic_knowledge_router.py`

**Interfaces:**

- Consumes: `SemanticDivergenceRequest`。
- Produces: `SemanticKnowledgeRouter.choose_route(request) -> KnowledgeRoute`。
- Produces: `SemanticKnowledgeRouter.collect(request, route) -> KnowledgeEvidence`。
- Reuses: `ground_wikidata`, `wikidata_first_hop`, `second_hop_parallel`。

- [ ] **Step 1: 写四条纯路由测试**

```python
def test_low_temperature_part_refinement_is_model_only(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="part", temperature=0.2, intent="帽檐稍微外卷"))
    assert route.mode == "model_only"
    assert route.use_wikidata is False


def test_material_intent_routes_to_getty(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="material_region", temperature=0.5, intent="探索皮包材质"))
    assert route.use_wikidata is True
    assert route.use_getty_aat is True
    assert route.use_asknature is False


def test_biomimetic_intent_routes_to_asknature(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="part", temperature=0.6, intent="仿生承重连接"))
    assert route.use_asknature is True


def test_high_temperature_cross_domain_uses_both_second_hops(router, request_factory) -> None:
    route = router.choose_route(request_factory(scope="whole", temperature=0.9, intent="跨域结构迁移"))
    assert route.use_getty_aat is True
    assert route.use_asknature is True
```

- [ ] **Step 2: 运行测试并确认路由类不存在**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_knowledge_router.py`

Expected: import failure for `SemanticKnowledgeRouter`.

- [ ] **Step 3: 实现纯函数路由表**

路由顺序必须固定：

```text
temperature >= 0.7 或明确跨域意图 → Wikidata + Getty + AskNature
material_region 或材质/纹理/工艺意图 → Wikidata + Getty
功能/仿生/机制意图 → Wikidata + AskNature，可附加 Getty
temperature <= 0.3 且无 material/biomimetic/cross-domain intent → model_only
其余 → Wikidata + Getty
```

语义判断集中在 `intent_flags(text, operation_hint)`，返回 `material`、`mechanism`、`cross_domain` 三个布尔值。不得在 API、前端或 Validator 中复制关键字表。

- [ ] **Step 4: 包装现有知识适配器并允许 partial failure**

`collect()` 必须：

1. 优先使用 `semantic_target.wikidata_qid`；
2. 否则以 `label_en + object_identity + semantic_role` grounding；
3. grounding 成功后执行 first-hop；
4. 只对 first-hop donor 执行 Getty/AskNature 二阶检索；
5. 将每个异常写入 `errors`，返回已有证据而不是抛出整次失败。

- [ ] **Step 5: 写降级测试并验证 Getty/AskNature 不会绕开 first-hop**

用 monkeypatch 令 Getty 抛 `RuntimeError("getty unavailable")`，断言 `evidence.partial_sources == ["getty_aat"]` 且 AskNature 证据仍在。令 grounding 返回 `None`，断言 mode 变为 `model_only` 且 errors 包含 `wikidata_grounding_failed`。

- [ ] **Step 6: 运行知识链现有与新增测试**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_knowledge_router.py backend/tests/test_contextual_divergence.py`

Expected: all pass;旧 contextual pipeline 行为不变。

- [ ] **Step 7: Reviewer checkpoint**

确认知识源只提供 donor evidence，没有任何 AAT preferred term 或 AskNature 标题直接成为显示词。

---

### Task 3: 实现 Gemini 主生成器与本地 VLM fallback 客户端

**Files:**

- Create: `backend/app/services/divergence/semantic_model_clients.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_semantic_divergence_service.py`

**Interfaces:**

- Consumes: `SemanticDivergenceRequest`, `KnowledgeEvidence`。
- Produces: `GeminiSemanticGenerator.generate(request, evidence) -> list[SemanticCandidate]`。
- Produces: `LocalVlmSemanticGenerator.generate(request, evidence) -> list[SemanticCandidate]`。
- Raises: `SemanticModelUnavailable`, `SemanticModelOutputError`。

- [ ] **Step 1: 写共享 schema、温度传递和 provider 测试**

```python
def test_gemini_payload_uses_mapped_temperature(gemini_generator, request, evidence) -> None:
    payload = gemini_generator.build_payload(request, evidence)
    assert payload["temperature"] == request.params.model_temperature
    assert "2–8个字" in payload["messages"][0]["content"]
    assert "Aesthetic" in payload["messages"][0]["content"]


def test_local_vlm_uses_same_response_schema(local_generator, request, evidence, monkeypatch) -> None:
    monkeypatch.setattr(local_generator, "_post_json", lambda payload: VALID_SEMANTIC_RESPONSE)
    result = local_generator.generate_sync(request, evidence)
    assert result[0].candidate_id == "kw_1"
    assert result[0].provenance.generator == "qwen2.5-vl"
```

- [ ] **Step 2: 运行测试并确认客户端尚不存在**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_service.py -k 'payload or same_response_schema'`

Expected: import or attribute failure.

- [ ] **Step 3: 实现唯一的系统 Prompt 契约**

系统 Prompt 必须要求：

```text
返回 JSON object，字段 candidates 为 9–15 项。
display_label_zh 为 2–8 个中文字符，禁止完整句子。
禁止把 Aesthetic、Structural、Functional、Cross-domain、shape、connection、material、surface、silhouette、ornament 作为标签。
每项必须包含 group、target_ref、operation、semantic_anchor、prompt_phrase、attribute_delta、scores。
保持 object identity；严格限制在 Gate target 与 scope。
knowledge evidence 是可选 donor，不得复制来源标题，也不得编造 provenance。
```

Gemini 使用 `gemini_api_base/key/model`；本地 VLM 使用 `iul_vlm_intent_url/model`。两者的解析、一次 JSON repair 和候选 schema 完全一致。

- [ ] **Step 4: 增加配置但不增加新密钥**

```python
semantic_divergence_enabled: bool = True
semantic_divergence_timeout_sec: float = 25
semantic_divergence_vlm_timeout_sec: float = 35
semantic_divergence_min_candidates: int = 9
semantic_divergence_max_candidates: int = 15
```

不得输出 API key，不得把 key 写进测试 fixture、日志或响应。

- [ ] **Step 5: 测试超时、无效 JSON 和一次 repair**

分别模拟 `URLError`、缺少 `prompt_phrase`、首次无效而第二次有效。断言技术错误转换为 `SemanticModelUnavailable`，schema 错误转换为 `SemanticModelOutputError`，repair 总次数不超过一次。

- [ ] **Step 6: 运行客户端测试**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_service.py -k 'gemini or local_vlm or repair or unavailable'`

Expected: all selected tests pass without network access.

- [ ] **Step 7: Reviewer checkpoint**

确认 Planner 的 `GeminiClient.decide()` 未被复用为发散器，两个模型职责在代码边界上可区分。

---

### Task 4: 实现确定性强校验与集合质量门

**Files:**

- Create: `backend/app/services/divergence/semantic_validator.py`
- Test: `backend/tests/test_semantic_divergence_service.py`

**Interfaces:**

- Consumes: `SemanticDivergenceRequest`, `list[SemanticCandidate]`。
- Produces: `SemanticCandidateValidator.validate(request, candidates) -> ValidationReport`。
- `ValidationReport` 包含 `accepted`、`rejected`、`rejection_counts` 和 `needs_fallback`。

- [ ] **Step 1: 写禁词、长度、scope、阈值和去重测试**

```python
def test_validator_rejects_taxonomy_labels(validator, request, candidate_factory) -> None:
    report = validator.validate(request, [candidate_factory(label="Aesthetic")])
    assert report.accepted == []
    assert report.rejection_counts["taxonomy_label"] == 1


def test_validator_applies_strictness_thresholds(validator, request_factory, candidate_factory) -> None:
    request = request_factory(strictness=0.8)
    report = validator.validate(request, [candidate_factory(identity=0.7, scope_score=0.95, relevance=0.95)])
    assert report.rejection_counts["identity_below_threshold"] == 1


def test_part_scope_rejects_whole_object_operation(validator, request_factory, candidate_factory) -> None:
    request = request_factory(scope="part", target_id="hat")
    candidate = candidate_factory(target_type="whole", target_id=None)
    assert validator.validate(request, [candidate]).accepted == []
```

- [ ] **Step 2: 运行测试并确认 Validator 尚不存在**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_service.py -k validator`

Expected: import failure for `SemanticCandidateValidator`.

- [ ] **Step 3: 实现单候选校验顺序**

顺序固定，保证审计计数可解释：

```text
schema → banned label → display length → inherited duplicate → target exists
→ scope/operation hard gate → identity threshold → scope threshold
→ relevance threshold → specificity > 0 → provenance consistency
```

`strictness` 只进入 `params.thresholds`，不得改变温度或候选数量。

- [ ] **Step 4: 实现规范化去重**

中文标签去除空格和标点后比较；英文标签 lower-case 后比较；同时使用 `target_ref.id + operation + attribute_delta` 做语义键。保留分数较高、provenance 更完整的一项。

- [ ] **Step 5: 实现集合质量门**

最终集合必须：

- 数量至少 9、至多请求的 `candidate_count`；
- 覆盖至少两个与当前 intent 相关的 group；
- `temperature >= 0.7` 时至少两个 `semantic_transfer`；
- 不含继承词的同义重复；
- 不用泛词补足数量。

不足 9 个时 `needs_fallback=True`，由 Task 5 调用本地 VLM。

- [ ] **Step 6: 运行强校验测试**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_service.py -k validator`

Expected: all validator tests pass.

- [ ] **Step 7: Reviewer checkpoint**

逐条检查 banned set，确认短标签可以不重复对象名，但后台 target、operation 和 prompt phrase 均不可为空。

---

### Task 5: 编排主备模型、知识增强、幂等与审计

**Files:**

- Create: `backend/app/services/divergence/semantic_divergence_service.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_semantic_divergence_service.py`

**Interfaces:**

- Consumes: Tasks 1–4 的类型、Router、Generator、Validator。
- Produces: `SemanticDivergenceService.diverge(run, params) -> SemanticDivergenceResponse`。
- Produces: `SemanticDivergenceService.request_key(run, params) -> str`。

- [ ] **Step 1: 写主模型成功、技术 fallback、质量 fallback 和双失败测试**

```python
async def test_primary_success_does_not_call_local_vlm(service, run, params) -> None:
    response = await service.diverge(run, params)
    assert response.status == "completed"
    assert response.fallback_used is False
    assert service.local_vlm.calls == 0


async def test_quality_failure_falls_back_to_local_vlm(service, run, params) -> None:
    service.gemini.result = [candidate("Aesthetic")]
    response = await service.diverge(run, params)
    assert response.fallback_used is True
    assert response.fallback_reason == "insufficient_valid_candidates"
    assert len(response.candidates) >= 9


async def test_double_failure_returns_no_fake_keywords(service, run, params) -> None:
    service.gemini.error = SemanticModelUnavailable("timeout")
    service.local_vlm.error = SemanticModelUnavailable("offline")
    response = await service.diverge(run, params)
    assert response.status == "failed"
    assert response.candidates == []
```

- [ ] **Step 2: 运行编排测试并确认服务尚不存在**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_service.py -k 'primary_success or quality_failure or double_failure'`

Expected: import failure for `SemanticDivergenceService`.

- [ ] **Step 3: 实现服务端可信上下文组装**

不得接受前端传来的 object identity、scope、target 或 behavior summary 作为事实。使用：

```text
object_identity ← run.source_context.object_type
semantic_target ← run.intent_ir.target + run.source_context target refs
scope           ← run.scope_gate.scope / run.intent_ir.intent.scope
user intent     ← run.intent_ir.intent.goal / observations.text
behavior        ← run.events 中 source_event_ids 对应的锁定窗口
constraints     ← intent constraints + selected Decision option constraints
```

前端只提交 `temperature`、`strictness`、`candidate_count` 和 `inherited_keywords`。

- [ ] **Step 4: 实现固定调用顺序**

```text
build request
→ choose knowledge route
→ collect optional evidence
→ Gemini generate
→ validate
→ 若 needs_fallback，则 Qwen2.5-VL generate
→ validate
→ 合并主备合格候选并再次去重
→ 保存 response 和 audit
```

Gemini 与本地 VLM 各最多一次正常调用和一次 JSON repair。知识源失败不得直接触发模型 fallback。

- [ ] **Step 5: 实现幂等键**

```python
material = {
    "run_id": run.run_id,
    "decision_id": run.decision.decision_id,
    "temperature": params.temperature,
    "strictness": params.strictness,
    "candidate_count": params.candidate_count,
    "inherited_keywords": sorted(set(params.inherited_keywords)),
}
request_key = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
```

当 `run.semantic_divergence.request_key` 相同时直接返回持久化响应，不再次调用外部服务。

- [ ] **Step 6: 使用现有 model audit 记录主备调用**

记录 provider、model、latency、error type 和 run_id；不得记录 API key、完整 data URL 或未裁剪的用户图像。

- [ ] **Step 7: 在 `main.py` 组装唯一服务实例**

注入现有 `four_stage_store`、`Gemini` 配置、`iul_vlm` 配置和知识适配器。测试环境通过依赖注入使用 fake generator，禁止访问真实网络。

- [ ] **Step 8: 运行服务全测**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_service.py backend/tests/test_semantic_knowledge_router.py`

Expected: all pass，且无网络请求。

- [ ] **Step 9: Reviewer checkpoint**

确认 `fallback_used`、`fallback_reason`、知识 partial source 和每条 rejection count 都能从响应审计。

---

### Task 6: 接入 FourStage Gate、IntentRevision 与刷新端点

**Files:**

- Modify: `backend/app/services/pipeline/four_stage_orchestrator.py`
- Modify: `backend/app/services/intent/realtime_observation.py`
- Modify: `backend/app/api/four_stage.py`
- Modify: `backend/app/api/realtime_observation.py`
- Modify: `backend/tests/test_four_stage.py`
- Modify: `backend/tests/test_four_stage_rerepresentation.py`
- Modify: `backend/tests/test_realtime_observation.py`

**Interfaces:**

- Consumes: `SemanticDivergenceService.diverge()`。
- Produces: Gate accept body field `divergence_params`。
- Produces: `POST /api/v1/four-stage/runs/{run_id}/semantic-divergence` for settled slider refresh/retry。

- [ ] **Step 1: 写 Gate 前禁止、Gate 后调用一次的 API 测试**

```python
def test_semantic_divergence_requires_accepted_gate(client, seeded_run) -> None:
    response = client.post(
        f"/api/v1/four-stage/runs/{seeded_run.run_id}/semantic-divergence",
        json={"temperature": 0.2, "strictness": 0.6},
    )
    assert response.status_code == 409


def test_revision_gate_accepts_divergence_parameters(client, awaiting_revision, fake_semantic_service) -> None:
    response = client.post(
        f"/api/v1/intent-revisions/{awaiting_revision.revision_id}/gate",
        json={"accepted": True, "divergence_params": {"temperature": 0.7, "strictness": 0.8}},
    )
    assert response.status_code == 200
    assert fake_semantic_service.calls[0].temperature == 0.7
```

- [ ] **Step 2: 运行测试并确认请求字段与端点不存在**

Run: `backend/.venv/bin/pytest -q backend/tests/test_four_stage.py backend/tests/test_realtime_observation.py -k semantic_divergence`

Expected: 404 or schema assertion failure.

- [ ] **Step 3: 扩展两个 Gate 路径**

`FourStageOrchestrator.resolve_gate()` 增加 `divergence_params`。仅在 `accept_option` 且 `auto_generate=False` 时调用服务；legacy `auto_generate=True` 不再从 Decision seeds 构造伪 selection，而应使用明确的 compatibility params 调用 Semantic Divergence，失败则阻止生成。

`RealtimeObservationService.resolve_gate()` 将 canonical revision 请求参数传入 orchestrator，并在成功后更新 `semantic_divergence_status`。

- [ ] **Step 4: 实现 slider refresh/retry 端点**

```python
@router.post(
    "/api/v1/four-stage/runs/{run_id}/semantic-divergence",
    response_model=SemanticDivergenceResponse,
)
async def refresh_semantic_divergence(
    run_id: str,
    request: SemanticDivergenceParams,
) -> SemanticDivergenceResponse:
    return await orchestrator.refresh_semantic_divergence(run_id, request)
```

`refresh_semantic_divergence()` 校验 run 仍在 `awaiting_gate`、Gate 已接受、decision 未变化。

- [ ] **Step 5: 删除新 UI 对 `DecisionIR.divergence_seeds` 的运行时依赖**

Planner schema 可暂时保留 seeds 兼容字段，但：

- Gate 接受不再把 seeds 写入 selection；
- `/divergence-options` 返回 Semantic Divergence candidates，旧 seeds 仅在响应 metadata 标记 deprecated；
- 新接口绝不使用 rule `_AXIS_SEEDS` 补词。

- [ ] **Step 6: 验证拒绝、多 Gate 和 Observation 连续性**

新增测试证明：拒绝 Gate 时 semantic service 调用次数为 0；两个 revisions 各自产生不同 request key；第二个 revision 发散期间仍可提交新 BehaviorSession。

- [ ] **Step 7: 运行 Gate 与 revision 回归**

Run: `backend/.venv/bin/pytest -q backend/tests/test_four_stage.py backend/tests/test_four_stage_rerepresentation.py backend/tests/test_realtime_observation.py`

Expected: all pass.

- [ ] **Step 8: Reviewer checkpoint**

确认 canonical UI 使用的 IntentRevision Gate 和兼容 FourStage Gate 都已覆盖，且没有 Gate 接受即自动生成图片。

---

### Task 7: 让候选 ID、完整 Prompt 与关键词继承进入生成链

**Files:**

- Modify: `backend/app/services/pipeline/four_stage_orchestrator.py`
- Modify: `backend/app/services/intent/realtime_observation.py`
- Modify: `backend/app/services/generation/four_stage_spec_builder.py`
- Modify: `backend/tests/test_four_stage_generation.py`
- Modify: `backend/tests/test_realtime_observation.py`

**Interfaces:**

- Consumes: `DivergenceSelection.selected_candidate_ids`。
- Produces: 服务端解析后的 `selected_keywords` 与 `resolved_prompt_phrases`。
- Produces: `GenerationSpec.prompt_candidates` 使用完整 phrase，UI 仍显示短标签。

- [ ] **Step 1: 写伪造 label、未知 ID、Prompt 解析和继承测试**

```python
def test_selection_resolves_server_side_candidate(run_with_semantic_response, orchestrator) -> None:
    selection = DivergenceSelection(selected_candidate_ids=["kw_lava"])
    updated = asyncio.run(orchestrator.save_divergence_selection(run_with_semantic_response.run_id, selection))
    assert updated.divergence_selection.selected_keywords == ["熔岩流线"]
    assert updated.divergence_selection.resolved_prompt_phrases == [
        "reshape only the table support with solidified lava-flow contours"
    ]


def test_unknown_candidate_id_is_rejected(run_with_semantic_response, orchestrator) -> None:
    with pytest.raises(FourStageError, match="unknown semantic candidate"):
        asyncio.run(orchestrator.save_divergence_selection(
            run_with_semantic_response.run_id,
            DivergenceSelection(selected_candidate_ids=["kw_fake"]),
        ))
```

- [ ] **Step 2: 运行测试并确认 selection 仍信任前端字符串**

Run: `backend/.venv/bin/pytest -q backend/tests/test_four_stage_generation.py backend/tests/test_realtime_observation.py -k 'candidate_id or inherited_prompt'`

Expected: failing assertions.

- [ ] **Step 3: 服务端解析选择**

`save_divergence_selection()` 只接受当前 `run.semantic_divergence.candidates` 中的 ID，重新生成 labels、dimensions 和 prompt phrases。兼容旧客户端时允许 label-only，但必须能唯一匹配当前候选；否则返回 409。

- [ ] **Step 4: 让继承发生在 revision 层**

接受新 Gate 时先查找最近一个已接受/生成中/完成的 revision：

```text
base_keywords = previous.effective_keywords
inherited prompt phrases = previous.divergence_selection.resolved_prompt_phrases
```

Semantic Divergence 将 `base_keywords` 作为去重输入。保存本次选择时：

```text
delta_keywords = 当前选择
effective_keywords = base + delta，稳定去重
resolved_prompt_phrases = previous prompts + current prompts，稳定去重
```

- [ ] **Step 5: 修改 GenerationSpecBuilder**

删除：

```python
if not system_keywords:
    system_keywords = list(option.divergence_seeds)
```

生成 Prompt 的 `USER-SELECTED DIRECTION` 使用 `resolved_prompt_phrases`；`GenerationSpec.keywords` 仍保存短标签用于审计。若没有选择任何候选，Generate 返回明确错误。

- [ ] **Step 6: 验证 8 个候选不会被一个强材质词统一污染**

测试 2 个已选候选时，8 个 Prompt 按候选 round-robin 分配，每个 Prompt 至多使用一个人选方向，并始终包含 identity、scope 和白色背景完整单体约束。

- [ ] **Step 7: 运行生成与 revision 测试**

Run: `backend/.venv/bin/pytest -q backend/tests/test_four_stage_generation.py backend/tests/test_realtime_observation.py`

Expected: all pass.

- [ ] **Step 8: Reviewer checkpoint**

抽查生成 Prompt，确认用户看到的是短标签，模型收到的是完整 phrase，且不存在 Decision 大类词回流。

---

### Task 8: 前端接入真实参数、候选分组与状态反馈

**Files:**

- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/state/studioStore.ts`
- Modify: `frontend/src/components/panels/AIBehaviorPanel.tsx`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/tests/semanticDivergence.test.ts`

**Interfaces:**

- Consumes: `FourStageRun.semantic_divergence` 与刷新端点。
- Produces: Gate body `divergence_params`。
- Produces: settled slider refresh、四组候选按钮、模型/知识降级状态和 candidate ID selection。

- [ ] **Step 1: 写源码契约测试**

```typescript
test("gate accept sends both divergence parameters", async () => {
  const source = await read("../src/state/studioStore.ts");
  assert.match(source, /divergence_params:\s*\{[^}]*temperature:\s*divergenceTemperature[^}]*strictness:\s*divergenceStrictness/s);
});

test("keyword panel no longer reads DecisionIR divergence seeds", async () => {
  const source = await read("../src/state/studioStore.ts");
  assert.doesNotMatch(source, /options\?\.flatMap\(\(option\) => option\.divergence_seeds/);
  assert.match(source, /semantic_divergence\?\.candidates/);
});

test("slider refresh is settled rather than fired on every input tick", async () => {
  const panel = await read("../src/components/panels/AIBehaviorPanel.tsx");
  assert.match(panel, /onPointerUp=\{onDivergenceParametersCommit\}/);
  assert.match(panel, /onKeyUp=\{onDivergenceParametersCommit\}/);
});
```

- [ ] **Step 2: 运行测试并确认旧链路失败**

Run: `cd frontend && node --experimental-strip-types --test tests/semanticDivergence.test.ts`

Expected: assertions fail because Gate body omits parameters and keywords still come from seeds.

- [ ] **Step 3: 增加前端类型**

定义 `SemanticCandidateGroup`、`SemanticCandidate`、`SemanticDivergenceResponse`，并在 `FourStageRun` 中加入 `semantic_divergence`。PromptToken 增加 `candidate_id`、`group_key` 和 `full_prompt_phrase`，但组件不渲染完整 phrase。

- [ ] **Step 4: Gate 接受时提交当前参数**

canonical `resolveIntentRevisionGate()` body：

```typescript
{
  accepted: true,
  divergence_params: {
    temperature: divergenceTemperature,
    strictness: divergenceStrictness,
    inherited_keywords: inheritedRevisionKeywords,
  },
}
```

Gate 返回后获取 run，将 `semantic_divergence.candidates` 转成 PromptToken。删除 `keywordChipsFromSeeds()` 作为运行时来源。

- [ ] **Step 5: settled slider 刷新**

滑杆 `onChange` 只更新本地显示；`onPointerUp`、键盘 `onKeyUp` 和 `onBlur` 调用同一 `onDivergenceParametersCommit()`。只有 active revision 已接受且 run 仍处于 `awaiting_gate` 时请求刷新；相同参数由服务端幂等返回。

- [ ] **Step 6: 按四个语义组显示**

显示映射固定为：

```typescript
const GROUP_LABELS = {
  shape: "形态",
  connection: "连接",
  surface: "表面/材质",
  semantic_transfer: "语义迁移",
} as const;
```

按钮文字只使用 `display_label_zh`。响应 `fallback_used=true` 时显示“本地 VLM 补充”；knowledge route 降级只在非阻塞状态提示，不显示内部错误堆栈。

- [ ] **Step 7: 保存 candidate IDs 而非信任 label**

`togglePromptToken()` 向 revision selection 发送 `selected_candidate_ids`。`selected_keywords` 可作为兼容显示字段发送，但后端必须重建它。

- [ ] **Step 8: 实现加载与双失败状态**

- Gate 接受后立即显示关键词骨架屏；
- 成功后原位替换为候选；
- 双模型失败显示“语义发散暂时不可用，请重试或补充意图”；
- 失败不清空继承关键词；
- 没有选中候选时 Generate 禁用并给出可访问说明。

- [ ] **Step 9: 运行前端测试与生产构建**

Run: `cd frontend && node --experimental-strip-types --test tests/semanticDivergence.test.ts tests/gateContract.test.ts tests/interactionReliability.test.ts`

Expected: all tests pass.

Run: `cd frontend && npm run build`

Expected: TypeScript/Vite build succeeds without new warnings.

- [ ] **Step 10: Reviewer checkpoint**

在 UI 中确认不会再次出现 “Structural” 分组下包含 “Aesthetic / Functional / Cross-domain” 的错误状态。

---

### Task 9: 建立三场景端到端与消融实验证据

**Files:**

- Modify: `backend/tests/test_four_stage_e2e.py`
- Create: `backend/tests/test_semantic_divergence_scenarios.py`
- Create: `docs/experiments/semantic-divergence-evaluation-protocol.md`

**Interfaces:**

- Consumes: 完整 Gate → Semantic Divergence → Selection → GenerationSpec 链路。
- Produces: 三个可重复 scenario fixtures、三种消融条件和统一指标记录格式。

- [ ] **Step 1: 建立三个固定 scenario fixture**

```python
SCENARIOS = {
    "stone_frog": {
        "object_identity": "frog character",
        "scope": "whole",
        "intent": "把小青蛙迁移成石像青蛙",
        "signals": ["text", "drag", "smooth"],
        "required_groups": {"surface", "semantic_transfer"},
    },
    "handbag_material": {
        "object_identity": "handbag",
        "scope": "material_region",
        "intent": "保持皮包形态，探索不同材质",
        "signals": ["text", "intent", "2d_brush"],
        "required_groups": {"surface"},
    },
    "lava_table": {
        "object_identity": "coffee table",
        "scope": "part",
        "intent": "保持茶几 identity，探索流动熔岩结构",
        "signals": ["text", "3d_brush"],
        "required_groups": {"shape", "semantic_transfer"},
    },
}
```

- [ ] **Step 2: 写端到端失败测试**

每个 fixture 必须断言：Gate 前无发散；Gate 后 9–15 个候选；无 banned label；短标签合规；候选 target 与 scope 合规；选择候选后 GenerationSpec 有 8 个 Prompt；每个 Prompt 包含 identity、局部约束以及白底完整单体 contract。

- [ ] **Step 3: 运行场景测试并修复暴露的契约遗漏**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_scenarios.py backend/tests/test_four_stage_e2e.py`

Expected: all pass with fake model/knowledge adapters and deterministic fixtures.

- [ ] **Step 4: 定义三种消融模式**

在 request metadata 或测试配置中使用明确枚举：

```text
llm_only
knowledge_only
knowledge_augmented_llm
```

生产 UI 不暴露该开关；研究运行和自动测试可以选择。三种模式必须使用同一 Validator 与相同 candidate count。

- [ ] **Step 5: 写评估协议**

文档逐项定义 Semantic Relevance、Keyword Specificity、Identity Preservation、Scope Compliance、Intra-set Diversity、Keyword Selection Rate、Solution Acceptance Rate、fallback rate、知识命中率和延迟；每个指标写明输入、计算方式和缺失值处理。

- [ ] **Step 6: 运行完整本地回归**

Run: `backend/.venv/bin/pytest -q backend/tests/test_semantic_divergence_models.py backend/tests/test_semantic_knowledge_router.py backend/tests/test_semantic_divergence_service.py backend/tests/test_semantic_divergence_scenarios.py backend/tests/test_four_stage.py backend/tests/test_four_stage_rerepresentation.py backend/tests/test_four_stage_generation.py backend/tests/test_realtime_observation.py backend/tests/test_four_stage_e2e.py`

Expected: all selected backend tests pass.

Run: `cd frontend && node --experimental-strip-types --test tests/semanticDivergence.test.ts tests/gateContract.test.ts tests/interactionReliability.test.ts`

Expected: all selected frontend tests pass.

Run: `cd frontend && npm run build`

Expected: production build succeeds.

- [ ] **Step 7: GPU smoke test without Git operations**

在用户批准执行阶段后，仅同步变更文件到 `/root/flowstudio_app`，重启 canonical backend/frontend，验证：

1. Gate 接受后显示 9–15 个短词；
2. 调整 temperature 后知识 route 和候选跨度发生可审计变化；
3. 调整 strictness 后过滤计数或合格候选发生可审计变化；
4. 模拟 Gemini 不可用时由本地 VLM 返回同 schema；
5. 模拟 Getty/AskNature 不可用时仍返回 model-only 结果；
6. 选择关键词后产生 6–8 个白底完整单体图；
7. 多 Gate 结果按 revision 追加，Observation 持续工作。

- [ ] **Step 8: Final reviewer checkpoint**

将三场景候选、生成 Prompt、模型/知识 provenance、拒绝计数和图片结果汇总给用户检查。证据不足时不得宣布论文核心机制完成。

---

## Execution Order and Review Gates

```text
Task 1 schema/storage
→ Task 2 knowledge route
→ Task 3 model clients
→ Task 4 validator
→ Task 5 orchestration
→ Task 6 Gate/API integration
→ Task 7 selection/generation/inheritance
→ Task 8 frontend
→ Task 9 scenarios and research evidence
```

Task 1、5、6、7 是状态契约 checkpoint；Task 2、3、4 是语义质量 checkpoint；Task 8 是交互 checkpoint；Task 9 是论文验收 checkpoint。每个 checkpoint 只进行测试与人工复核，不执行 Git commit、push 或部署。
