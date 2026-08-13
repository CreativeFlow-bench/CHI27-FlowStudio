import fs from "node:fs/promises";

const dir = "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/intent_annotation_frontend";
const cases = JSON.parse(await fs.readFile(`${dir}/cases.json`, "utf8"));
const accounts = ["coder_1", "coder_2", "coder_3", "coder_4", "coder_5"];

const overlapTargetByTask = new Map([
  ["Task 1 · Character / Organic Modeling", 12],
  ["Task 2 · Product / Industrial Modeling", 18],
  ["Task 3 · Hard-surface / Mechanical Modeling", 16],
  ["Task 4 · Material / Rendering / Evaluation", 4],
]);

const byTask = new Map();
cases.forEach((item, index) => {
  const key = item.task_group || "Unassigned";
  if (!byTask.has(key)) byTask.set(key, []);
  byTask.get(key).push({ item, index });
});

const overlap = [];
for (const [task, target] of overlapTargetByTask) {
  const bucket = byTask.get(task) || [];
  const verified = bucket.filter(({ item }) => item.human_verified);
  const candidates = bucket.filter(({ item }) => !item.human_verified);
  overlap.push(...[...verified, ...candidates].slice(0, target));
}

const overlapIds = new Set(overlap.map(({ item }) => item.case_id));
const rest = cases
  .map((item, index) => ({ item, index }))
  .filter(({ item }) => !overlapIds.has(item.case_id));

const assignments = Object.fromEntries(accounts.map((account) => [account, overlap.map(({ item }) => item.case_id)]));
rest.forEach(({ item }, index) => {
  assignments[accounts[index % accounts.length]].push(item.case_id);
});

const caseMeta = Object.fromEntries(
  cases.map((item) => [
    item.case_id,
    {
      task_group: item.task_group,
      video_id: item.video_id,
      human_verified: item.human_verified,
      source_url: item.source_url,
    },
  ]),
);

const summary = {};
for (const account of accounts) {
  const ids = assignments[account];
  const taskCounts = {};
  for (const id of ids) {
    const task = caseMeta[id].task_group;
    taskCounts[task] = (taskCounts[task] || 0) + 1;
  }
  summary[account] = {
    total: ids.length,
    overlap: overlap.length,
    individual: ids.length - overlap.length,
    task_counts: taskCounts,
  };
}

const payload = {
  schema_version: "flowstudio_assignment_v1",
  accounts,
  overlap_case_ids: overlap.map(({ item }) => item.case_id),
  assignments,
  case_meta: caseMeta,
  summary,
};

await fs.writeFile(`${dir}/assignment.json`, `${JSON.stringify(payload, null, 2)}\n`);
console.log(JSON.stringify({ overlap: overlap.length, rest: rest.length, summary }, null, 2));
