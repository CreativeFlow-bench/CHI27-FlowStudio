/**
 * Pure Three.js scene helpers (refactor plan P1a).
 * No React, no component state: safe to unit-test and reuse.
 */

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { MTLLoader } from "three/examples/jsm/loaders/MTLLoader.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { API_BASE, inferMeshExtension, inferMtlUrl } from "../../api";
import type { CanvasDisplayMode, CanvasPrimitive } from "../../types";

export function buildPrimitiveObject(primitive: Exclude<CanvasPrimitive, null>) {
  const material = new THREE.MeshStandardMaterial({
    color: "#6b7c93",
    roughness: 0.72,
    metalness: 0.03,
  });
  if (primitive === "sphere" || primitive === "ico_sphere") {
    const mesh = new THREE.Mesh(
      primitive === "ico_sphere" ? new THREE.IcosahedronGeometry(1, 1) : new THREE.SphereGeometry(1, 64, 32),
      material,
    );
    mesh.name = primitive;
    return mesh;
  }
  if (primitive === "cylinder") {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.82, 0.82, 1.8, 48), material);
    mesh.name = "cylinder";
    return mesh;
  }
  if (primitive === "cone") {
    const mesh = new THREE.Mesh(new THREE.ConeGeometry(0.95, 1.8, 48), material);
    mesh.name = "cone";
    return mesh;
  }
  if (primitive === "torus") {
    const mesh = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.32, 24, 48), material);
    mesh.name = "torus";
    return mesh;
  }
  if (primitive === "plane" || primitive === "circle") {
    const mesh = new THREE.Mesh(
      primitive === "circle" ? new THREE.CircleGeometry(1.1, 48) : new THREE.PlaneGeometry(2.2, 2.2, 1, 1),
      material,
    );
    mesh.name = primitive;
    return mesh;
  }
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1.7, 1.7, 1.7, 8, 8, 8), material);
  mesh.name = "cube";
  return mesh;
}

export function addStudioPreviewLighting(scene: THREE.Scene) {
  scene.add(new THREE.AmbientLight("#ffffff", 0.55));
  scene.add(new THREE.HemisphereLight("#ffffff", "#9aa9bd", 0.7));

  [
    { position: [-3.8, 4.5, 5.2], intensity: 1.7 },
    { position: [4.5, 1.2, 2.8], intensity: 0.75 },
    { position: [0, 3.2, -5.5], intensity: 1.1 },
  ].forEach(({ position, intensity }) => {
    const light = new THREE.DirectionalLight("#ffffff", intensity);
    light.position.set(position[0], position[1], position[2]);
    scene.add(light);
  });
}

export function loadObjWithOptionalMtl(
  modelUrl: string,
  sourceUrl: string,
  onLoad: (object: THREE.Group) => void,
  onError: () => void,
) {
  const fallback = () => {
    new OBJLoader().load(modelUrl, onLoad, undefined, onError);
  };
  if (sourceUrl.includes("/white-models/")) {
    fallback();
    return;
  }
  const mtlUrl = inferMtlUrl(sourceUrl);
  if (!mtlUrl) {
    fallback();
    return;
  }
  // 先探测 MTL 是否存在：很多白模 OBJ 没有配套 material.mtl，
  // 直接加载会在控制台产生 404 噪音并触发多余的降级。
  fetch(mtlUrl, { method: "HEAD" })
    .then((response) => {
      if (!response.ok) {
        fallback();
        return;
      }
      const manager = new THREE.LoadingManager();
      const mtlLoader = new MTLLoader(manager);
      const resourcePath = mtlUrl.slice(0, mtlUrl.lastIndexOf("/") + 1);
      mtlLoader.setResourcePath(resourcePath);
      mtlLoader.load(
        mtlUrl,
        (materials) => {
          materials.preload();
          const loader = new OBJLoader(manager);
          loader.setMaterials(materials);
          loader.load(modelUrl, onLoad, undefined, fallback);
        },
        undefined,
        fallback,
      );
    })
    .catch(() => {
      fallback();
    });
}

