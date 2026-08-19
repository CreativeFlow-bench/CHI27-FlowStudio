/**
 * Pure sculpting algorithms (refactor plan P1a).
 * No React / component state: all functions operate on a mesh + stroke params.
 */

import * as THREE from "three";
import type { SculptTool } from "../../types";

export function sculptFalloff(t: number) {
  const clamped = Math.max(0, Math.min(1, t));
  return 1 - 3 * clamped * clamped + 2 * clamped * clamped * clamped;
}

/** World-space radius of the editable mesh — used to keep brush size/strength
 * proportional to the model instead of Three's non-uniform scale vector length. */
export function sculptModelRadius(mesh: THREE.Mesh) {
  const box = new THREE.Box3().setFromObject(mesh);
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  return Math.max(1e-3, sphere.radius);
}

export function sculptWorldRadius(uiRadius: number, modelRadius: number) {
  const t = Math.max(0.02, Math.min(1, uiRadius));
  return modelRadius * (0.04 + t * 0.42);
}

export function sculptWorldStrength(uiStrength: number, modelRadius: number) {
  const t = Math.max(0.02, Math.min(1, uiStrength));
  // Per-dab push as a fraction of model size. Spacing in continue() prevents
  // high-frequency pointer events from stacking this into spikes.
  return modelRadius * (0.004 + t * 0.028);
}

export function sculptWorldPositions(mesh: THREE.Mesh) {
  const geometry = mesh.geometry as THREE.BufferGeometry;
  const attribute = geometry.getAttribute("position") as THREE.BufferAttribute;
  const positions = attribute.array as Float32Array;
  const matrixWorld = mesh.matrixWorld;
  const count = attribute.count;
  const world = new Float32Array(count * 3);
  for (let index = 0; index < count; index += 1) {
    const x = positions[index * 3];
    const y = positions[index * 3 + 1];
    const z = positions[index * 3 + 2];
    world[index * 3] = matrixWorld.elements[0] * x + matrixWorld.elements[4] * y + matrixWorld.elements[8] * z + matrixWorld.elements[12];
    world[index * 3 + 1] = matrixWorld.elements[1] * x + matrixWorld.elements[5] * y + matrixWorld.elements[9] * z + matrixWorld.elements[13];
    world[index * 3 + 2] = matrixWorld.elements[2] * x + matrixWorld.elements[6] * y + matrixWorld.elements[10] * z + matrixWorld.elements[14];
  }
  return { positions, world, count };
}

/** Convert a world-space direction into mesh-local space without the
 * translation component of the inverse matrix (applyMatrix4 would add the
 * mesh origin offset and corrupt the direction). */
function worldDirectionToLocal(direction: THREE.Vector3, inverse: THREE.Matrix4) {
  const length = direction.length();
  const out = direction.clone().transformDirection(inverse);
  if (length > 0) out.multiplyScalar(length);
  return out;
}

export function sculptApplyOffset(
  mesh: THREE.Mesh,
  center: THREE.Vector3,
  radius: number,
  offsetFor: (distance: number, index: number, worldPosition: Float32Array) => THREE.Vector3,
  falloff: (t: number) => number = sculptFalloff,
) {
  const { positions, world, count } = sculptWorldPositions(mesh);
  const inverse = new THREE.Matrix4().copy(mesh.matrixWorld).invert();
  const offset = new THREE.Vector3();
  for (let index = 0; index < count; index += 1) {
    const wx = world[index * 3];
    const wy = world[index * 3 + 1];
    const wz = world[index * 3 + 2];
    const distance = Math.sqrt(
      (wx - center.x) * (wx - center.x) + (wy - center.y) * (wy - center.y) + (wz - center.z) * (wz - center.z),
    );
    if (distance > radius) continue;
    const direction = offsetFor(distance, index, world.subarray(index * 3, index * 3 + 3));
    direction.multiplyScalar(falloff(distance / radius));
    offset.copy(worldDirectionToLocal(direction, inverse));
    positions[index * 3] += offset.x;
    positions[index * 3 + 1] += offset.y;
    positions[index * 3 + 2] += offset.z;
  }
}

export type GrabStroke = {
  indices: Uint32Array;
  baseWorld: Float32Array;
  weights: Float32Array;
  accumulatedDelta: THREE.Vector3;
  inverseWorld: THREE.Matrix4;
};

/** True grab: picked vertices translate together with the pointer, weighted by
 * the initial falloff so the boundary blends softly. */
