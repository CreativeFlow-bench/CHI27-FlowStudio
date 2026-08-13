import fs from "node:fs/promises";

const casesPath =
  "/Users/primav/Documents/博一/CHI27-FlowStudio/outputs/intent_annotation_frontend/cases.json";

const cases = JSON.parse(await fs.readFile(casesPath, "utf8"));

const migrated = cases.map((item) => {
  const Cognitive_Status = item.Cognitive_Status || item.state;
  const Intuitive_Signals = item.Intuitive_Signals || item.signals || [];
  const Creativeflow_route = item.Creativeflow_route || item.creativeflow_route;
  const next = {
    ...item,
    Cognitive_Status,
    Intuitive_Signals,
    Creativeflow_route,
    retrieval_text: [
      Cognitive_Status?.label,
      Intuitive_Signals.map((signal) => signal.label).join("；"),
      Creativeflow_route?.label,
      item.episode_summary,
      item.task_group,
    ]
      .filter(Boolean)
      .join("\n"),
  };
  delete next.state;
  delete next.signals;
  delete next.creativeflow_route;
  return next;
});

await fs.writeFile(casesPath, `${JSON.stringify(migrated, null, 2)}\n`);
console.log(JSON.stringify({ cases: migrated.length, first: migrated[0].case_id, last: migrated.at(-1).case_id }, null, 2));
