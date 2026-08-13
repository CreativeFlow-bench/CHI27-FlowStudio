/**
 * Viewport screenshot evidence capture + upload (P1).
 *
 * Captures the three.js viewport canvas as a compressed JPEG, uploads it to
 * POST /api/v1/screenshots and returns the persisted artifact. Keeps base64
 * out of WebSocket payloads (only the artifact URL travels).
 */
import { API_BASE } from "../api";
import type { ArtifactRecord, ThreeViewportHandle } from "../types";

export async function uploadViewportScreenshot(
  dataUrl: string,
  opts: {
    sessionId: string;
    assetId?: string | null;
    partId?: string | null;
    metadata?: Record<string, unknown>;
  },
): Promise<ArtifactRecord | null> {
  try {
    const blob = await (await fetch(dataUrl)).blob();
    const form = new FormData();
    form.set("session_id", opts.sessionId);
    if (opts.assetId) form.set("asset_id", opts.assetId);
    if (opts.partId) form.set("part_id", opts.partId);
    if (opts.metadata) form.set("metadata", JSON.stringify(opts.metadata));
    form.set("file", blob, "viewport.jpg");
    const response = await fetch(`${API_BASE}/api/v1/screenshots`, { method: "POST", body: form });
    if (!response.ok) throw new Error(`screenshot upload failed: ${response.status}`);
    return (await response.json()) as ArtifactRecord;
  } catch (error) {
    console.warn("viewport screenshot capture failed", error);
    return null;
  }
}

export async function captureAndUploadViewport(
  viewport: ThreeViewportHandle | null,
  opts: {
    sessionId: string;
    assetId?: string | null;
    partId?: string | null;
    metadata?: Record<string, unknown>;
    width?: number;
    quality?: number;
  },
): Promise<ArtifactRecord | null> {
  // Prefer orthographic front from the three-view capture so identity / Generate
  // stay front-facing instead of whatever the user last orbited to.
  const views = viewport?.captureThreeViews?.(opts.width ?? 640, opts.quality ?? 0.7) ?? {};
  const dataUrl =
    views.front ??
    viewport?.captureJpeg?.(opts.width ?? 640, opts.quality ?? 0.7) ??
    null;
  if (!dataUrl) return null;
  return uploadViewportScreenshot(dataUrl, {
    sessionId: opts.sessionId,
    assetId: opts.assetId,
    partId: opts.partId,
    metadata: {
      ...(opts.metadata ?? {}),
      view: "front",
      has_side: Boolean(views.side),
      has_top: Boolean(views.top),
    },
  });
}