export function grabDisplace(mesh: THREE.Mesh, stroke: GrabStroke) {
  const attribute = (mesh.geometry as THREE.BufferGeometry).getAttribute("position") as THREE.BufferAttribute;
  const positions = attribute.array as Float32Array;
  const { indices, baseWorld, weights, accumulatedDelta, inverseWorld } = stroke;
  const target = new THREE.Vector3();
  let maxD = 0;
  for (let k = 0; k < indices.length; k += 1) {
    const index = indices[k];
    const weight = weights[index];
    if (weight <= 0) continue;
    target
      .set(baseWorld[index * 3], baseWorld[index * 3 + 1], baseWorld[index * 3 + 2])
      .addScaledVector(accumulatedDelta, weight)
      .applyMatrix4(inverseWorld);
    const d = Math.hypot(target.x - positions[index*3], target.y - positions[index*3+1], target.z - positions[index*3+2]);
    if (d > maxD) maxD = d;
    positions[index * 3] = target.x;
    positions[index * 3 + 1] = target.y;
    positions[index * 3 + 2] = target.z;
  }
}

/** Falloff-weighted Laplacian-style blur over the fixed picked region. */
export function smoothDisplace(mesh: THREE.Mesh, stroke: GrabStroke, strength: number) {
  const attribute = (mesh.geometry as THREE.BufferGeometry).getAttribute("position") as THREE.BufferAttribute;
  const positions = attribute.array as Float32Array;
  const { indices, weights, inverseWorld } = stroke;
  const point = new THREE.Vector3();
  const centroid = new THREE.Vector3();
  let totalWeight = 0;
  for (let k = 0; k < indices.length; k += 1) {
    const index = indices[k];
    const weight = weights[index];
    if (weight <= 0) continue;
    point.set(positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2]).applyMatrix4(mesh.matrixWorld);
    centroid.addScaledVector(point, weight);
    totalWeight += weight;
  }
  if (totalWeight > 0) centroid.divideScalar(totalWeight);
  for (let k = 0; k < indices.length; k += 1) {
    const index = indices[k];
    const weight = weights[index];
    if (weight <= 0) continue;
    point.set(positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2]).applyMatrix4(mesh.matrixWorld);
    const delta = new THREE.Vector3().copy(centroid).sub(point).multiplyScalar(strength * weight);
    delta.copy(worldDirectionToLocal(delta, inverseWorld));
    positions[index * 3] += delta.x;
    positions[index * 3 + 1] += delta.y;
    positions[index * 3 + 2] += delta.z;
  }
}

export function createBrushCursor() {
  return new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      Array.from({ length: 48 }, (_, index) => {
        const angle = (index / 48) * Math.PI * 2;
        return new THREE.Vector3(Math.cos(angle) * 0.5, Math.sin(angle) * 0.5, 0);
      }),
    ),
    new THREE.LineBasicMaterial({ color: 0x3b82f6, transparent: true, opacity: 0.9 }),
  );
}

export function positionBrushCursor(
  cursor: THREE.Line,
  point: THREE.Vector3,
  normal: THREE.Vector3,
  radius: number,
) {
  cursor.position.copy(point);
  cursor.lookAt(point.clone().add(normal));
  cursor.scale.setScalar(Math.max(1e-3, radius) * 2);
}

export type SculptStrokeEvidence = {
  tool: SculptTool;
  engine: "client_webgl_sculpt";
  center: number[];
  radius: number;
  strength: number;
  vertex_count: number;
  positions: Float32Array;
};

/**
 * Interactive sculpt session: begin/continue/finish over one pointer stroke.
 * Owns grabbed-region bookkeeping so the viewport effect stays thin
 * (refactor plan P1a; drag delta is accumulated per move).
 */
export class SculptSession {
  tool: SculptTool | null = null;
  active = false;
  center = new THREE.Vector3();
  startCenter = new THREE.Vector3();
  strokeNormal = new THREE.Vector3(0, 1, 0);
  lastPointer = { x: 0, y: 0 };
  radiusWorld = 0.05;
  strength = 0.01;
  modelRadius = 1;
  travelSinceDab = 0;
  basePositions: Float32Array | null = null;
  grabbed: GrabStroke | null = null;
  targetMesh: THREE.Mesh | null = null;

