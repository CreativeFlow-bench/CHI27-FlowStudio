import type { VersionGraphNode } from "../types";

export const FLOWSTUDIO_CANDIDATE_MIME = "application/x-flowstudio-candidate";

const ACTIVE_NODE_SIZE = 520;
const HISTORY_NODE_SIZE = 220;
const COLUMN_GAP = 120;
const ACTIVE_ANCHOR_X = 640;

/** Pan so the active editor's box center lands on the free-area center. */
export function computeCenteredActiveCanvasPan(input: {
  shellWidth: number;
  shellHeight: number;
  /** Target center X inside the shell (defaults to geometric mid). */
  targetCenterX?: number;
  /** Target center Y inside the shell (defaults to geometric mid). */
  targetCenterY?: number;
  nodeX: number;
  nodeY: number;
  nodeWidth: number;
  nodeHeight: number;
}) {
  const centerX = input.targetCenterX ?? input.shellWidth / 2;
  const centerY = input.targetCenterY ?? input.shellHeight / 2;
  return {
    x: Math.round(centerX - (input.nodeX + input.nodeWidth / 2)),
    y: Math.round(centerY - (input.nodeY + input.nodeHeight / 2)),
  };
}

/** Fit+center an overview graph on a free band. Do not pad min/max with 0/520. */
export function computeOverviewCanvasCamera(
  nodes: Array<{ x: number; y: number; width: number; height: number }>,
  band: { width: number; height: number; centerX: number; centerY: number },
) {
  if (!nodes.length) {
    return { zoom: 1, pan: { x: Math.round(band.centerX), y: Math.round(band.centerY) } };
  }
  const minX = Math.min(...nodes.map((node) => node.x));
  const minY = Math.min(...nodes.map((node) => node.y));
  const maxX = Math.max(...nodes.map((node) => node.x + node.width));
  const maxY = Math.max(...nodes.map((node) => node.y + node.height));
  const spanX = maxX - minX + 240;
  const spanY = maxY - minY + 240;
  const zoom = Math.max(0.35, Math.min(1, Math.min(band.width / spanX, band.height / spanY)));
  return {
    zoom,
    pan: {
      x: Math.round(band.centerX - ((minX + maxX) / 2) * zoom),
      y: Math.round(band.centerY - ((minY + maxY) / 2) * zoom),
    },
  };
}

export function compactVersionLabel(label: string): string {
  const parts = label
    .split("·")
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.at(-1) ?? "Untitled";
}


export type VersionGraphLayoutNode = {
  id: string;
  graphNode: VersionGraphNode;
  x: number;
  y: number;
  width: number;
  height: number;
  isActive: boolean;
  isActivePath: boolean;
};

export type VersionGraphLayoutLink = {
  id: string;
  parentId: string;
  childId: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  controlX1: number;
  controlX2: number;
  isActivePath: boolean;
};


export function activePathNodeIds(
  nodes: VersionGraphNode[],
  activeNodeId: string | null,
): Set<string> {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const path = new Set<string>();
  let currentId = activeNodeId;
  while (currentId && !path.has(currentId)) {
    const current = byId.get(currentId);
    if (!current) break;
    path.add(current.node_id);
    currentId = current.parent_node_id;
  }
  return path;
}


