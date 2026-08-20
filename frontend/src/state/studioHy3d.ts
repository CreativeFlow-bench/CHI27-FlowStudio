import type { MutableRefObject } from "react";
import type {
  AssetRecord,
  Candidate,
  FourStageUiState,
  PartDiscoveryResponse,
  SessionRecord,
  VersionGraphNode,
  VersionGraphState,
} from "../types";
import { api } from "../api";
import {
  candidatePreviewUrl,
  partSegmentationUrl,
  rankCandidates,
  remoteWorkerPathFromUrl,
} from "../utils/appHelpers";
import { reduceSolutionSpaceVisibility } from "../utils/solutionSpaceVisibility";
import { fourStageRunIdFromCandidate } from "./studioInteraction";
import {
  centeredActiveCanvasPan,
  HY3D_POLL_ATTEMPTS,
  HY3D_POLL_MS,
} from "./studioStoreLayout";

export type StudioHy3dHost = {
  session: SessionRecord | null;
  asset: AssetRecord | null;
  hy3dCandidateIds: string[];
  hy3dAdoptedRef: MutableRefObject<Set<string>>;
  hy3dWatchRef: MutableRefObject<Map<string, Promise<void>>>;
  versionGraphRef: MutableRefObject<VersionGraphState>;
  versionViewModeRef: MutableRefObject<"active" | "overview">;
  versionCanvasShellRef: MutableRefObject<HTMLDivElement | null>;
  fourStageRef: MutableRefObject<FourStageUiState>;
  allCandidates: Candidate[];
  projectRecorder: {
    record: (
      type: string,
      payload?: unknown,
      key?: string,
      options?: { critical?: boolean },
    ) => Promise<unknown> | unknown;
  };
  setAsset: (value: AssetRecord | ((current: AssetRecord | null) => AssetRecord | null)) => void;
  setParts: (value: AssetRecord["parts"]) => void;
  setCandidates: (value: Candidate[] | ((current: Candidate[]) => Candidate[])) => void;
  setPreviewCandidate: (value: Candidate | null) => void;
  setCanvasPreview: (value: { url: string; label: string } | null) => void;
  setHy3dCandidateIds: (value: string[] | ((current: string[]) => string[])) => void;
  setHy3dProgress: (value: { message: string; progress: number } | null) => void;
  setVersionViewMode: (value: "active" | "overview") => void;
  setSolutionSpaceReleased: (value: boolean | ((current: boolean) => boolean)) => void;
  setCanvasZoom: (value: number) => void;
  setCanvasPan: (value: { x: number; y: number }) => void;
  setSelectedCandidateId: (value: string | null) => void;
  setAcceptedCandidateIds: (value: string[] | ((current: string[]) => string[])) => void;
  addLog: (label: string, detail: string) => void;
  patchVersionNode: (
    nodeId: string,
    update: Partial<Pick<VersionGraphNode, "status" | "preview_url" | "mesh_url" | "obj_url" | "hy3d_job_id" | "error">>,
  ) => Promise<VersionGraphNode>;
  mergeVersionGraphNode: (node: VersionGraphNode, makeActive?: boolean) => void;
  applyVersionGraph: (next: VersionGraphState) => void;
  ensureSourceVersionNode: (session: SessionRecord, asset: AssetRecord) => Promise<VersionGraphState>;
  discoverPartsForAsset: (
    targetAsset: AssetRecord,
    trigger: "manual" | "upload" | "brush" | "hy3d",
  ) => Promise<PartDiscoveryResponse | null>;
};

