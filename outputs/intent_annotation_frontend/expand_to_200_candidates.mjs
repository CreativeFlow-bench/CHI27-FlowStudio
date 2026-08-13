import fs from "node:fs/promises";

const casesPath =
  "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/intent_annotation_frontend/cases.json";

const existing = JSON.parse(await fs.readFile(casesPath, "utf8"));

const taskGroups = {
  character: "Task 1 · Character / Organic Modeling",
  product: "Task 2 · Product / Industrial Modeling",
  hard_surface: "Task 3 · Hard-surface / Mechanical Modeling",
  material: "Task 4 · Material / Rendering / Evaluation",
};

function classifyTask(item) {
  const text = [
    item.case_id,
    item.video_id,
    item.software,
    item.source_title,
    item.episode_summary,
    item.state?.code,
  ]
    .join(" ")
    .toLowerCase();
  if (/hard|mecha|helmet|toaster|camera|chainsaw|controller|机械|机甲|头盔|硬表面|sensor|sci-fi/.test(text)) {
    return taskGroups.hard_surface;
  }
  if (/rhino|product|industrial|产品|工业|吹风机|奶瓶|麦克风|榨汁机|咖啡机|扫地机|剃须刀|充电枪|筋膜枪|风扇|胶带|电熨斗|搅拌器|独轮车/.test(text)) {
    return taskGroups.product;
  }
  if (/material|render|shading|evaluation|evaluate|材质|渲染|评估|展示|paint/.test(text)) {
    return taskGroups.material;
  }
  return taskGroups.character;
}

function stateForText(text) {
  if (/analysis|setup|reference|image plane|前期分析|参考|目标|导入/.test(text)) return ["early_exploration", "Early Exploration"];
  if (/block|main body|body|主体|大型构建|模型构建|base|基础|大轮廓|建模$/.test(text)) return ["coarse_forming", "Coarse Forming"];
  if (/material|render|arnold|turntable|渲染|材质|动画|输出|展示/.test(text)) return ["evaluation", "Evaluation"];
  if (/detail|refinement|finishing|edge|loop|flow|倒角|细节|布线|收敛|补面|刀头|细分|曲面/.test(text)) return ["local_refinement", "Local Refinement"];
  if (/handle|hooks|buttons|knobs|lens|switch|parts|plate|关系|组件|装配/.test(text)) return ["relationship_adjustment", "Relationship Adjustment"];
  return ["local_refinement", "Local Refinement"];
}

const routeForState = {
  early_exploration: ["generate_breakthrough_reference_variants", "生成突破性的参考变体"],
  coarse_forming: ["generate_contour_variants", "生成轮廓变体"],
  local_refinement: ["generate_local_variants", "生成局部变体"],
  relationship_adjustment: ["generate_local_variants", "生成局部变体"],
  material_refinement: ["generate_material_variants", "生成材质变体"],
  evaluation: ["no_intervention", "不介入"],
};

function signalsForText(text) {
  const signals = [];
  const add = (code, label, group) => signals.push({ code, label, group });
  if (/reference|image plane|前期分析|参考/.test(text)) add("match_reference", "贴合参考", "语义与认知信号");
  if (/main body|body|主体|大型构建|base|block|大轮廓/.test(text)) add("zoom_out", "缩小看整体", "空间与视口信号");
  if (/detail|buttons|knobs|lens|switch|倒角|细节|刀头|孔|edge|loop/.test(text)) add("local_zoom", "局部放大", "空间与视口信号");
  if (/edge|flow|布线|收敛|补面|曲面|subd|surface/.test(text)) add("repeated_micro_edit", "反复微调", "行为与时间信号");
  if (/material|render|渲染|材质|arnold|turntable/.test(text)) add("surface_change", "表面/材质变化", "语义与认知信号");
  if (/final|evaluation|render|展示|输出|评估/.test(text)) add("long_compare", "长时间比较", "行为与时间信号");
  return signals.length ? signals : [{ code: "multi_view_check", label: "多视角检查", group: "空间与视口信号" }];
}

