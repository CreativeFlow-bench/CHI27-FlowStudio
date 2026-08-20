import { readdir, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export async function readStateSource() {
  const dir = join(dirname(fileURLToPath(import.meta.url)), "../src/state");
  const files = (await readdir(dir)).filter((name) => name.endsWith(".ts")).sort();
  const chunks = await Promise.all(files.map((name) => readFile(join(dir, name), "utf8")));
  return chunks.join("\n");
}
