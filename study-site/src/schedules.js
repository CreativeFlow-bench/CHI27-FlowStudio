const ORDERS = {
  G1: ["Flow-A1", "Flow-B1", "Text-A2", "Text-B2"],
  G2: ["Text-A1", "Text-B1", "Flow-A2", "Flow-B2"],
  G3: ["Flow-B1", "Flow-A1", "Text-B2", "Text-A2"],
  G4: ["Text-B1", "Text-A1", "Flow-B2", "Flow-A2"],
};

const SYSTEM_LABELS = {
  Flow: "FlowStudio",
  Text: "Text-Hunyuan3D",
};

function systemOf(taskCode) {
  return taskCode.startsWith("Flow-") ? "Flow" : "Text";
}

function taskStep(code, index) {
  const [system, task] = code.split("-");
  return {
    id: `task-${index + 1}`,
    kind: "task",
    code,
    system,
    systemLabel: SYSTEM_LABELS[system],
    task,
    title: `任务 ${index + 1}`,
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

export { ORDERS };