function mmss(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function makeCase({ prefix, video_id, software, title, page, part, duration, sourceUrl }) {
  const text = `${title} ${part}`;
  const [stateCode, stateLabel] = stateForText(text);
  const [routeCode, routeLabel] = routeForState[stateCode];
  const episodeSummary = part;
  const source_url = page
    ? `https://www.bilibili.com/video/${video_id}/?p=${page}&t=0`
    : sourceUrl;
  const base = {
    case_id: `${prefix}_${String(page ?? 1).padStart(2, "0")}`,
    video_id,
    software,
    source_url,
    start_time: "00:00",
    end_time: mmss(duration),
    episode_summary: episodeSummary,
    state: { code: stateCode, label: stateLabel, status: "candidate_needs_human_check" },
    creativeflow_route: { code: routeCode, label: routeLabel, status: "candidate_needs_human_check" },
    signals: signalsForText(text),
    raw_signals: [],
    retrieval_text: [stateLabel, routeLabel, episodeSummary].join("\n"),
    human_verified: false,
    source_title: title,
    note: "Auto-sampled candidate behavior episode; human coders should open the segment and revise labels.",
  };
  return { ...base, task_group: classifyTask(base) };
}

async function view(bvid) {
  const res = await fetch(`https://api.bilibili.com/x/web-interface/view?bvid=${bvid}`, {
    headers: { "User-Agent": "Mozilla/5.0", Referer: "https://www.bilibili.com/" },
  });
  const data = await res.json();
  if (data.code !== 0) throw new Error(`${bvid}: ${data.message}`);
  return data.data;
}

const multiVideos = [
  {
    bvid: "BV1vf421S7rF",
    prefix: "bilibili_rhino85_industrial_product",
    software: "Rhino",
    includePages: Array.from({ length: 47 }, (_, i) => i + 18),
  },
  {
    bvid: "BV1234y1s7gp",
    prefix: "bilibili_maya_hardsurface_core",
    software: "Maya",
    includePages: Array.from({ length: 56 }, (_, i) => i + 8),
  },
  {
    bvid: "BV1bjeBzRE7a",
    prefix: "bilibili_rhino8_surface_product",
    software: "Rhino",
    includePages: Array.from({ length: 21 }, (_, i) => i + 14),
  },
];

const pageCases = [];
for (const cfg of multiVideos) {
  const data = await view(cfg.bvid);
  for (const page of data.pages.filter((p) => cfg.includePages.includes(p.page))) {
    pageCases.push(
      makeCase({
        prefix: cfg.prefix,
        video_id: data.bvid,
        software: cfg.software,
        title: data.title,
        page: page.page,
        part: page.part,
        duration: page.duration,
      }),
    );
  }
}

const singleVideos = [
  {
    bvid: "BV1fs421c7eF",
    prefix: "bilibili_c4d_product_rendering",
    software: "Cinema 4D",
    windows: [
      ["00:00", "05:00", "产品建模目标与基础体块搭建"],
      ["05:00", "10:00", "主体轮廓和比例调整"],
      ["10:00", "15:00", "局部结构和装饰细节建模"],
      ["15:00", "20:00", "材质与表面质感设置"],
      ["20:00", "27:00", "灯光渲染与最终效果评估"],
      ["27:00", "34:30", "收尾展示与参数微调"],
    ],
  },
  {
    bvid: "BV1pP12YdEyu",
    prefix: "bilibili_blender_product_rendering",
    software: "Blender",
    windows: [
      ["00:00", "06:00", "产品参考与整体建模目标确认"],
      ["06:00", "12:00", "主体几何和大轮廓搭建"],
      ["12:00", "18:00", "局部组件和转折面细化"],
      ["18:00", "24:00", "倒角、布线和表面质量调整"],
      ["24:00", "32:00", "材质、灯光和渲染设置"],
      ["32:00", "40:00", "视角构图和效果比较"],
      ["40:00", "48:00", "最终修改与展示"],
      ["48:00", "53:14", "输出检查"],
    ],
  },
  {
    bvid: "BV1eN411d79r",
    prefix: "bilibili_c4d_industrial_design",
    software: "Cinema 4D",
    windows: [
      ["00:00", "05:00", "工业设计造型参考与建模目标"],
      ["05:00", "10:00", "产品主体轮廓构建"],
      ["10:00", "15:00", "曲面过渡和部件关系调整"],
      ["15:00", "20:00", "局部细节和边缘质量处理"],
      ["20:00", "27:00", "材质/灯光展示设置"],
      ["27:00", "33:00", "最终效果评估"],
    ],
  },
  {
    bvid: "BV1Pq4y1P74o",
    prefix: "bilibili_blender_hexnut_industrial",
    software: "Blender",
    windows: [
      ["00:00", "03:30", "六角螺母硬表面建模目标确认"],
      ["03:30", "07:00", "主体低模轮廓搭建"],
      ["07:00", "10:30", "孔洞和内外环结构处理"],
      ["10:30", "14:30", "倒角和支撑边控制"],
      ["14:30", "17:30", "细分表面质量检查"],
      ["17:30", "20:19", "最终模型评估"],
    ],
  },
];

const singleCases = [];
for (const cfg of singleVideos) {
  const data = await view(cfg.bvid);
  cfg.windows.forEach(([start, end, summary], idx) => {
    const duration = toSeconds(end) - toSeconds(start);
    singleCases.push(
      makeCase({
        prefix: cfg.prefix,
        video_id: data.bvid,
        software: cfg.software,
        title: data.title,
        page: idx + 1,
        part: summary,
        duration,
        sourceUrl: `https://www.bilibili.com/video/${data.bvid}/?t=${toSeconds(start)}`,
      }),
    );
    singleCases[singleCases.length - 1].start_time = start;
    singleCases[singleCases.length - 1].end_time = end;
    singleCases[singleCases.length - 1].source_url = `https://www.bilibili.com/video/${data.bvid}/?t=${toSeconds(start)}`;
  });
}

function toSeconds(time) {
  const [m, s] = time.split(":").map(Number);
  return m * 60 + s;
}

const existingWithGroups = existing.map((item) => ({ ...item, task_group: item.task_group || classifyTask(item) }));
const additions = [...pageCases, ...singleCases];
const additionIds = new Set(additions.map((item) => item.case_id));
const merged = [...existingWithGroups.filter((item) => !additionIds.has(item.case_id)), ...additions];

await fs.writeFile(casesPath, `${JSON.stringify(merged, null, 2)}\n`);

const byTask = {};
for (const item of merged) byTask[item.task_group] = (byTask[item.task_group] || 0) + 1;
console.log(JSON.stringify({ before: existing.length, added_or_updated: additions.length, after: merged.length, byTask }, null, 2));
