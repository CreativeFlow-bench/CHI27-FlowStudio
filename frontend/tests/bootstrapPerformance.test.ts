import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("workspace mounts before non-critical service hydration completes", async () => {
  const source = await readFile(new URL("../src/state/studioStore.ts", import.meta.url), "utf8");
  const bootstrap = source.slice(source.indexOf("const bootstrap = async"), source.indexOf("const activeCaseAssetId"));
  const ready = bootstrap.indexOf("setWorkspaceChromeReady(true)");
  const ancillary = bootstrap.indexOf("Promise.allSettled");
  assert.ok(ready >= 0, "bootstrap must mark the workspace ready");
  assert.ok(ancillary >= 0, "bootstrap must still hydrate ancillary data");
  assert.ok(ready < ancillary, "workspace readiness must not wait for ancillary requests");
});

