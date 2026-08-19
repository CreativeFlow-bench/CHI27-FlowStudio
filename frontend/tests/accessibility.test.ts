import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

test("intent composer gives the input and every icon action an accessible name", async () => {
  const source = await read("../src/components/panels/IntentComposer.tsx");
  assert.match(source, /<textarea[\s\S]*?aria-label="Design intent"/);
  for (const label of ["Hover mode", "Brush sculpt", "Annotation", "Drag sculpt", "Smooth sculpt", "Add primitive", "Send intent"]) {
    assert.match(source, new RegExp(`aria-label=[{\"]+[^\\n]*${label}`, "i"));
  }
});

test("floating panel resize handle is a keyboard-operable button", async () => {
  const source = await read("../src/components/ui/primitives.tsx");
  assert.match(source, /<button[\s\S]*?className={`resize-handle/);
  assert.match(source, /onKeyDown=/);
  assert.match(source, /aria-label={`Resize/);
});

test("keyboard focus is visibly styled", async () => {
  const css = await read("../src/styles.css");
  assert.match(css, /:focus-visible/);
  assert.match(css, /outline:\s*2px solid/);
});

test("solution images reserve their layout dimensions", async () => {
  const source = await read("../src/components/panels/SolutionSpaceRail.tsx");
  assert.match(source, /<img[^>]*width=\{220\}[^>]*height=\{150\}/);
});

test("collapsed studio menu is inert and its handle supports keyboard toggling", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  assert.match(source, /inert=\{!studioDrawerOpen\}/);
  assert.match(source, /onMenuToggle/);
  assert.match(source, /event\.key === "Enter" \|\| event\.key === " "/);
  assert.match(source, /onKeyDown=\{onMenuHandleKeyDown\}/);
});

test("intent input has form metadata and Enter submits when enabled", async () => {
  const source = await read("../src/components/panels/IntentComposer.tsx");
  assert.match(source, /name="design-intent"/);
  assert.match(source, /autoComplete="off"/);
  assert.match(source, /event\.key === "Enter"/);
  assert.match(source, /!event\.nativeEvent\.isComposing/);
  assert.match(source, /placeholder="Make this snowman cuter…"/);
});
