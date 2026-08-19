/**
 * Network and URL helpers (refactor plan P1a).
 * Single place for API base, WebSocket base and fetch/url utilities.
 */

import { resolveRuntimeEndpoints } from "./utils/runtimeEndpoints";

declare global {
  interface Window {
    __FLOWSTUDIO_API_BASE__?: string;
    __FLOWSTUDIO_WS_BASE__?: string;
  }
}

const runtimeEndpoints = resolveRuntimeEndpoints({
  buildApiBase: import.meta.env.VITE_API_BASE,
  buildWsBase: import.meta.env.VITE_WS_BASE,
  runtimeApiBase: window.__FLOWSTUDIO_API_BASE__,
  runtimeWsBase: window.__FLOWSTUDIO_WS_BASE__,
  protocol: window.location.protocol,
  hostname: window.location.hostname,
  port: window.location.port,
  origin: window.location.origin,
});

export const API_BASE = runtimeEndpoints.apiBase;
export const WS_BASE = runtimeEndpoints.wsBase;

export const SESSION_STORAGE_KEY = "flowstudio:last-session-id";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

export type SseEventKind = "phase" | "final" | "done" | "error";

export interface SseEvent {
  event: SseEventKind;
  data: unknown;
  /**
   * Parsed raw data for the named event. ``done`` events carry the full
   * semantic-divergence response; ``final``/``phase`` events carry a
   * structured progress payload.
   */
  raw: string;
}

export async function* sseFetch(
  path: string,
  init?: RequestInit,
): AsyncGenerator<SseEvent, void, void> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    throw new Error(text || response.statusText || `sse ${path} failed`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent: SseEventKind | null = null;
  let dataLines: string[] = [];
  const emit = (): SseEvent | null => {
    if (currentEvent === null || dataLines.length === 0) return null;
    const raw = dataLines.join("\n");
    let parsed: unknown = raw;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // Keep raw string when payload is not JSON.
    }
    const event = currentEvent;
    currentEvent = null;
    dataLines = [];
    return { event, data: parsed, raw };
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      const line = buffer.slice(0, newlineIndex).replace(/\r$/, "");
      buffer = buffer.slice(newlineIndex + 1);
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim() as SseEventKind;
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      } else if (line === "") {
        const out = emit();
        if (out) yield out;
      }
      newlineIndex = buffer.indexOf("\n");
    }
  }
  if (buffer.length > 0) {
    const line = buffer.replace(/\r$/, "");
    if (line.startsWith("event:")) {
      currentEvent = line.slice(6).trim() as SseEventKind;
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  const tail = emit();
  if (tail) yield tail;
}

export function timeoutAfter(ms: number, label: string): Promise<never> {
  return new Promise((_, reject) => {
    window.setTimeout(() => reject(new Error(`${label} timed out`)), ms);
  });
}

export function absoluteUrl(url: string) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${API_BASE}${url}`;
}

export function inferMeshExtension(url: string | null | undefined) {
  if (!url) return null;
  if (["none", "null", "undefined", "nan"].includes(url.trim().toLowerCase())) return null;
  const directExtension = url.split("?")[0].toLowerCase().split(".").pop();
  if (directExtension && ["glb", "gltf", "obj", "ply"].includes(directExtension)) {
    return directExtension;
  }
  try {
    const parsed = new URL(url, API_BASE);
    const artifactPath = parsed.searchParams.get("path");
    const artifactExtension = artifactPath?.toLowerCase().split("?")[0].split(".").pop();
    if (artifactExtension && ["glb", "gltf", "obj", "ply"].includes(artifactExtension)) {
      return artifactExtension;
    }
  } catch {
    return null;
  }
  return null;
}

export function inferMtlUrl(sourceUrl: string) {
  try {
    const parsed = new URL(sourceUrl, API_BASE);
    const remotePath = parsed.searchParams.get("path");
    if (remotePath?.toLowerCase().endsWith(".obj")) {
      const mtlPath = remotePath.replace(/[^/]+\.obj$/i, "material.mtl");
      parsed.searchParams.set("path", mtlPath);
      return parsed.toString();
    }
  } catch {
    // Fall through to direct local path handling.
  }
  if (!sourceUrl.toLowerCase().split("?")[0].endsWith(".obj")) return null;
  const nextUrl = sourceUrl.replace(/[^/]+\.obj(\?.*)?$/i, "material.mtl");
  if (nextUrl.startsWith("http")) return nextUrl;
  return `${API_BASE}${nextUrl}`;
}

export function assetExportUrl(assetId: string, format: "glb" | "obj") {
  return `${API_BASE}/api/v1/assets/${assetId}/export?format=${format}`;
}

export async function downloadAssetExport(
  assetId: string,
  format: "glb" | "obj",
  filename?: string,
) {
  const response = await fetch(assetExportUrl(assetId, format));
  if (!response.ok) {
    throw new Error((await response.text()) || `export ${format} failed`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || `export.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
