import assert from "node:assert/strict";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { buildAccounts, buildAdminAccount, buildReviewerAccount, refreshAccountSchedules, verifyPassword } from "../src/auth.js";
import { buildParticipantSchedules, ORDERS } from "../src/schedules.js";
import { createInitialRecord, submitCurrentStep } from "../src/workflow.js";
import { initializeDatabase, readRecords, writeRecord } from "../src/store.js";

test("builds 20 formal and 5 pilot accounts with balanced schedules", () => {
  const schedules = buildParticipantSchedules();

  assert.equal(schedules.length, 25);
  assert.equal(schedules.filter((item) => item.cohort === "formal").length, 20);
  assert.equal(schedules.filter((item) => item.cohort === "pilot").length, 5);
  assert.deepEqual(
    schedules.slice(0, 4).map((item) => item.sequence),
    ["G1", "G2", "G3", "G4"],
  );
  assert.equal(new Set(schedules.map((item) => item.username)).size, 25);
  assert.equal(schedules.every((item) => item.steps.filter((step) => step.kind === "task").length === 2), true);
  assert.deepEqual(ORDERS, {
    G1: ["Flow-XMAS", "Text-HANDBAG"],
    G2: ["Text-XMAS", "Flow-HANDBAG"],
    G3: ["Flow-HANDBAG", "Text-XMAS"],
    G4: ["Text-HANDBAG", "Flow-XMAS"],
  });
  assert.deepEqual(
    schedules.slice(0, 20).reduce((counts, item) => ({ ...counts, [item.sequence]: (counts[item.sequence] || 0) + 1 }), {}),
    { G1: 5, G2: 5, G3: 5, G4: 5 },
  );
});

test("generated account passwords are verifiable but not stored in plaintext", () => {
  const { publicAccounts, credentials } = buildAccounts(() => "FixedPass9K");

  assert.equal(publicAccounts.length, 25);
  assert.equal(credentials.length, 25);
  assert.equal(publicAccounts[0].password, undefined);
  assert.notEqual(publicAccounts[0].passwordHash, credentials[0].password);
  assert.equal(verifyPassword(credentials[0].password, publicAccounts[0]), true);
  assert.equal(verifyPassword("wrong-password", publicAccounts[0]), false);
});

test("builds a separate administrator account", () => {
  const { account, credential } = buildAdminAccount(() => "AdminPass8K");

  assert.equal(account.username, "ADMIN");
  assert.equal(account.role, "admin");
  assert.equal(account.steps, undefined);
  assert.equal(credential.password, "AdminPass8K");
  assert.equal(verifyPassword(credential.password, account), true);
});

test("builds a non-participant questionnaire reviewer account", () => {
  const { account, credential } = buildReviewerAccount(() => "ReviewPass7K");

  assert.equal(account.username, "P000");
  assert.equal(account.role, "reviewer");
  assert.equal(account.steps, undefined);
  assert.equal(credential.password, "ReviewPass7K");
  assert.equal(verifyPassword(credential.password, account), true);
});

test("schedule refresh preserves participant passwords and non-participant accounts", () => {
  const { publicAccounts } = buildAccounts(() => "FixedPass9K");
  const { account: admin } = buildAdminAccount(() => "AdminPass8K");
  const { account: reviewer } = buildReviewerAccount(() => "ReviewPass7K");
  const existing = [...publicAccounts.map((account) => ({ ...account, order: ["old"] })), admin, reviewer];

  const refreshed = refreshAccountSchedules(existing);
  const participant = refreshed.find((account) => account.username === "P001");
  assert.deepEqual(participant.order, ["Flow-XMAS", "Text-HANDBAG"]);
  assert.equal(participant.passwordHash, publicAccounts[0].passwordHash);
  assert.equal(participant.salt, publicAccounts[0].salt);
  assert.deepEqual(refreshed.find((account) => account.username === "ADMIN"), admin);
  assert.deepEqual(refreshed.find((account) => account.username === "P000"), reviewer);
});

