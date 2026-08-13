/**
 * EditorScene: the single source of truth for mesh editing in FlowStudio.
 *
 * Mirrors the DCC pattern described in
 * docs/FLOWSTUDIO_MESH_EDITOR_ARCH_REVIEW_V1_ZH.md:
 *   - geometry lives here (not inside a viewport component closure);
 *   - every edit is a Command with apply()/revert() on one unified stack;
 *   - geometry edits and editor-state edits share the same undo/redo order;
 *   - editOps() feeds asset versions and the perception/planner evidence chain.
 */

import * as THREE from "three";
import type { EditorSnapshot } from "./types";

export type EditEvidence = Record<string, unknown>;

export interface EditorCommand {
  id: string;
  label: string;
  tool: string;
  evidence: EditEvidence;
  apply: () => void;
  revert: () => void;
}

export class EditorScene {
  geometry: THREE.BufferGeometry | null = null;

  private commands: EditorCommand[] = [];
  private redoCommands: EditorCommand[] = [];
  private pendingAfterCaptureId: string | null = null;

  onCommandChange: (() => void) | null = null;
  onGeometryApply: ((positions: Float32Array | null) => void) | null = null;

  setGeometry(geometry: THREE.BufferGeometry | null): void {
    this.geometry = geometry;
  }

  getGeometry(): THREE.BufferGeometry | null {
    return this.geometry;
  }

  pushGeometryEdit(
    label: string,
    tool: string,
    before: Float32Array,
    after: Float32Array,
    evidence: EditEvidence,
  ): string {
    const id = `cmd_${Math.random().toString(36).slice(2, 10)}`;
    const applyPositions = after;
    const revertPositions = before;
    this.commands.push({
      id,
      label,
      tool,
      evidence,
      apply: () => this.onGeometryApply?.(applyPositions),
      revert: () => this.onGeometryApply?.(revertPositions),
    });
    this.redoCommands = [];
    this.onCommandChange?.();
    return id;
  }

  pushEditorCommand(
    label: string,
    snapshotBefore: EditorSnapshot,
    restore: (snapshot: EditorSnapshot) => void,
  ): string {
    const id = `cmd_${Math.random().toString(36).slice(2, 10)}`;
    const command: EditorCommand = {
      id,
      label,
      tool: "editor",
      evidence: { source: "editor", label },
      apply: () => {}, // captured after the next render settles
      revert: () => restore(snapshotBefore),
    };
    this.commands.push(command);
    this.redoCommands = [];
    this.pendingAfterCaptureId = id;
    this.onCommandChange?.();
    return id;
  }

  captureEditorAfter(snapshotAfter: EditorSnapshot, restore: (snapshot: EditorSnapshot) => void): void {
    if (!this.pendingAfterCaptureId) return;
    const command = this.commands.find((item) => item.id === this.pendingAfterCaptureId);
    if (command) {
      command.apply = () => restore(snapshotAfter);
    }
    this.pendingAfterCaptureId = null;
  }

  undo(): boolean {
    const command = this.commands.pop();
    if (!command) return false;
    command.revert();
    this.redoCommands.push(command);
    this.onCommandChange?.();
    return true;
  }

  redo(): boolean {
    const command = this.redoCommands.pop();
    if (!command) return false;
    command.apply();
    this.commands.push(command);
    this.onCommandChange?.();
    return true;
  }

  get canUndo(): boolean {
    return this.commands.length > 0;
  }

  get canRedo(): boolean {
    return this.redoCommands.length > 0;
  }

  get lastLabel(): string | null {
    return this.commands.length > 0 ? this.commands[this.commands.length - 1].label : null;
  }

  editOps(): EditEvidence[] {
    return this.commands
      .filter((command) => command.tool !== "editor")
      .map((command) => ({
        command_id: command.id,
        tool: command.tool,
        label: command.label,
        ...command.evidence,
      }));
  }

  reset(): void {
    this.commands = [];
    this.redoCommands = [];
    this.pendingAfterCaptureId = null;
    this.onCommandChange?.();
  }
}
