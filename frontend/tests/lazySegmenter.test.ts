import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("loads MobileSAM only when segmentation is requested", async () => {
  const source = await readFile(new URL("../src/state/studioStore.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /import\s+\{[^}]*segmentPoints[^}]*\}\s+from\s+["']\.\.\/utils\/segmenter["']/);
  assert.match(source, /import\(["']\.\.\/utils\/segmenter["']\)/);
});
