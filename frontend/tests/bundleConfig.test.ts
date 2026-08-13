import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("production build separates heavy Three and React vendors", async () => {
  const config = await readFile(new URL("../vite.verify.config.ts", import.meta.url), "utf8");
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(pkg.scripts.build, /--config\s+vite\.verify\.config\.ts/);
  assert.match(config, /manualChunks/);
  assert.match(config, /vendor-three/);
  assert.match(config, /vendor-react/);
});

