import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const oldJson = "/Users/primav/.codex/attachments/4068a9a2-3469-4e7c-a835-cd9ffbf0c65d/pasted-text.txt";
const newJson = "/Users/primav/.codex/attachments/3fdf44b9-6140-4f54-ba71-dd8552ede8af/pasted-text.txt";
const outputDir = "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/episode_candidates";
const outputPath = `${outputDir}/FlowStudio_behavior_episode候选标注表.xlsx`;

const oldRows = JSON.parse(await fs.readFile(oldJson, "utf8"));
const newRows = JSON.parse(await fs.readFile(newJson, "utf8"));
const rows = [...oldRows, ...newRows];

const recommended = new Map([
  ["blender_character_blockout_01", "核心"],
  ["blender_character_blockout_02", "核心"],
  ["blender_character_blockout_03", "核心"],
  ["blender_character_blockout_04", "核心"],
  ["blender_character_blockout_05", "核心"],
  ["blender_character_blockout_06", "核心"],
  ["blender_character_blockout_07", "备选"],
  ["blender_character_blockout_08", "备选"],
  ["blender_character_blockout_09", "备选"],
  ["blender_character_blockout_10", "核心"],
  ["blender_character_blockout_11", "备选"],
  ["blender_character_blockout_12", "核心"],
  ["blender_character_blockout_13", "核心"],
  ["blender_character_blockout_14", "核心"],
  ["blender_character_blockout_15", "核心"],
  ["blender_character_blockout_16", "核心"],
]);

function toSeconds(value) {
  const [m, s] = value.split(":").map(Number);
  return m * 60 + s;
}

const headers = [
  "candidate_id",
  "video_id",
  "start_time",
  "end_time",
  "duration",
  "clip_url",
  "pre_state",
  "observable_signals",
  "target_visible / Where",
  "observable_result / What",
  "建议保留",
  "人工保留",
];

const values = rows.map((row) => {
  const startSeconds = toSeconds(row.start_time);
  const endSeconds = toSeconds(row.end_time);
  return [
    row.candidate_id,
    row.video_id,
    startSeconds / 86400,
    endSeconds / 86400,
    null,
    `${row.source_url}&t=${startSeconds}s`,
    row.pre_state,
    row.observable_signals.join("\n• ").replace(/^/, "• "),
    row.target_visible,
    row.observable_result,
    recommended.get(row.candidate_id) ?? "待定",
    "",
  ];
});

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("候选片段");
sheet.showGridLines = false;
sheet.getRange(`A1:L${rows.length + 1}`).values = [headers, ...values];

for (let row = 2; row <= rows.length + 1; row++) {
  sheet.getRange(`E${row}`).formulas = [[`=D${row}-C${row}`]];
}

sheet.getRange("A1:T1").format = {
  fill: "#243B53",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  verticalAlignment: "center",
};
sheet.getRange(`A2:L${rows.length + 1}`).format = {
  font: { color: "#243B53" },
  verticalAlignment: "top",
};
sheet.getRange(`C2:E${rows.length + 1}`).format.numberFormat = "[m]:ss";
sheet.getRange(`G2:J${rows.length + 1}`).format.wrapText = true;
sheet.getRange(`K2:L${rows.length + 1}`).format.horizontalAlignment = "center";

sheet.getRange(`K2:K${rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "核心",
  format: { fill: "#D9EAD3", font: { color: "#274E13", bold: true } },
});
sheet.getRange(`K2:K${rows.length + 1}`).conditionalFormats.add("containsText", {
  text: "备选",
  format: { fill: "#FFF2CC", font: { color: "#7F6000" } },
});

sheet.getRange(`L2:L${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["保留", "排除", "待讨论"] },
};
const widths = {
  A: 30, B: 15, C: 11, D: 11, E: 11, F: 28,
  G: 34, H: 44, I: 26, J: 38, K: 12, L: 12,
};
for (const [col, width] of Object.entries(widths)) {
  sheet.getRange(`${col}:${col}`).format.columnWidth = width;
}
sheet.getRange("1:1").format.rowHeight = 36;
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(2);
const table = sheet.tables.add(`A1:L${rows.length + 1}`, true, "EpisodeCandidates");
table.style = "TableStyleMedium2";
table.showFilterButton = true;

