import assert from "node:assert/strict";
import test from "node:test";

import { captureCanvasJpeg } from "../src/utils/canvasCapture.ts";

test("viewport identity capture composites transparency over pure white before encoding", () => {
  const operations: Array<{ name: string; args: unknown[] }> = [];
  const pixels = new Uint8ClampedArray(68);
  pixels[64] = 255;
  pixels[65] = 255;
  pixels[66] = 255;
  pixels[67] = 255;
  const context = {
    fillStyle: "",
    fillRect: (...args: unknown[]) => operations.push({ name: "fillRect", args }),
    drawImage: (...args: unknown[]) => operations.push({ name: "drawImage", args }),
    getImageData: () => ({ data: pixels }),
  };
  const output = {
    width: 0,
    height: 0,
    getContext: () => context,
    toDataURL: (type: string, quality: number) => `${type}:${quality}`,
  };
  const source = { width: 640, height: 480 };

  const result = captureCanvasJpeg(source as HTMLCanvasElement, 640, 0.8, () => output as unknown as HTMLCanvasElement);

  assert.equal(context.fillStyle, "#ffffff");
  assert.deepEqual(operations[0], { name: "fillRect", args: [0, 0, 640, 480] });
  assert.equal(operations[1]?.name, "drawImage");
  assert.equal(result, "image/jpeg:0.8");
});
