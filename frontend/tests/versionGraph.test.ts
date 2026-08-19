import assert from "node:assert/strict";
import test from "node:test";

import * as versionGraph from "../src/utils/versionGraph.ts";
import type { VersionGraphNode } from "../src/types.ts";

const { layoutVersionGraph } = versionGraph;

test("active version metadata keeps only the object name", () => {
  const compact = (versionGraph as typeof versionGraph & {
    compactVersionLabel?: (label: string) => string;
  }).compactVersionLabel;

  assert.equal(typeof compact, "function", "compact version label projection is missing");
  assert.equal(compact?.("Christmas · Snowman"), "Snowman");
  assert.equal(compact?.("Snowman"), "Snowman");
});


const node = (
  node_id: string,
  version_number: number,
  parent_node_id: string | null,
): VersionGraphNode => ({
  node_id,
  session_id: "session",
  version_number,
  parent_node_id,
  candidate_id: node_id === "source" ? null : `candidate_${node_id}`,
  label: `Version ${version_number}`,
  preview_url: `/${node_id}.png`,
  mesh_url: null,
  obj_url: null,
  status: node_id === "source" ? "mesh_ready" : "image_ready",
  hy3d_job_id: null,
  error: null,
  created_at: `2026-08-06T00:00:0${version_number}Z`,
  updated_at: `2026-08-06T00:00:0${version_number}Z`,
});


const source = node("source", 1, null);
const v2 = node("v2", 2, "source");
const v3 = node("v3", 3, "v2");
const sibling = node("sibling", 4, "source");
const third = node("third", 5, "source");


test("places ancestors left of the active node", () => {
  const result = layoutVersionGraph([source, v2, v3], "v3");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));

  assert.ok(byId.source.x < byId.v2.x);
  assert.ok(byId.v2.x < byId.v3.x);
});


test("keeps the first branch on the horizontal spine", () => {
  const result = layoutVersionGraph([source, v2], "v2");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));

  assert.equal(byId.v2.y, 0);
  assert.equal(byId.source.y, 0);
  assert.ok(byId.source.x < byId.v2.x);
});


test("opens a ternary fan: forward, then up, then down", () => {
  const result = layoutVersionGraph([source, v2, sibling, third], "source");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));

  assert.equal(byId.source.y, 0);
  assert.equal(byId.v2.y, 0, "first sibling stays on the spine");
  assert.ok(byId.sibling.y < 0, "second sibling goes up");
  assert.ok(byId.third.y > 0, "third sibling goes down");
});


test("stacks later sibling branches vertically away from the first", () => {
  const result = layoutVersionGraph([source, v2, sibling], "v2");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));

  assert.equal(byId.v2.y, 0);
  assert.notEqual(byId.v2.y, byId.sibling.y);
});


test("keeps an active 520px node from covering a sibling history node", () => {
  const result = layoutVersionGraph([source, v2, v3, sibling], "sibling");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));
  const active = byId.sibling;
  const historySibling = byId.v2;
  const overlaps = !(
    active.x + active.width <= historySibling.x
    || historySibling.x + historySibling.width <= active.x
    || active.y + active.height <= historySibling.y
    || historySibling.y + historySibling.height <= active.y
  );

  assert.equal(overlaps, false);
});


test("keeps an expanded active node from covering its first child", () => {
  const result = layoutVersionGraph([source, v2], "source");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));
  const overlaps = !(
    byId.source.x + byId.source.width <= byId.v2.x
    || byId.v2.x + byId.v2.width <= byId.source.x
    || byId.source.y + byId.source.height <= byId.v2.y
    || byId.v2.y + byId.v2.height <= byId.source.y
  );

  assert.equal(overlaps, false);
});


test("keeps a viewport-sized active node from covering its first child", () => {
  const result = layoutVersionGraph([source, v2], "source", true, { width: 1400, height: 900 });
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));

  assert.equal(byId.source.width, 1400);
  assert.ok(byId.source.x + byId.source.width <= byId.v2.x);
});


test("keeps a branch's descendants on that branch's row", () => {
  const nephew = node("nephew", 6, "sibling");
  const result = layoutVersionGraph([source, v2, sibling, nephew], "source");
  const byId = Object.fromEntries(result.nodes.map((item) => [item.id, item]));

  assert.equal(byId.nephew.y, byId.sibling.y);
  assert.notEqual(byId.nephew.y, byId.v2.y);
});


test("keeps the active node at the main editing anchor", () => {
  const active = layoutVersionGraph([source, v2], "v2").nodes.find(
    (item) => item.id === "v2",
  );

  // First child of Version 1 continues on the same horizontal spine.
  assert.deepEqual(
    { x: active?.x, y: active?.y, width: active?.width, height: active?.height },
    { x: 640, y: 0, width: 520, height: 520 },
  );
});

test("centers the active editor on the free-area midpoint", () => {
  const { computeCenteredActiveCanvasPan, computeOverviewCanvasCamera } = versionGraph as typeof versionGraph & {
    computeCenteredActiveCanvasPan: typeof versionGraph.computeCenteredActiveCanvasPan;
    computeOverviewCanvasCamera: typeof versionGraph.computeOverviewCanvasCamera;
  };
  assert.deepEqual(
    computeCenteredActiveCanvasPan({
      shellWidth: 1000,
      shellHeight: 800,
      targetCenterX: 500,
      targetCenterY: 400,
      nodeX: 640,
      nodeY: 0,
      nodeWidth: 720,
      nodeHeight: 600,
    }),
    { x: -500, y: 100 },
  );
  assert.deepEqual(
    computeOverviewCanvasCamera(
      [{ x: 640, y: 0, width: 220, height: 220 }],
      { width: 1000, height: 800, centerX: 500, centerY: 400 },
    ),
    { zoom: 1, pan: { x: -250, y: 290 } },
  );
});


test("overview layout stays put when the highlighted node changes", () => {
  const highlightedLeaf = layoutVersionGraph([source, v2, v3], "v3", false);
  const highlightedRoot = layoutVersionGraph([source, v2, v3], "source", false);
  assert.deepEqual(
    highlightedLeaf.nodes.map((item) => ({ id: item.id, x: item.x, y: item.y })),
    highlightedRoot.nodes.map((item) => ({ id: item.id, x: item.x, y: item.y })),
  );
});


test("returns one parent link per non-root node", () => {
  const result = layoutVersionGraph([source, v2, v3, sibling], "v3");

  assert.equal(result.links.length, 3);
  assert.equal(result.links.filter((link) => link.isActivePath).length, 2);
});