  begin(
    mesh: THREE.Mesh,
    hitPoint: THREE.Vector3,
    pointer: { x: number; y: number },
    tool: SculptTool,
    radius: number,
    strength: number,
    strokeNormal?: THREE.Vector3 | null,
  ) {
    const geometry = mesh.geometry as THREE.BufferGeometry;
    const attribute = geometry.getAttribute("position") as THREE.BufferAttribute;
    this.targetMesh = mesh;
    this.basePositions = new Float32Array(attribute.array as Float32Array);
    const modelRadius = sculptModelRadius(mesh);
    const radiusWorld = sculptWorldRadius(radius, modelRadius);
    const strengthWorld = sculptWorldStrength(strength, modelRadius);
    let grabbed: GrabStroke | null = null;
    if (tool === "drag" || tool === "smooth") {
      const { world, count } = sculptWorldPositions(mesh);
      const picked: number[] = [];
      const baseWorld = new Float32Array(count * 3);
      const weights = new Float32Array(count);
      for (let index = 0; index < count; index += 1) {
        const wx = world[index * 3];
        const wy = world[index * 3 + 1];
        const wz = world[index * 3 + 2];
        const distance = Math.sqrt(
          (wx - hitPoint.x) ** 2 + (wy - hitPoint.y) ** 2 + (wz - hitPoint.z) ** 2,
        );
        if (distance <= radiusWorld) {
          picked.push(index);
          baseWorld[index * 3] = wx;
          baseWorld[index * 3 + 1] = wy;
          baseWorld[index * 3 + 2] = wz;
          weights[index] = sculptFalloff(distance / radiusWorld);
        }
      }
      grabbed = {
        indices: new Uint32Array(picked),
        baseWorld,
        weights,
        accumulatedDelta: new THREE.Vector3(),
        inverseWorld: new THREE.Matrix4().copy(mesh.matrixWorld).invert(),
      };
    }
    this.tool = tool;
    this.active = true;
    this.center.copy(hitPoint);
    this.startCenter.copy(hitPoint);
    this.strokeNormal.copy(strokeNormal ?? new THREE.Vector3(0, 1, 0));
    this.lastPointer = pointer;
    this.radiusWorld = radiusWorld;
    this.strength = strengthWorld;
    this.modelRadius = modelRadius;
    this.travelSinceDab = Number.POSITIVE_INFINITY; // allow first dab immediately
    this.grabbed = grabbed;
  }

  continue(
    mesh: THREE.Mesh,
    hitPoint: THREE.Vector3,
    faceNormal: THREE.Vector3 | null,
    pointer: { x: number; y: number },
    shiftKey: boolean,
    ray?: THREE.Ray,
  ) {
    if (this.tool === "drag" && this.grabbed) {
      // True grab: vertices picked at stroke start translate together with the
      // pointer. Delta is always measured from the stroke START, otherwise each
      // move would reset the displacement and the grab would "rebound".
      if (ray) {
        if (!shiftKey) {
          // Default: constrain to strokeNormal (perpendicular to surface)
          const p1 = this.startCenter;
          const d1 = this.strokeNormal.clone().normalize();
          const p2 = ray.origin;
          const d2 = ray.direction.clone().normalize();
          
          const w0 = p1.clone().sub(p2);
          const b = d1.dot(d2);
          const d = d1.dot(w0);
          const e = d2.dot(w0);
          const denominator = 1 - b * b;
          
          if (denominator > 1e-5) {
            const t = (b * e - d) / denominator;
            this.grabbed.accumulatedDelta.copy(d1).multiplyScalar(t);
          }
        } else {
          // Shift pressed: drag freely in camera plane
          const planeNormal = ray.direction.clone().multiplyScalar(-1); 
          const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(planeNormal, this.startCenter);
          const planeHit = new THREE.Vector3();
          if (ray.intersectPlane(plane, planeHit)) {
            this.grabbed.accumulatedDelta.copy(planeHit).sub(this.startCenter);
          }
        }
      } else {
        this.grabbed.accumulatedDelta.copy(hitPoint).sub(this.startCenter);
      }
      grabDisplace(mesh, this.grabbed);
    } else if (this.tool === "brush") {
      const travel = hitPoint.distanceTo(this.center);
      this.travelSinceDab += travel;
      // Space dabs so high-frequency pointer events cannot explode the mesh.
      const spacing = Math.max(this.radiusWorld * 0.22, this.modelRadius * 0.003);
      if (this.travelSinceDab >= spacing) {
        const step = Math.min(
          this.strength * Math.min(1.25, this.travelSinceDab / spacing),
          this.modelRadius * 0.035,
        );
        const direction = (shiftKey ? -1 : 1) * step;
        // Dab at the current hit — previous center only tracks travel.
        sculptApplyOffset(
          mesh,
          hitPoint,
          this.radiusWorld,
          () => this.strokeNormal.clone().multiplyScalar(direction),
        );
        this.travelSinceDab = 0;
      }
    } else if (this.tool === "smooth" && this.grabbed) {
      const smoothStep = Math.min(this.strength * 0.35, 0.18);
      smoothDisplace(mesh, this.grabbed, smoothStep);
    }
    this.center.copy(hitPoint);
    this.lastPointer = pointer;
  }

