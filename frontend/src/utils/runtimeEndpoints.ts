export type RuntimeEndpointOptions = {
  buildApiBase?: string;
  buildWsBase?: string;
  runtimeApiBase?: string;
  runtimeWsBase?: string;
  protocol: string;
  hostname: string;
  port?: string;
  origin?: string;
};

function normalizedBase(value: string | undefined) {
  const normalized = value?.trim().replace(/\/+$/, "");
  return normalized || undefined;
}

function inferredApiBase(options: RuntimeEndpointOptions) {
  const port = options.port || "";
  if (port === "5184") return `${options.protocol}//${options.hostname}:18001`;
  if (port === "5173") return `${options.protocol}//${options.hostname}:18000`;
  // AutoDL / nginx same-origin gateways (e.g. :8443 → backend :18000).
  if (port && port !== "18000" && port !== "18001" && options.origin) {
    return options.origin.replace(/\/+$/, "");
  }
  return `${options.protocol}//${options.hostname}:18000`;
}

export function resolveRuntimeEndpoints(options: RuntimeEndpointOptions) {
  const apiBase =
    normalizedBase(options.buildApiBase) ??
    normalizedBase(options.runtimeApiBase) ??
    inferredApiBase(options);
  const wsBase =
    normalizedBase(options.buildWsBase) ??
    normalizedBase(options.runtimeWsBase) ??
    apiBase.replace(/^http/i, "ws");

  return { apiBase, wsBase };
}
