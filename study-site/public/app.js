const app = document.querySelector("#app");
let session = null;

const NASA = [
  ["mental", "这项任务在心理和认知上的要求有多高？", "非常低", "非常高"],
  ["physical", "这项任务在身体操作上的要求有多高？", "非常低", "非常高"],
  ["temporal", "完成任务的节奏有多匆忙？", "非常从容", "非常匆忙"],
  ["performance", "你认为自己多成功地完成了任务？", "完全成功", "完全失败"],
  ["effort", "为达到你的表现水平，你付出了多少努力？", "非常少", "非常多"],
  ["frustration", "任务中你感到多么不安、泄气、烦躁或受挫？", "完全没有", "非常强烈"],
];

const CSI = [
  ["enjoy_regular", "我愿意经常使用这个系统或工具。"],
  ["enjoy_use", "我喜欢使用这个系统或工具。"],
  ["explore_many", "使用这个系统，我很容易探索许多不同的想法、选项或结果。"],
  ["explore_track", "这个系统有助于我追踪不同的想法、结果或可能性。"],
  ["express_creative", "使用这个系统时，我能够充分发挥创造力。"],
  ["express_ideas", "这个系统使我能够充分表达自己的想法。"],
  ["immerse_attention", "我的注意力能够充分投入设计活动。"],
  ["immerse_absorbed", "我能够沉浸在设计活动中。"],
  ["result_satisfied", "我对使用这个系统得到的结果感到满意。"],
  ["result_effort", "我产出的结果值得我为此付出的努力。"],
];

const SUS = [
  "我愿意经常使用这个系统。", "我觉得这个系统不必要地复杂。", "我觉得这个系统容易使用。",
  "我认为需要技术人员的帮助才能使用这个系统。", "我觉得这个系统中的各项功能整合得很好。",
  "我觉得这个系统存在太多不一致之处。", "我认为大多数人能很快学会使用这个系统。",
  "我觉得这个系统使用起来很笨拙。", "我对使用这个系统很有信心。", "在开始使用这个系统前，我需要学习很多东西。",
];

const INTERVIEW_DIMENSIONS = [
  {
    title: "整体体验与系统比较",
    time: "约 4 分钟",
    questions: [
      { text: "请简要比较两个系统的整体体验。", probes: ["它们分别给你什么感觉？", "你更愿意继续使用哪个？为什么？"] },
      { text: "两个系统分别让你觉得自己是在怎样进行创作？", probes: ["哪个过程更自然？", "哪个更符合你的创作习惯？"] },
    ],
  },
  {
    title: "创作习惯与思考过程",
    time: "约 5 分钟",
    questions: [
      { text: "你平时创作时有什么习惯？一般会先想什么、再做什么？", probes: ["你会先想整体、故事或细节，还是边做边想？", "刚才有没有改变原来的习惯？"] },
      { text: "刚才你的想法是怎样一步步变化的？", probes: ["最开始想做什么？后来变成了什么？", "是什么让你的想法发生变化？"] },
    ],
  },
  {
    title: "投入、心流与中断",
    time: "约 5 分钟",
    questions: [
      { text: "刚才有没有一段时间，你很投入地一直做下去？", probes: ["当时在做什么、想什么？", "为什么能够一直做下去？", "有没有感觉时间过得很快？"] },
      { text: "有没有什么事情打断了你的思路或创作状态？", probes: ["你后来是怎么重新开始的？", "哪个系统更容易让你保持投入？"] },
    ],
  },
  {
    title: "灵感、困难与创意发散",
    time: "约 5 分钟",
    questions: [
      { text: "当你想不出来或不知道下一步做什么时，你一般怎么办？刚才发生过吗？", probes: ["系统有没有帮助你继续？", "它是给了答案，还是让你想到别的东西？"] },
      { text: "刚才什么地方最能帮助你产生新的想法？", probes: ["是某次操作、局部变化、生成结果、系统反馈，还是一个意外？", "可以讲一个刚才的例子吗？"] },
    ],
  },
  {
    title: "表达、细节与控制感",
    time: "约 6 分钟",
    questions: [
      { text: "在刚才的作品中，你最在意哪些地方？为什么？", probes: ["有没有看起来很小，但你不希望 AI 随便改变的地方？", "这些地方表达了什么？"] },
      { text: "什么时候你觉得是自己在创作？什么时候更像是 AI 在替你创作？", probes: ["什么时候系统理解了你？", "有没有没理解你、结果却仍然有帮助的时候？", "你当时有什么感觉？"] },
    ],
  },
  {
    title: "改进与未来工具",
    time: "约 5 分钟",
    questions: [
      { text: "如果只能改进一个地方，你会改进什么？", probes: ["它在什么时候影响了你？", "改进后你希望它怎样工作？"] },
      { text: "你希望未来的 AI 创作工具怎样帮助你？", probes: ["没有想法、做到一半卡住或非常投入时，它分别应该做什么？", "什么时候它应该保持安静？"] },
    ],
  },
];

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "content-type": "application/json" }, ...options });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function renderLogin(error = "") {
  app.innerHTML = `<div class="login-shell">
    <section class="login-context"><div><div class="brand">FlowStudio Research</div><h1>3D 创意工作流<br>用户研究</h1><p>请使用研究员提供的匿名参与者账号登录。系统会保存你的当前进度。</p></div><div class="study-code">STUDY PORTAL · V0.1</div></section>
    <section class="login-panel"><form class="login-form" id="login-form"><h2>参与者登录</h2><p>账号不包含真实姓名。请勿与其他参与者交换账号。</p><label for="username">参与者账号</label><input id="username" name="username" type="text" autocomplete="username" placeholder="P001" required /><label for="password">密码</label><input id="password" name="password" type="password" autocomplete="current-password" required /><button class="primary" type="submit">登录并继续</button>${error ? `<p class="error">${escapeHtml(error)}</p>` : ""}</form></section>
  </div>`;
  document.querySelector("#login-form").addEventListener("submit", login);
}