  finish(mesh: THREE.Mesh | null): SculptStrokeEvidence | null {
    if (!this.active) return null;
    this.active = false;
    const basePositions = this.basePositions;
    if (!mesh || !basePositions) return null;
    const evidence: SculptStrokeEvidence = {
      tool: this.tool as SculptTool,
      engine: "client_webgl_sculpt",
      center: this.center.toArray(),
      radius: this.radiusWorld,
      strength: this.strength,
      vertex_count: (mesh.geometry as THREE.BufferGeometry).getAttribute("position").count,
      positions: basePositions,
    };
    this.targetMesh = null;
    return evidence;
  }

  reset() {
    this.active = false;
    this.tool = null;
    this.grabbed = null;
    this.basePositions = null;
    this.targetMesh = null;
    this.travelSinceDab = 0;
  }
}

export function createMeshSelectionHandlers(opts: {
  renderer: THREE.WebGLRenderer;
  camera: THREE.PerspectiveCamera;
  raycaster: THREE.Raycaster;
  pointer: THREE.Vector2;
  interactive: THREE.Mesh[];
  hoverThrottleMs?: number;
  isSculpting: () => boolean;
  lastHover: { name: string; at: number };
  onSelect(name: string): void;
  onHover(name: string): void;
}) {
  const { renderer, camera, raycaster, pointer, interactive, isSculpting, onSelect, onHover } = opts;
  const throttleMs = opts.hoverThrottleMs ?? 250;
  const onPointerDown = (event: PointerEvent) => {
    if (isSculpting()) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(interactive, true)[0];
    if (hit?.object.name) onSelect(hit.object.name);
  };
  const onPointerMove = (event: PointerEvent) => {
    if (isSculpting()) return;
    const now = Date.now();
    if (now - opts.lastHover.at < throttleMs) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(interactive, true)[0];
    const name = hit?.object.name || "";
    if (name === opts.lastHover.name) return;
    opts.lastHover.name = name;
    opts.lastHover.at = now;
    onHover(name);
  };
  const attach = () => {
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
  };
  const detach = () => {
    renderer.domElement.removeEventListener("pointerdown", onPointerDown);
    renderer.domElement.removeEventListener("pointermove", onPointerMove);
  };
  return { attach, detach };
}

export class SculptPointerController {
  private renderer: THREE.WebGLRenderer;
  private camera: THREE.PerspectiveCamera;
  private raycaster: THREE.Raycaster;
  private pointer: THREE.Vector2;
  private interactive: THREE.Mesh[];
  private controls: { enabled: boolean };
  private cursor: THREE.Line;
  private session: SculptSession;
  private getTool: () => SculptTool | null;
  private getRadius: () => number;
  private getStrength: () => number;
  private getTarget: () => THREE.Mesh | null;
  private onBegin: (mesh: THREE.Mesh, session: SculptSession) => void;
  private onEvidence: (tool: SculptTool, evidence: SculptStrokeEvidence) => void;

  constructor(opts: {
    renderer: THREE.WebGLRenderer;
    camera: THREE.PerspectiveCamera;
    raycaster: THREE.Raycaster;
    pointer: THREE.Vector2;
    interactive: THREE.Mesh[];
    controls: { enabled: boolean };
    cursor: THREE.Line;
    session: SculptSession;
    getTool: () => SculptTool | null;
    getRadius: () => number;
    getStrength: () => number;
    getTarget: () => THREE.Mesh | null;
    onBegin: (mesh: THREE.Mesh, session: SculptSession) => void;
    onEvidence: (tool: SculptTool, evidence: SculptStrokeEvidence) => void;
  }) {
    this.renderer = opts.renderer;
    this.camera = opts.camera;
    this.raycaster = opts.raycaster;
    this.pointer = opts.pointer;
    this.interactive = opts.interactive;
    this.controls = opts.controls;
    this.cursor = opts.cursor;
    this.session = opts.session;
    this.getTool = opts.getTool;
    this.getRadius = opts.getRadius;
    this.getStrength = opts.getStrength;
    this.getTarget = opts.getTarget;
    this.onBegin = opts.onBegin;
    this.onEvidence = opts.onEvidence;
  }

