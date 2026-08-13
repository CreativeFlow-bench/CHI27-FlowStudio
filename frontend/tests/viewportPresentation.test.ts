import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readScene = () => readFile(new URL("../src/components/viewport/scene.ts", import.meta.url), "utf8");

test("studio lighting uses a bounded key-fill-rim rig", async () => {
  const source = await readScene();
  const lighting = source.slice(source.indexOf("export function addStudioPreviewLighting"), source.indexOf("export function loadObjWithOptionalMtl"));
  const values = [...lighting.matchAll(/intensity:\s*([\d.]+)/g)].map((match) => Number(match[1]));
  assert.ok(values.length <= 4, `expected at most 4 directional lights, got ${values.length}`);
  assert.ok(values.reduce((sum, value) => sum + value, 0) <= 4, "directional light intensity is still overexposed");
  assert.match(lighting, /AmbientLight\("#ffffff",\s*0\./);
});

test("textured mode gives untextured near-white materials visible clay contrast", async () => {
  const source = await readScene();
  const display = source.slice(source.indexOf("export function applyDisplayMaterial"), source.indexOf("export function standardizeMeshMaterial"));
  assert.match(display, /!material\.map/);
  assert.match(display, /luminance/);
  assert.match(display, /material\.color\.set\("#[0-9a-f]{6}"\)/i);
});

test("textured mode preserves actual texture maps", async () => {
  const source = await readScene();
  const display = source.slice(source.indexOf("export function applyDisplayMaterial"), source.indexOf("export function standardizeMeshMaterial"));
  assert.match(display, /if\s*\(displayMode === "textured"\)/);
  assert.doesNotMatch(display, /material\.map\s*=\s*null[\s\S]*if\s*\(displayMode === "textured"\)/);
});

test("renderer exposure does not wash out light surfaces", async () => {
  const source = await readFile(new URL("../src/components/ThreeViewport.tsx", import.meta.url), "utf8");
  const match = source.match(/toneMappingExposure\s*=\s*([\d.]+)/);
  assert.ok(match, "renderer must set an explicit tone-mapping exposure");
  assert.ok(Number(match[1]) <= 1, `expected exposure <= 1, got ${match[1]}`);
});
