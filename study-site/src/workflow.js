function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function createInitialRecord(schedule) {
  return {
    username: schedule.username,
    sequence: schedule.sequence,
    cohort: schedule.cohort,
    currentStep: 0,
    responses: {},
    updatedAt: new Date().toISOString(),
    completedAt: null,
  };
}

export function submitCurrentStep(record, schedule, stepId, answers) {
  const current = schedule.steps[record.currentStep];
  if (!current || current.id !== stepId) throw new Error("step_mismatch");
  if (!answers || typeof answers !== "object" || Array.isArray(answers)) throw new Error("invalid_answers");
  if (current.kind === "welcome" && answers.consent !== true) throw new Error("consent_required");

  const next = clone(record);
  next.responses[stepId] = { ...answers, submittedAt: new Date().toISOString() };
  next.currentStep = Math.min(record.currentStep + 1, schedule.steps.length - 1);
  next.updatedAt = new Date().toISOString();
  if (current.kind === "interview") next.completedAt = next.updatedAt;
  return next;
}
