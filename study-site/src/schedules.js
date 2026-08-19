const ORDERS = {
  G1: ["Flow-XMAS", "Text-HANDBAG"],
  G2: ["Text-XMAS", "Flow-HANDBAG"],
  G3: ["Flow-HANDBAG", "Text-XMAS"],
  G4: ["Text-HANDBAG", "Flow-XMAS"],
};

const SYSTEM_LABELS = {
  Flow: "FlowStudio",
  Text: "纯文本 Hunyuan3D",
};

const SYSTEM_GUIDES = {
  Flow: "从预设 3D 模型开始，通过空间交互进行修改和发散；不能上传参考图。",
  Text: "使用纯文本提示词，可进行多轮修改、查看历史结果并选择最终方案；不能上传参考图。",
};

const TASK_BRIEFS = {
  XMAS: {
    theme: "圣诞解谜游戏的场景关键道具设计",
    scene: "你正在为一个圣诞主题解谜游戏设计场景中的关键 3D 道具。",
    goal: "请开放探索一个以雪人为核心、能够支持谜题或场景叙事的道具设计。",
    requirements: ["设计中应包含清晰可辨的雪人元素。", "道具应具有至少一个体现其用途或故事的创意细节。", "最终选择一个完整的 3D 道具方案。"],
  },
  HANDBAG: {
    theme: "新中式手包设计",
    scene: "你正在为日常使用场景设计一款具有新中式风格的手包。",
    goal: "请开放探索传统文化表达与当代使用方式相结合的手包设计。",
    requirements: ["设计应保持手包的基本可识别性。", "通过至少一个造型或细节体现你对“新中式”的理解。", "最终选择一个完整的手包方案。"],
  },
};

function systemOf(taskCode) {
  return taskCode.startsWith("Flow-") ? "Flow" : "Text";
}

function taskStep(code, index) {
  const [system, task] = code.split("-");
  const brief = TASK_BRIEFS[task];
  return {
    id: `task-${index + 1}`,
    kind: "task",
    code,
    system,
    systemLabel: SYSTEM_LABELS[system],
    task,
    title: `开放式创意探索 ${index + 1}`,
    duration: "12–15 分钟",
    systemGuide: SYSTEM_GUIDES[system],
    ...brief,
  };
}

function buildSteps(order) {
  const tasks = order.map(taskStep);
  const steps = [{ id: "welcome", kind: "welcome" }, { id: "prestudy", kind: "prestudy" }];
  let previousSystem = null;

  tasks.forEach((task, index) => {
    if (previousSystem && task.system !== previousSystem) {
      steps.push({ id: `csi-${previousSystem.toLowerCase()}`, kind: "csi", system: previousSystem, systemLabel: SYSTEM_LABELS[previousSystem] });
      steps.push({ id: `sus-${previousSystem.toLowerCase()}`, kind: "sus", system: previousSystem, systemLabel: SYSTEM_LABELS[previousSystem] });
      steps.push({ id: "break", kind: "break" });
    }
    steps.push(task);
    steps.push({ id: `nasa-${index + 1}`, kind: "nasa", taskCode: task.code, system: task.system, systemLabel: task.systemLabel });
    previousSystem = task.system;
  });

  steps.push({ id: `csi-${previousSystem.toLowerCase()}`, kind: "csi", system: previousSystem, systemLabel: SYSTEM_LABELS[previousSystem] });
  steps.push({ id: `sus-${previousSystem.toLowerCase()}`, kind: "sus", system: previousSystem, systemLabel: SYSTEM_LABELS[previousSystem] });
  steps.push({ id: "comparison", kind: "comparison" });
  steps.push({ id: "interview", kind: "interview" });
  steps.push({ id: "complete", kind: "complete" });
  return steps;
}

export function buildParticipantSchedules() {
  return Array.from({ length: 25 }, (_, index) => {
    const number = index + 1;
    const sequence = `G${(index % 4) + 1}`;
    const order = ORDERS[sequence];
    return {
      username: `P${String(number).padStart(3, "0")}`,
      cohort: number <= 20 ? "formal" : "pilot",
      sequence,
      order,
      steps: buildSteps(order),
    };
  });
}

export { ORDERS, TASK_BRIEFS };