export function applyDisplayMaterial(
  material: THREE.MeshStandardMaterial,
  displayMode: CanvasDisplayMode,
  index: number,
  partCount: number,
) {
  const hasMaps = Boolean(material.map || material.roughnessMap || material.metalnessMap || material.normalMap);
  if (displayMode === "textured") {
    if (hasMaps) {
      material.envMapIntensity = 1;
      return;
    }
    material.envMapIntensity = 0;
    const luminance = 0.2126 * material.color.r + 0.7152 * material.color.g + 0.0722 * material.color.b;
    if (luminance > 0.72) {
      material.color.set("#6b7c93");
      material.metalness = 0.02;
    }
    material.roughness = Math.min(material.roughness, 0.68);
    return;
  }
  material.map = null;
  material.normalMap = null;
  material.roughnessMap = null;
  material.metalness = 0.02;
  material.envMapIntensity = 0;
  if (displayMode === "parts") {
    const palette = ["#4f7bd9", "#45a67b", "#d99b3d", "#c65f79", "#7d65c7", "#49aebd"];
    material.color = new THREE.Color(palette[index % Math.max(1, Math.min(partCount || 1, palette.length))]);
    material.roughness = 0.58;
    return;
  }
  if (displayMode === "heatmap") {
    const t = partCount > 1 ? index / Math.max(1, partCount - 1) : 0.45;
    material.color = new THREE.Color().setHSL(0.62 - t * 0.52, 0.78, 0.56);
    material.roughness = 0.5;
    return;
  }
  material.color = new THREE.Color("#6b7c93");
  material.roughness = 0.82;
}

export function standardizeMeshMaterial(material: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) return material.map((item) => standardizeSingleMaterial(item));
  return standardizeSingleMaterial(material);
}

function standardizeSingleMaterial(material: THREE.Material) {
  if (material instanceof THREE.MeshStandardMaterial) return material;
  const source = material as THREE.MeshPhongMaterial & {
    map?: THREE.Texture | null;
    normalMap?: THREE.Texture | null;
    roughnessMap?: THREE.Texture | null;
    metalnessMap?: THREE.Texture | null;
  };
  return new THREE.MeshStandardMaterial({
    color: source.color instanceof THREE.Color ? source.color.clone() : new THREE.Color("#6b7c93"),
    map: source.map ?? null,
    normalMap: source.normalMap ?? null,
    roughnessMap: source.roughnessMap ?? null,
    metalnessMap: source.metalnessMap ?? null,
    metalness: 0.05,
    roughness: 0.58,
    transparent: material.transparent,
    opacity: material.opacity,
    side: material.side,
  });
}

export function clearSceneGroup(group: THREE.Group, interactive: THREE.Mesh[]) {
  for (const child of [...group.children]) group.remove(child);
  interactive.length = 0;
}

export function trackMesh(mesh: THREE.Mesh, interactive: THREE.Mesh[], fallbackName = "body") {
  mesh.name = mesh.name || fallbackName;
  interactive.push(mesh);
}

export function fitLoadedModel(
  root: THREE.Object3D,
  controls: { target: THREE.Vector3; update(): void },
  camera: THREE.PerspectiveCamera,
) {
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
  root.position.sub(center);
  root.scale.setScalar(2.5 / maxDimension);
  controls.target.set(0, 0, 0);
  camera.position.set(0, 0, 5.2);
  camera.lookAt(controls.target);
  controls.update();
}

export function stageLoadedModel(
  root: THREE.Object3D,
  group: THREE.Group,
  interactive: THREE.Mesh[],
  controls: { target: THREE.Vector3; update(): void },
  camera: THREE.PerspectiveCamera,
) {
  fitLoadedModel(root, controls, camera);
  root.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.material = standardizeMeshMaterial(child.material);
      const inherited = child.name || child.parent?.name || "body";
      trackMesh(child, interactive, inherited);
    }
  });
  const firstMesh = root.getObjectByProperty("isMesh", true) as THREE.Mesh | undefined;
  group.scale.setScalar(1);
  group.add(root);
  return firstMesh?.geometry ?? null;
}

function nameTokens(value: string) {
  return value.split(/[,|;/]/).map((item) => item.trim()).filter(Boolean);
}

export function meshNameMatches(meshName: string, target: string) {
  if (!meshName || !target) return false;
  if (meshName === target) return true;
  const meshTokens = nameTokens(meshName);
  const targetTokens = nameTokens(target);
  if (targetTokens.includes(meshName) || meshTokens.includes(target)) return true;
  return targetTokens.some((token) => meshTokens.includes(token));
}

export function updateSceneMaterials(
  interactive: THREE.Mesh[],
  displayMode: CanvasDisplayMode,
  partCount: number,
  selectedName: string,
  hoverName = "",
) {
  interactive.forEach((mesh, index) => {
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of materials) {
      if (material instanceof THREE.MeshStandardMaterial) {
        applyDisplayMaterial(material, displayMode, index, partCount);
        const isSelected = meshNameMatches(mesh.name, selectedName);
        const isHovered = !isSelected && Boolean(hoverName) && meshNameMatches(mesh.name, hoverName);
        material.emissive = new THREE.Color(isSelected ? "#2563eb" : isHovered ? "#f59e0b" : "#000000");
        material.emissiveIntensity = isSelected ? 0.28 : isHovered ? 0.18 : 0;
      }
    }
  });
}

