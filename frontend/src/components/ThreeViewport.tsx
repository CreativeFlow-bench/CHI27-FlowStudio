/**
 * Three viewport: renderer + client sculpting (refactor plan P1a).
 */
import React, { useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { captureCanvasJpeg } from "../utils/canvasCapture";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { RefreshCw } from "lucide-react";
import { API_BASE } from "../api";
import { partViewportMatchName } from "../utils/appHelpers";
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

const VIEWPORT_FALLBACK_ASPECT = 16 / 10;
const BLOCKED_TRANSFORM_HANDLES: Record<"translate" | "rotate" | "scale", Set<string>> = {
  translate: new Set(["XY", "YZ", "XZ", "XYZ"]),
  rotate: new Set(["E", "XYZE"]),
  scale: new Set(["XY", "YZ", "XZ", "XYZ"]),
};

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
  const displayModeRef = useRef(displayMode);
  displayModeRef.current = displayMode;
  const primitiveRef = useRef(primitive);
  primitiveRef.current = primitive;
  const groupRef = useRef<THREE.Group | null>(null);
  const transformControlRef = useRef<any>(null);
  const primitiveObjectRef = useRef<THREE.Mesh | null>(null);
  const transformModeRef = useRef<"translate" | "rotate" | "scale">("translate");
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

  const getPrimitiveTransform = () => {
    const mesh = primitiveObjectRef.current;
    if (!mesh) return null;
    return {
      position: [mesh.position.x, mesh.position.y, mesh.position.z],
      rotation: [mesh.rotation.x, mesh.rotation.y, mesh.rotation.z],
      scale: [mesh.scale.x, mesh.scale.y, mesh.scale.z],
    };
  };

  const attachPrimitiveTransformControls = (name?: string) => {
    const primitiveObject = primitiveObjectRef.current;
    const transformControl = transformControlRef.current;
    if (!primitiveObject || !transformControl) return false;
    if (name && name !== primitiveObject.name) return false;
    primitiveObject.updateMatrixWorld(true);
    selectedRef.current = primitiveObject.name;
    transformControl.visible = true;
    transformControl.setMode(transformModeRef.current);
    transformControl.attach(primitiveObject);
    enforceTransformHandleFilter(
      typeof transformControl.getHelper === "function"
        ? (transformControl.getHelper() as THREE.Object3D)
        : null,
      transformModeRef.current,
    );
    onSelectRef.current(primitiveObject.name);
    return true;
  };

  const enforceTransformHandleFilter = (helper: THREE.Object3D | null, mode: "translate" | "rotate" | "scale") => {
    if (!helper) return;
    const blocked = BLOCKED_TRANSFORM_HANDLES[mode];
    helper.traverse((node) => {
      if (!node.name) return;
      if (blocked.has(node.name)) {
        node.visible = false;
      }
    });
  };

  const positionPrimitiveForEditing = (mesh: THREE.Mesh) => {
    const sceneMeshes = loadedMeshesRef.current.filter((item) => item !== mesh && !item.userData.flowstudioPrimitive);
    if (!sceneMeshes.length) {
      mesh.position.set(0.9, 0.8, 0.35);
      return;
    }
    const box = new THREE.Box3();
    let valid = false;
    for (const sceneMesh of sceneMeshes) {
      sceneMesh.updateWorldMatrix(true, true);
      sceneMesh.geometry.computeBoundingBox();
      const local = sceneMesh.geometry.boundingBox;
      if (!local) continue;
      box.union(local.clone().applyMatrix4(sceneMesh.matrixWorld));
      valid = true;
    }
    if (!valid || box.isEmpty()) {
      mesh.position.set(0.9, 0.8, 0.35);
      return;
    }
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    mesh.position.set(
      box.max.x + Math.max(0.45, size.x * 0.22),
      center.y + Math.max(0.18, size.y * 0.08),
      box.max.z + Math.max(0.28, size.z * 0.14),
    );
  };

  useImperativeHandle(ref, () => ({
    applySculptSnapshot,
    capturePositions,
    captureJpeg,
    captureThreeViews,
    getLastPointer,
    exportMeshOBJ,
    getModelScreenBounds,
    getPrimitiveTransform,
  }));

  useEffect(() => {
    onSelectRef.current = onSelectPart;
    onHoverRef.current = onHoverPart;
    onViewportInteractionRef.current = onViewportInteraction;
    selectedRef.current = selectedPart;
  }, [onHoverPart, onSelectPart, onViewportInteraction, selectedPart]);

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
    const camera = new THREE.PerspectiveCamera(45, VIEWPORT_FALLBACK_ASPECT, 0.1, 100);
    camera.position.set(0, 0, 5.2);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
    rendererRef.current = renderer;
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(Math.max(1, mount.clientWidth || 960), Math.max(1, mount.clientHeight || 600), false);
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
    controls.target.set(0, 0, 0);
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
    const onOrbitEnd = () => {};
    controls.addEventListener("end", onOrbitEnd);
    const detachOrbitProbe = createOrbitInteractionProbe(controls, camera, getObjectRadius, (signal) =>
      emitViewportSignal(signal.type, signal.dwell_ms),
    );

    addStudioPreviewLighting(scene);
    const pmrem = new THREE.PMREMGenerator(renderer);
    const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = environment;
    scene.environmentIntensity = 0.9;
    pmrem.dispose();

    const group = new THREE.Group();
    groupRef.current = group;
    group.position.y = 0;
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

    let onKeyDown: ((e: KeyboardEvent) => void) | null = null;

    const baseModelUrl = asset?.mesh_url ?? asset?.obj_url ?? null;
    const sourceMeshUrl = previewMeshUrl ?? baseModelUrl;
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
    } else {
      resetModel();
      if (asset) {
        setModelLoadMessage(`No renderable source mesh: ${asset.label}`);
      }
    }
    const updateMaterials = () => {
      const selectedId = selectedRef.current;
      const selectedPartRecord = partsRef.current.find((item) => item.part_id === selectedId);
      updateSceneMaterials(
        interactive,
        displayModeRef.current,
        partsRef.current.length,
        selectedPartRecord ? partViewportMatchName(selectedPartRecord) : selectedId,
        hoverNameRef.current,
      );
    };
    updateMaterials();

    const selection = createMeshSelectionHandlers({
      renderer,
      camera,
      raycaster,
      pointer,
      interactive,
      isSculpting: () => Boolean(sculptToolRef.current),
      lastHover: lastHoverRef.current,
      onSelect: (name) => {
        if (attachPrimitiveTransformControls(name.split(",")[0]?.trim() || name)) return;
        onSelectRef.current(name);
      },
      onHover: (name) => {
        hoverNameRef.current = name;
        onHoverRef.current(name);
      },
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

    const syncRendererSize = () => {
      const nextWidth = Math.max(1, Math.round(mount.clientWidth));
      const nextHeight = Math.max(1, Math.round(mount.clientHeight));
      camera.aspect = nextWidth / Math.max(1, nextHeight);
      camera.updateProjectionMatrix();
      // Keep a sharp backing store while letting CSS fill the adaptive frame.
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(nextWidth, nextHeight, false);
    };
    syncRendererSize();

    let frame = 0;
    const animate = () => {
      frame = requestAnimationFrame(animate);
      controls.update();
      updateMaterials();
      renderer.render(scene, camera);
    };
    animate();

    const resizeObserver = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => syncRendererSize())
      : null;
    resizeObserver?.observe(mount);
    window.addEventListener("resize", syncRendererSize);

  

  return () => {
      cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", syncRendererSize);
      if (onKeyDown) window.removeEventListener('keydown', onKeyDown);

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
      controls.removeEventListener("end", onOrbitEnd);
      detachOrbitProbe();
      scene.remove(brushCursor);
      brushCursor.geometry.dispose();
      (brushCursor.material as THREE.Material).dispose();
      environment.dispose();
      scene.environment = null;
      controls.dispose();
      mount.removeChild(renderer.domElement);
      renderer.dispose();
    };
  }, [asset?.mesh_url, asset?.obj_url, previewMeshUrl, viewResetKey]);



  useEffect(() => {
    const scene = sceneRef.current;
    const camera = cameraRef.current;
    const renderer = rendererRef.current;
    const group = groupRef.current;
    const controls = controlsRef.current;
    if (!scene || !camera || !renderer || !group || !controls) return;

    let primitiveObject: THREE.Mesh | null = null;
    let transformControl: any = null;
    let transformHelper: THREE.Object3D | null = null;
    let onKeyDown: ((e: KeyboardEvent) => void) | null = null;
    let gizmoPointerArmed = false;

    if (primitive) {
      primitiveObject = buildPrimitiveObject(primitive);
      primitiveObject.scale.setScalar(primitive === "cube" ? 0.28 : 0.25);
      primitiveObject.userData.flowstudioPrimitive = true;
      primitiveObjectRef.current = primitiveObject;
      positionPrimitiveForEditing(primitiveObject);
      trackMesh(primitiveObject, loadedMeshesRef.current, primitive);
      group.add(primitiveObject);

      transformControl = new TransformControls(camera, renderer.domElement);
      transformControl.addEventListener("dragging-changed", (event: any) => {
        if (event.value) gizmoPointerArmed = false;
        controls.enabled = !event.value;
      });
      transformControl.setSpace("world");
      transformControl.setMode(transformModeRef.current);
      transformControl.setSize(0.9);
      transformControl.visible = false;
      transformHelper = typeof transformControl.getHelper === "function"
        ? (transformControl.getHelper() as THREE.Object3D)
        : (transformControl as THREE.Object3D);
      const originalTransformHelperUpdateMatrixWorld = transformHelper.updateMatrixWorld.bind(transformHelper);
      transformHelper.updateMatrixWorld = (force?: boolean) => {
        originalTransformHelperUpdateMatrixWorld(force);
        enforceTransformHandleFilter(transformHelper, transformControl.mode);
      };
      scene.add(transformHelper);
      transformControlRef.current = transformControl;

      const onPointerDownTransformHandle = () => {
        if (!transformControl.visible || !transformControl.object || !transformControl.axis) return;
        gizmoPointerArmed = true;
        controls.enabled = false;
      };

      const onPointerUpTransformHandle = () => {
        if (!gizmoPointerArmed) return;
        gizmoPointerArmed = false;
        if (!transformControl.dragging) {
          controls.enabled = true;
        }
      };

      renderer.domElement.addEventListener("pointerdown", onPointerDownTransformHandle, true);
      renderer.domElement.addEventListener("pointerup", onPointerUpTransformHandle, true);

      onKeyDown = (event: KeyboardEvent) => {
        if (!transformControl) return;
        switch (event.key.toLowerCase()) {
          case "t":
            transformModeRef.current = "translate";
            transformControl.setMode("translate");
            attachPrimitiveTransformControls();
            break;
          case "r":
            transformModeRef.current = "rotate";
            transformControl.setMode("rotate");
            attachPrimitiveTransformControls();
            break;
          case "s":
            transformModeRef.current = "scale";
            transformControl.setMode("scale");
            attachPrimitiveTransformControls();
            break;
        }
      };
      window.addEventListener("keydown", onKeyDown);
      const onPointerDownSelectPrimitive = (event: PointerEvent) => {
        if (!primitiveObject || !transformControl || sculptToolRef.current) return;
        if (gizmoPointerArmed || transformControl.dragging || transformControl.axis) return;
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        const raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(pointer, camera);
        const hit = raycaster.intersectObject(primitiveObject, true)[0];
        if (!hit) return;
        event.stopPropagation();
        attachPrimitiveTransformControls(primitiveObject.name);
      };
      renderer.domElement.addEventListener("pointerdown", onPointerDownSelectPrimitive, true);
      window.requestAnimationFrame(() => {
        attachPrimitiveTransformControls(primitiveObject?.name);
      });

      return () => {
        renderer.domElement.removeEventListener("pointerdown", onPointerDownTransformHandle, true);
        renderer.domElement.removeEventListener("pointerup", onPointerUpTransformHandle, true);
        renderer.domElement.removeEventListener("pointerdown", onPointerDownSelectPrimitive, true);
        if (onKeyDown) window.removeEventListener("keydown", onKeyDown);
        if (transformControl) {
          transformControl.detach();
          transformControl.dispose();
        }
        if (transformHelper) {
          scene.remove(transformHelper);
        }
        transformControlRef.current = null;
        primitiveObjectRef.current = null;
        if (primitiveObject) {
          group.remove(primitiveObject);
          const index = loadedMeshesRef.current.indexOf(primitiveObject);
          if (index !== -1) {
            loadedMeshesRef.current.splice(index, 1);
          }
        }
      };
    }

    return () => {
      primitiveObjectRef.current = null;
    };
  }, [primitive]);

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
