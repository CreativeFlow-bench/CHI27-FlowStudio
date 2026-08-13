# Semantic Divergence 评估协议

## 1. 目的与证据边界

本协议评估 Gate 接受后的 Semantic Divergence 候选词、用户选择和后续 Solution 结果。固定场景为石像青蛙叙事迁移、皮包材质探索、熔岩茶几结构迁移。

本地 fake 测试只能证明状态、schema、过滤、选择和 Prompt 约束。它不能证明生成图片的实际 identity preservation、视觉多样性、局部编辑精度或 3D 重建质量。这些指标必须等获得授权的 GPU/图片/3D 证据后才能计算；缺少该证据时记为 `NA_evidence_missing`，不得以 Prompt 包含约束代替成果评分。

## 2. 评估单元与固定输入

一个评估单元是 `(scenario_id, ablation_mode, run_id, divergence_id)`。每个单元保存：

- 输入：对象 identity、目标 part/material region、scope、用户语义、锁定行为窗口、继承词、temperature、strictness 和 candidate count。
- 过程：Gate 决定、knowledge route、每个模型调用、fallback 原因、validator rejection counts。
- 输出：所有候选及 provenance、选中 ID、GenerationSpec、Solution 图片/模型、用户接受与拒绝。

三种消融模式为 `llm_only`、`knowledge_only`、`knowledge_augmented_llm`。每种模式使用相同 scenario 输入、candidate count、validator、strictness 和生成后评估器；只改变候选来源。消融开关仅存在研究运行/自动测试配置中，不暴露于生产 UI。

## 3. 通用聚合与缺失值规则

- Candidate-level 指标先在每个 divergence set 内取算术平均，再按 scenario 和 ablation 对 set-level 分数报告均值、标准差、中位数和 95% bootstrap CI。
- Solution-level 指标先在每批 8 个结果内聚合，再按 scenario 和 ablation 聚合。不满 8 个时同时报告实际分母与 missing count。
- 可判定的单个样本缺值不做零分填充；记录原因并从该指标分母排除。若一个 cell 超过 20% 样本缺失，该 cell 标记 `insufficient_evidence`。
- 模型/知识失败本身是 fallback/knowledge-hit 的有效观测，不因候选词缺失而删除。超时记录实际 timeout 上限并标记 censored。

## 4. 十项核心指标

### 4.1 Semantic Relevance（语义相关性）

- 输入：用户语义、对象 identity、target/scope、候选 `semantic_anchor + prompt_phrase`。
- 计算：三名不知消融条件的评审者以 1–5 评分，判断该方向是否回应意图且指向正确对象/部件。主分数为评审均值；附带 Krippendorff's alpha。
- 聚合：先 candidate → set，再按 scenario × ablation 聚合。
- 缺失：少于 2 个有效评分则该 candidate 记 `NA_rater_missing`。

### 4.2 Keyword Specificity（关键词具体度）

- 输入：`display_label_zh`、`label_en`、group、operation、attribute delta。
- 计算：硬规则通过率（非 taxonomy/generic label、中文 2–8 字或英文 1–4 词、明确形态/连接/表面/语义迁移）与盲评 1–5 的平均值分开报告。
- 聚合：硬规则用通过 candidate/全部 candidate；盲评按 4.1 聚合。
- 缺失：标签缺失属 schema rejection，计入不通过；人评缺失按 4.1 处理。

### 4.3 Identity Preservation（身份保持）

- 输入：源图、源对象 mask/关键点/类别，生成图；如有 3D，加入渲染多视图。
- 计算：图像语义相似度、轮廓/关键点保持率与三人 1–5 identity 盲评分开报告；不用 Prompt 中的 `preserve` 文字代替结果评估。
- 聚合：先对每个 Solution 计算，再批次、scenario 和 ablation 聚合。
- 缺失：无图片/可比较源时记 `NA_evidence_missing`；本地 fake 测试一律为 NA。

### 4.4 Scope Compliance（范围合规）

- 输入：目标 scope/mask/part ID、源图/源 3D、生成结果。
- 计算：目标区域改变量与非目标区域改变量的比率，并以盲评判断 whole/material_region/part 约束是否满足。本地 contract 测试另报 target-ref 和 Prompt scope 约束通过率，不与结果分数混合。
- 聚合：Solution → batch → scenario × ablation。
- 缺失：无 mask/part correspondence 时像素比率记 NA，但有效盲评仍可单独报告。

### 4.5 Intra-set Diversity（集合内多样性）

- 输入：一个 divergence set 的 candidate embeddings/group/attribute deltas，以及一批 Solution 的 image embeddings。
- 计算：候选层为两两 cosine distance 均值、group entropy 和唯一 attribute-delta 比率；图片层为两两 perceptual/image-embedding distance 均值。
- 聚合：每个 set 产生一个值，再按 scenario × ablation 聚合。
- 缺失：有效项少于 2 时记 NA；无图像时只报候选层，图片层记 `NA_evidence_missing`。