test("requires NASA after every task and CSI plus SUS after each system block", () => {
  const [schedule] = buildParticipantSchedules();
  const kinds = schedule.steps.map((step) => step.kind);

  assert.deepEqual(kinds, [
    "welcome", "prestudy",
    "task", "nasa", "csi", "sus", "break",
    "task", "nasa", "csi", "sus",
    "comparison", "interview", "complete",
  ]);
});

test("each task presents an open exploration brief and the correct system constraints", () => {
  const schedules = buildParticipantSchedules();
  const taskSteps = schedules.flatMap((schedule) => schedule.steps.filter((step) => step.kind === "task"));

  assert.equal(taskSteps.every((step) => step.duration === "12–15 分钟"), true);
  assert.equal(taskSteps.every((step) => step.requirements.length >= 2 && step.requirements.length <= 3), true);
  assert.equal(taskSteps.filter((step) => step.task === "XMAS").every((step) => step.requirements.some((item) => item.includes("雪人"))), true);
  assert.equal(taskSteps.filter((step) => step.system === "Flow").every((step) => step.systemGuide.includes("预设 3D 模型") && step.systemGuide.includes("不能上传参考图")), true);
  assert.equal(taskSteps.filter((step) => step.system === "Text").every((step) => step.systemGuide.includes("多轮") && step.systemGuide.includes("历史") && step.systemGuide.includes("不能上传参考图")), true);
});

test("workflow only advances after the current step has a valid answer", () => {
  const [schedule] = buildParticipantSchedules();
  const record = createInitialRecord(schedule);

  assert.throws(() => submitCurrentStep(record, schedule, "prestudy", {}), /step_mismatch/);
  const next = submitCurrentStep(record, schedule, "welcome", { consent: true });
  assert.equal(next.currentStep, 1);
  assert.equal(next.responses.welcome.consent, true);
});

test("reviewer sees the dimensional interview guide while participants only confirm the oral interview", async () => {
  const appSource = await readFile(new URL("../public/app.js", import.meta.url), "utf8");

  for (const heading of ["整体体验与系统比较", "创作习惯与思考过程", "投入、心流与中断", "灵感、困难与创意发散", "表达、细节与控制感", "改进与未来工具"]) {
    assert.match(appSource, new RegExp(heading));
  }
  assert.match(appSource, /请简要比较两个系统的整体体验。/);
  assert.match(appSource, /如果只能改进一个地方，你会改进什么？/);
  assert.match(appSource, /研究员将进行约 30 分钟的口头访谈并录音\/记录/);
  assert.doesNotMatch(appSource, /name="interview1"/);
});

test("questionnaire copy describes two open explorations instead of four tasks", async () => {
  const appSource = await readFile(new URL("../public/app.js", import.meta.url), "utf8");

  assert.match(appSource, /两次开放式创意探索/);
  assert.match(appSource, /每项任务后填写一次，共两次/);
  assert.match(appSource, /新中式手包设计（主题待确认）/);
  assert.doesNotMatch(appSource, /四项设计任务/);
  assert.doesNotMatch(appSource, /四项任务/);
});

test("SQLite storage preserves concurrent participant submissions", async () => {
  const directory = await mkdtemp(join(tmpdir(), "flowstudio-study-"));
  const databasePath = join(directory, "study.sqlite3");
  await initializeDatabase(databasePath);

  await Promise.all(Array.from({ length: 6 }, (_, index) => {
    const username = `P00${index + 1}`;
    return writeRecord(databasePath, username, { username, currentStep: index + 1, responses: { task: index } });
  }));

  const records = await readRecords(databasePath);
  assert.equal(Object.keys(records).length, 6);
  assert.equal(records.P001.currentStep, 1);
  assert.equal(records.P006.responses.task, 5);
});
