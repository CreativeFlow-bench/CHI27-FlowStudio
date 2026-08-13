export function projectPresentation(detail: {
  project: { title: string };
  active_run: { run_number: number; recording_status: string } | null;
} | null) {
  if (!detail) {
    return {
      title: "临时工作区",
      status: "未记录",
      primaryAction: "新建实验文件",
      tone: "temporary" as const,
    };
  }
  const run = detail.active_run;
  return {
    title: detail.project.title,
    status: run
      ? `正在记录 · Run ${String(run.run_number).padStart(2, "0")}`
      : "Run 已结束",
    primaryAction: "查看时间线",
    tone: run?.recording_status === "paused" ? "warning" as const : "recording" as const,
  };
}