async function login(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
    await loadSession();
  } catch (error) { renderLogin(error.message); }
}

async function loadSession() {
  try { session = await api("/api/session"); session.admin ? await renderAdmin() : session.reviewer ? renderReviewer() : renderStudy(); }
  catch { renderLogin(); }
}

function reviewList(items, suffix = "") {
  return `<ol>${items.map((item) => `<li>${Array.isArray(item) ? item[1] : item}${suffix ? `<span class="review-scale">${suffix}</span>` : ""}</li>`).join("")}</ol>`;
}

function reviewInterviewGuide() {
  const dimensions = INTERVIEW_DIMENSIONS.map((dimension, dimensionIndex) => `<section class="interview-dimension">
    <header><span class="interview-number">${dimensionIndex + 1}</span><div><h3>${dimension.title}</h3><span class="interview-time">${dimension.time}</span></div></header>
    <ol>${dimension.questions.map((question) => `<li><strong>${question.text}</strong><div class="interview-probes"><span>可选追问</span>${question.probes.map((probe) => `<p>${probe}</p>`).join("")}</div></li>`).join("")}</ol>
  </section>`).join("");
  return `<div class="interview-guide-intro"><strong>建议节奏：约 30 分钟</strong><p>按参与者的回答自然追问，不必逐字念完所有可选追问。尽量让参与者讲述刚才发生的具体事情。</p></div>${dimensions}
    <div class="interview-closing"><h3>结束补充</h3><p>还有没有什么刚才发生的事情，是我们没有问到，但你觉得对理解你的创作过程很重要的？</p></div>
    <div class="interview-recording"><h3>研究员记录建议</h3><p>访谈全程录音，并记录关键原话、对应系统或任务、发生时的具体事件，以及值得继续追问的原因。</p><div class="record-tags"><span>投入</span><span>中断</span><span>灵感</span><span>卡住</span><span>细节</span><span>控制感</span><span>意外结果</span><span>改进建议</span></div><p class="review-note">通用追问：可以举一个刚才的例子吗？你当时在想什么？为什么这件事对你很重要？</p></div>`;
}

