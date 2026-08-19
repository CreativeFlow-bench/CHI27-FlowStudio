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

test("static preview on 5173 talks to GPU backend 18000", () => {
  assert.deepEqual(
    resolveRuntimeEndpoints({
      protocol: "http:",
      hostname: "gpu.example",
      port: "5173",
      origin: "http://gpu.example:5173",
    }),
    { apiBase: "http://gpu.example:18000", wsBase: "ws://gpu.example:18000" },
  );
});

test("public same-origin gateway keeps API on the page origin", () => {
  assert.deepEqual(
    resolveRuntimeEndpoints({
      protocol: "https:",
      hostname: "u857862.example",
      port: "8443",
      origin: "https://u857862.example:8443",
    }),
    { apiBase: "https://u857862.example:8443", wsBase: "wss://u857862.example:8443" },
  );
});
