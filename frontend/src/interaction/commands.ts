import type { DivergenceSelection } from "../types.ts";

export type CommandMeta = {
  command_id: string;
  idempotency_key: string;
  expected_version?: number;
};

export type CommandIdentity = Pick<CommandMeta, "command_id" | "idempotency_key">;

export function commandMeta(
  prefix: string,
  expectedVersion?: number,
  identity?: Partial<CommandIdentity>,
): CommandMeta {
  const id = identity?.command_id ?? `${prefix}_${crypto.randomUUID()}`;
  return {
    command_id: id,
    idempotency_key: identity?.idempotency_key ?? id,
    ...(expectedVersion !== undefined ? { expected_version: expectedVersion } : {}),
  };
}

export function gatePayload(accepted: boolean, meta: CommandMeta, options?: Record<string, unknown>) {
  return { accepted, ...meta, ...(options ?? {}) };
}

export function selectionPayload(selection: DivergenceSelection, meta: CommandMeta) {
  return { ...selection, ...meta };
}
