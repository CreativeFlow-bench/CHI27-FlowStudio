import fs from "node:fs/promises";

const casesPath =
  "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/intent_annotation_frontend/cases.json";

const baseCases = JSON.parse(await fs.readFile(casesPath, "utf8"));

const videos = [
  {
    prefix: "bilibili_3dsmax_cartoon_robot",
    video_id: "BV17JYYzsEPG",
    software: "3ds Max",
    title: "【3dmax角色建模】简单的卡通机器人建模全流程制作，适合初学者的3dmax入门案例！",
    url: "https://www.bilibili.com/video/BV17JYYzsEPG/",
    windows: [
      ["00:00", "08:00", "开场与参考/建模目标确认"],
      ["08:00", "18:00", "机器人头部与主体大体块搭建"],
      ["18:00", "28:00", "躯干与四肢基础比例建立"],
      ["28:00", "38:00", "关节、手脚等局部结构建模"],
      ["38:00", "48:00", "面部/装饰部件细化"],
      ["48:00", "58:00", "整体比例与部件关系调整"],
      ["58:00", "68:00", "模型细节补充与硬边处理"],
      ["68:00", "78:00", "材质或颜色初步设置"],
      ["78:00", "88:00", "整体效果检查与修改"],
      ["88:00", "98:00", "局部问题修正与收尾"],
      ["98:00", "108:00", "渲染/展示准备"],
      ["108:00", "114:50", "最终效果评估"],
    ],
  },
  {
    prefix: "bilibili_zbrush_luguo_figure",
    video_id: "BV1zZsjevEtK",
    software: "ZBrush",
    title: "【zbrush手办建模】20分钟建模一个价值498的手办外包《果宝特工》陆小果，ZB手办模型雕刻教程！",
    url: "https://www.bilibili.com/video/BV1zZsjevEtK/",
    windows: [
      ["00:00", "03:30", "角色参考与基础体块建立"],
      ["03:30", "07:00", "头身比例和大轮廓雕刻"],
      ["07:00", "10:30", "五官/服饰局部细化"],
      ["10:30", "14:00", "配件与角色部件关系调整"],
      ["14:00", "18:00", "表面细节和造型修整"],
      ["18:00", "22:30", "最终检查与展示"],
    ],
  },
  {
    prefix: "bilibili_maya_mecha_helmet",
    video_id: "BV1wfh1z8EVE",
    software: "Maya",
    title: "【Maya建模】超帅机甲头盔模型制作，次世代硬表面布线基础教学",
    url: "https://www.bilibili.com/video/BV1wfh1z8EVE/",
    windows: [
      ["00:00", "08:00", "参考与硬表面建模目标确认"],
      ["08:00", "18:00", "头盔主体大轮廓搭建"],
      ["18:00", "28:00", "面罩/侧面大结构切分"],
      ["28:00", "38:00", "硬表面板块局部细化"],
      ["38:00", "48:00", "边线、倒角和支撑线处理"],
      ["48:00", "58:00", "多部件比例与结构关系调整"],
      ["58:00", "68:00", "细节件、孔洞和装饰结构添加"],
      ["68:00", "78:00", "布线检查与局部修正"],
      ["78:00", "88:00", "整体视觉效果评估"],
      ["88:00", "94:52", "收尾展示与最终检查"],
    ],
  },
];

const stateForSummary = (summary) => {
  if (/参考|目标|开场/.test(summary)) return ["early_exploration", "Early Exploration"];
  if (/大体块|大轮廓|主体|基础|比例建立/.test(summary)) return ["coarse_forming", "Coarse Forming"];
  if (/材质|颜色|表面/.test(summary)) return ["material_refinement", "Material Refinement"];
  if (/关系|比例|调整|修正|布线检查/.test(summary)) return ["relationship_adjustment", "Relationship Adjustment"];
  if (/评估|展示|检查|最终/.test(summary)) return ["evaluation", "Evaluation"];
  return ["local_refinement", "Local Refinement"];
};

const routeForState = {
  early_exploration: ["generate_breakthrough_reference_variants", "生成突破性的参考变体"],
  coarse_forming: ["generate_contour_variants", "生成轮廓变体"],
  local_refinement: ["generate_local_variants", "生成局部变体"],
  relationship_adjustment: ["generate_local_variants", "生成局部变体"],
  material_refinement: ["generate_material_variants", "生成材质变体"],
  evaluation: ["no_intervention", "不介入"],
};

const signalsForSummary = (summary) => {
  const signals = [];
  const add = (code, label, group) => signals.push({ code, label, group });
  if (/参考|目标/.test(summary)) add("match_reference", "贴合参考", "语义与认知信号");
  if (/大体块|大轮廓|主体|比例/.test(summary)) add("zoom_out", "缩小看整体", "空间与视口信号");
  if (/局部|细化|边线|倒角|孔洞|五官|配件/.test(summary)) add("local_zoom", "局部放大", "空间与视口信号");
  if (/调整|修正|检查/.test(summary)) add("repeated_micro_edit", "反复微调", "行为与时间信号");
  if (/材质|颜色|表面/.test(summary)) add("surface_change", "表面/材质变化", "语义与认知信号");
  if (/评估|展示|最终/.test(summary)) add("long_compare", "长时间比较", "行为与时间信号");
  return signals.length ? signals : [{ code: "multi_view_check", label: "多视角检查", group: "空间与视口信号" }];
};

const newCases = videos.flatMap((video) =>
  video.windows.map(([start, end, summary], i) => {
    const [stateCode, stateLabel] = stateForSummary(summary);
    const [routeCode, routeLabel] = routeForState[stateCode];
    return {
      case_id: `${video.prefix}_${String(i + 1).padStart(2, "0")}`,
      video_id: video.video_id,
      software: video.software,
      source_url: `${video.url}?t=${toSeconds(start)}`,
      start_time: start,
      end_time: end,
      episode_summary: summary,
      state: { code: stateCode, label: stateLabel, status: "candidate_needs_human_check" },
      creativeflow_route: { code: routeCode, label: routeLabel, status: "candidate_needs_human_check" },
      signals: signalsForSummary(summary),
      raw_signals: [],
      retrieval_text: [stateLabel, routeLabel, summary].join("\n"),
      human_verified: false,
      source_title: video.title,
      note: "Bilibili long-video candidate window; please open the segment and revise labels.",
    };
  }),
);

function toSeconds(time) {
  const [mm, ss] = time.split(":").map(Number);
  return mm * 60 + ss;
}

const oldIds = new Set(baseCases.map((item) => item.case_id));
const merged = [...baseCases.filter((item) => !newCases.some((n) => n.case_id === item.case_id)), ...newCases];
if (newCases.some((item) => oldIds.has(item.case_id))) {
  console.log("Updated existing Bilibili candidate cases.");
}
await fs.writeFile(casesPath, `${JSON.stringify(merged, null, 2)}\n`);
console.log(JSON.stringify({ before: baseCases.length, added_or_updated: newCases.length, after: merged.length }, null, 2));
