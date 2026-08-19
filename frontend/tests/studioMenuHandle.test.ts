/**
 * StudioMenu handle button: click/drag toggle contract.
 *
 * Interaction rules:
 * 1. Clicking the handle when the menu is closed → opens it.
 * 2. Clicking the handle when the menu is open  → closes it.
 * 3. A real drag (pointer move > threshold) must NOT toggle on release.
 * 4. The button has onClick that calls onMenuToggle.
 * 5. The button uses aria-expanded to reflect drawer state.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path: string) => readFile(new URL(path, import.meta.url), "utf8");

// Extract the handle button markup by finding <button whose aria-label contains
// studioDrawerOpen, then reading up to the closing > of the opening tag.
// We scan past nested braces manually rather than using a greedy [^}]* regex.
function getHandleButtonMarkup(source: string): string {
  const triggerIdx = source.indexOf('aria-label={studioDrawerOpen');
  if (triggerIdx < 0) return "";
  const btnStart = source.lastIndexOf("<button", triggerIdx);
  if (btnStart < 0) return "";
  // Read forward, tracking brace depth to find the real '>' of <button ...>
  let i = btnStart + 7; // skip '<button'
  let braceDepth = 0;
  let inString = false;
  let stringChar = "";
  while (i < source.length) {
    const ch = source[i];
    if (!inString) {
      if (ch === "{" || ch === "(") { braceDepth++; }
      else if (ch === "}" || ch === ")") { braceDepth--; }
      else if (ch === '"' || ch === "'" || ch === "`") {
        inString = true; stringChar = ch;
      }
      else if (ch === ">" && braceDepth === 0) {
        return source.slice(btnStart, i + 1);
      }
    } else {
      if (ch === "\\") { i++; } // skip escape
      else if (ch === stringChar) { inString = false; }
    }
    i++;
  }
  return "";
}

test("handle button has aria-expanded reflecting drawer state", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  const btn = getHandleButtonMarkup(source);
  assert.ok(btn, "handle button found");
  assert.ok(btn.includes("aria-expanded={studioDrawerOpen}"), "aria-expanded present");
});

test("handle button does not have aria-hidden attribute", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  const btn = getHandleButtonMarkup(source);
  assert.ok(btn, "handle button found");
  assert.ok(!btn.includes("aria-hidden"), "button does not have aria-hidden");
});

test("handle button has onClick that calls onMenuToggle", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  const btn = getHandleButtonMarkup(source);
  assert.ok(btn, "handle button found");
  // The button markup contains onClick handler
  assert.ok(btn.includes("onClick="), "onClick attribute present");
  // And the full source has the onMenuToggle() call inside that onClick body
  const onclickBodyStart = btn.indexOf("onClick={");
  assert.ok(onclickBodyStart >= 0, "onClick found");
  const after = source.slice(source.indexOf("onClick={") + 9); // past 'onClick={'
  assert.ok(after.includes("onMenuToggle()"), "onMenuToggle() called in onClick");
});

test("handle button has onPointerDown that resets handleDragMovedRef", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  const btn = getHandleButtonMarkup(source);
  assert.ok(btn, "handle button found");
  assert.ok(btn.includes("onPointerDown="), "onPointerDown present");
  const after = source.slice(source.indexOf("onPointerDown=") + 15);
  assert.ok(after.includes("handleDragMovedRef.current = false"), "resets handleDragMovedRef in onPointerDown");
});

test("handle button has onPointerUp that suppresses click after drag", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  const btn = getHandleButtonMarkup(source);
  assert.ok(btn, "handle button found");
  assert.ok(btn.includes("onPointerUp="), "onPointerUp present");
  const after = source.slice(source.indexOf("onPointerUp=") + 12);
  assert.ok(after.includes("stopPropagation()"), "calls stopPropagation in onPointerUp");
  assert.ok(after.includes("handleDragMovedRef.current"), "checks handleDragMovedRef in onPointerUp");
});

test("handle button has title reflecting current state", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  const btn = getHandleButtonMarkup(source);
  assert.ok(btn, "handle button found");
  assert.match(btn, /title=\{studioDrawerOpen \? "Drag to resize, click to collapse" : "Open studio menu"\}/);
});

test("StudioMenu uses handleDragMovedRef to distinguish drag from click", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  assert.match(source, /const handleDragMovedRef = useRef\(false\)/);
  assert.match(source, /handleDragMovedRef\.current = true/);
  assert.match(source, /handleDragMovedRef\.current = false/);
});

test("StudioMenu imports useRef", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  assert.match(source, /import \{ useRef/);
});

test("StudioMenu can probe the 3D worker", async () => {
  const source = await read("../src/components/menu/StudioMenu.tsx");
  assert.match(source, /测3D/);
  assert.match(source, /\/api\/v1\/remote-worker\/health/);
  assert.match(source, /hy3d_script_exists/);
});

test("main.tsx wires menuDragRef to StudioMenu", async () => {
  const main = await read("../src/main.tsx");
  assert.match(main, /menuDragRef=\{menuDragRef\}/);
});