export type StudioModelLoadHandlers = {
  label: string | null;
  onLoaded(object: THREE.Object3D): void;
  onReset(): void;
  onMessage(message: string | null): void;
};

/**
 * Load a GLB/OBJ/PLY mesh into the preview scene, falling back to the base
 * asset mesh when an edit preview fails (must never blank the canvas).
 */
export function loadStudioModel(url: string, fallbackUrl: string | null, handlers: StudioModelLoadHandlers) {
  const { label, onLoaded, onReset, onMessage } = handlers;
  const load = (targetUrl: string, isFallback: boolean) => {
    const resolved = targetUrl.startsWith("http") ? targetUrl : `${API_BASE}${targetUrl}`;
    const extension = inferMeshExtension(targetUrl);
    const handleLoadError = () => {
      if (!isFallback && fallbackUrl && fallbackUrl !== targetUrl) {
        load(fallbackUrl, true);
      } else {
        onReset();
        onMessage(`Model failed to load: ${label ?? "selected asset"}`);
      }
    };
    if (extension === "glb" || extension === "gltf") {
      new GLTFLoader().load(resolved, (gltf) => onLoaded(gltf.scene), undefined, handleLoadError);
    } else if (extension === "obj") {
      loadObjWithOptionalMtl(resolved, targetUrl, (object) => {
        object.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.name = child.name || child.parent?.name || "body";
          }
        });
        onLoaded(object);
      }, handleLoadError);
    } else if (extension === "ply") {
      const loader = new PLYLoader();
      loader.load(
        resolved,
        (geometry) => {
          geometry.computeVertexNormals();
          const mesh = new THREE.Mesh(
            geometry,
            new THREE.MeshStandardMaterial({
              color: "#6b7c93",
              metalness: 0.05,
              roughness: 0.58,
              vertexColors: geometry.hasAttribute("color"),
            }),
          );
          mesh.name = "body";
          onLoaded(mesh);
        },
        undefined,
        handleLoadError,
      );
    } else {
      onReset();
      onMessage(`Unsupported model URL: ${label ?? "selected asset"}`);
    }
  };
  load(url, false);
}

/**
 * Framing classification, replicated from the reference Flow Studio
 * observation model (`viewMode()`): when the object diameter fills more
 * than 90% of the viewport height the user has zoomed in enough that the
 * form overflows the frame — scrutinising a single region (`detail`).
 * When it drops below half the viewport the whole silhouette is being
 * surveyed (`survey`); a fully-framed form in between is `compare`.
 */
export function computeViewMode(
  camera: THREE.PerspectiveCamera,
  objectRadius: number,
  cameraDistance: number,
  screenScale = 1,
): "empty" | "survey" | "detail" | "compare" {
  if (objectRadius <= 0 || cameraDistance <= 0) return "empty";
  const halfViewportHeight = cameraDistance * Math.tan(((camera.fov * Math.PI) / 180) / 2);
  const fill = (objectRadius / Math.max(1e-4, halfViewportHeight)) * screenScale;
  if (fill > 0.9) return "detail";
  if (fill < 0.5) return "survey";
  return "compare";
}

export function createOrbitInteractionProbe(
  controls: { addEventListener(type: string, listener: () => void): void; removeEventListener(type: string, listener: () => void): void; target: THREE.Vector3 },
  camera: THREE.PerspectiveCamera,
  getObjectRadius: () => number,
  onSignal: (signal: { type: "zoom" | "orbit"; dwell_ms: number; camera_distance: number; view_mode: "empty" | "survey" | "detail" | "compare" }) => void,
) {
  let interactionStartDistance = camera.position.distanceTo(controls.target);
  let interactionStartAt = Date.now();
  let lastInteractionEndAt = Date.now();
  const onControlsStart = () => {
    interactionStartDistance = camera.position.distanceTo(controls.target);
    interactionStartAt = Date.now();
  };
  const onControlsEnd = () => {
    const distance = camera.position.distanceTo(controls.target);
    const distanceDelta = Math.abs(distance - interactionStartDistance);
    const now = Date.now();
    const dwellMs = Math.min(12000, Math.max(0, interactionStartAt - lastInteractionEndAt));
    lastInteractionEndAt = now;
    onSignal({
      type: distanceDelta > 0.12 ? "zoom" : "orbit",
      dwell_ms: dwellMs,
      camera_distance: Number(distance.toFixed(3)),
      view_mode: computeViewMode(camera, getObjectRadius(), distance),
    });
  };
  controls.addEventListener("start", onControlsStart);
  controls.addEventListener("end", onControlsEnd);
  return () => {
    controls.removeEventListener("start", onControlsStart);
    controls.removeEventListener("end", onControlsEnd);
  };
}
