export type CanvasFactory = () => HTMLCanvasElement;

/**
 * Encode a viewport identity image on a pure-white canvas.
 *
 * The Three renderer is transparent, so the compositing color becomes part of
 * the image-edit model's identity condition. Keeping this white prevents the
 * model from inheriting the studio's dark UI backdrop into every candidate.
 *
 * After draw, non-white subject bounds are cropped with a small margin so the
 * identity image (and later Qwen outputs) are not drowned in empty studio space.
 */
export function captureCanvasJpeg(
  source: HTMLCanvasElement,
  width = 640,
  quality = 0.7,
  createCanvas: CanvasFactory = () => document.createElement("canvas"),
): string | null {
  const scale = Math.max(0.25, Math.min(1, width / Math.max(source.width, 1)));
  const output = createCanvas();
  output.width = Math.max(1, Math.round(source.width * scale));
  output.height = Math.max(1, Math.round(source.height * scale));
  const context = output.getContext("2d");
  if (!context) return null;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, output.width, output.height);
  context.drawImage(source, 0, 0, output.width, output.height);
  const pixels = context.getImageData(0, 0, output.width, output.height).data;
  let min = 255;
  let max = 0;
  for (let index = 0; index < pixels.length; index += 64) {
    const luminance = (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3;
    min = Math.min(min, luminance);
    max = Math.max(max, luminance);
  }
  if (max - min < 8) return null;
  const cropped = cropSubjectToFill(output, createCanvas, 0.08);
  return (cropped ?? output).toDataURL("image/jpeg", quality);
}

/** Crop near-white margins and re-letterbox the subject to fill most of the frame. */
export function cropSubjectToFill(
  source: HTMLCanvasElement,
  createCanvas: CanvasFactory = () => document.createElement("canvas"),
  marginRatio = 0.08,
): HTMLCanvasElement | null {
  const context = source.getContext("2d");
  if (!context || source.width < 2 || source.height < 2) return null;
  const { data, width, height } = context.getImageData(0, 0, source.width, source.height);
  const isWhite = (index: number) => {
    const r = data[index];
    const g = data[index + 1];
    const b = data[index + 2];
    return r >= 245 && g >= 245 && b >= 245 && Math.max(r, g, b) - Math.min(r, g, b) <= 10;
  };
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      if (isWhite(index)) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  if (maxX < minX || maxY < minY) return null;
  const subjectW = maxX - minX + 1;
  const subjectH = maxY - minY + 1;
  const coverage = (subjectW * subjectH) / (width * height);
  // Already filling the frame — keep as-is.
  if (coverage >= 0.42) return null;

  const padX = Math.max(2, Math.round(subjectW * marginRatio));
  const padY = Math.max(2, Math.round(subjectH * marginRatio));
  const cropX = Math.max(0, minX - padX);
  const cropY = Math.max(0, minY - padY);
  const cropW = Math.min(width - cropX, subjectW + padX * 2);
  const cropH = Math.min(height - cropY, subjectH + padY * 2);

  const framed = createCanvas();
  framed.width = width;
  framed.height = height;
  const framedCtx = framed.getContext("2d");
  if (!framedCtx) return null;
  framedCtx.fillStyle = "#ffffff";
  framedCtx.fillRect(0, 0, width, height);
  const fit = Math.min(width / cropW, height / cropH) * (1 - marginRatio * 2);
  const drawW = Math.max(1, Math.round(cropW * fit));
  const drawH = Math.max(1, Math.round(cropH * fit));
  framedCtx.drawImage(
    source,
    cropX,
    cropY,
    cropW,
    cropH,
    Math.round((width - drawW) / 2),
    Math.round((height - drawH) / 2),
    drawW,
    drawH,
  );
  return framed;
}
