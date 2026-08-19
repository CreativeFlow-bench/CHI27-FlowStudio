import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { refreshAccountSchedules } from "../src/auth.js";

const here = dirname(fileURLToPath(import.meta.url));
const accountsPath = resolve(here, "../data/accounts.json");
const existing = JSON.parse(await readFile(accountsPath, "utf8"));
const refreshed = refreshAccountSchedules(existing);

await writeFile(accountsPath, `${JSON.stringify(refreshed, null, 2)}\n`, { mode: 0o600 });
console.log(`Refreshed schedules for ${refreshed.filter((account) => account.role === "participant").length} participants; credentials unchanged.`);
