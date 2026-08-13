export type RuntimeEndpointOptions = {
  buildApiBase?: string;
  buildWsBase?: string;
  runtimeApiBase?: string;
  runtimeWsBase?: string;
  protocol: string;
  hostname: string;
};

function normalizedBase(value: string | undefined) {
  const normalized = value?.trim().replace(/\/+$/, "");
  return normalized || undefined;
}

export function resolveRuntimeEndpoints(options: RuntimeEndpointOptions) {
  const apiBase =
    normalizedBase(options.buildApiBase) ??
    normalizedBase(options.runtimeApiBase) ??
    `${options.protocol}//${options.hostname}:18000`;
  const wsBase =
    normalizedBase(options.buildWsBase) ??
    normalizedBase(options.runtimeWsBase) ??
    apiBase.replace(/^http/i, "ws");

  return { apiBase, wsBase };
}
