/**
 * Left studio menu: source uploads, runtime status, export, case (refactor P1a).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Box, Download, GripVertical, Play, RefreshCw, Rocket, Save, Upload, Wifi } from "lucide-react";
import type {
  ArtifactRecord,
  AssetRecord,
  BackendHealth,
  BenchmarkAsset,
  CanvasPrimitive,
  CaseRecord,
  JobRecord,
  ModelApiProbeResult,
  RemoteWorkerHealth,
  SessionRecord,
  SystemServiceInfo,
  ExperimentProjectDetail,
  ExperimentEvent,
  ExperimentExportRecord,
} from "../../types";
import { API_BASE, absoluteUrl, api, downloadAssetExport, inferMeshExtension } from "../../api";
import { benchmarkAssetGroups, benchmarkPreviewUrl } from "../../utils/appHelpers";
import { EmptyState, KeyValue, Panel } from "../ui/primitives";
import { ProjectSection } from "../project/ProjectSection";
import { ProjectDialog } from "../project/ProjectDialog";
import { ProjectTimeline } from "../project/ProjectTimeline";

export function StudioMenu({
  studioDrawerOpen,
  menuWidth,
  fileInputRef,
  referenceImageInputRef,
  referenceModelInputRef,
  uploadAsset,
  uploadReferenceImage,
  uploadReferenceModel,
  uploading,
  session,
  referenceImages,
  referenceModels,
  benchmarkAssets,
  selectedBenchmarkId,
  loadingBenchmark,
  switchBenchmarkAsset,
  loadBenchmarkAssets,
  asset,
  canvasPrimitive,
  startBlankWorkspace,
  hasRealModel,
  backendHealth,
  remoteOnline,
  geometryReady,
  renderReady,
  job,
  refreshRemoteHealth,
  refreshSystemServices,
  startSystemService,
  bootstrapSystemServices,
  systemServices,
  systemServicesLoading,
  startingServiceIds,
  bootstrapRunning,
  acceptedCandidateIds,
  caseTitle,
  setCaseTitle,
  activeCaseAssetId,
  savingCase,
  saveCase,
  savedCase,
  onMenuHandlePointerDown,
  onMenuHandlePointerMove,
  onMenuHandlePointerUp,
  onMenuToggle,
  menuDragRef,
  project,
  projectList,
  projectEvents,
  projectDialogOpen,
  setProjectDialogOpen,
  projectTimelineOpen,
  setProjectTimelineOpen,
  projectBusy,
  recordingError,
  createExperimentProject,
  openExperimentProject,
  endExperimentRun,
  exportExperimentProject,
}: {
  studioDrawerOpen: boolean,
  menuWidth: number,
  fileInputRef: React.RefObject<HTMLInputElement | null>,
  referenceImageInputRef: React.RefObject<HTMLInputElement | null>,
  referenceModelInputRef: React.RefObject<HTMLInputElement | null>,
  uploadAsset: (file: File | undefined) => void,
  uploadReferenceImage: (file: File | undefined) => void,
  uploadReferenceModel: (file: File | undefined) => void,
  uploading: boolean,
  session: SessionRecord | null,
  referenceImages: ArtifactRecord[],
  referenceModels: ArtifactRecord[],
  benchmarkAssets: BenchmarkAsset[],
  selectedBenchmarkId: string,
  loadingBenchmark: boolean,
  switchBenchmarkAsset: (id: string) => void,
  loadBenchmarkAssets: () => Promise<unknown>,
  asset: AssetRecord | null,
  canvasPrimitive: CanvasPrimitive,
  startBlankWorkspace: () => void,
  hasRealModel: boolean,
  backendHealth: BackendHealth | null,
  remoteOnline: boolean,
  geometryReady: boolean,
  renderReady: boolean,
  job: JobRecord | null,
  refreshRemoteHealth: () => void,
  refreshSystemServices: () => void,
  startSystemService: (id: string) => void,
  bootstrapSystemServices: () => void,
  systemServices: SystemServiceInfo[],
  systemServicesLoading: boolean,
  startingServiceIds: string[],
  bootstrapRunning: boolean,
  acceptedCandidateIds: string[],
  caseTitle: string,
  setCaseTitle: (v: string) => void,
  activeCaseAssetId: string | null,
  savingCase: boolean,
  saveCase: () => void,
  savedCase: CaseRecord | null,
  onMenuHandlePointerDown: (event: React.PointerEvent<HTMLButtonElement>) => void,
  onMenuHandlePointerMove: (event: React.PointerEvent<HTMLButtonElement>) => void,
  onMenuHandlePointerUp: (event: React.PointerEvent<HTMLButtonElement>) => void,
  onMenuToggle: () => void,
  menuDragRef: React.MutableRefObject<{
    pointerId: number;
    startX: number;
    startWidth: number;
    wasOpen: boolean;
    moved: boolean;
  } | null>,
  project: ExperimentProjectDetail | null,
  projectList: ExperimentProjectDetail[],
  projectEvents: ExperimentEvent[],
  projectDialogOpen: boolean,
  setProjectDialogOpen: (open: boolean) => void,
  projectTimelineOpen: boolean,
  setProjectTimelineOpen: (open: boolean) => void,
  projectBusy: boolean,
  recordingError: string | null,
  createExperimentProject: (input: { title: string; participantCode?: string; conditionLabel?: string; baselineMode: "blank" | "current_state" }) => Promise<unknown>,
  openExperimentProject: (id: string) => Promise<unknown>,
  endExperimentRun: () => Promise<unknown>,
  exportExperimentProject: () => Promise<ExperimentExportRecord | null>,
}) {
  // Tracks whether the most recent pointer interaction on the handle moved
  // beyond the click threshold. A click after a drag should not toggle the menu.
  const handleDragMovedRef = useRef(false);
  const groups = useMemo(() => benchmarkAssetGroups(benchmarkAssets), [benchmarkAssets]);
  const defaultOpenGroup = useMemo(() => {
    if (!groups.length) return "";
    if (selectedBenchmarkId) {
      const matched = groups.find((group) =>
        group.assets.some((item) => item.benchmark_id === selectedBenchmarkId),
      );
      if (matched) return matched.label;
    }
    return groups[0]?.label ?? "";
  }, [groups, selectedBenchmarkId]);
  const [openBenchmarkGroup, setOpenBenchmarkGroup] = useState<string | null>(null);
  const [failedPreviewUrls, setFailedPreviewUrls] = useState<Set<string>>(() => new Set());
  const [modelProbe, setModelProbe] = useState<ModelApiProbeResult | null>(null);
  const [modelProbeBusy, setModelProbeBusy] = useState(false);
  const [modelProbeError, setModelProbeError] = useState<string | null>(null);
  const [hy3dProbe, setHy3dProbe] = useState<{
    ok: boolean;
    latencyMs: number;
    python: string;
    error: string | null;
    workerOk: boolean;
    pythonOk: boolean;
    hy3dOk: boolean;
  } | null>(null);
  const [hy3dProbeBusy, setHy3dProbeBusy] = useState(false);
  const activeBenchmarkGroup = openBenchmarkGroup ?? defaultOpenGroup;

  const runModelProbe = async (includeImage: boolean) => {
    setModelProbeBusy(true);
    setModelProbeError(null);
    try {
      const result = await api<ModelApiProbeResult>(
        `/api/v1/model-api/probe?include_image=${includeImage ? "true" : "false"}`,
      );
      setModelProbe(result);
    } catch (error) {
      setModelProbe(null);
      setModelProbeError(String(error).slice(0, 180));
    } finally {
      setModelProbeBusy(false);
    }
  };
  const runHy3dProbe = async () => {
    setHy3dProbeBusy(true);
    const started = Date.now();
    try {
      const health = await api<RemoteWorkerHealth>("/api/v1/remote-worker/health");
      const pythonOk = Boolean(health.python_bin_exists);
      const hy3dOk = Boolean(
        health.hy3d_script_exists
        && health.mesh_worker_exists
        && (health.creativeflow_pipeline?.hy3d_ready ?? pythonOk),
      );
      const workerOk = Boolean(health.ok) && !health.error;
      setHy3dProbe({
        ok: workerOk && pythonOk && hy3dOk,
        latencyMs: Date.now() - started,
        python: health.python_bin || "python",
        error: health.error ?? null,
        workerOk,
        pythonOk,
        hy3dOk,
      });
    } catch (error) {
      setHy3dProbe({
        ok: false,
        latencyMs: Date.now() - started,
        python: "—",
        error: String(error).slice(0, 180),
        workerOk: false,
        pythonOk: false,
        hy3dOk: false,
      });
    } finally {
      setHy3dProbeBusy(false);
    }
  };
  useEffect(() => {
    if (!studioDrawerOpen) return;
    const missingPreview = benchmarkAssets.some((item) => !benchmarkPreviewUrl(item));
    if (!benchmarkAssets.length || missingPreview) {
      void loadBenchmarkAssets();
    }
  }, [studioDrawerOpen]);
  return (
    <>
      <aside
        id="studio-rail"
        className={`studio-rail ${studioDrawerOpen ? "is-open" : ""}`}
        style={{ width: studioDrawerOpen ? menuWidth : 0 }}
        aria-label="Studio menu"
        aria-hidden={!studioDrawerOpen}
        inert={!studioDrawerOpen}
      >
        <div className="studio-rail-scroll">
          <div className="studio-menu-primary">
            <span className="studio-menu-section-label">Experiment file</span>
            <ProjectSection
              project={project}
              recordingError={recordingError}
              onNew={() => setProjectDialogOpen(true)}
              onOpen={() => setProjectDialogOpen(true)}
              onTimeline={() => setProjectTimelineOpen(true)}
            />
          </div>
          <section className="studio-menu-section studio-source-section" aria-labelledby="studio-source-label">
            <div className="studio-menu-section-heading">
              <span id="studio-source-label" className="studio-menu-section-label">Workspace</span>
              <small>输入与参考</small>
            </div>
            <Panel title="Source" icon={<Upload size={16} />}>
              <div className="upload-row">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".glb,.obj,.zip"
                  onChange={(event) => void uploadAsset(event.target.files?.[0])}
                />
                <input
                  ref={referenceImageInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(event) => void uploadReferenceImage(event.target.files?.[0])}
                />
                <input
                  ref={referenceModelInputRef}
                  type="file"
                  accept=".glb,.obj,.zip"
                  onChange={(event) => void uploadReferenceModel(event.target.files?.[0])}
                />
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading || !session}>
                  <Upload size={16} /> {uploading ? "Uploading" : "Upload OBJ/GLB"}
                </button>
                <button onClick={() => referenceImageInputRef.current?.click()} disabled={uploading || !session}>
                  <Upload size={16} /> Ref Image
                </button>
                <button onClick={() => referenceModelInputRef.current?.click()} disabled={uploading || !session}>
                  <Upload size={16} /> Ref Model
                </button>
              </div>
              {referenceImages.length ? (
                <div className="reference-image-strip">
                  {referenceImages.slice(0, 4).map((item) => (
                    <div className="reference-image-chip" key={item.artifact_id}>
                      <img src={absoluteUrl(item.url)} alt="reference" width={72} height={52} loading="lazy" />
                      <span>{String(item.metadata?.role ?? "reference")}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {referenceModels.length ? (
                <div className="reference-model-strip">
                  {referenceModels.slice(0, 4).map((item) => (
                    <div className="reference-model-chip" key={item.artifact_id}>
                      <Box size={13} />
                      <span>{String(item.metadata?.uploaded_filename ?? item.metadata?.role ?? "model ref")}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {benchmarkAssets.length ? (
                <div className="design-db-browser" aria-label="Design DB white models">
                  <div className="design-db-browser-head">
                    <span>Design DB</span>
                    {loadingBenchmark ? <em>加载中…</em> : <em>{benchmarkAssets.length} models</em>}
                  </div>
                  <div className="design-db-group-tabs" role="tablist" aria-label="Model groups">
                    {groups.map((group) => (
                      <button
                        key={group.label}
                        type="button"
                        role="tab"
                        aria-selected={activeBenchmarkGroup === group.label}
                        className={activeBenchmarkGroup === group.label ? "is-active" : undefined}
                        onClick={() => setOpenBenchmarkGroup(group.label)}
                      >
                        {group.label.replace(/^White Models · /, "")}
                        <i>{group.assets.length}</i>
                      </button>
                    ))}
                  </div>
                  {groups
                    .filter((group) => group.label === activeBenchmarkGroup)
                    .map((group) => (
                      <div className="design-db-grid" key={group.label} role="listbox" aria-label={group.label}>
                        {group.assets.map((item) => {
                          const preview = benchmarkPreviewUrl(item);
                          const showPreview = Boolean(preview && !failedPreviewUrls.has(preview));
                          const selected = selectedBenchmarkId === item.benchmark_id;
                          const disabled = loadingBenchmark || !session || item.model_available === false;
                          return (
                            <button
                              key={item.benchmark_id}
                              type="button"
                              role="option"
                              aria-selected={selected}
                              className={`design-db-card${selected ? " is-selected" : ""}${item.model_available === false ? " is-unavailable" : ""}`}
                              disabled={disabled}
                              title={item.label}
                              onClick={() => void switchBenchmarkAsset(item.benchmark_id)}
                            >
                              <span className="design-db-thumb">
                                {showPreview && preview ? (
                                  <img
                                    src={preview}
                                    alt=""
                                    loading="lazy"
                                    onError={() => {
                                      setFailedPreviewUrls((current) => {
                                        if (current.has(preview)) return current;
                                        const next = new Set(current);
                                        next.add(preview);
                                        return next;
                                      });
                                    }}
                                  />
                                ) : (
                                  <span className="design-db-thumb-fallback" aria-hidden="true">
                                    {(item.label.split("·").pop() ?? item.label).trim().slice(0, 1).toUpperCase()}
                                  </span>
                                )}
                              </span>
                              <strong>{item.label.includes("·") ? item.label.split("·").pop()?.trim() : item.label}</strong>
                            </button>
                          );
                        })}
                      </div>
                    ))}
                </div>
              ) : (
                <div className="benchmark-loading">白模库加载中…</div>
              )}
              <button className="ghost compact" disabled={!session || (!asset && !canvasPrimitive)} onClick={startBlankWorkspace}>
                Start Blank
              </button>
              {hasRealModel ? <KeyValue label="model" value={asset?.label} /> : <EmptyState text="Blank workspace: compose text, refs, or choose/upload a model" />}
            </Panel>
          </section>
          <section className="studio-menu-section studio-output-section" aria-labelledby="studio-output-label">
            <div className="studio-menu-section-heading">
              <span id="studio-output-label" className="studio-menu-section-label">Output</span>
              <small>导出与保存</small>
            </div>
            {asset && hasRealModel ? (
              <Panel title="Export 3D" icon={<Download size={16} />}>
                <p className="export-note">Download only real mesh outputs from the active asset.</p>
                <div className="case-link-row">
                  {asset.mesh_url && inferMeshExtension(asset.mesh_url) !== "obj" ? (
                    <button
                      type="button"
                      className="export-file-link"
                      onClick={() => {
                        void downloadAssetExport(asset.asset_id, "glb", `${asset.label || "model"}.glb`).catch((error) => {
                          window.alert(String(error).slice(0, 180));
                        });
                      }}
                    >
                      Export GLB
                    </button>
                  ) : null}
                  {asset.obj_url || inferMeshExtension(asset.mesh_url ?? "") === "obj" ? (
                    <button
                      type="button"
                      className="export-file-link"
                      onClick={() => {
                        void downloadAssetExport(asset.asset_id, "obj", `${asset.label || "model"}.obj`).catch((error) => {
                          window.alert(String(error).slice(0, 180));
                        });
                      }}
                    >
                      Export OBJ
                    </button>
                  ) : null}
                </div>
              </Panel>
            ) : null}

            {acceptedCandidateIds.length ? (
              <Panel title="Case" icon={<Save size={16} />}>
                <label>
                  Title
                  <input value={caseTitle} onChange={(event) => setCaseTitle(event.target.value)} />
                </label>
                <button className="ghost" disabled={!activeCaseAssetId || savingCase} onClick={saveCase}>
                  <Save size={16} /> {savingCase ? "Saving" : "Save case"}
                </button>
                {savedCase?.report_url ? (
                  <div className="case-link-row">
                    <a href={`${API_BASE}${savedCase.report_url}`} target="_blank" rel="noreferrer">
                      Report
                    </a>
                  </div>
                ) : null}
              </Panel>
            ) : null}
            {!asset && !acceptedCandidateIds.length ? (
              <p className="studio-output-empty">生成或接受方案后，可在这里导出模型并保存案例。</p>
            ) : null}
          </section>
          <details className="studio-system-disclosure">
            <summary>
              <span className="studio-system-summary-icon"><Activity size={15} /></span>
              <span>
                <strong>System status</strong>
                <small>{backendHealth?.status === "ok" && remoteOnline ? "All core services online" : "Check runtime and services"}</small>
              </span>
              <i aria-hidden="true" />
            </summary>
            <div className="studio-system-body">
              <Panel title="Runtime" icon={<Activity size={16} />}>
                <div className="runtime-chip-row">
                  <span>backend {backendHealth?.status === "ok" ? "online" : "offline"}</span>
                  {remoteOnline ? <span>worker online</span> : <span>worker offline</span>}
                  {geometryReady ? <span>geometry</span> : null}
                  {renderReady ? <span>render</span> : null}
                  {session ? <span>{session.session_id.slice(0, 10)}</span> : null}
                  {job ? <span>{job.status}</span> : null}
                </div>
                <button className="ghost compact" onClick={refreshRemoteHealth}>
                  <RefreshCw size={16} /> Check runtime
                </button>
              </Panel>
            <Panel title="Services" icon={<Activity size={16} />}>
              <div className="service-toolbar">
                <button
                  className="ghost compact"
                  onClick={() => void refreshSystemServices()}
                  disabled={systemServicesLoading}
                >
                  <RefreshCw size={14} /> Refresh
                </button>
                <button
                  className="ghost compact"
                  onClick={() => void bootstrapSystemServices()}
                  disabled={bootstrapRunning || systemServicesLoading}
                >
                  <Rocket size={14} /> {bootstrapRunning ? "Starting…" : "Start missing"}
                </button>
              </div>
              {systemServices.length === 0 ? (
                <EmptyState text={systemServicesLoading ? "probing services…" : "no service info"} />
              ) : (
                <ul className="service-list">
                  {systemServices.map((service) => {
                    const starting = Boolean(
                      service.starting || startingServiceIds.includes(service.id),
                    );
                    const up = service.state === "up";
                    return (
                      <li className={`service-item state-${service.state}`} key={service.id}>
                        <span className="service-dot" title={service.detail ?? service.state} />
                        <span className="service-name">
                          {service.name_zh ?? service.name ?? service.id}
                          <em>
                            :{service.port} · {service.state}
                            {service.required ? " · required" : ""}
                          </em>
                        </span>
                        {!up && service.startable && !starting ? (
                          <button
                            className="ghost compact service-start"
                            onClick={() => startSystemService(service.id)}
                            title={`Start ${service.name ?? service.id}`}
                          >
                            <Play size={13} /> Start
                          </button>
                        ) : starting ? (
                          <span className="service-starting">starting…</span>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="service-note">
                初始化只拉起本机服务：worker、前端、KG 代理。图片走 Model API，不再启动本地 Qwen / planner。
              </p>
            </Panel>
            </div>
          </details>

          <section className="studio-model-probe" aria-label="Model API connectivity">
            <div className="studio-model-probe-head">
              <Wifi size={15} aria-hidden="true" />
              <div>
                <strong>Model API</strong>
                <small>实验前先测大模型、图片模型和 3D worker</small>
              </div>
            </div>
            <div className="service-toolbar">
              <button
                className="ghost compact"
                type="button"
                disabled={modelProbeBusy}
                onClick={() => void runModelProbe(false)}
                title="只测文本大模型（快）"
              >
                <RefreshCw size={14} /> {modelProbeBusy ? "Probing…" : "测文本"}
              </button>
              <button
                className="ghost compact"
                type="button"
                disabled={modelProbeBusy}
                onClick={() => void runModelProbe(true)}
                title="文本 + 图片（图片可能要 20–40 秒）"
              >
                <Wifi size={14} /> {modelProbeBusy ? "Probing…" : "测文本+图片"}
              </button>
              <button
                className="ghost compact"
                type="button"
                disabled={hy3dProbeBusy}
                onClick={() => void runHy3dProbe()}
                title="检查 3D worker 是否在线、Python 与 Hunyuan 脚本是否就绪"
              >
                <Box size={14} /> {hy3dProbeBusy ? "探测中…" : "测3D"}
              </button>
            </div>
            {modelProbeError ? (
              <p className="service-note is-error">{modelProbeError}</p>
            ) : null}
            {modelProbe || hy3dProbe ? (
              <ul className="model-probe-list">
                {modelProbe ? (
                  <>
                <li className={modelProbe.text.ok ? "is-ok" : "is-bad"}>
                  <span className="service-dot" />
                  <span>
                    Text · {modelProbe.text.model ?? "—"}
                    <em>
                      {modelProbe.text.ok
                        ? `ok · ${modelProbe.text.latency_ms ?? "—"}ms`
                        : modelProbe.text.error || "failed"}
                    </em>
                  </span>
                </li>
                <li className={modelProbe.image.skipped ? "is-skip" : modelProbe.image.ok ? "is-ok" : "is-bad"}>
                  <span className="service-dot" />
                  <span>
                    Image · {modelProbe.image.model ?? "—"}
                    <em>
                      {modelProbe.image.skipped
                        ? "skipped"
                        : modelProbe.image.ok
                          ? `ok · ${modelProbe.image.latency_ms ?? "—"}ms · ${modelProbe.image.bytes ?? 0}B`
                          : modelProbe.image.error || "failed"}
                    </em>
                  </span>
                </li>
                  </>
                ) : null}
                {hy3dProbe ? (
                  <>
                    <li className={hy3dProbe.workerOk ? "is-ok" : "is-bad"}>
                      <span className="service-dot" />
                      <span>
                        3D worker
                        <em>
                          {hy3dProbe.workerOk
                            ? `online · ${hy3dProbe.latencyMs}ms`
                            : hy3dProbe.error || "offline"}
                        </em>
                      </span>
                    </li>
                    <li className={hy3dProbe.pythonOk ? "is-ok" : "is-bad"}>
                      <span className="service-dot" />
                      <span>
                        Python
                        <em>{hy3dProbe.pythonOk ? hy3dProbe.python : `missing · ${hy3dProbe.python}`}</em>
                      </span>
                    </li>
                    <li className={hy3dProbe.hy3dOk ? "is-ok" : "is-bad"}>
                      <span className="service-dot" />
                      <span>
                        Hunyuan3D
                        <em>{hy3dProbe.hy3dOk ? "scripts ready" : "pipeline not ready"}</em>
                      </span>
                    </li>
                  </>
                ) : null}
              </ul>
            ) : (
              <p className="service-note">
                {modelProbeBusy || hy3dProbeBusy
                  ? "正在探测…"
                  : "未测试。不通时可稍后再点，或改用本地部署模型。"}
              </p>
            )}
            {modelProbe?.hint ? <p className="service-note">{modelProbe.hint}</p> : null}
            {modelProbe?.api_base ? (
              <p className="service-note mono">{modelProbe.api_base}</p>
            ) : null}
          </section>
        </div>
      </aside>
      {projectDialogOpen ? (
        <ProjectDialog
          projects={projectList}
          busy={projectBusy}
          onClose={() => setProjectDialogOpen(false)}
          onCreate={createExperimentProject}
          onOpen={openExperimentProject}
        />
      ) : null}
      {projectTimelineOpen && project ? (
        <ProjectTimeline
          project={project}
          events={projectEvents}
          onClose={() => setProjectTimelineOpen(false)}
          onEnd={endExperimentRun}
          onExport={exportExperimentProject}
        />
      ) : null}
      <button
        className={`studio-rail-handle ${studioDrawerOpen ? "is-open" : ""}`}
        type="button"
        style={{ left: studioDrawerOpen ? Math.max(8, menuWidth - 14) : 10 }}
        title={studioDrawerOpen ? "Drag to resize, click to collapse" : "Open studio menu"}
        aria-label={studioDrawerOpen ? "Resize or collapse studio menu" : "Open studio menu"}
        aria-expanded={studioDrawerOpen}
        onPointerDown={(event) => {
          handleDragMovedRef.current = false;
          onMenuHandlePointerDown(event);
        }}
        onPointerMove={(event) => {
          onMenuHandlePointerMove(event);
          const drag = menuDragRef.current;
          if (drag && drag.moved) handleDragMovedRef.current = true;
        }}
        onPointerUp={(event) => {
          const wasDragged = handleDragMovedRef.current;
          onMenuHandlePointerUp(event);
          if (wasDragged) {
            handleDragMovedRef.current = false;
            // Suppress the click that follows a real drag.
            event.stopPropagation();
            event.preventDefault();
          }
        }}
        onPointerCancel={(event) => {
          handleDragMovedRef.current = false;
          onMenuHandlePointerUp(event);
        }}
        onClick={(event) => {
          if (handleDragMovedRef.current) {
            handleDragMovedRef.current = false;
            event.stopPropagation();
            event.preventDefault();
            return;
          }
          onMenuToggle();
        }}
      >
        <GripVertical size={14} aria-hidden="true" />
      </button>
    </>
  );
}
