/**
 * Three viewport: renderer + client sculpting (refactor plan P1a).
 */
import React, { useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { captureCanvasJpeg } from "../utils/canvasCapture";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RefreshCw } from "lucide-react";
import { API_BASE } from "../api";
import type { AssetRecord, CanvasDisplayMode, CanvasPrimitive, CanvasTool, PartRecord, SculptTool, ThreeViewportHandle, ThreeViewportProps, ViewportInteractionSignal } from "../types";
import {
  addStudioPreviewLighting,
  buildPrimitiveObject,
  clearSceneGroup,
  computeViewMode,
  createOrbitInteractionProbe,
  loadStudioModel,
  stageLoadedModel,
  trackMesh,
  updateSceneMaterials,
} from "./viewport/scene";
import { createBrushCursor, createMeshSelectionHandlers, SculptPointerController, SculptSession } from "./viewport/sculptEngine";

const VIEWPORT_BUFFER_WIDTH = 2400;
const VIEWPORT_BUFFER_HEIGHT = 1900;
const VIEWPORT_BUFFER_ASPECT = VIEWPORT_BUFFER_WIDTH / VIEWPORT_BUFFER_HEIGHT;

export const ThreeViewport = React.forwardRef<ThreeViewportHandle, ThreeViewportProps>(function ThreeViewport({
  asset,
  previewMeshUrl,
  previewLabel,
  onClearPreview,
  selectedPart,
  hoverLabel,
  primitive,
  tool,
  displayMode,
  parts,
  onSelectPart,
  onHoverPart,
  onViewportInteraction,
  sculptTool,
  onSculptAction,
  sculptRadius,
  sculptStrength,
  canvasZoom,
  hoverMaskDataUrl,
  onGeometryReady,
}, ref): React.ReactElement {
  return (
    <ThreeViewportInner
      asset={asset}
      previewMeshUrl={previewMeshUrl}
      previewLabel={previewLabel}
      onClearPreview={onClearPreview}
      selectedPart={selectedPart}
      hoverLabel={hoverLabel}
      primitive={primitive}
      tool={tool}
      displayMode={displayMode}
      parts={parts}
      onSelectPart={onSelectPart}
      onHoverPart={onHoverPart}
      onViewportInteraction={onViewportInteraction}
      sculptTool={sculptTool}
      onSculptAction={onSculptAction}
      sculptRadius={sculptRadius}
      sculptStrength={sculptStrength}
      canvasZoom={canvasZoom}
      hoverMaskDataUrl={hoverMaskDataUrl}
      onGeometryReady={onGeometryReady}
      ref={ref}
    />
  );
});