export function layoutVersionGraph(
  nodes: VersionGraphNode[],
  activeNodeId: string | null,
  expandActive = true,
  activeExtent?: { width: number; height: number },
): { nodes: VersionGraphLayoutNode[]; links: VersionGraphLayoutLink[] } {
  if (!nodes.length) return { nodes: [], links: [] };
  const sorted = [...nodes].sort(
    (left, right) => left.version_number - right.version_number,
  );
  const byId = new Map(sorted.map((node) => [node.node_id, node]));
  const resolvedActiveId = byId.has(activeNodeId ?? "")
    ? activeNodeId
    : sorted[sorted.length - 1].node_id;
  const activePath = activePathNodeIds(sorted, resolvedActiveId);
  const depthMemo = new Map<string, number>();

  const depthOf = (nodeId: string, visiting = new Set<string>()): number => {
    const cached = depthMemo.get(nodeId);
    if (cached !== undefined) return cached;
    if (visiting.has(nodeId)) return 0;
    const node = byId.get(nodeId);
    if (!node?.parent_node_id || !byId.has(node.parent_node_id)) {
      depthMemo.set(nodeId, 0);
      return 0;
    }
    const nextVisiting = new Set(visiting).add(nodeId);
    const depth = depthOf(node.parent_node_id, nextVisiting) + 1;
    depthMemo.set(nodeId, depth);
    return depth;
  };

  // Ternary fan: 1st child continues horizontally; 2nd goes up; 3rd goes down…
  const siblingIndexById = new Map<string, number>();
  const childrenByParent = new Map<string, VersionGraphNode[]>();
  for (const node of sorted) {
    if (!node.parent_node_id) continue;
    const list = childrenByParent.get(node.parent_node_id) ?? [];
    list.push(node);
    childrenByParent.set(node.parent_node_id, list);
  }
  for (const children of childrenByParent.values()) {
    children
      .sort((left, right) => left.version_number - right.version_number)
      .forEach((child, index) => siblingIndexById.set(child.node_id, index));
  }

  // Overview must not re-anchor when the highlight changes, or the first
  // click of a double-click moves the node out from under the pointer.
  const activeDepth = expandActive ? depthOf(resolvedActiveId ?? sorted[0].node_id) : 0;
  const nodeWidth = expandActive
    ? Math.round(activeExtent?.width ?? ACTIVE_NODE_SIZE)
    : HISTORY_NODE_SIZE;
  const nodeHeight = expandActive
    ? Math.round(activeExtent?.height ?? ACTIVE_NODE_SIZE)
    : HISTORY_NODE_SIZE;
  const columnPitch = nodeWidth + COLUMN_GAP;
  const rowPitch = nodeHeight + COLUMN_GAP;

  const xOf = (depth: number) => ACTIVE_ANCHOR_X + (depth - activeDepth) * columnPitch;

  const yMemo = new Map<string, number>();
  const yOf = (nodeId: string): number => {
    const cached = yMemo.get(nodeId);
    if (cached !== undefined) return cached;
    const graphNode = byId.get(nodeId);
    const parentId = graphNode?.parent_node_id;
    const parentY = parentId && byId.has(parentId) ? yOf(parentId) : 0;
    const siblingIndex = siblingIndexById.get(nodeId) ?? 0;
    if (siblingIndex <= 0) {
      yMemo.set(nodeId, parentY);
      return parentY;
    }
    const distance = Math.ceil(siblingIndex / 2);
    const y = parentY + distance * rowPitch * (siblingIndex % 2 === 1 ? -1 : 1);
    yMemo.set(nodeId, y);
    return y;
  };

  const positioned: VersionGraphLayoutNode[] = sorted.map((node) => {
    const isActive = node.node_id === resolvedActiveId;
    const isActivePath = activePath.has(node.node_id);
    return {
      id: node.node_id,
      graphNode: node,
      x: xOf(depthOf(node.node_id)),
      y: yOf(node.node_id),
      width: nodeWidth,
      height: nodeHeight,
      isActive,
      isActivePath,
    };
  });
  const positionedById = new Map(positioned.map((node) => [node.id, node]));
  const links = positioned.flatMap((child): VersionGraphLayoutLink[] => {
    const parentId = child.graphNode.parent_node_id;
    const parent = parentId ? positionedById.get(parentId) : undefined;
    if (!parent) return [];
    const x1 = parent.x + parent.width;
    const y1 = parent.y + parent.height / 2;
    const x2 = child.x;
    const y2 = child.y + child.height / 2;
    const bend = Math.max(48, Math.abs(x2 - x1) * 0.5);
    return [{
      id: `link-${parent.id}-${child.id}`,
      parentId: parent.id,
      childId: child.id,
      x1,
      y1,
      x2,
      y2,
      controlX1: x1 + bend,
      controlX2: x2 - bend,
      isActivePath: parent.isActivePath && child.isActivePath,
    }];
  });
  return { nodes: positioned, links };
}
