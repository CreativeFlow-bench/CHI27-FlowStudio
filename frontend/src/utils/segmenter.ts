/**
 * MobileSAM (ONNX, WebAssembly) browser segmenter (P3).
 *
 * Loads the MobileSAM encoder/decoder ONNX exports, encodes the viewport
 * screenshot once, then decodes point/box prompts on demand (hover, brush
 * scribble). Fallback: the caller keeps the 3D Raycaster path and treats the
 * segmenter as best-effort.
 */
import * as ort from "onnxruntime-web";

// Model URLs are overridable at build time (VITE_SAM_ENCODER_URL /
// VITE_SAM_DECODER_URL). Leave them unset to skip browser MobileSAM and
// fall back to raycaster / backend viewport segmentation.
const ENCODER_URL = String(import.meta.env.VITE_SAM_ENCODER_URL || "");
const DECODER_URL = String(import.meta.env.VITE_SAM_DECODER_URL || "");

const IMAGE_SIZE = 1024;
const EMBEDDING_SIZE = 256;

type SegmenterState = {
  encoder: ort.InferenceSession;
  decoder: ort.InferenceSession;
  imageEmbedding: ort.Tensor;
  originalWidth: number;
  originalHeight: number;
  scaleX: number;
  scaleY: number;
};

let statePromise: Promise<SegmenterState> | null = null;

async function loadImageData(dataUrl: string): Promise<{
  width: number;
  height: number;
  data: Float32Array;
}> {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("segmenter image decode failed"));
    img.src = dataUrl;
  });
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  const canvas = document.createElement("canvas");
  canvas.width = IMAGE_SIZE;
  canvas.height = IMAGE_SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("segmenter canvas unavailable");
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, IMAGE_SIZE, IMAGE_SIZE);
  const scale = Math.min(IMAGE_SIZE / width, IMAGE_SIZE / height);
  const drawWidth = Math.round(width * scale);
  const drawHeight = Math.round(height * scale);
  const offsetX = Math.round((IMAGE_SIZE - drawWidth) / 2);
  const offsetY = Math.round((IMAGE_SIZE - drawHeight) / 2);
  ctx.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);
  const raw = ctx.getImageData(0, 0, IMAGE_SIZE, IMAGE_SIZE).data;
  const data = new Float32Array(IMAGE_SIZE * IMAGE_SIZE * 3);
  for (let i = 0; i < IMAGE_SIZE * IMAGE_SIZE; i += 1) {
    data[i * 3] = (raw[i * 4] / 255 - 0.485) / 0.229;
    data[i * 3 + 1] = (raw[i * 4 + 1] / 255 - 0.456) / 0.224;
    data[i * 3 + 2] = (raw[i * 4 + 2] / 255 - 0.406) / 0.225;
  }
  return { width, height, data };
}

async function loadSession(url: string): Promise<ort.InferenceSession> {
  const timeout = new Promise<never>((_, reject) => {
    window.setTimeout(() => reject(new Error(`segmenter model load timeout: ${url}`)), 30_000);
  });
  return Promise.race([
    ort.InferenceSession.create(url, {
      executionProviders: ["wasm"],
      graphOptimizationLevel: "all",
    }),
    timeout,
  ]);
}

export async function ensureSegmenter(dataUrl: string): Promise<SegmenterState> {
  if (!ENCODER_URL || !DECODER_URL) {
    throw new Error("segmenter models not configured");
  }
  if (statePromise) return statePromise;
  statePromise = (async () => {
    const [encoder, decoder, image] = await Promise.all([
      loadSession(ENCODER_URL),
      loadSession(DECODER_URL),
      loadImageData(dataUrl),
    ]);
    const pixelValues = new ort.Tensor("float32", image.data, [1, 3, IMAGE_SIZE, IMAGE_SIZE]);
    const encoded = await encoder.run({ pixel_values: pixelValues });
    const imageEmbedding = (encoded.image_embeddings ?? encoded.image_embedding ?? Object.values(encoded)[0]) as ort.Tensor;
    const scaleX = IMAGE_SIZE / image.width;
    const scaleY = IMAGE_SIZE / image.height;
    return {
      encoder,
      decoder,
      imageEmbedding,
      originalWidth: image.width,
      originalHeight: image.height,
      scaleX,
      scaleY,
    };
  })();
  return statePromise;
}