  updateCursor(clientX?: number, clientY?: number) {
    if (!this.getTool() || clientX === undefined || clientY === undefined) {
      this.cursor.visible = false;
      return;
    }
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects(this.interactive, true)[0];
    if (!hit?.point) {
      this.cursor.visible = false;
      return;
    }
    const normal = hit.face
      ? hit.face.normal.clone().transformDirection(hit.object.matrixWorld)
      : new THREE.Vector3(0, 0, 1);
    const scale = this.getTarget() ? sculptModelRadius(this.getTarget()!) : 1;
    positionBrushCursor(this.cursor, hit.point, normal, sculptWorldRadius(this.getRadius(), scale));
    this.cursor.visible = true;
  }

  onPointerDown = (event: PointerEvent) => {
    const sculptActive = this.getTool();
    if (!sculptActive) return;
    try {
      const rect = this.renderer.domElement.getBoundingClientRect();
      this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      this.raycaster.setFromCamera(this.pointer, this.camera);
      const hit = this.raycaster.intersectObjects(this.interactive, true)[0];
      if (!hit?.object || !(hit.object instanceof THREE.Mesh)) return;
      const mesh = hit.object as THREE.Mesh;
      this.session.begin(
        mesh,
        hit.point,
        { x: event.clientX, y: event.clientY },
        sculptActive,
        this.getRadius(),
        this.getStrength(),
        hit.face ? hit.face.normal.clone().transformDirection(mesh.matrixWorld) : null,
      );
      this.onBegin(mesh, this.session);
      this.controls.enabled = false;
      this.renderer.domElement.setPointerCapture(event.pointerId);
      event.preventDefault();
    } catch (error) {
      this.controls.enabled = true;
      this.session.reset();
      console.error("sculpt begin error", error);
    }
  };

  onPointerMove = (event: PointerEvent) => {
    this.updateCursor(event.clientX, event.clientY);
    if (!this.session.active) return;
    try {
      const mesh = this.getTarget();
      if (!mesh) return;
      const rect = this.renderer.domElement.getBoundingClientRect();
      this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      this.raycaster.setFromCamera(this.pointer, this.camera);
      const hit = this.raycaster.intersectObject(mesh, true)[0];
      const hitPoint = hit?.point ?? this.session.center;
      const faceNormal = hit?.face
        ? hit.face.normal.clone().transformDirection(mesh.matrixWorld)
        : null;
      this.session.continue(
        mesh,
        hitPoint,
        faceNormal,
        { x: event.clientX, y: event.clientY },
        event.shiftKey,
        this.raycaster.ray
      );
      (mesh.geometry as THREE.BufferGeometry).getAttribute("position").needsUpdate = true;
      (mesh.geometry as THREE.BufferGeometry).computeVertexNormals();
      event.preventDefault();
    } catch (error) {
      console.error("sculpt continue error", error);
    }
  };

  onPointerUp = (event: PointerEvent) => {
    const evidence = this.session.finish(this.getTarget());
    if (evidence) {
      this.onEvidence(evidence.tool, evidence);
    }
    this.controls.enabled = true;
    try {
      this.renderer.domElement.releasePointerCapture(event.pointerId);
    } catch {
      // ignore release errors
    }
  };

  onPointerLeave = () => {
    this.cursor.visible = false;
  };

  attach() {
    this.renderer.domElement.addEventListener("pointerdown", this.onPointerDown);
    this.renderer.domElement.addEventListener("pointermove", this.onPointerMove);
    this.renderer.domElement.addEventListener("pointerup", this.onPointerUp);
    this.renderer.domElement.addEventListener("pointercancel", this.onPointerUp);
    this.renderer.domElement.addEventListener("pointerleave", this.onPointerLeave);
  }

  detach() {
    this.renderer.domElement.removeEventListener("pointerdown", this.onPointerDown);
    this.renderer.domElement.removeEventListener("pointermove", this.onPointerMove);
    this.renderer.domElement.removeEventListener("pointerup", this.onPointerUp);
    this.renderer.domElement.removeEventListener("pointercancel", this.onPointerUp);
    this.renderer.domElement.removeEventListener("pointerleave", this.onPointerLeave);
  }
}
