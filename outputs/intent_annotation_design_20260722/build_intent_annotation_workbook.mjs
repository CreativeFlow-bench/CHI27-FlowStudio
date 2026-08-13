import fs from "node:fs/promises";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/intent_annotation_design_20260722";
const outputPath = `${outputDir}/FlowStudio_Intent_Annotation_Design_v1.xlsx`;

const wb = Workbook.create();
const colors = {
  navy: "#17365D", blue: "#2F75B5", lightBlue: "#D9EAF7", paleBlue: "#EEF5FB",
  green: "#548235", lightGreen: "#E2F0D9", amber: "#BF8F00", lightAmber: "#FFF2CC",
  red: "#C00000", lightRed: "#FCE4D6", gray: "#666666", lightGray: "#F2F2F2", white: "#FFFFFF"
};

function colLetter(n) {
  let s = "";
  while (n > 0) { n--; s = String.fromCharCode(65 + (n % 26)) + s; n = Math.floor(n / 26); }
  return s;
}

function title(sheet, text, endCol, subtitle="") {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${endCol}1`).merge();
  sheet.getRange("A1").values = [[text]];
  sheet.getRange(`A1:${endCol}1`).format = {
    fill: colors.navy, font: { bold: true, color: colors.white, size: 16 },
    verticalAlignment: "center", rowHeight: 30
  };
  if (subtitle) {
    sheet.getRange(`A2:${endCol}2`).merge();
    sheet.getRange("A2").values = [[subtitle]];
    sheet.getRange(`A2:${endCol}2`).format = {
      fill: colors.paleBlue, font: { color: "#244062", italic: true, size: 10 },
      wrapText: true, rowHeight: 34, verticalAlignment: "center"
    };
  }
}

function header(range) {
  range.format = {
    fill: colors.blue, font: { bold: true, color: colors.white },
    wrapText: true, verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#9EADBA" }
  };
}

function body(range) {
  range.format = {
    verticalAlignment: "top", wrapText: true,
    borders: { insideHorizontal: { style: "thin", color: "#D9E2F3" } }
  };
}

function writeTable(sheet, startRow, headers, rows, widths=[]) {
  const endCol = colLetter(headers.length);
  sheet.getRange(`A${startRow}:${endCol}${startRow}`).values = [headers];
  header(sheet.getRange(`A${startRow}:${endCol}${startRow}`));
  sheet.getRange(`A${startRow}:${endCol}${startRow}`).format.rowHeight = 36;
  if (rows.length) {
    sheet.getRange(`A${startRow+1}:${endCol}${startRow+rows.length}`).values = rows;
    body(sheet.getRange(`A${startRow+1}:${endCol}${startRow+rows.length}`));
  }
  widths.forEach((w, i) => sheet.getRange(`${colLetter(i+1)}:${colLetter(i+1)}`).format.columnWidth = w);
  sheet.freezePanes.freezeRows(startRow);
  return { endCol, endRow: startRow + rows.length };
}

// README
{
  const s = wb.worksheets.add("README");
  title(s, "FlowStudio 意图编码与案例库研究设计", "F", "用途：从教程与真实创作数据中归纳交互信号—候选意图—结果关系，形成可检索的 Intent Case Library，并反哺意图中间表示设计。版本：v1 / 2026-07-22");
  const rows = [
    ["核心原则", "可观察信号与解释性意图分开；意图保留 Top-k 假设、证据与反证；意图置信度不等于 Agent 执行权限。", "必须"],
    ["推荐人员", "2名主编码者 + 1名仲裁者/方法负责人；VLM负责全量预标注。", "建议"],
    ["推荐样本", "48个教程视频用于发现；12名创作者×2次真实会话用于验证；另设受控微任务作为已知目标数据。", "可按资源调整"],
    ["双人编码", "至少25%的 episode 进行分层盲法双人独立编码；金标准子集不能让编码者先看VLM答案。", "质量底线"],
    ["分析单位", "Intent Episode：从目标/焦点启动，到接受、拒绝、修复或意图转移结束；不是单击，也不是整段视频。", "必须"],
    ["使用顺序", "先修改 Study_Design 参数 → 建立 Sampling_Frame → 人工精标金标准 → VLM预标 → Human_Review → Reliability_QA → Case Library。", "工作流"],
    ["不应声称", "教程标注提供 expressed/pedagogical intent，不直接等于真实潜在心理意图；高层意图需真实会话与回忆验证。", "论文边界"]
  ];
  writeTable(s, 4, ["项目", "说明", "状态"], rows, [20, 82, 18]);
  s.getRange("A13:F13").merge();
  s.getRange("A13").values = [["工作簿结构"]];
  s.getRange("A13:F13").format = { fill: colors.green, font: { bold: true, color: colors.white } };
  const sheets = [
    ["Study_Design", "人员、视频、会话和episode数量的可修改参数与公式"],
    ["Sampling_Frame", "教程/真实会话/受控任务应覆盖的工具、任务、水平和结果类型"],
    ["Episode_Headers", "正式标注数据表的扁平化headers、定义、值类型与人工/VLM责任"],
    ["Annotation_Template", "可直接导入标注系统或作为Excel pilot的空白模板"],
    ["Codebook", "首版意图、交互功能、承诺、修复与权限类别"],
    ["VLM_Human_Workflow", "VLM预标、人类审核、盲法复核和主动学习流程"],
    ["Reliability_QA", "κ、Top-k recall、接受率、幻觉率、边界F1等计算"],
    ["IR_Mapping", "每类标注如何进入 Intent Hypothesis Graph 和检索索引"],
    ["Deliverables", "研究最终产出及其在DC1和系统中的用途"],
    ["Sources", "方法和工具来源链接"]
  ];
  writeTable(s, 14, ["Sheet", "作用"], sheets, [26, 94]);
}

// Study design
{
  const s = wb.worksheets.add("Study_Design");
  title(s, "人员与样本量设计", "H", "黄色单元格为可编辑假设；公式自动计算目标数量。推荐规模是 CHI 可执行方案，不是机械的统计标准。");
  const headers = ["阶段", "目的", "输入类型", "可编辑参数1", "数值1", "可编辑参数2", "数值2", "计算结果"];
  const rows = [
    ["A 教程发现", "归纳词表、信号—意图候选和常见操作链", "公开视频教程", "工具/平台家族", 4, "每家族视频数", 12, null],
    ["B 真实创作验证", "检验教程schema在自然探索、撤销和修复中的适用性", "屏幕+日志+语音+3D状态", "参与者人数", 12, "每人会话数", 2, null],
    ["C 受控微任务", "提供已知目标和约束的评估数据", "预设目标微任务", "参与者人数", 12, "每人任务数", 8, null],
    ["D 双人盲法复核", "计算人工一致性并建立金标准", "分层抽样episode", "预计总episode", 600, "重叠编码比例", 0.25, null],
    ["E VLM人工审核", "估计预标注节省量和严重错误", "全部episode", "预计总episode", 600, "人工审核比例", 1, null]
  ];
  writeTable(s, 4, headers, rows, [20, 42, 34, 24, 14, 24, 14, 24]);
  s.getRange("H5:H9").formulas = [
    ["=E5*G5"], ["=E6*G6"], ["=E7*G7"], ["=ROUNDUP(E8*G8,0)"], ["=ROUNDUP(E9*G9,0)"]
  ];
  s.getRange("E5:G9").format.fill = colors.lightAmber;
  s.getRange("G8:G9").format.numberFormat = "0%";
  s.getRange("H5:H9").format = { fill: colors.lightGreen, font: { bold: true }, numberFormat: "0" };
  const team = [
    ["Coder 1", "主编码者", "参与codebook训练；审核VLM预标；对盲法子集独立编码", "约60%–70% episode"],
    ["Coder 2", "主编码者", "盲法复核分层25%；参与疑难case讨论", "至少25% episode"],
    ["Coder 3/PI", "仲裁者", "解决分歧、维护codebook版本、避免类别漂移", "仅分歧及每轮校准"],
    ["VLM", "预标注器", "全量生成episode边界建议、观察信号、Top-k意图、证据/反证", "100% episode"],
    ["参与创作者", "意图验证者", "think-aloud与stimulated recall；确认高层目标、约束和承诺", "真实会话关键片段"]
  ];
  writeTable(s, 12, ["角色", "定位", "任务", "覆盖量"], team, [22, 22, 72, 26]);
}

// Sampling frame
{
  const s = wb.worksheets.add("Sampling_Frame");
  title(s, "采样覆盖框架", "H", "每条视频/会话在采样表中记录覆盖项；优先最大差异采样，不追求每格完全等量。教程建议目标48个。");
  const rows = [
    ["工具/平台", "DCC通用建模", "Blender/Maya/3ds Max等", "至少2个生态", "避免单工具心智模型偏差"],
    ["工具/平台", "雕刻/形变", "ZBrush/Nomad/Sculpt模式等", "至少1个生态", "覆盖局部形变与表面操作"],
    ["工具/平台", "AI/生成式3D", "文本/草图/局部编辑/生成修复", "可获得则至少8个视频", "与Mixed-Initiative直接相关"],
    ["任务内容", "对象与部位选择", "选择、遮罩、语义部位、层级", "必须", "目标指称与scope"],
    ["任务内容", "变换与空间参考系", "移动/旋转/缩放；世界/局部/视图/法线", "必须", "DC1核心"],
    ["任务内容", "几何建模与雕刻", "挤出、膨胀、平滑、拓扑、比例", "必须", "操作—效果映射"],
    ["任务内容", "材质/外观/灯光", "颜色、粗糙度、风格、构图", "建议", "非几何意图对照"],
    ["任务内容", "评价与比较", "旋转查看、A/B、停顿、局部检查", "必须", "epistemic/evaluative intent"],
    ["任务内容", "撤销、修复与迭代", "undo、重做、参数回调、替代工具", "必须", "接管边界与负案例"],
    ["创作者", "技能水平", "新手/中级/专家", "真实会话建议4/4/4", "比较心智模型差异"],
    ["创作者", "表达方式", "有旁白/无旁白；教学/自然创作", "均覆盖", "避免语言泄漏"],
    ["结果类型", "接受", "操作或Agent建议被保留", "必须", "成功案例"],
    ["结果类型", "修复", "意图大致正确但参数/范围/约束错误", "必须", "高价值监督"],
    ["结果类型", "拒绝", "用户撤销、抢回、换方案", "必须", "权限边界"],
    ["结果类型", "歧义", "多个候选无法从现有证据区分", "必须", "询问/预览策略"]
  ];
  writeTable(s, 4, ["维度", "覆盖类别", "例子", "建议配额", "研究作用"], rows, [20, 28, 58, 28, 42]);
}

// Episode header dictionary
const headerRows = [
  ["episode_id", "ID", "意图片段唯一ID", "text", "人工/自动", "主键；不可重复", "case_id"],
  ["video_id", "ID", "来源视频或会话ID", "text", "自动", "关联视频元数据", "provenance.video"],
  ["source_type", "来源", "tutorial/authentic/controlled/deployed_log", "category", "人工", "教程不能当latent intent真值", "provenance.source_type"],
  ["source_url_or_path", "来源", "公开视频URL或受控文件路径", "text", "自动", "注意隐私与授权", "provenance.uri"],
  ["creator_or_participant_id", "来源", "匿名创作者/参与者ID", "text", "人工", "不要存真实姓名", "provenance.actor_id"],
  ["tool_name", "上下文", "3D软件/FlowStudio/工具", "category", "VLM提议+人工", "记录版本", "context.tool"],
  ["tool_version", "上下文", "软件版本", "text", "人工/自动", "未知填NA", "context.tool_version"],
  ["expertise_level", "上下文", "novice/intermediate/expert/unknown", "category", "人工", "教程可为unknown", "context.expertise"],
  ["task_family", "上下文", "选择/变换/建模/雕刻/外观/评价/修复/AI协作", "multi-label", "人工", "可多选", "context.task_family"],
  ["design_stage", "上下文", "ideation/blockout/refinement/evaluation/finalization", "category", "VLM提议+人工", "允许unknown", "context.design_stage"],
  ["episode_start_sec", "分段", "episode开始秒", "number", "VLM提议+人工", "保留0.1秒", "observation.window.start"],
  ["episode_end_sec", "分段", "episode结束秒", "number", "VLM提议+人工", "结束于接受/修复/转移", "observation.window.end"],
  ["episode_duration_sec", "分段", "结束-开始", "formula", "自动", "end minus start", "observation.window.duration"],
  ["boundary_trigger_start", "分段", "焦点/目标/工具/语言启动线索", "category", "VLM提议+人工", "记录依据", "observation.boundary.start_trigger"],
  ["boundary_trigger_end", "分段", "accept/reject/repair/transition", "category", "VLM提议+人工", "记录依据", "observation.boundary.end_trigger"],
  ["object_id", "指称", "被操作的对象", "text", "日志优先+VLM", "稳定内部ID优先", "context.target.object"],
  ["semantic_part", "指称", "语义部位，如nose/leg/handle", "text", "VLM提议+人工", "无明确部位填whole_object", "context.target.part"],
  ["selection_scope", "指称", "vertex/face/region/part/object/group/scene", "category", "日志+人工", "与semantic_part分开", "context.target.scope"],
  ["active_tool", "信号", "当前工具/模式", "text", "日志优先+VLM", "记录工具切换", "observations.tool"],
  ["event_sequence", "信号", "按时间排列的选择、拖动、暂停、撤销等", "JSON/text", "日志+VLM", "每个事件带时间戳", "observations.events"],
  ["pointer_or_gesture_trajectory", "信号", "方向、距离、速度、曲率", "JSON/text", "日志优先", "不能仅靠视频估算精确值", "observations.trajectory"],
  ["camera_view", "信号", "front/side/top/perspective/custom", "category", "VLM+日志", "记录视角切换", "context.camera"],
  ["reference_frame", "空间", "world/local/view/surface_normal/semantic_axis/unknown", "category", "日志+人工", "DC1关键潜变量", "hypotheses.reference_frame"],
  ["pre_state_summary", "3D状态", "episode前对象与几何状态", "text/JSON", "状态差分+VLM", "避免只存截图", "context.pre_state"],
  ["post_state_summary", "3D状态", "episode后对象与几何状态", "text/JSON", "状态差分+VLM", "记录是否最终保留", "outcome.post_state"],
  ["geometry_or_parameter_delta", "3D状态", "transform/mesh/参数的机器可读差分", "JSON", "自动", "尽可能从系统日志获得", "observations.state_delta"],
  ["speech_transcript", "语言", "ASR或字幕", "text", "ASR+人工抽检", "保留时间戳", "observations.language.transcript"],
  ["explicit_intent_phrase", "语言", "创作者明确说出的目标短语", "text", "VLM提取+人工", "无明确表达填NA", "evidence.explicit_intent"],
  ["intent_source", "证据", "explicit_narration/think_aloud/recall/task_ground_truth/inferred", "category", "人工", "决定真值强度", "provenance.intent_source"],
  ["evidence_strength", "证据", "strong/medium/weak", "category", "人工", "不能等同模型confidence", "provenance.evidence_strength"],
  ["intent_level", "意图", "motor/operation/edit_goal/design_goal/project_goal", "multi-label", "VLM提议+人工", "层级可并存", "hypotheses.level"],
  ["candidate_intent_1", "意图", "Top-1候选意图", "text", "VLM提议+人工", "用受控词表+自由文本", "hypotheses[0].intent"],
  ["candidate_intent_1_confidence", "意图", "Top-1相对置信度", "number 0-1", "VLM+校准", "不可直接当真实概率", "hypotheses[0].confidence"],
  ["candidate_intent_1_evidence", "意图", "支持H1的时间戳/事件/语言", "text/JSON", "VLM提议+人工", "必须可追溯", "hypotheses[0].evidence"],
  ["candidate_intent_1_counterevidence", "意图", "反驳H1的信号", "text/JSON", "VLM提议+人工", "允许none", "hypotheses[0].counterevidence"],
  ["candidate_intent_2", "意图", "Top-2候选意图", "text", "VLM提议+人工", "歧义时必须填写", "hypotheses[1].intent"],
  ["candidate_intent_2_confidence", "意图", "Top-2相对置信度", "number 0-1", "VLM+校准", "与H1可不严格和为1", "hypotheses[1].confidence"],
  ["candidate_intent_3", "意图", "Top-3候选意图", "text", "VLM提议+人工", "可为空", "hypotheses[2].intent"],
  ["candidate_intent_3_confidence", "意图", "Top-3相对置信度", "number 0-1", "VLM+校准", "可为空", "hypotheses[2].confidence"],
  ["desired_effect", "意图", "希望产生的语义/视觉/功能效果", "text/category", "VLM提议+人工", "区别于工具操作", "hypotheses.desired_effect"],
  ["operation_family", "意图", "translate/rotate/scale/deform/sculpt/generate/compare/repair等", "category", "VLM提议+人工", "不等同高层意图", "hypotheses.operation_family"],
  ["interaction_function", "意图", "pragmatic/epistemic/evaluative/communicative/repair", "category", "人工确认", "关键功能维度", "hypotheses.function"],
  ["constraints_to_preserve", "意图", "对称、拓扑、体积、身份、风格等", "multi-label", "人工/回忆验证", "未观察到则标unknown", "hypotheses.constraints"],
  ["commitment_strength", "权限", "exploratory/tentative/committed/unknown", "category", "人工确认", "与intent confidence分开", "control.commitment"],
  ["ambiguity_level", "权限", "low/medium/high", "category", "人工+规则", "依据Top-k差距和缺失证据", "control.ambiguity"],
  ["action_reversibility", "权限", "easy/moderate/hard", "category", "系统规则", "权限决策输入", "control.reversibility"],
  ["destructiveness_or_scope_risk", "权限", "low/medium/high", "category", "系统规则+人工", "覆盖拓扑/批量修改等", "control.risk"],
  ["recommended_agent_authority", "权限", "observe/suggest/preview/ask/execute_reversible/confirm_before_commit", "category", "规则+人工", "不是意图标签", "control.authority"],
  ["agent_action_if_any", "结果", "Agent实际建议/预览/执行", "text/category", "日志", "无Agent填none", "outcome.agent_action"],
  ["user_response", "结果", "accept/modify/reject/undo/takeover/no_response", "category", "日志+人工", "接管事件核心", "outcome.user_response"],
  ["final_intent_status", "结果", "confirmed/revised/unresolved", "category", "人工", "由语言/结果/回忆决定", "outcome.intent_status"],
  ["repair_type", "结果", "intent/target/reference_frame/operation/parameter/scope/constraint/timing/authority", "multi-label", "人工", "不要把undo都视为意图错", "outcome.repair_type"],
  ["accepted_final_intent", "结果", "最终被确认或采用的意图", "text", "人工/回忆", "可能与H1不同", "outcome.accepted_intent"],
  ["case_quality", "质控", "gold/silver/weak/exclude", "category", "人工", "决定是否进入检索库", "provenance.quality"],
  ["vlm_model_and_prompt_version", "质控", "模型、prompt和schema版本", "text", "自动", "保证可复现", "provenance.vlm_version"],
  ["vlm_needs_review", "质控", "true/false", "boolean", "VLM", "低置信/冲突/高风险为true", "provenance.needs_review"],
  ["human_reviewer_id", "质控", "人工审核者匿名ID", "text", "自动", "审计字段", "provenance.reviewer"],
  ["human_edit_fields", "质控", "被人工改动的字段列表", "text/JSON", "自动", "用于计算接受率", "provenance.edits"],
  ["second_coder_id", "质控", "盲法复核者ID", "text", "自动", "非重叠样本填NA", "provenance.second_coder"],
  ["adjudication_status", "质控", "not_needed/pending/resolved", "category", "人工", "分歧处理", "provenance.adjudication"],
  ["coder_notes", "质控", "歧义、缺失信息和特殊情况", "text", "人工", "不可替代结构化字段", "provenance.notes"]
];

{
  const s = wb.worksheets.add("Episode_Headers");
  title(s, "Episode Annotation Headers 数据字典", "G", "每行定义一个正式数据字段。建议以该表生成JSON Schema和Label Studio界面；不要删除来源、证据、结果与质控字段。");
  writeTable(s, 4, ["header", "字段组", "定义", "数据类型", "主要标注者", "编码规则/注意", "Intent IR路径"], headerRows, [34, 16, 58, 20, 24, 54, 38]);
}

// Annotation template
{
  const s = wb.worksheets.add("Annotation_Template");
  const headers = headerRows.map(r => r[0]);
  const endCol = colLetter(headers.length);
  title(s, "Intent Episode 标注模板", endCol, "每行一个episode。首轮可在Excel中pilot；稳定后导入Label Studio/JSONL。示例行仅用于理解，应在正式标注前删除或复制到训练集。");
  s.getRange(`A4:${endCol}4`).values = [headers];
  header(s.getRange(`A4:${endCol}4`));
  s.getRange(`A4:${endCol}4`).format.rowHeight = 48;
  const example = new Array(headers.length).fill("");
  const set = (name, value) => { example[headers.indexOf(name)] = value; };
  set("episode_id", "EX-001"); set("video_id", "TUT-001"); set("source_type", "tutorial");
  set("tool_name", "Blender"); set("expertise_level", "unknown"); set("task_family", "transform|evaluation");
  set("design_stage", "refinement"); set("episode_start_sec", 12.4); set("episode_end_sec", 19.8);
  set("boundary_trigger_start", "focus_shift"); set("boundary_trigger_end", "undo"); set("object_id", "character_head");
  set("semantic_part", "nose"); set("selection_scope", "region"); set("active_tool", "grab/deform");
  set("event_sequence", "12.4 select nose; 13.1 drag outward; 15.2 pause; 19.8 undo"); set("camera_view", "side");
  set("reference_frame", "surface_normal"); set("explicit_intent_phrase", "make the nose project a little more");
  set("intent_source", "explicit_narration"); set("evidence_strength", "strong"); set("intent_level", "operation|edit_goal");
  set("candidate_intent_1", "increase nose protrusion"); set("candidate_intent_1_confidence", 0.65);
  set("candidate_intent_1_evidence", "outward drag; side view; explicit phrase"); set("candidate_intent_1_counterevidence", "immediate undo");
  set("candidate_intent_2", "explore profile silhouette"); set("candidate_intent_2_confidence", 0.28);
  set("desired_effect", "stronger side-profile projection"); set("operation_family", "deform"); set("interaction_function", "epistemic|pragmatic");
  set("constraints_to_preserve", "symmetry|face_identity"); set("commitment_strength", "tentative"); set("ambiguity_level", "medium");
  set("action_reversibility", "easy"); set("destructiveness_or_scope_risk", "low"); set("recommended_agent_authority", "preview");
  set("user_response", "undo"); set("final_intent_status", "revised"); set("repair_type", "parameter"); set("case_quality", "silver");
  set("vlm_needs_review", true); set("adjudication_status", "not_needed");
  s.getRange(`A5:${endCol}5`).values = [example];
  body(s.getRange(`A5:${endCol}5`));
  s.getRange(`M5`).formulas = [["=L5-K5"]];
  s.freezePanes.freezeRows(4);
  s.freezePanes.freezeColumns(3);
  for (let i=1;i<=headers.length;i++) s.getRange(`${colLetter(i)}:${colLetter(i)}`).format.columnWidth = i <= 5 ? 18 : 22;
  s.getRange("K:M").format.numberFormat = "0.0";
  for (const h of ["candidate_intent_1_confidence","candidate_intent_2_confidence","candidate_intent_3_confidence"]) {
    const c = colLetter(headers.indexOf(h)+1); s.getRange(`${c}5:${c}500`).format.numberFormat = "0.00";
  }
}

// Codebook
{
  const s = wb.worksheets.add("Codebook");
  title(s, "首版编码词表", "G", "本表是起点，先用10%–15%数据开放编码修订；类别冻结前不要批量标注全部视频。");
  const rows = [
    ["intent_level", "motor", "输入动作本身", "拖动、点击、捏合", "不要当成高层设计意图", "观察+推断"],
    ["intent_level", "operation", "工具/几何操作目标", "沿法线膨胀区域", "与desired_effect区分", "推断"],
    ["intent_level", "edit_goal", "局部可见效果", "让鼻子更突出", "最常用案例检索层", "推断+验证"],
    ["intent_level", "design_goal", "风格、语义、功能目标", "让角色更卡通", "教程旁白可支持但不等于latent truth", "推断+回忆"],
    ["intent_level", "project_goal", "作品/活动层目标", "探索角色概念", "通常跨多个episode", "回忆/任务"],
    ["interaction_function", "pragmatic", "直接改变作品", "执行形变", "可能同时含其他功能", "推断"],
    ["interaction_function", "epistemic", "通过操作获取信息", "旋转查看、试参数", "不是失败或噪声", "推断"],
    ["interaction_function", "evaluative", "比较或判断结果", "A/B、停顿、检查轮廓", "常与epistemic相邻", "观察+推断"],
    ["interaction_function", "communicative", "向Agent表达目标/指称", "涂抹区域提示Agent", "动作可同时是操作与沟通", "推断+语言"],
    ["interaction_function", "repair", "纠正先前人或Agent结果", "undo后换工具", "必须进一步编码repair_type", "观察+推断"],
    ["commitment", "exploratory", "试探，不表示提交", "快速尝试后比较", "Agent仅建议/预览", "人工确认"],
    ["commitment", "tentative", "有偏好但仍可调整", "小幅修改后停顿", "可预览，不自动提交高风险动作", "人工确认"],
    ["commitment", "committed", "目标及执行意愿明确", "明确命令并接受", "仍受风险/可逆性限制", "语言+结果"],
    ["repair_type", "intent", "Agent/编码者理解的目标错误", "想拉长却做成变粗", "与parameter错误区分", "人工/回忆"],
    ["repair_type", "reference_frame", "空间坐标系理解错误", "沿世界轴而非表面法线", "DC1核心失败", "日志+人工"],
    ["repair_type", "parameter", "方向/目标对但幅度等参数错误", "突出太多", "不要记成意图错误", "观察+结果"],
    ["repair_type", "constraint", "破坏应保留属性", "破坏对称或身份", "触发权限降级", "人工/回忆"],
    ["repair_type", "timing", "介入时机不合适", "探索中自动提交", "Mixed-Initiative关键", "结果+访谈"],
    ["authority", "observe", "只观察和更新假设", "高歧义或抢回后", "最低权限", "策略"],
    ["authority", "suggest", "提供候选解释或建议", "展示2个可能目标", "不改变作品", "策略"],
    ["authority", "preview", "生成可撤销预览", "ghost/branch结果", "默认安全介入", "策略"],
    ["authority", "ask", "请求必要澄清", "候选接近且影响大", "避免频繁打断", "策略"],
    ["authority", "execute_reversible", "执行容易撤销的小范围动作", "明确且低风险", "需高commitment", "策略"],
    ["authority", "confirm_before_commit", "提交前明确确认", "拓扑/批量/覆盖成果", "高风险边界", "策略"]
  ];
  writeTable(s, 4, ["维度", "代码", "定义", "例子", "边界规则", "证据类型"], rows, [22, 24, 48, 48, 60, 24]);
}

// Workflow
{
  const s = wb.worksheets.add("VLM_Human_Workflow");
  title(s, "VLM—人工协同标注流程", "H", "VLM是预标注器，不是latent intent真值提供者。金标准子集需盲于VLM输出，以便独立估计模型和人工质量。");
  const rows = [
    [1, "数据同步", "视频、关键帧、ASR、操作日志、3D状态差分", "切分候选episode", "检查同步误差", "同步数据包", "全部"],
    [2, "人工种子集", "最大差异抽样30–50 episode", "无", "两人讨论并精标，修订codebook", "schema v0.1", "30–50"],
    [3, "金标准扩展", "约100–200 episode", "不得先看VLM答案", "双人独立编码+仲裁", "gold set v1", "100–200"],
    [4, "VLM预标", "新episode+检索到的5–15个示例", "边界、可观察信号、Top-k意图、证据/反证、review flag", "不直接接受高层意图", "silver candidates", "全部"],
    [5, "人工审核", "VLM JSON", "保留模型原始版本", "接受/修改/驳回；记录被改字段", "reviewed cases", "全部"],
    [6, "盲法复核", "分层25% episode", "无", "Coder 2独立编码", "reliability subset", "≥25%"],
    [7, "仲裁", "分歧和严重错误", "汇总分歧模式", "Coder 3依据codebook裁决", "adjudicated gold", "按需"],
    [8, "主动学习", "低置信、模型分歧、高风险、罕见case", "排序待审样本", "人工优先审核", "下一轮训练/示例池", "持续"],
    [9, "冻结版本", "稳定后的schema+codebook", "批量导出JSONL/Parquet", "抽检、版本锁定", "Case Library v1", "正式分析前"]
  ];
  writeTable(s, 4, ["步骤", "阶段", "输入", "VLM任务", "人工任务", "输出", "覆盖"], rows, [10, 22, 48, 55, 55, 30, 16]);
}

// Reliability and QA
{
  const s = wb.worksheets.add("Reliability_QA");
  title(s, "一致性与VLM质量计算", "I", "黄色单元格填入计数；绿色单元格自动计算。正式报告中按字段分别计算，不应只报告一个总体数字。");
  const headers = ["指标", "适用字段", "输入N", "输入1", "输入2", "输入3", "计算结果", "建议解释", "备注"];
  const rows = [
    ["Cohen κ（二分类示例）", "单一categorical字段", 100, 82, 55, 53, null, "≥0.80较强；0.67–0.80可暂用并修订；勿机械阈值化", "D=一致数；E=CoderA yes；F=CoderB yes"],
    ["Top-1 accuracy", "VLM候选意图", 100, 68, 0, 0, null, "仅辅助；不能代替Top-k与校准", "D=Top1正确数"],
    ["Top-3 recall", "VLM候选意图", 100, 89, 0, 0, null, "衡量正确意图是否进入候选集合", "D=Top3包含金标准数"],
    ["字段接受率", "全部VLM字段", 3000, 2280, 0, 0, null, "越高表示人工无需改动的字段越多", "D=未修改字段数"],
    ["人工字段修改率", "全部VLM字段", 3000, 720, 0, 0, null, "按字段组拆解更有用", "D=被修改字段数"],
    ["严重幻觉率", "目标/语言/意图证据", 600, 18, 0, 0, null, "任何虚构界面事件、语言或证据均计入", "D=含严重幻觉episode数"],
    ["Episode边界F1", "事件分段", 50, 42, 8, 10, null, "允许±2秒匹配窗口，并同时报告平均边界偏差", "D=TP；E=FP；F=FN"],
    ["约束漏报率", "constraints_to_preserve", 120, 14, 0, 0, null, "接管安全关键指标，越低越好", "D=漏报数"],
    ["权限严重错误率", "recommended_agent_authority", 120, 7, 0, 0, null, "把应询问/预览标为自动执行属于严重错误", "D=严重错误数"]
  ];
  writeTable(s, 4, headers, rows, [28, 32, 14, 14, 14, 14, 18, 55, 50]);
  s.getRange("C5:F13").format.fill = colors.lightAmber;
  s.getRange("G5:G13").formulas = [
    ["=IFERROR(((D5/C5)-((E5/C5)*(F5/C5)+((C5-E5)/C5)*((C5-F5)/C5)))/(1-((E5/C5)*(F5/C5)+((C5-E5)/C5)*((C5-F5)/C5))),0)"],
    ["=IFERROR(D6/C6,0)"], ["=IFERROR(D7/C7,0)"], ["=IFERROR(D8/C8,0)"],
    ["=IFERROR(D9/C9,0)"], ["=IFERROR(D10/C10,0)"],
    ["=IFERROR(2*D11/(2*D11+E11+F11),0)"], ["=IFERROR(D12/C12,0)"], ["=IFERROR(D13/C13,0)"]
  ];
  s.getRange("G5:G13").format = { fill: colors.lightGreen, font: { bold: true }, numberFormat: "0.0%" };
  s.getRange("A16:I16").merge(); s.getRange("A16").values = [["按数据类型选择指标"]];
  s.getRange("A16:I16").format = { fill: colors.green, font: { bold: true, color: colors.white } };
  const methods = [
    ["单一类别", "Cohen κ（2人）或Krippendorff α（多人/缺失）", "intent function、commitment、authority"],
    ["多标签", "每标签二元κ/α + micro/macro F1 + Jaccard", "constraints、repair_type、intent_level"],
    ["连续数值", "ICC/MAE/相关性；不要只报告相关", "时间边界、拖动幅度"],
    ["时间分段", "±2秒容忍下Boundary Precision/Recall/F1 + 平均偏差", "episode start/end"],
    ["候选意图", "Top-1 accuracy + Top-k recall + MRR", "candidate_intent_1..3"],
    ["置信度", "Brier score/ECE/可靠性曲线", "VLM confidence"],
    ["接管决策", "严重错误率、过度介入率、漏介入率、用户撤销率", "agent authority"]
  ];
  writeTable(s, 17, ["字段类型", "推荐计算", "例子"], methods, [26, 72, 48]);
}

// IR mapping
{
  const s = wb.worksheets.add("IR_Mapping");
  title(s, "从标注到意图中间表示", "H", "编码结果不是最终ontology本身；通过开放编码、可靠性和失败案例迭代，决定哪些字段成为IR核心、检索键、运行时状态或仅作研究元数据。");
  const rows = [
    ["Context", "object_id, semantic_part, selection_scope, design_stage, tool, camera", "context", "是", "过滤+结构相似度", "中", "当前状态覆盖", "限制候选意图空间"],
    ["Observations", "event_sequence, trajectory, state_delta, speech", "observations[]", "是", "轨迹+语义检索", "高", "追加事件", "保留原始证据，不提前压成标签"],
    ["Reference frame", "reference_frame", "hypotheses.reference_frame", "是", "高权重结构键", "高", "随证据更新", "3D心智模型核心潜变量"],
    ["Intent hypotheses", "candidate_intent_1..3 + confidence", "hypotheses[]", "是", "语义检索", "高", "Bayesian/LLM更新", "必须允许竞争、refine和supersede"],
    ["Evidence graph", "evidence, counterevidence, intent_source", "evidence[] + links", "是", "解释性重排", "高", "不可覆盖原始证据", "抑制LLM过度自信"],
    ["Desired effect", "desired_effect, operation_family, scope", "hypotheses.effect/action", "是", "主要检索键", "高", "由结果修订", "连接语义目标与可执行操作"],
    ["Constraints", "constraints_to_preserve", "hypotheses.constraints", "是", "硬过滤/惩罚", "高", "仅经确认写长期记忆", "决定生成和接管安全"],
    ["Interaction function", "pragmatic/epistemic/evaluative/communicative/repair", "hypotheses.function", "是", "对比案例键", "高", "episode内可变化", "区分操作与探索"],
    ["Commitment", "commitment_strength", "control.commitment", "是", "策略检索键", "高", "短期状态", "不与intent confidence合并"],
    ["Risk & authority", "ambiguity, reversibility, risk, authority", "control", "是", "权限案例检索", "高", "用户抢回立即降级", "人机接管边界"],
    ["Outcome", "user_response, final status, repair type, accepted intent", "outcome", "训练/评估时", "结果重排", "高", "episode结束写入", "case质量与学习信号"],
    ["Provenance", "source type, model/prompt, reviewer, quality", "provenance", "否", "质量过滤", "高", "不可丢失", "区分教程表达、推断和创作者确认"]
  ];
  writeTable(s, 4, ["IR模块", "来源headers", "建议JSON路径", "运行时可见", "案例检索作用", "重要性", "更新规则", "设计意义"], rows, [25, 68, 34, 18, 30, 14, 34, 48]);
}

// Deliverables
{
  const s = wb.worksheets.add("Deliverables");
  title(s, "最终产出与使用方式", "G", "每项产出都对应论文方法、系统实现或评估；避免只得到一堆视频标签而不能进入Agent。");
  const rows = [
    ["Intent Codebook v1", "稳定的维度、类别、定义、边界和例子", "Episode_Headers + Codebook", "DC1理论构件", "修订历史+一致性证据", "论文方法/附录"],
    ["Gold Episode Set", "双人编码并仲裁的100–200+ episode", "JSONL/Parquet", "VLM评估、prompt示例、后续微调", "盲法建立", "模型与方法验证"],
    ["Silver Episode Set", "VLM预标且人工审核的全量案例", "JSONL/Parquet", "Case Library主体", "保留VLM原始输出和编辑记录", "检索与分析"],
    ["Intent Hypothesis Graph Schema", "context-observation-hypotheses-control-outcome结构", "JSON Schema", "Agent运行时中间表示", "从高一致性且有系统用途的字段提炼", "核心系统贡献"],
    ["Case Retrieval Index", "成功、近失、失败、替代意图和用户个性案例", "向量+结构化metadata", "给LLM提供支持与反例", "按quality/source过滤", "推理时RAG/CBR"],
    ["Takeover Boundary Dataset", "承诺、风险、权限、抢回、撤销与修复", "episode子集", "学习何时观察/建议/预览/询问/执行", "不能仅来自教程", "Mixed-Initiative贡献"],
    ["VLM Annotation Prompt Pack", "schema、正例、歧义例、失败例、证据要求", "版本化prompt", "批量预标注", "每轮记录模型与版本", "可复现流程"],
    ["Evaluation Benchmark", "留出且不进入检索示例的gold cases", "固定test split", "Top-k、校准、约束、权限错误评估", "按创作者/视频划分避免泄漏", "实证结果"],
    ["Design Implications", "信号组合、参考系、修复、权限边界和记忆策略", "主题/命题", "界面与Agent设计原则", "由跨来源三角验证支持", "论文discussion"]
  ];
  writeTable(s, 4, ["产出", "内容", "格式", "系统用途", "质量要求", "论文用途"], rows, [30, 58, 28, 54, 50, 32]);
}

// Sources
{
  const s = wb.worksheets.add("Sources");
  title(s, "方法与工具来源", "E", "链接用于核查方法基础和现成工具能力；教程样本本身应在正式Sampling表中另行记录URL、日期和纳入理由。");
  const rows = [
    ["Interaction Analysis", "Jordan & Henderson (1995)", "细粒度视频交互分析", "https://doi.org/10.1207/s15327809jls0401_2", "视频是可分析互动记录，不等于直接读取心理状态"],
    ["Event Segmentation Theory", "Zacks et al. (2007)", "连续活动切分为事件", "https://doi.org/10.1037/0033-2909.133.2.273", "支持Intent Episode边界设计"],
    ["Case-Based Reasoning", "Aamodt & Plaza (1994)", "retrieve-reuse-revise-retain", "https://doi.org/10.3233/AIC-1994-7104", "支持case库生命周期"],
    ["Plan Recognition as Planning", "Ramírez & Geffner (2009)", "用观察序列比较候选目标", "https://www.ijcai.org/Proceedings/09/Papers/296.pdf", "支持Top-k候选意图而非单标签"],
    ["Label Studio", "Official documentation", "模型预标注和人工审核", "https://labelstud.io/guide/ml.html", "推荐pilot工具"],
    ["CVAT", "Official documentation", "视频/空间区域/自动标注", "https://docs.cvat.ai/docs/annotation/auto-annotation/automatic-annotation/", "需要逐帧空间标注时使用"],
    ["FiftyOne", "Official documentation", "数据集浏览、模型分析与标注集成", "https://docs.voxel51.com/integrations/annotation.html", "后期大规模数据质控"]
  ];
  writeTable(s, 4, ["主题", "来源", "作用", "URL", "本研究中的用法"], rows, [32, 38, 42, 72, 62]);
}

// Global finishing
for (let i=0; i<11; i++) {
  const s = wb.worksheets.getItemAt(i);
  const used = s.getUsedRange();
  if (used) used.format.font = { name: "Aptos", size: 10 };
}

await fs.mkdir(outputDir, { recursive: true });
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(outputPath);

// Compact verification and render every sheet.
const inspect = await wb.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 });
console.log(inspect.ndjson);
const errorScan = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula errors" });
console.log(errorScan.ndjson);
for (let i=0; i<11; i++) {
  const s = wb.worksheets.getItemAt(i);
  const preview = await wb.render({ sheetName: s.name, autoCrop: "all", scale: 0.75, format: "png" });
  await fs.writeFile(`${outputDir}/preview_${String(i+1).padStart(2,"0")}_${s.name}.png`, new Uint8Array(await preview.arrayBuffer()));
}
console.log(outputPath);
