import assert from "node:assert/strict";
import test from "node:test";

import { resolveRuntimeEndpoints } from "../src/utils/runtimeEndpoints.ts";

test("build-time endpoints take precedence over runtime overrides", () => {
  assert.deepEqual(
    resolveRuntimeEndpoints({
      buildApiBase: "https://build.example/api/",
      buildWsBase: "wss://build.example/ws/",
      runtimeApiBase: "https://runtime.example/api",
      runtimeWsBase: "wss://runtime.example/ws",
      protocol: "https:",
      hostname: "gpu.example",
    }),
    { apiBase: "https://build.example/api", wsBase: "wss://build.example/ws" },
  );
});

test("runtime API override owns the derived WebSocket endpoint", () => {
  assert.deepEqual(
    resolveRuntimeEndpoints({
      runtimeApiBase: "http://127.0.0.1:18000/",
      protocol: "http:",
      hostname: "gpu.example",
    }),
    { apiBase: "http://127.0.0.1:18000", wsBase: "ws://127.0.0.1:18000" },
  );
});

test("production fallback targets same-host GPU port 18000", () => {
  assert.deepEqual(
    resolveRuntimeEndpoints({ protocol: "https:", hostname: "gpu.example" }),
    { apiBase: "https://gpu.example:18000", wsBase: "wss://gpu.example:18000" },
  );
});
