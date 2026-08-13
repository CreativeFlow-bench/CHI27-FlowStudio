export type ExperimentRecordingHealth = "healthy" | "degraded" | "paused";

export type BrowserExperimentEvent = {
  event_type: string;
  actor: "user";
  idempotency_key: string;
  occurred_at: string;
  payload: Record<string, unknown>;
  asset_refs?: Array<Record<string, unknown>>;
};

type RecorderOptions = {
  isActive: () => boolean;
  postBatch: (events: BrowserExperimentEvent[]) => Promise<unknown>;
  now?: () => number;
  onHealthChange?: (health: ExperimentRecordingHealth, error?: string) => void;
};

const SECRET_KEYS = new Set(["authorization", "cookie", "api_key", "apikey", "token", "password"]);

export function sanitizeExperimentPayload<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeExperimentPayload(item)) as T;
  }
  if (value && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      if (SECRET_KEYS.has(key.toLowerCase())) continue;
      result[key] = sanitizeExperimentPayload(item);
    }
    return result as T;
  }
  if (typeof value === "string" && /^https?:\/\//.test(value)) {
    try {
      const url = new URL(value);
      url.search = "";
      url.hash = "";
      return url.toString() as T;
    } catch {
      return value;
    }
  }
  return value;
}

export function createExperimentEventRecorder(options: RecorderOptions) {
  let chain: Promise<unknown> = Promise.resolve();
  const now = options.now ?? Date.now;

  const record = (
    eventType: string,
    payload: Record<string, unknown>,
    idempotencyKey: string,
    config: { critical?: boolean; assetRefs?: Array<Record<string, unknown>> } = {},
  ): Promise<unknown | null> => {
    if (!options.isActive()) return Promise.resolve(null);
    const event: BrowserExperimentEvent = {
      event_type: eventType,
      actor: "user",
      idempotency_key: idempotencyKey,
      occurred_at: new Date(now()).toISOString(),
      payload: sanitizeExperimentPayload(payload),
      ...(config.assetRefs?.length
        ? { asset_refs: sanitizeExperimentPayload(config.assetRefs) }
        : {}),
    };
    const write = chain.then(() => options.postBatch([event]));
    chain = write.catch(() => undefined);
    return write.then(
      (result) => {
        options.onHealthChange?.("healthy");
        return result;
      },
      (error) => {
        options.onHealthChange?.(config.critical ? "paused" : "degraded", String(error));
        throw error;
      },
    );
  };

  return { record, flush: () => chain };
}

export async function recordedMutation<T>({
  requested,
  mutate,
  completed,
  failed,
}: {
  requested: () => Promise<unknown>;
  mutate: () => Promise<T>;
  completed?: (result: T) => Promise<unknown>;
  failed?: (error: unknown) => Promise<unknown>;
}): Promise<T> {
  await requested();
  try {
    const result = await mutate();
    await completed?.(result);
    return result;
  } catch (error) {
    await failed?.(error);
    throw error;
  }
}

export function createTextSnapshotDebouncer({
  record,
  delayMs = 500,
}: {
  record: (text: string, idempotencyKey: string) => Promise<unknown>;
  delayMs?: number;
}) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending: { text: string; key: string } | null = null;
  const flush = async () => {
    if (timer) clearTimeout(timer);
    timer = null;
    const next = pending;
    pending = null;
    if (next) await record(next.text, next.key);
  };
  const schedule = (text: string, key: string) => {
    pending = { text, key };
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void flush(), delayMs);
  };
  return { schedule, flush, cancel: () => { if (timer) clearTimeout(timer); pending = null; } };
}