export function bindStudioHy3d(h: StudioHy3dHost) {
  const {
    session,
    asset,
    hy3dCandidateIds,
    hy3dAdoptedRef,
    hy3dWatchRef,
    versionGraphRef,
    versionViewModeRef,
    versionCanvasShellRef,
    fourStageRef,
    allCandidates,
    projectRecorder,
    setAsset,
    setParts,
    setCandidates,
    setPreviewCandidate,
    setCanvasPreview,
    setHy3dCandidateIds,
    setHy3dProgress,
    setVersionViewMode,
    setSolutionSpaceReleased,
    setCanvasZoom,
    setCanvasPan,
    setSelectedCandidateId,
    setAcceptedCandidateIds,
    addLog,
    patchVersionNode,
    mergeVersionGraphNode,
    applyVersionGraph,
    ensureSourceVersionNode,
    discoverPartsForAsset,
  } = h;

  const adoptHy3dMeshAsActiveAsset = async (
    candidate: Candidate,
    meshUrl: string | null | undefined,
    objUrl: string | null | undefined,
    previewUrl: string | null | undefined,
    remotePath: string | null | undefined,
    versionNodeId?: string,
  ) => {
    if (!session || (!meshUrl && !objUrl)) return null;
    const adoptKey = versionNodeId || meshUrl || objUrl || "";
    if (adoptKey && hy3dAdoptedRef.current.has(adoptKey)) return null;
    if (adoptKey) hy3dAdoptedRef.current.add(adoptKey);
    try {
      const adopted = await api<AssetRecord>("/api/v1/assets", {
        method: "POST",
        body: JSON.stringify({
          session_id: session.session_id,
          object_type: asset?.object_type || "object",
          label: candidate.label || asset?.label || "generated model",
          mesh_url: meshUrl ?? null,
          obj_url: objUrl ?? null,
          thumbnail_url: previewUrl ?? candidate.thumbnail_url ?? null,
          metadata: {
            source: "hy3d_generated",
            source_candidate_id: candidate.candidate_id,
            parent_asset_id: asset?.asset_id ?? null,
            remote_asset: remotePath ? { path: remotePath } : undefined,
          },
        }),
      });
      const editingThisNode = !versionNodeId
        || (
          versionViewModeRef.current === "active"
          && versionGraphRef.current.active_node_id === versionNodeId
        );
      if (editingThisNode) {
        setAsset(adopted);
        setParts(adopted.parts);
        addLog("hy3d", `mesh adopted as ${adopted.asset_id}`);
        void discoverPartsForAsset(adopted, "hy3d").then((discovered) => {
          const segmented = partSegmentationUrl(discovered?.parts ?? adopted.parts);
          if (!segmented) return;
          setAsset((current) => (
            current && current.asset_id === adopted.asset_id
              ? { ...current, mesh_url: segmented, parts: discovered?.parts ?? current.parts }
              : current
          ));
        });
      }
      return adopted;
    } catch (error) {
      addLog("hy3d", `adopt mesh failed: ${String(error).slice(0, 160)}`);
      return null;
    }
  };

  /** 拖拽和按钮的统一入口：先持久化图片节点，再在后台升级同一 node_id。 */
  const dropCandidateIntoVersionGraph = async (candidate: Candidate) => {
    if (!session || !asset) return;
    try {
      await projectRecorder.record(
        "candidate.added_to_canvas",
        { candidate_id: candidate.candidate_id, parent_node_id: versionGraphRef.current.active_node_id },
        `candidate-canvas:${candidate.candidate_id}:${versionGraphRef.current.active_node_id ?? "source"}`,
        { critical: true },
      );
    } catch {
      return;
    }
    const previewUrl = candidatePreviewUrl(candidate);
    if (!previewUrl) {
      addLog("version", `${candidate.label} 没有可用预览图，无法创建版本`);
      return;
    }
    const graph = await ensureSourceVersionNode(session, asset);
    const sourceNodeId = graph.nodes.find((node) => node.parent_node_id === null)?.node_id;
    const activeNode = graph.nodes.find((node) => node.node_id === graph.active_node_id);
    const parentNodeId = activeNode?.node_id ?? sourceNodeId;
    if (!parentNodeId) throw new Error("Version 1 尚未就绪");
    const existing = graph.nodes.find(
      (node) => node.parent_node_id === parentNodeId && node.candidate_id === candidate.candidate_id,
    );
    const hasMesh = Boolean(candidate.mesh_url || candidate.obj_url);
    const now = new Date().toISOString();
    const optimisticNode: VersionGraphNode = existing ?? {
      node_id: `pending_${crypto.randomUUID().slice(0, 10)}`,
      session_id: session.session_id,
      version_number: Math.max(0, ...graph.nodes.map((item) => item.version_number)) + 1,
      parent_node_id: parentNodeId,
      candidate_id: candidate.candidate_id,
      label: candidate.label,
      preview_url: previewUrl,
      mesh_url: candidate.mesh_url,
      obj_url: candidate.obj_url,
      status: hasMesh ? "mesh_ready" : "generating_3d",
      hy3d_job_id: null,
      error: null,
      created_at: now,
      updated_at: now,
    };
    // Render before the persistence round-trip so the image node appears in the
    // same frame as the drop. The server node replaces this provisional id.
    mergeVersionGraphNode(optimisticNode, true);
    setVersionViewMode("active");
    setSolutionSpaceReleased((current) =>
      reduceSolutionSpaceVisibility(current, { type: "collapse" }),
    );
    setCanvasZoom(1);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        setCanvasPan(centeredActiveCanvasPan(versionCanvasShellRef.current));
      });
    });
    setSelectedCandidateId(candidate.candidate_id);
    setAcceptedCandidateIds((current) => Array.from(new Set([...current, candidate.candidate_id])));
    setPreviewCandidate(candidate);
    setCanvasPreview(hasMesh ? null : { url: previewUrl, label: candidate.label });
    let node: VersionGraphNode;
    try {
      node = await api<VersionGraphNode>(
        `/api/v1/sessions/${session.session_id}/version-nodes`,
        {
          method: "POST",
          body: JSON.stringify({
            parent_node_id: parentNodeId,
            candidate_id: candidate.candidate_id,
            label: candidate.label,
            preview_url: previewUrl,
            status: hasMesh ? "mesh_ready" : "generating_3d",
          }),
        },
      );
    } catch (error) {
      applyVersionGraph(graph);
      addLog("version", `版本创建失败：${String(error).slice(0, 160)}`);
      return;
    }
    if (optimisticNode.node_id !== node.node_id) {
      applyVersionGraph({
        active_node_id: graph.active_node_id,
        nodes: versionGraphRef.current.nodes.filter((item) => item.node_id !== optimisticNode.node_id),
      });
    }
    mergeVersionGraphNode(node, true);
    const activated = await api<VersionGraphState>(
      `/api/v1/sessions/${session.session_id}/active-version/${node.node_id}`,
      { method: "PUT" },
    );
    applyVersionGraph(activated);
    if (hasMesh) {
      if (node.status !== "mesh_ready") {
        await patchVersionNode(node.node_id, {
          status: "mesh_ready",
          preview_url: previewUrl,
          mesh_url: candidate.mesh_url,
          obj_url: candidate.obj_url,
          error: null,
        });
      }
      addLog("version", `Version ${node.version_number} 已载入可编辑 3D`);
      return;
    }
    addLog("version", `Version ${node.version_number} 图片已出现，后台生成 3D`);
    if (existing?.status === "generating_3d") return;
    if (node.status !== "generating_3d") {
      await patchVersionNode(node.node_id, { status: "generating_3d", error: null });
    }
    const runId = fourStageRunIdFromCandidate(candidate, fourStageRef.current.runId);
    if (!runId) {
      addLog("hy3d", `Version ${node.version_number} 无法生成 3D：缺少 run`);
      return;
    }
    void runFourStageHy3d(
      {
        ...candidate,
        metadata: { ...candidate.metadata, four_stage_artifact: true, run_id: runId },
      },
      node.node_id,
      true,
    );
  };

  /** 全览里点选高亮：不进入编辑，作为下一次 Solution Space 拖入的接入点。 */
  const watchFourStageHy3dJob = (
    remoteJobId: string,
    candidate: Candidate,
    versionNodeId?: string,
    seed?: {
      status: string;
      message?: string | null;
      progress?: number | null;
      mesh_url?: string | null;
      obj_url?: string | null;
      preview_url?: string | null;
      mesh_path?: string | null;
      obj_path?: string | null;
    },
  ) => {
    const existing = hy3dWatchRef.current.get(remoteJobId);
    if (existing) return existing;
    const startedAt = Date.now();
    const promise = (async () => {
      let updated = seed ?? {
        status: "running",
        message: "Hunyuan3D 运行中",
        progress: 0.08,
        mesh_url: null,
        obj_url: null,
      };
      if (!updated.mesh_url && !updated.obj_url) {
        try {
          updated = await api(`/api/v1/four-stage/hy3d-jobs/${encodeURIComponent(remoteJobId)}`);
        } catch (error) {
          const message = String(error);
          if (!/failed to fetch|networkerror|timeout|504|524/i.test(message)) throw error;
        }
      }
      for (let i = 0; i < HY3D_POLL_ATTEMPTS; i += 1) {
        const elapsed = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
        const clock = elapsed >= 60
          ? `${Math.floor(elapsed / 60)}m${String(elapsed % 60).padStart(2, "0")}s`
          : `${elapsed}s`;
        const base = String(updated.message || "").trim() || "Hunyuan3D 运行中";
        setHy3dProgress({
          message: `${base} · ${clock}`,
          progress: Number(updated.progress ?? 0.08),
        });
        if (updated.mesh_url || updated.obj_url) break;
        if (updated.status === "failed" || updated.status === "cancelled") {
          throw new Error(String(updated.message || updated.status));
        }
        await new Promise((resolve) => window.setTimeout(resolve, HY3D_POLL_MS));
        try {
          updated = await api(`/api/v1/four-stage/hy3d-jobs/${encodeURIComponent(remoteJobId)}`);
        } catch (error) {
          const message = String(error);
          if (/failed to fetch|networkerror|timeout|504|524/i.test(message)) {
            continue;
          }
          throw error;
        }
      }
      if (updated.mesh_url || updated.obj_url) {
        const upgraded: Candidate = {
          ...candidate,
          mesh_url: updated.mesh_url ?? candidate.mesh_url,
          obj_url: updated.obj_url ?? candidate.obj_url,
          thumbnail_url: updated.preview_url ?? candidate.thumbnail_url,
          metadata: { ...candidate.metadata, hy3d_status: "completed" },
        };
        setCandidates((current) =>
          rankCandidates(current.map((item) => (item.candidate_id === upgraded.candidate_id ? upgraded : item))),
        );
        setPreviewCandidate(upgraded);
        setCanvasPreview(null);
        if (versionNodeId) {
          await patchVersionNode(versionNodeId, {
            status: "mesh_ready",
            preview_url: candidatePreviewUrl(upgraded),
            mesh_url: upgraded.mesh_url,
            obj_url: upgraded.obj_url,
            error: null,
          });
        }
        addLog("hy3d", "四阶段 mesh ready — 已原位升级当前版本");
        const remotePath =
          String(updated.obj_path || updated.mesh_path || "").trim()
          || remoteWorkerPathFromUrl(upgraded.obj_url)
          || remoteWorkerPathFromUrl(upgraded.mesh_url);
        void adoptHy3dMeshAsActiveAsset(
          upgraded,
          upgraded.mesh_url,
          upgraded.obj_url,
          candidatePreviewUrl(upgraded),
          remotePath,
          versionNodeId,
        );
        return;
      }
      throw new Error(String(updated.message || updated.status || "Hy3D timed out"));
    })()
      .catch(async (error) => {
        const message = String(error);
        const transient = /failed to fetch|networkerror|timeout|504|524/i.test(message);
        const stillGenerating = versionNodeId
          ? versionGraphRef.current.nodes.find((item) => item.node_id === versionNodeId)?.status === "generating_3d"
          : false;
        if (versionNodeId && stillGenerating && !transient) {
          await patchVersionNode(versionNodeId, {
            status: "mesh_failed",
            error: message.slice(0, 500),
          }).catch(() => undefined);
        } else if (transient) {
          addLog("hy3d", "请求中断，继续等待 GPU 上的 3D 任务");
        }
        addLog("hy3d", `四阶段候选 hy3d: ${message.slice(0, 160)}`);
      })
      .finally(() => {
        hy3dWatchRef.current.delete(remoteJobId);
        setHy3dCandidateIds((current) => current.filter((id) => id !== candidate.candidate_id));
      });
    hy3dWatchRef.current.set(remoteJobId, promise);
    return promise;
  };

  const runFourStageHy3d = async (candidate: Candidate, versionNodeId?: string, force = false) => {
    const runId = String(candidate.metadata?.run_id ?? fourStageRef.current.runId ?? "");
    const artifactUrl = candidate.thumbnail_url ?? candidatePreviewUrl(candidate);
    if (!runId || !artifactUrl || (!force && hy3dCandidateIds.includes(candidate.candidate_id))) return;
    setHy3dCandidateIds((current) => [...current, candidate.candidate_id]);
    setHy3dProgress({ message: "已提交 Hunyuan3D", progress: 0.08 });
    try {
      const started = await api<{
        status: string;
        remote_job_id?: string | null;
        message?: string | null;
        progress?: number | null;
        mesh_url?: string | null;
        obj_url?: string | null;
        preview_url?: string | null;
        mesh_path?: string | null;
        obj_path?: string | null;
      }>(
        `/api/v1/four-stage/runs/${runId}/hy3d-candidate`,
        {
          method: "POST",
          body: JSON.stringify({
            session_id: session?.session_id,
            candidate_id: candidate.candidate_id,
            image_url: artifactUrl,
            prompt_index: Number(candidate.metadata?.prompt_index ?? 0),
            version_node_id: versionNodeId ?? null,
          }),
        },
      );
      const remoteJobId = String(started.remote_job_id || "").trim();
      if (versionNodeId && remoteJobId) {
        await patchVersionNode(versionNodeId, { hy3d_job_id: remoteJobId }).catch(() => undefined);
      }
      if (!remoteJobId) {
        throw new Error(started.status || "Hy3D worker did not return a job id");
      }
      await watchFourStageHy3dJob(remoteJobId, candidate, versionNodeId, started);
    } catch (error) {
      const message = String(error);
      const transient = /failed to fetch|networkerror|timeout|504|524/i.test(message);
      if (versionNodeId && !transient) {
        await patchVersionNode(versionNodeId, {
          status: "mesh_failed",
          error: message.slice(0, 500),
        }).catch(() => undefined);
      } else if (transient) {
        addLog("hy3d", "提交中断，后端会继续盯 GPU 上的 3D 任务");
      }
      addLog("hy3d", `四阶段候选 hy3d: ${message.slice(0, 160)}`);
      setHy3dCandidateIds((current) => current.filter((id) => id !== candidate.candidate_id));
    }
  };

  const retryVersionNode = async (nodeId: string) => {
    const node = versionGraphRef.current.nodes.find((item) => item.node_id === nodeId);
    if (!node || node.status === "mesh_ready") return;
    const live = node.candidate_id
      ? allCandidates.find((item) => item.candidate_id === node.candidate_id)
      : undefined;
    const fourStageMatch = node.candidate_id ? /^fourstage_(.+)_(\d+)$/.exec(node.candidate_id) : null;
    const runId = fourStageRunIdFromCandidate(
      live ?? { candidate_id: node.candidate_id, metadata: {} },
      fourStageRef.current.runId,
    ) || (fourStageMatch?.[1] ?? "");
    const imageUrl = live?.thumbnail_url ?? (live ? candidatePreviewUrl(live) : null) ?? node.preview_url;
    const existingMesh = live?.mesh_url ?? node.mesh_url;
    const existingObj = live?.obj_url ?? node.obj_url;
    const sibling = versionGraphRef.current.nodes.find((item) => (
      item.node_id !== nodeId
      && item.parent_node_id !== null
      && item.status === "mesh_ready"
      && Boolean(item.mesh_url || item.obj_url)
      && Boolean(node.candidate_id)
      && item.candidate_id === node.candidate_id
    ));
    if (existingMesh || existingObj || sibling) {
      const meshUrl = existingMesh ?? sibling?.mesh_url ?? null;
      const objUrl = existingObj ?? sibling?.obj_url ?? null;
      await patchVersionNode(nodeId, {
        status: "mesh_ready",
        preview_url: imageUrl ?? sibling?.preview_url ?? node.preview_url,
        mesh_url: meshUrl,
        obj_url: objUrl,
        error: null,
      });
      addLog("hy3d", "复用已完成的 3D，不再重新生成");
      return;
    }
    const retryCandidate: Candidate = live ?? {
      candidate_id: node.candidate_id ?? `retry_${node.node_id}`,
      job_id: "",
      session_id: session?.session_id ?? "",
      source_asset_id: "",
      source_part_id: null,
      label: node.label,
      decision: "accepted",
      mesh_url: null,
      obj_url: null,
      thumbnail_url: imageUrl,
      scores: {},
      metadata: {
        four_stage_artifact: Boolean(runId && (live?.metadata?.four_stage_artifact || fourStageMatch)),
        run_id: runId || undefined,
        prompt_index: fourStageMatch ? Math.max(0, Number(fourStageMatch[2]) - 1) : 0,
      },
    };
    const useFourStage = Boolean(runId && imageUrl);
    if (!useFourStage) {
      addLog("hy3d", `Version ${node.version_number} 无法重试 3D：缺少预览图或 run`);
      return;
    }
    const existingJobId = String(node.hy3d_job_id || "").trim();
    if (useFourStage && node.status === "generating_3d" && existingJobId) {
      const watching = {
        ...retryCandidate,
        thumbnail_url: imageUrl,
        metadata: { ...retryCandidate.metadata, four_stage_artifact: true, run_id: runId },
      };
      setHy3dCandidateIds((current) => (
        current.includes(watching.candidate_id) ? current : [...current, watching.candidate_id]
      ));
      setHy3dProgress({ message: "Hunyuan3D 运行中", progress: 0.08 });
      void watchFourStageHy3dJob(existingJobId, watching, nodeId);
      return;
    }
    await patchVersionNode(nodeId, { status: "generating_3d", error: null });
    setHy3dProgress({ message: "已提交 Hunyuan3D", progress: 0.08 });
    void runFourStageHy3d(
      {
        ...retryCandidate,
        thumbnail_url: imageUrl,
        metadata: { ...retryCandidate.metadata, four_stage_artifact: true, run_id: runId },
      },
      nodeId,
      true,
    );
  };

  return {
    adoptHy3dMeshAsActiveAsset,
    dropCandidateIntoVersionGraph,
    watchFourStageHy3dJob,
    runFourStageHy3d,
    retryVersionNode,
  };
}
