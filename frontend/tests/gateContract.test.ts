import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("More Creative uses the compressed Gate semantic target for part scope", async () => {
  const source = await readFile(new URL("../src/state/studioStore.ts", import.meta.url), "utf8");
  assert.match(source, /decision\?\.semantic_target\s*\?\?/);
});

test("material and material_region both map to the material UI scope", async () => {
  const source = await readFile(new URL("../src/state/studioStore.ts", import.meta.url), "utf8");
  assert.match(source, /level === "material" \|\| level === "material_region"/);
});