const ThreeViewportInner = React.forwardRef<ThreeViewportHandle, ThreeViewportProps>(function ThreeViewportInner({
  asset,
  previewMeshUrl,
  previewLabel,
  onClearPreview,
  selectedPart,
  hoverLabel,
  primitive,
  tool,
  displayMode,
  parts,
  onSelectPart,
  onHoverPart,
  onViewportInteraction,
  sculptTool,
  onSculptAction,
  sculptRadius,
  sculptStrength,
  canvasZoom,
  hoverMaskDataUrl,
  onGeometryReady,
}, ref): React.ReactElement {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const onSelectRef = useRef(onSelectPart);
  const onHoverRef = useRef(onHoverPart);
  const onViewportInteractionRef = useRef(onViewportInteraction);
  const selectedRef = useRef(selectedPart);
  const hoverNameRef = useRef("");
  const lastHoverRef = useRef({ name: "", at: 0 });
  const [viewResetKey, setViewResetKey] = useState(0);
  const [modelLoadMessage, setModelLoadMessage] = useState<string | null>(null);
  const sculptToolRef = useRef<SculptTool | null>(sculptTool);
  const onSculptActionRef = useRef(onSculptAction);
  const onGeometryReadyRef = useRef(onGeometryReady);
  const canvasZoomRef = useRef(canvasZoom ?? 1);
  const reclassifyFramingRef = useRef<() => void>(() => undefined);
  const sculptRadiusRef = useRef(sculptRadius);
  const sculptStrengthRef = useRef(sculptStrength);
  const partsRef = useRef(parts);
  partsRef.current = parts;
  const sculptTargetRef = useRef<THREE.Mesh | null>(null);
  const loadedMeshesRef = useRef<THREE.Mesh[]>([]);
  const sculptPositionsRef = useRef<Float32Array | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const lastPointerRef = useRef<{ x: number; y: number } | null>(null);

  const applySculptSnapshot = (positions: Float32Array | null) => {
    const mesh = sculptTargetRef.current;
    if (!mesh) return;
    const geometry = mesh.geometry as THREE.BufferGeometry;
    const attribute = geometry.getAttribute("position") as THREE.BufferAttribute;
    if (positions && positions.length === attribute.array.length) {
      attribute.array.set(positions);
      attribute.needsUpdate = true;
      geometry.computeVertexNormals();
    }
  };

  const capturePositions = (): Float32Array | null => {
    const mesh = sculptTargetRef.current ?? loadedMeshesRef.current[0] ?? null;
    if (!mesh) return null;
    const attribute = (mesh.geometry as THREE.BufferGeometry).getAttribute("position") as THREE.BufferAttribute;
    return new Float32Array(attribute.array as Float32Array);
  };

  const exportMeshOBJ = () => {
    const mesh = loadedMeshesRef.current[0];
    if (!mesh) return null;
    const geometry = mesh.geometry as THREE.BufferGeometry;
    const attribute = geometry.getAttribute("position") as THREE.BufferAttribute;
    const index = geometry.getIndex();
    const positions = attribute.array as Float32Array;
    const matrix = mesh.matrixWorld;
    const point = new THREE.Vector3();
    const lines: string[] = ["s 0", "o mesh_0"];
    for (let i = 0; i < attribute.count; i += 1) {
      point.set(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]).applyMatrix4(matrix);
      lines.push(`v ${point.x.toFixed(6)} ${point.y.toFixed(6)} ${point.z.toFixed(6)}`);
    }
    if (index) {
      for (let i = 0; i < index.count; i += 3) {
        lines.push(`f ${index.getX(i) + 1} ${index.getX(i + 1) + 1} ${index.getX(i + 2) + 1}`);
      }
    } else {
      for (let i = 0; i < attribute.count; i += 3) {
        lines.push(`f ${i + 1} ${i + 2} ${i + 3}`);
      }
    }
    return lines.join("\n");
  };

  const captureJpeg = (width = 640, quality = 0.7): string | null => {
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const mount = mountRef.current;
    if (!renderer || !scene || !camera || !mount) return null;
    renderer.render(scene, camera);
    return captureCanvasJpeg(renderer.domElement, width, quality);
  };

  const captureThreeViews = (width = 640, quality = 0.7) => {
    const renderer = rendererRef.current;
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!renderer || !scene || !camera || !controls) return {};
    const savedPosition = camera.position.clone();
    const savedUp = camera.up.clone();
    const savedTarget = controls.target.clone();
    const distance = Math.max(
      1.05,
      Math.min(2.4, savedPosition.distanceTo(savedTarget) * 0.72),
    );
    const renderAt = (offset: THREE.Vector3): string | null => {
      camera.up.set(0, 1, 0);
      camera.position.copy(savedTarget).add(offset.multiplyScalar(distance));
      camera.lookAt(savedTarget);
      camera.updateMatrixWorld(true);
      renderer.render(scene, camera);
      return captureCanvasJpeg(renderer.domElement, width, quality);
    };
    const views = {
      front: renderAt(new THREE.Vector3(0, 0, 1)),
      side: renderAt(new THREE.Vector3(1, 0, 0)),
      top: renderAt(new THREE.Vector3(0, 1, 0)),
    };
    camera.position.copy(savedPosition);
    camera.up.copy(savedUp);
    controls.target.copy(savedTarget);
    controls.update();
    renderer.render(scene, camera);
    return views;
  };

  const getLastPointer = () => {
    const mount = mountRef.current;
    if (!mount || !lastPointerRef.current) return null;
    return { ...lastPointerRef.current };
  };

  const getModelScreenBounds = () => {
    const mount = mountRef.current;
    const camera = cameraRef.current;
    const meshes = loadedMeshesRef.current;
    if (!mount || !camera || !meshes.length) return null;
    const box = new THREE.Box3();
    let valid = false;
    for (const mesh of meshes) {
      mesh.updateWorldMatrix(true, true);
      mesh.geometry.computeBoundingBox();
      const local = mesh.geometry.boundingBox;
      if (!local) continue;
      box.union(local.clone().applyMatrix4(mesh.matrixWorld));
      valid = true;
    }
    if (!valid || box.isEmpty()) return null;
    const rect = mount.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const corners = [
      new THREE.Vector3(box.min.x, box.min.y, box.min.z),
      new THREE.Vector3(box.min.x, box.min.y, box.max.z),
      new THREE.Vector3(box.min.x, box.max.y, box.min.z),
      new THREE.Vector3(box.min.x, box.max.y, box.max.z),
      new THREE.Vector3(box.max.x, box.min.y, box.min.z),
      new THREE.Vector3(box.max.x, box.min.y, box.max.z),
      new THREE.Vector3(box.max.x, box.max.y, box.min.z),
      new THREE.Vector3(box.max.x, box.max.y, box.max.z),
    ];
    let minX = Number.POSITIVE_INFINITY;
    let minY = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    let maxY = Number.NEGATIVE_INFINITY;
    for (const corner of corners) {
      const projected = corner.project(camera);
      const x = (projected.x * 0.5 + 0.5) * rect.width;
      const y = (-projected.y * 0.5 + 0.5) * rect.height;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
    if (!Number.isFinite(minX) || !Number.isFinite(minY)) return null;
    return {
      x: minX,
      y: minY,
      width: Math.max(1, maxX - minX),
      height: Math.max(1, maxY - minY),
    };
  };

  useImperativeHandle(ref, () => ({
    applySculptSnapshot,
    capturePositions,
    captureJpeg,
    captureThreeViews,
    getLastPointer,
    exportMeshOBJ,
    getModelScreenBounds,
  }));

  useEffect(() => {
    onSelectRef.current = onSelectPart;
    onHoverRef.current = onHoverPart;
    onViewportInteractionRef.current = onViewportInteraction;
    selectedRef.current = selectedPart;
  }, [onHoverPart, onSelectPart, onViewportInteraction, selectedPart]);
  useEffect(() => {
    hoverNameRef.current = hoverLabel ?? "";
  }, [hoverLabel]);

  useEffect(() => {
    sculptToolRef.current = sculptTool;
  }, [sculptTool]);
  useEffect(() => {
    sculptRadiusRef.current = sculptRadius;
  }, [sculptRadius]);
  useEffect(() => {
    sculptStrengthRef.current = sculptStrength;
  }, [sculptStrength]);
  useEffect(() => {
    onSculptActionRef.current = onSculptAction;
  }, [onSculptAction]);
  useEffect(() => {
    onGeometryReadyRef.current = onGeometryReady;
  }, [onGeometryReady]);
  useEffect(() => {
    canvasZoomRef.current = canvasZoom ?? 1;
    reclassifyFramingRef.current();
  }, [canvasZoom]);

  useEffect(() => {
    if (!mountRef.current) return;
    setModelLoadMessage(null);
    const mount = mountRef.current;
    const scene = new THREE.Scene();
    scene.background = null;
    const camera = new THREE.PerspectiveCamera(45, VIEWPORT_BUFFER_ASPECT, 0.1, 100);
    camera.position.set(0, 1.2, 5.2);
    camera.lookAt(0, 0.4, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    rendererRef.current = renderer;
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(1);
    renderer.setSize(VIEWPORT_BUFFER_WIDTH, VIEWPORT_BUFFER_HEIGHT, false);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.95;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    sceneRef.current = scene;
    cameraRef.current = camera;
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.rotateSpeed = 0.7;
    controls.zoomSpeed = 0.85;
    controls.panSpeed = 0.65;
    controls.minDistance = 0.8;
    controls.maxDistance = 18;
    controls.target.set(0, 0.2, 0);
    // Explicit mouse mapping: only left-drag rotates; bare hover never does.
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    };
    controls.touches = {
      ONE: THREE.TOUCH.ROTATE,
      TWO: THREE.TOUCH.DOLLY_PAN,
    };
    controls.update();
    // Keep OrbitControls pointer ownership on the WebGL canvas so outer
    // studio-canvas pan handlers cannot leave rotate state stuck.
    const stopCanvasPanSteal = (event: PointerEvent) => {
      event.stopPropagation();
    };
    renderer.domElement.addEventListener("pointerdown", stopCanvasPanSteal);
    const getObjectRadius = () => {
      if (!interactive.length) return 0;
      const box = new THREE.Box3();
      let valid = false;
      for (const mesh of interactive) {
        mesh.geometry.computeBoundingBox();
        const bounds = mesh.geometry.boundingBox;
        if (!bounds) continue;
        valid = true;
        box.union(bounds.clone().applyMatrix4(mesh.matrixWorld));
      }
      return valid ? box.getBoundingSphere(new THREE.Sphere()).radius : 0;
    };
    const emitViewportSignal = (type: "zoom" | "orbit", dwell_ms: number, initial = false) => {
      const distance = camera.position.distanceTo(controls.target);
      onViewportInteractionRef.current({
        type,
        dwell_ms,
        camera_distance: Number(distance.toFixed(3)),
        view_mode: computeViewMode(camera, getObjectRadius(), distance, canvasZoomRef.current),
        ...(initial ? { initial: true } : {}),
      });
    };
    reclassifyFramingRef.current = () => emitViewportSignal("zoom", 0, true);
    const onOrbitActivity = () => {
      // Reset idle Gate while the user is still dragging the camera.
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("flowstudio:user-activity"));
      }
    };
    controls.addEventListener("start", onOrbitActivity);
    const detachOrbitProbe = createOrbitInteractionProbe(controls, camera, getObjectRadius, (signal) =>
      emitViewportSignal(signal.type, signal.dwell_ms),
    );

    addStudioPreviewLighting(scene);

    const group = new THREE.Group();
    group.position.y = 0.2;
    scene.add(group);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const interactive: THREE.Mesh[] = [];
    loadedMeshesRef.current = interactive;
    const brushCursor = createBrushCursor();
    brushCursor.visible = false;
    scene.add(brushCursor);
    const sculptSession = new SculptSession();

    const resetModel = () => {
      clearSceneGroup(group, interactive);
      onGeometryReadyRef.current?.(null);
    };

    const primitiveObject = primitive ? buildPrimitiveObject(primitive) : null;
    if (primitiveObject) {
      resetModel();
      trackMesh(primitiveObject, interactive, primitive ?? "body");
      group.add(primitiveObject);
    }

    const baseModelUrl = primitiveObject ? null : asset?.mesh_url ?? asset?.obj_url ?? null;
    const sourceMeshUrl = primitiveObject ? null : previewMeshUrl ?? baseModelUrl;
    const modelUrl = sourceMeshUrl
      ? sourceMeshUrl.startsWith("http")
        ? sourceMeshUrl
        : `${API_BASE}${sourceMeshUrl}`
      : null;
    const applyLoadedModel = (root: THREE.Object3D) => {
      setModelLoadMessage(null);
      resetModel();
      const geometry = stageLoadedModel(root, group, interactive, controls, camera);
      onGeometryReadyRef.current?.(geometry);
      // Seed the initial framing state so perception can distinguish
      // silhouette surveying from part-level scrutiny before the user moves.
      window.setTimeout(() => emitViewportSignal("orbit", 0, true), 150);
    };
    if (modelUrl) {
      loadStudioModel(modelUrl, baseModelUrl, {
        label: asset?.label ?? null,
        onLoaded: applyLoadedModel,
        onReset: resetModel,
        onMessage: setModelLoadMessage,
      });
    } else if (!primitiveObject) {
      resetModel();
      if (asset) setModelLoadMessage(`No renderable source mesh: ${asset.label}`);
    }
    const updateMaterials = () =>
      updateSceneMaterials(
        interactive,
        displayMode,
        partsRef.current.length,
        selectedRef.current,
        hoverNameRef.current,
      );
    updateMaterials();

    const selection = createMeshSelectionHandlers({
      renderer,
      camera,
      raycaster,
      pointer,
      interactive,
      isSculpting: () => Boolean(sculptToolRef.current),
      lastHover: lastHoverRef.current,
      onSelect: (name) => onSelectRef.current(name),
      onHover: (name) => onHoverRef.current(name),
    });
    const sculptPointer = new SculptPointerController({
      renderer,
      camera,
      raycaster,
      pointer,
      interactive,
      controls,
      cursor: brushCursor,
      session: sculptSession,
      getTool: () => sculptToolRef.current,
      getRadius: () => sculptRadiusRef.current,
      getStrength: () => sculptStrengthRef.current,
      getTarget: () => sculptTargetRef.current,
      onBegin: (mesh, session) => {
        sculptTargetRef.current = mesh;
        sculptPositionsRef.current = session.basePositions;
      },
      onEvidence: (tool, evidence) => onSculptActionRef.current(tool, evidence),
    });
    const updatePointerFromEvent = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      lastPointerRef.current = {
        x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
        y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
      };
    };
    renderer.domElement.addEventListener("pointermove", updatePointerFromEvent);
    renderer.domElement.addEventListener("pointerdown", updatePointerFromEvent);
    selection.attach();
    sculptPointer.attach();

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
      updateMaterials();
      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      camera.aspect = VIEWPORT_BUFFER_ASPECT;
      camera.updateProjectionMatrix();
      renderer.setSize(VIEWPORT_BUFFER_WIDTH, VIEWPORT_BUFFER_HEIGHT, false);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
      rendererRef.current = null;
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      renderer.domElement.removeEventListener("pointermove", updatePointerFromEvent);
      renderer.domElement.removeEventListener("pointerdown", updatePointerFromEvent);
      renderer.domElement.removeEventListener("pointerdown", stopCanvasPanSteal);
      selection.detach();
      sculptPointer.detach();
      controls.removeEventListener("start", onOrbitActivity);
      detachOrbitProbe();
      scene.remove(brushCursor);
      brushCursor.geometry.dispose();
      (brushCursor.material as THREE.Material).dispose();
      controls.dispose();
      mount.removeChild(renderer.domElement);
      renderer.dispose();
    };
  }, [asset?.mesh_url, asset?.obj_url, previewMeshUrl, viewResetKey, primitive, tool, displayMode]);

  return (
    <div className="viewport-wrap">
      {previewLabel ? (
        <div className="viewport-tools">
          <button className="ghost compact" onClick={onClearPreview}>
            <RefreshCw size={15} /> Source
          </button>
        </div>
      ) : null}
      <div className="viewport" ref={mountRef} />
      {modelLoadMessage ? <div className="viewport-message">{modelLoadMessage}</div> : null}
      {hoverLabel ? (
        <div className="viewport-hover-label" aria-live="polite">
          {hoverLabel}
        </div>
      ) : null}
      {hoverMaskDataUrl ? (
        <img className="viewport-hover-mask" src={hoverMaskDataUrl} alt="hover segmentation mask" width={960} height={720} />
      ) : null}
    </div>
  );
});
