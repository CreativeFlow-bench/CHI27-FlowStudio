import fs from "node:fs/promises";

const inspectPath =
  "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/three_video_cases/FlowStudio_八视频_behavior_state案例库.xlsx.inspect.ndjson";
const outPath =
  "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/intent_annotation_frontend/cases.json";

const lines = (await fs.readFile(inspectPath, "utf8")).split("\n").filter(Boolean);
const table = lines.map((line) => JSON.parse(line)).find((item) => item.kind === "table");
if (!table?.values?.length) throw new Error("Cannot find case table in inspect file.");

const [header, ...rows] = table.values;
const index = Object.fromEntries(header.map((name, i) => [name, i]));

const stateMap = {
  exploration: "early_exploration",
  "coarse forming": "coarse_forming",
  "local refinement": "local_refinement",
  "relationship adjustment": "relationship_adjustment",
  "workflow transition": "early_exploration",
  repair: "relationship_adjustment",
  evaluation: "evaluation",
};

const stateLabels = {
  early_exploration: "Early Exploration",
  coarse_forming: "Coarse Forming",
  local_refinement: "Local Refinement",
  relationship_adjustment: "Relationship Adjustment",
  material_refinement: "Material Refinement",
  evaluation: "Evaluation",
};

const routeMap = {
  early_exploration: ["generate_breakthrough_reference_variants", "生成突破性的参考变体"],
  coarse_forming: ["generate_contour_variants", "生成轮廓变体"],
  local_refinement: ["generate_local_variants", "生成局部变体"],
  relationship_adjustment: ["generate_local_variants", "生成局部变体"],
  material_refinement: ["generate_material_variants", "生成材质变体"],
  evaluation: ["no_intervention", "不介入"],
};

function excelTimeToText(value) {
  const seconds = Math.round(Number(value) * 86400);
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function signalLabels(text) {
  const labels = [];
  const lower = text.toLowerCase();
  const add = (code, label, group) => labels.push({ code, label, group });
  if (/orbit|rotate|旋转|view|视图|camera|相机/.test(lower)) add("global_orbit", "全局旋转", "空间与视口信号");
  if (/zoom|拉近|局部|face|面部|眼|手指|slot|vent|button|毛球|胡须/.test(lower)) add("local_zoom", "局部放大", "空间与视口信号");
  if (/select|选中|选择/.test(lower)) add("select_part", "选择局部", "空间与视口信号");
  if (/brush|笔刷|mask|遮罩/.test(lower)) add("small_brush", "小范围笔刷/遮罩", "空间与视口信号");
  if (/undo|撤销|redo|重做/.test(lower)) add("undo_redo_loop", "撤销/重做循环", "行为与时间信号");
  if (/reference|参考|spotlight|对齐/.test(lower)) add("match_reference", "贴合参考", "语义与认知信号");
  if (/material|paint|shading|roughness|metalness|材质|颜色|色|paint|着色/.test(lower))
    add("surface_change", "表面/材质变化", "语义与认知信号");
  if (/compare|inspect|evaluate|review|检查|评估|观察/.test(lower)) add("long_compare", "长时间比较", "行为与时间信号");
  return [...new Map(labels.map((item) => [item.code, item])).values()];
}

const cases = rows.map((row) => {
  const oldState = row[index.state];
  const stateCode = stateMap[oldState] ?? "early_exploration";
  const [routeCode, routeLabel] = routeMap[stateCode];
  const rawSignals = String(row[index["signals（逐条）"]] ?? "")
    .split("\n")
    .map((line) => line.replace(/^\d+\.\s*/, "").trim())
    .filter(Boolean);
  return {
    case_id: row[index.case_id],
    video_id: row[index.video],
    software: row[index.software],
    source_url: row[index["source（带时间点）"]],
    start_time: excelTimeToText(row[index.start]),
    end_time: excelTimeToText(row[index.end]),
    episode_summary: row[index.result],
    state: {
      code: stateCode,
      label: stateLabels[stateCode],
      original_label: oldState,
    },
    creativeflow_route: {
      code: routeCode,
      label: routeLabel,
    },
    signals: signalLabels(rawSignals.join("\n")),
    raw_signals: rawSignals,
    retrieval_text: [
      stateLabels[stateCode],
      routeLabel,
      rawSignals.join("；"),
      row[index.result],
    ].join("\n"),
    human_verified: true,
  };
});

if (cases.length !== 58) throw new Error(`Expected 58 cases, got ${cases.length}`);
await fs.writeFile(outPath, `${JSON.stringify(cases, null, 2)}\n`);
console.log(JSON.stringify({ outPath, cases: cases.length }, null, 2));