function renderReviewer() {
  app.innerHTML = `<div class="review-shell"><header class="admin-header"><div><div class="brand">FlowStudio Research</div><div class="participant-meta">P000 · 研究材料审阅</div></div><button class="secondary" id="review-logout">退出登录</button></header><nav class="review-nav"><a href="#flow">流程</a><a href="#prestudy">前测</a><a href="#tasks">任务</a><a href="#nasa">NASA-TLX</a><a href="#csi">CSI</a><a href="#sus">SUS</a><a href="#comparison">系统比较</a><a href="#interview">访谈</a></nav><main class="review-content"><section class="review-intro"><div class="eyebrow">Review mode</div><h1>实验问卷总览</h1><p class="lead">这个账号只用于阅读和讨论，不提交答案，也不会写入参与者数据。</p></section>
    <section class="review-section" id="flow"><h2>完整实验流程</h2><p class="review-note">前测 → 系统一任务 1 → NASA → 系统一任务 2 → NASA → CSI → SUS → 休息 → 系统二任务 1 → NASA → 系统二任务 2 → NASA → CSI → SUS → 系统比较 → 半结构化访谈。</p><h3>四种平衡顺序</h3><ol><li>G1：Flow-A1 → Flow-B1 → Text-A2 → Text-B2</li><li>G2：Text-A1 → Text-B1 → Flow-A2 → Flow-B2</li><li>G3：Flow-B1 → Flow-A1 → Text-B2 → Text-A2</li><li>G4：Text-B1 → Text-A1 → Flow-B2 → Flow-A2</li></ol></section>
    <section class="review-section" id="prestudy"><h2>实验前问卷</h2>${reviewList(["主要设计背景或创意领域", "3D 建模经验：无 / 入门 / 中等 / 熟练 / 专业", "生成式 AI 使用频率：很少 / 每月数次 / 每周数次 / 几乎每天"])}</section>
    <section class="review-section" id="tasks"><h2>四项设计任务</h2><p class="review-note">具体任务内容目前保留为空，待我们讨论后填写。正式页面不会向参与者展示 A/B 等研究标签。</p><ol><li>A1：定向设计任务，占位</li><li>B1：开放设计任务，占位</li><li>A2：定向设计任务，占位</li><li>B2：开放设计任务，占位</li></ol></section>
    <section class="review-section" id="nasa"><h2>NASA-TLX</h2><p>每项任务后填写一次，共四次。</p>${reviewList(NASA, "1–11 分，对应原始 0–100")}</section>
    <section class="review-section" id="csi"><h2>适配版 CSI</h2><p>每完成一个系统后填写一次，共两次。单人任务不包含 Collaboration。</p>${reviewList(CSI, "1–10 分")}</section>
    <section class="review-section" id="sus"><h2>System Usability Scale</h2><p>每完成一个系统后填写一次，共两次，保留完整 10 题。</p>${reviewList(SUS, "1–5 分")}</section>
    <section class="review-section" id="comparison"><h2>最终系统比较</h2>${reviewList(["总体上更偏好哪个系统？", "哪个系统更有助于探索不同创意方向？", "哪个系统更有助于表达设计意图？", "哪个系统更有控制感？", "哪个系统更容易使用？", "哪个系统更适合实际设计工作？"], "FlowStudio / Text-Hunyuan3D / 相近")}</section>
    <section class="review-section review-interview" id="interview"><h2>半结构化访谈指南</h2><p>供研究员口头提问、录音和记录。主问题共 12 题，按 6 个维度组织。</p>${reviewInterviewGuide()}</section>
  </main></div>`;
  document.querySelector("#review-logout").addEventListener("click", logout);
}

async function renderAdmin() {
  const payload = await api("/api/admin/participants");
  const completed = payload.participants.filter((item) => item.completedAt).length;
  app.innerHTML = `<div class="admin-shell"><header class="admin-header"><div><div class="brand">FlowStudio Research</div><div class="participant-meta">管理员控制台</div></div><div class="admin-actions"><button class="secondary" id="export-data">导出回答 JSON</button><button class="secondary" id="admin-logout">退出登录</button></div></header><main class="admin-content"><h1>参与者进度</h1><p class="admin-summary">共 ${payload.participants.length} 个账号，${completed} 人已完成。任务正文当前仍为占位内容。</p><div class="admin-table-wrap"><table class="admin-table"><thead><tr><th>账号</th><th>样本</th><th>顺序</th><th>任务编排</th><th>当前环节</th><th>进度</th><th>最近保存</th></tr></thead><tbody>${payload.participants.map((item) => `<tr><td><strong>${item.username}</strong></td><td>${item.cohort === "formal" ? "正式" : "预测试"}</td><td>${item.sequence}</td><td>${item.order.join(" → ")}</td><td><span class="status ${item.completedAt ? "complete" : ""}">${item.completedAt ? "已完成" : stageName({ kind: item.currentStage })}</span></td><td>${item.percent}%</td><td>${new Date(item.updatedAt).toLocaleString("zh-CN")}</td></tr>`).join("")}</tbody></table></div></main></div>`;
  document.querySelector("#admin-logout").addEventListener("click", logout);
  document.querySelector("#export-data").addEventListener("click", exportAdminData);
}

