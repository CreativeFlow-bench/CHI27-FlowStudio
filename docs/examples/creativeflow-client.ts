/**
 * CreativeFlow v1 server-side client.
 *
 * Do not bundle this file or CREATIVEFLOW_API_KEY into browser code.
 */

export type Variation = "low_fidelity" | "part" | "texture";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface CreativeFlowJob {
  job_id: string;
  client_job_id: string;
  variation: Variation;
  status: JobStatus;
  stage: string;
  progress: number;
  message?: string | null;
  error?: string | null;
  candidates: Array<{
    candidate_id: string;
    label?: string;
    prompt?: string;
    image_url?: string | null;
    mesh_glb_url?: string | null;
    mesh_obj_url?: string | null;
    multiview_url?: string | null;
    graph_anchor?: string | null;
    mapping?: Record<string, unknown>;
  }>;
  result_manifest_url?: string | null;
}

export class CreativeFlowClient {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "X-CreativeFlow-Key": this.apiKey,
        ...init.headers,
      },
    });
    if (!response.ok) {
      throw new Error(`CreativeFlow ${response.status}: ${await response.text()}`);
    }
    return response.json() as Promise<T>;
  }

  capabilities(): Promise<Record<string, unknown>> {
    return this.request("/api/v1/variations/capabilities");
  }

  async upload(
    file: Blob,
    filename: string,
    assetId: string,
    sessionId = "",
  ): Promise<{ asset_id: string }> {
    const form = new FormData();
    form.set("flowstudio_asset_id", assetId);
    form.set("session_id", sessionId);
    form.set("file", file, filename);
    return this.request("/api/v1/assets", { method: "POST", body: form });
  }

  submit(body: Record<string, unknown>): Promise<CreativeFlowJob> {
    return this.request("/api/v1/variation-jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  job(jobId: string): Promise<CreativeFlowJob> {
    return this.request(`/api/v1/variation-jobs/${encodeURIComponent(jobId)}`);
  }

  cancel(jobId: string): Promise<CreativeFlowJob> {
    return this.request(`/api/v1/variation-jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
  }

  async wait(
    jobId: string,
    options: { intervalMs?: number; timeoutMs?: number } = {},
  ): Promise<CreativeFlowJob> {
    const intervalMs = options.intervalMs ?? 5000;
    const timeoutMs = options.timeoutMs ?? 3_600_000;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const job = await this.job(jobId);
      if (["completed", "failed", "cancelled"].includes(job.status)) return job;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new Error(`CreativeFlow job ${jobId} timed out`);
  }
}