### 4.6 Keyword Selection Rate（关键词选择率）

- 输入：展示给用户的 authoritative candidate IDs 和最终 selected IDs。
- 计算：`selected_unique_candidate_ids / displayed_valid_candidate_ids`；同时报告至少选 1 个的 run 比率。
- 聚合：比率先按 run，再按 scenario × ablation；总体也报告 micro-average。
- 缺失：候选未成功展示时分母为 0，记 NA 并由 fallback/failure 指标承担；用户明确跳过记 0。

### 4.7 Solution Acceptance Rate（方案接受率）

- 输入：成功展示的 Solution IDs 和用户 accept/reject/branch 结果。
- 计算：`accepted_or_branched_unique_solutions / displayed_valid_solutions`；重复点击按 Solution ID 去重。
- 聚合：run → scenario × ablation，附 micro-average。
- 缺失：未展示不进分母；展示后 session 结束且无动作记 `NA_no_feedback`，不自动当作 reject。

### 4.8 Fallback Rate

- 输入：每次 divergence 的 primary status、`fallback_used`、`fallback_reason`和最终 status。
- 计算：`fallback_used_runs / all_divergence_attempts`；按模型不可用、输出格式错误、质量不足分层。知识源部分失败不计为模型 fallback。
- 聚合：scenario × ablation 报告比率及 Wilson 95% CI。
- 缺失：审计字段丢失的 run 记 `unknown_fallback_state`，不猜测 false。

### 4.9 Knowledge Hit Rate（知识命中率）

- 输入：knowledge route、每源 status、候选 provenance 中 Wikidata/Getty AAT/AskNature authoritative IDs。
- 计算：主指标为 `accepted_candidates_with_at_least_one_authoritative_id / accepted_candidates_in_knowledge-enabled_runs`；辅助指标为 route 启用后至少有一个有效 evidence 的 run 比率和分源命中率。
- 聚合：scenario × ablation 和 source 分层报告。
- 缺失：`llm_only` 中记 `NA_not_routed`，不计 0；已启用但服务失败计 0 并保留 partial/error 原因。

### 4.10 Latency（延迟）

- 输入：Gate accept timestamp、knowledge start/end、primary/fallback model start/end、validation end、候选可见 timestamp、生成开始/首图/批次完成 timestamp。
- 计算：分别计算 knowledge、model、validation、Gate-to-keywords、Generate-to-first-image 和 Generate-to-batch-complete 毫秒延迟。
- 聚合：scenario × ablation 报告 p50/p90/p95、均值和超时比率，不只报平均。
- 缺失：已达 timeout 的步骤记为上限值且 `censored=true`；无授权的 GPU 生成阶段记 `NA_not_run`。

## 5. Provenance 与 rejection 审计

每个候选保存 `candidate_id`、generator/model/version、ablation mode、knowledge route、Wikidata QID/Getty AAT ID/AskNature URL 或 ID、prompt version 和各分数。只记权威 ID 和必要标签，不记 API key、data URL 或原始大图。

Validator 在每次 primary、fallback 和 merge/revalidate 阶段保存候选总数、接受数和分原因 rejection counts，包括 schema、taxonomy label、display length、inherited duplicate、target not found、scope/operation、identity/scope/relevance threshold、specificity、provenance、duplicate、candidate limit、minimum candidates 和 group coverage。报告同时给出原始 count 和以该阶段输入为分母的 rate，防止不同 candidate count 误导比较。

## 6. 消融比较

每个 scenario 使用配对的意图、行为窗口、temperature、strictness、candidate count 和随机种子运行三种消融。主比较为：

1. `knowledge_augmented_llm - llm_only`：检验知识增强对相关性、具体度、多样性、knowledge hit 和延迟的影响。
2. `knowledge_augmented_llm - knowledge_only`：检验 LLM 组合/语境化是否提升可选性与语义相关性。
3. 三模式的 fallback、rejection 构成和 latency 差异。

对连续指标报告配对差值、95% bootstrap CI 和效应量；对接受/选择类二元结果报告配对比例差和区间。多重比较使用 Holm 校正。每个表格 cell 必须显示 `n_runs / n_candidates / n_solutions`和缺失数，不仅显示 p 值。

## 7. 本地与 GPU 验收分工

- 本地已可验证：Gate 前不发散；Gate 后 9–15 个合法候选；禁用大类词/短标签/target/scope；authoritative ID 选择；8 个 Prompt 含 identity、scope 和白底完整单体约束；三种消融共用 validator 与 candidate count。
- 必须等 GPU/图片/3D 证据：真实 identity preservation、scope compliance、图像集合内多样性、实际 Solution acceptance、首图/批次延迟和 3D 可编辑质量。
