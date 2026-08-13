# FlowStudio 交互信号驱动的设计状态估计机制（MVP）

## 1. 目的与边界

本机制根据 FlowStudio 已经采集的思考、GUI 和语义信号，为以下四种系统工作状态计算证据分数：

- `exploration`：用户正在浏览或扩大设计方向；
- `formation`：用户正在把一个方向形成具体方案；
- `refinement`：用户正在稳定方向内修改局部或细节；
- `evaluation`：用户正在比较、检查或判断已有结果。

这些状态是系统选择辅助策略的工作假设，不代表对用户真实心理状态的判断。输出百分比称为 `evidence_score`，不称为认知概率。

## 2. 使用的现有信号

第一版只使用平台已有字段，不新增复杂行为特征。

| 信号类别 | 使用字段 |
| --- | --- |
| 思考 | `dwell_ms`、`compare_dwell_ms`、`hesitation`、`recent_undo_count` |
| GUI | `part_id`、`brush_count`、`annotation_count`、`viewport_orbit_count`、`viewport_zoom_count`、`same_part_recent_edits`、当前事件类型 |
| 语义与参考 | `semantic_distance`、`new_case_attempt_rate`、`intent_text`、`image_ref_count`、`model_ref_count` |

判断窗口使用最近 20 秒或最近 12 个有效交互事件，谁先达到就结束窗口。页面失焦和后台生成等待不计入停顿。

## 3. 最小状态规则

每条命中的主规则为对应状态增加 `1.0` 票。辅助规则增加 `0.5` 票。

### 3.1 Exploration

主规则：

```text
semantic_distance >= 0.55
OR new_case_attempt_rate >= 0.45
```

辅助规则：

```text
没有稳定 part_id
AND viewport_orbit_count + viewport_zoom_count >= 2
```

解释：用户在切换语义方向，或从全局视角浏览对象。

### 3.2 Formation

主规则：

```text
存在 brush / drag / annotation / add 操作
AND same_part_recent_edits < 3
AND 当前不是 candidate_compared
```

辅助规则：

```text
0.25 <= semantic_distance < 0.55
```

解释：用户已经开始塑造方案，但操作目标和形式还没有稳定到局部细化阶段。

### 3.3 Refinement

主规则：

```text
存在 part_id
AND same_part_recent_edits >= 3
```

辅助规则：

```text
brush_count >= 2
AND new_case_attempt_rate < 0.35
```

解释：用户持续修改同一个部件，并且较少尝试新的设计方向。

### 3.4 Evaluation

主规则：

```text
event_type == candidate_compared
OR compare_dwell_ms >= 2500
```

辅助规则：

```text
viewport_orbit_count + viewport_zoom_count >= 3
AND brush_count + annotation_count == 0
```

解释：用户主要在比较候选或进行多视图检查，而不是继续编辑。

## 4. 停顿与犹豫规则

停顿和犹豫存在较强歧义，因此不能单独决定状态，只用于修正已有判断。

```text
hesitation >= 0.70
AND same_part_recent_edits >= 3
→ Refinement +0.5，并标记 possible_fixation=true

hesitation >= 0.70
AND (event_type == candidate_compared OR compare_dwell_ms >= 2500)
→ Evaluation +0.5

只有长停顿或高犹豫，没有其他证据
→ 不增加任何状态票
```

## 5. 规则、VLM 与状态先验的融合

规则命中后，先将四种状态的票数归一化为 `rule_score`。VLM读取结构化信号、命中规则、上一状态和必要的截图/文本，输出四种状态的 `vlm_score`。

最终分数：

```text
final_score = 0.70 * rule_score
            + 0.20 * vlm_score
            + 0.10 * previous_state_prior
```

`previous_state_prior` 是上一状态的 one-hot 分布，用于减少短时抖动。如果当前窗口没有命中任何主规则，则不允许切换状态；VLM只能给出解释或请求继续观察。

## 6. VLM 的限定任务

VLM只负责：

1. 处理 GUI 与语言信号冲突；
2. 判断停顿更接近继续编辑还是候选评估；
3. 在 `formation/refinement` 或 `exploration/evaluation` 分数接近时进行裁决。

VLM不得：

- 根据单次停顿、旋转或缩放直接决定状态；
- 使用输入中不存在的行为证据；
- 输出四种状态以外的新阶段；
- 把 evidence score 描述成用户心理概率。

建议 VLM 输出：

```json
{
  "state_scores": {
    "exploration": 0.10,
    "formation": 0.22,
    "refinement": 0.54,
    "evaluation": 0.14
  },
  "recommended_state": "refinement",
  "confidence": 0.72,
  "evidence": [
    "stable part_id",
    "same_part_recent_edits >= 3"
  ],
  "conflict": null,
  "insufficient_evidence": false
}
```

如果 VLM 未引用有效输入证据、输出格式错误或调用失败，系统直接使用规则结果。

## 7. 状态切换

只有同时满足以下条件才切换状态：

```text
最高 final_score >= 0.45
AND 最高分比第二名高 >= 0.10
AND 至少命中一条主规则
AND 连续两个判断窗口得到相同结果
```

`candidate_compared` 可以立即切换到 `evaluation`。其余证据不足时保持上一状态，并返回 `insufficient_evidence=true`。

## 8. 输出与辅助策略

```json
{
  "working_state": "refinement",
  "evidence_score": 0.51,
  "state_scores": {
    "exploration": 0.11,
    "formation": 0.25,
    "refinement": 0.51,
    "evaluation": 0.13
  },
  "matched_rules": ["refinement.primary", "refinement.supporting"],
  "previous_state": "formation",
  "state_changed": true,
  "possible_fixation": false,
  "suggested_policy": "local_constrained_divergence"
}
```

状态与系统策略的最小映射：

| 工作状态 | 系统策略 |
| --- | --- |
| `exploration` | 提供差异较大的方向 |
| `formation` | 围绕当前方向提供结构化候选 |
| `refinement` | 提供局部、受约束的变化 |
| `evaluation` | 减少新生成，提供比较与验证 |

## 9. 第一版验收

第一版只需验证：

1. 相同输入是否稳定地产生相同结果；
2. 单独停顿或视口旋转是否不会错误切换状态；
3. 连续局部编辑能否进入 `refinement`；
4. 候选比较能否进入 `evaluation`；
5. VLM失败时规则结果是否仍可用。

## 10. 2026-08-05 实现状态

该机制可用，已作为常驻 Observation 的规则主层接入，不再使用“最后一个工具直接覆盖阶段”。

- 窗口：最近 20 秒且最多 12 个已提交 Behavior；
- 输出：`design_phase/state_scores/matched_rules/possible_fixation/suggested_policy`；
- 切换：普通状态连续两个窗口一致才切换，`candidate_compared` 立即进入 `evaluation`；
- 容错：没有主规则或分差不足时保持上一状态；后台 Intent 编码置信度单独保存在 `intent_confidence`，不再覆盖状态证据分；
- 信号语义纠正：前端现有 `new_case_attempt_rate` 实际是累计次数，规则层按“窗口次数 / 有效 Behavior 数”归一化后使用；
- 比较闭环：候选比较同时提交一个 `compare` Behavior，确保常驻 Observation 能看到该信号。

当前尚未接入公式中的 VLM 20% 裁决层；规则层和上一状态迟滞已经独立可用。VLM 只应在两组状态接近时补充，不能覆盖无主规则时的“继续观察”。