async function exportAdminData() {
  const payload = await api("/api/admin/export");
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `flowstudio-study-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function stageName(step) {
  return ({ welcome: "研究说明", prestudy: "实验前问卷", task: "设计任务", nasa: "任务负荷", csi: "创造力支持", sus: "系统可用性", break: "休息", comparison: "系统比较", interview: "访谈问卷", complete: "完成" })[step.kind];
}

function renderStudy() {
  const { account, record } = session;
  const step = account.steps[record.currentStep];
  const percent = Math.round((record.currentStep / (account.steps.length - 1)) * 100);
  const visible = account.steps.filter((item) => item.kind !== "nasa");
  app.innerHTML = `<div class="study-shell"><aside class="sidebar"><div class="brand">FlowStudio Research</div><div class="participant-meta">${account.username} · ${account.cohort === "formal" ? "正式实验" : "预测试"}</div><div class="progress-label"><span>实验进度</span><span>${percent}%</span></div><div class="progress-track"><span style="width:${percent}%"></span></div><ol class="stage-list">${visible.map((item) => { const index = account.steps.indexOf(item); return `<li class="${index === record.currentStep ? "current" : index < record.currentStep ? "done" : ""}">${index < record.currentStep ? "✓ " : ""}${stageName(item)}${item.systemLabel ? ` · ${item.systemLabel}` : ""}</li>`; }).join("")}</ol><button class="logout" id="logout">退出登录</button></aside><section class="content">${renderStep(step)}</section></div>`;
  document.querySelector("#logout").addEventListener("click", logout);
  document.querySelector("#step-form")?.addEventListener("submit", submitStep);
}

function renderStep(step) {
  const views = { welcome: welcomeView, prestudy: prestudyView, task: taskView, nasa: nasaView, csi: csiView, sus: susView, break: breakView, comparison: comparisonView, interview: interviewView, complete: completeView };
  return `<div class="step">${views[step.kind](step)}</div>`;
}

function formShell(step, eyebrow, title, lead, fields, button = "提交并继续") {
  return `<div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="lead">${lead}</p><form id="step-form" data-step="${step.id}">${fields}<div class="actions"><span class="save-note">提交后自动保存</span><button class="primary" type="submit">${button}</button></div><p class="error" id="form-error"></p></form>`;
}

function scale(name, count, low, high) {
  return `<div class="scale" style="--count:${count}">${Array.from({ length: count }, (_, i) => `<label><input type="radio" name="${name}" value="${i + 1}" required><span>${i + 1}</span></label>`).join("")}</div><div class="scale-ends"><span>${low}</span><span>${high}</span></div>`;
}

function ratingQuestions(items, count, low = "非常不同意", high = "非常同意") {
  return items.map(([name, label], index) => `<fieldset class="question"><legend>${index + 1}. ${label}</legend>${scale(name, count, low, high)}</fieldset>`).join("");
}

function welcomeView(step) {
  return formShell(step, "开始前", "欢迎参加用户研究", "本网站用于安排实验步骤并收集问卷。研究评价的是系统，而不是你的设计能力。", `<div class="task-brief"><h2>预计流程</h2><p>四项设计任务；每项任务后填写一次 NASA-TLX；每完成一个系统后填写一次 CSI 和 SUS；最后完成系统比较与访谈问卷。</p></div><div class="choice-list"><label><input type="checkbox" name="consent" required>我已阅读研究说明，并同意开始实验。</label></div>`, "开始实验");
}

function prestudyView(step) {
  return formShell(step, "实验前", "基本信息", "这些信息用于理解不同经验背景下的系统体验。", `<label for="background">主要设计背景或创意领域</label><input id="background" name="background" type="text" required><label for="experience">3D 建模经验</label><div class="choice-list">${["无", "入门", "中等", "熟练", "专业"].map((x) => `<label><input type="radio" name="experience" value="${x}" required>${x}</label>`).join("")}</div><label for="ai-frequency">生成式 AI 使用频率</label><div class="choice-list">${["很少", "每月数次", "每周数次", "几乎每天"].map((x) => `<label><input type="radio" name="aiFrequency" value="${x}" required>${x}</label>`).join("")}</div>`);
}

function taskView(step) {
  return formShell(step, step.systemLabel, step.title, "请按照研究员指引在对应系统中完成设计。任务正文将在预测试前统一替换。", `<div class="task-brief"><h2>当前任务</h2><div class="placeholder">具体任务内容待确认。内部任务代码：${step.task}</div><p>完成设计并在系统中选择最终方案后，再返回本页继续。</p></div><div class="choice-list"><label><input type="checkbox" name="taskCompleted" required>我已完成当前任务并选择最终方案。</label></div>`, "进入任务后问卷");
}

function nasaView(step) {
  return formShell(step, `${step.systemLabel} · 任务后`, "NASA-TLX 任务负荷", "请只评价刚刚完成的任务。", NASA.map(([name, label, low, high], index) => `<fieldset class="question"><legend>${index + 1}. ${label}</legend>${scale(name, 11, low, high)}</fieldset>`).join(""));
}

function csiView(step) { return formShell(step, step.systemLabel, "创造力支持体验", "请综合评价刚才使用该系统完成两项任务的体验。", ratingQuestions(CSI, 10)); }
function susView(step) { return formShell(step, step.systemLabel, "系统可用性", "请综合评价刚才使用的系统。", ratingQuestions(SUS.map((label, i) => [`sus${i + 1}`, label]), 5)); }

function breakView(step) {
  return formShell(step, "中场休息", "请休息 5 分钟", "接下来将切换到另一套设计系统。请不要沿用上一套系统的中间结果。", `<div class="break-panel">准备好后点击继续。研究员也可以在此检查下一套系统是否已就绪。</div><div class="choice-list"><label><input type="checkbox" name="ready" required>我已休息并准备继续。</label></div>`, "进入下一套系统");
}

function comparisonView(step) {
  const choices = ["FlowStudio", "Text-Hunyuan3D", "相近或无明显偏好"];
  const items = ["总体上更偏好哪个系统？", "哪个系统更有助于探索不同创意方向？", "哪个系统更有助于表达设计意图？", "哪个系统更有控制感？", "哪个系统更容易使用？", "哪个系统更适合实际设计工作？"];
  return formShell(step, "总体比较", "比较两套系统", "请根据四项任务的整体体验作答。", items.map((label, index) => `<fieldset class="question"><legend>${index + 1}. ${label}</legend><div class="choice-list">${choices.map((choice) => `<label><input type="radio" name="compare${index + 1}" value="${choice}" required>${choice}</label>`).join("")}</div></fieldset>`).join(""));
}

function interviewView(step) {
  return formShell(step, "最后环节", "半结构化访谈", "研究员将进行约 30 分钟的口头访谈并录音/记录。请根据自己的真实经历自由回答，没有标准答案。", `<div class="task-brief"><h2>请联系研究员</h2><p>访谈将围绕整体体验、创作习惯、投入状态、灵感与困难、细节表达以及未来工具展开。</p></div><div class="choice-list"><label><input type="checkbox" name="interviewCompleted" required>研究员已完成口头访谈和记录。</label></div>`, "完成实验");
}

function completeView() { return `<div class="eyebrow">已完成</div><h1>感谢你的参与</h1><div class="complete-panel"><p class="lead">所有问卷已保存。请联系研究员完成实验结束确认。</p></div>`; }

async function submitStep(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const entries = [...new FormData(event.currentTarget).entries()];
    const answers = Object.fromEntries(entries.map(([key, value]) => [key, value === "on" ? true : value]));
    const payload = await api("/api/submit", { method: "POST", body: JSON.stringify({ stepId: event.currentTarget.dataset.step, answers }) });
    session.record = payload.record;
    window.scrollTo({ top: 0, behavior: "smooth" });
    renderStudy();
  } catch (error) {
    document.querySelector("#form-error").textContent = error.message;
    button.disabled = false;
  }
}

async function logout() { await api("/api/logout", { method: "POST", body: "{}" }); session = null; renderLogin(); }

loadSession();