export function resetSegmenter() {
  statePromise = null;
}

function pointToPrompt(state: SegmenterState, point: { x: number; y: number }) {
  // Normalized viewport point -> letterboxed 1024x1024 coordinates.
  const canvasScale = Math.min(1 / state.scaleX, 1 / state.scaleY);
  const drawWidth = state.originalWidth * canvasScale;
  const drawHeight = state.originalHeight * canvasScale;
  const offsetX = (IMAGE_SIZE - drawWidth) / 2;
  const offsetY = (IMAGE_SIZE - drawHeight) / 2;
  return {
    x: offsetX + point.x * state.originalWidth * canvasScale,
    y: offsetY + point.y * state.originalHeight * canvasScale,
  };
}

function maskToDataUrl(state: SegmenterState, mask: Float32Array): string {
  const width = state.originalWidth;
  const height = state.originalHeight;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  const imageData = ctx.createImageData(width, height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const sx = Math.round((x / width) * IMAGE_SIZE);
      const sy = Math.round((y / height) * IMAGE_SIZE);
      const value = mask[sy * IMAGE_SIZE + sx];
      const alpha = Math.max(0, Math.min(255, Math.round(value * 255)));
      const idx = (y * width + x) * 4;
      imageData.data[idx] = 74;
      imageData.data[idx + 1] = 154;
      imageData.data[idx + 2] = 245;
      imageData.data[idx + 3] = alpha;
    }
  }
  ctx.putImageData(imageData, 0, 0);
  return canvas.toDataURL("image/png");
}

export async function segmentPoints(
  dataUrl: string,
  points: Array<{ x: number; y: number; label?: 0 | 1 }>,
): Promise<{ maskDataUrl: string; coverage: number } | null> {
  try {
    const state = await ensureSegmenter(dataUrl);
    const prompts = points.slice(0, 8);
    const coords = new Float32Array(prompts.length * 2);
    const labels = new Float32Array(prompts.length);
    prompts.forEach((point, index) => {
      const prompt = pointToPrompt(state, point);
      coords[index * 2] = prompt.x;
      coords[index * 2 + 1] = prompt.y;
      labels[index] = point.label ?? 1;
    });
    const maskInput = new ort.Tensor("float32", new Float32Array(1 * 1 * EMBEDDING_SIZE * EMBEDDING_SIZE), [
      1,
      1,
      EMBEDDING_SIZE,
      EMBEDDING_SIZE,
    ]);
    const hasBox = new ort.Tensor("float32", new Float32Array([0]), [1]);
    const feeds: Record<string, ort.Tensor> = {
      image_embeddings: state.imageEmbedding,
      point_coords: new ort.Tensor("float32", coords, [prompts.length, 2]),
      point_labels: new ort.Tensor("float32", labels, [prompts.length]),
      mask_input: maskInput,
      has_mask_input: new ort.Tensor("float32", new Float32Array([0]), [1]),
      orig_im_size: new ort.Tensor("float32", new Float32Array([state.originalHeight, state.originalWidth]), [2]),
      low_res_masks: new ort.Tensor("float32", new Float32Array(1 * 1 * EMBEDDING_SIZE * EMBEDDING_SIZE), [
        1,
        1,
        EMBEDDING_SIZE,
        EMBEDDING_SIZE,
      ]),
      has_box_input: hasBox,
    };
    const result = await state.decoder.run(feeds);
    const masks = (result.masks ?? result.low_res_masks ?? result.scores ?? Object.values(result)[0]) as ort.Tensor;
    const rawData = masks.data as unknown as ArrayBuffer;
    const maskArray =
      masks.data instanceof Float32Array
        ? (masks.data as Float32Array)
        : new Float32Array(rawData.byteLength > 0 ? rawData : (masks.data as unknown as ArrayBufferLike));
    if (maskArray.length < IMAGE_SIZE * IMAGE_SIZE) {
      throw new Error(`segmenter mask output too small: ${maskArray.length}`);
    }
    const maskDataUrl = maskToDataUrl(state, maskArray);
    let positive = 0;
    let total = 0;
    for (let i = 0; i < maskArray.length; i += 1) {
      if (maskArray[i] > 0.5) positive += 1;
      total += 1;
    }
    return { maskDataUrl, coverage: total ? positive / total : 0 };
  } catch (error) {
    console.warn("segmenter point prompt failed", error);
    return null;
  }
}