const labels = workbook.worksheets.add("分类标注");
labels.showGridLines = false;
const labelHeaders = [
  "candidate_id",
  "clip",
  "人工保留",
  "Where / target_level",
  "What / desired_effect",
  "How / operation_family",
  "behavior_pattern",
  "creative_stage",
  "divergence_need",
  "CreativeFlow_route",
  "intervention_boundary",
  "human_verified",
  "reviewer_notes",
];
labels.getRange(`A1:M${rows.length + 1}`).values = [
  labelHeaders,
  ...rows.map((row) => [
    row.candidate_id,
    `${row.source_url}&t=${toSeconds(row.start_time)}s`,
    "", "", "", "", "", "", "", "", "", "", "",
  ]),
];
labels.getRange("A1:M1").format = {
  fill: "#243B53",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  verticalAlignment: "center",
};
labels.getRange(`A2:M${rows.length + 1}`).format.verticalAlignment = "top";
labels.getRange(`D2:M${rows.length + 1}`).format.wrapText = true;
labels.getRange(`D2:D${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["viewport", "whole_object", "object_part", "surface_region", "geometry_element", "material_texture", "scene", "unknown"] },
};
labels.getRange(`C2:C${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["保留", "排除", "待讨论"] },
};
labels.getRange(`H2:H${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["vision", "inspiration", "ideation", "development", "refinement", "evaluation", "其他/待定"] },
};
labels.getRange(`I2:I${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["none", "low", "medium", "high", "unknown"] },
};
labels.getRange(`L2:L${rows.length + 1}`).dataValidation = {
  rule: { type: "list", values: ["yes", "partial", "no"] },
};
const labelWidths = {
  A: 30, B: 14, C: 12, D: 22, E: 26, F: 26, G: 28,
  H: 18, I: 16, J: 28, K: 28, L: 16, M: 34,
};
for (const [col, width] of Object.entries(labelWidths)) {
  labels.getRange(`${col}:${col}`).format.columnWidth = width;
}
labels.getRange("1:1").format.rowHeight = 36;
labels.freezePanes.freezeRows(1);
labels.freezePanes.freezeColumns(3);
const labelTable = labels.tables.add(`A1:M${rows.length + 1}`, true, "EpisodeLabels");
labelTable.style = "TableStyleMedium2";
labelTable.showFilterButton = true;

const guide = workbook.worksheets.add("标注说明");
guide.showGridLines = false;
guide.getRange("A1:D1").merge();
guide.getRange("A1").values = [["FlowStudio behavior episode 候选筛选说明"]];
guide.getRange("A1:D1").format = {
  fill: "#243B53",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  verticalAlignment: "center",
};
guide.getRange("1:1").format.rowHeight = 34;
guide.getRange("A3:D10").values = [
  ["步骤", "要做什么", "填写列", "判断标准"],
  ["1", "点击clip_url，只观看对应时间片段", "—", "无需重看完整视频"],
  ["2", "判断候选是否进入案例池", "人工保留", "前端可观察、有主要目标、有可观察结果"],
  ["3", "确认Gemini描述是否真实可见", "human_verified", "快捷键或工具不可见时填partial/no"],
  ["4", "抽象操作方式", "How / operation_family", "如inspect、transform、deform、refine、align、repair"],
  ["5", "归纳行为模式", "behavior_pattern", "避免保留眼睛、耳朵等教程专有语义"],
  ["6", "标注创意阶段与发散需求", "creative_stage、divergence_need", "无法判断时保持unknown/待定"],
  ["7", "填写系统路由和介入边界", "CreativeFlow_route、intervention_boundary", "必须包含不介入的负案例"],
];
guide.getRange("A3:D3").format = {
  fill: "#486581",
  font: { bold: true, color: "#FFFFFF" },
};
guide.getRange("A3:D10").format.wrapText = true;
guide.getRange("A:A").format.columnWidth = 10;
guide.getRange("B:B").format.columnWidth = 34;
guide.getRange("C:C").format.columnWidth = 34;
guide.getRange("D:D").format.columnWidth = 48;
guide.getRange("A1:D10").format.verticalAlignment = "top";
guide.freezePanes.freezeRows(3);

await fs.mkdir(outputDir, { recursive: true });

const inspection = await workbook.inspect({
  kind: "table",
  range: "候选片段!A1:L17",
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 12,
  maxChars: 12000,
});
console.log(inspection.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

for (const [sheetName, range, file] of [
  ["候选片段", "A1:L17", "preview_candidates.png"],
  ["分类标注", "A1:M17", "preview_labels.png"],
  ["标注说明", "A1:D10", "preview_guide.png"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${file}`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`SAVED ${outputPath}`);
