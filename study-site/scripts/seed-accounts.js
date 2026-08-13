import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { buildAccounts, buildAdminAccount, buildReviewerAccount } from "../src/auth.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const privateDir = resolve(root, "private");
const dataDir = resolve(root, "data");
const { publicAccounts, credentials } = buildAccounts();
const { account: adminAccount, credential: adminCredential } = buildAdminAccount();
const { account: reviewerAccount, credential: reviewerCredential } = buildReviewerAccount();

await mkdir(privateDir, { recursive: true });
await mkdir(dataDir, { recursive: true });
await writeFile(resolve(dataDir, "accounts.json"), `${JSON.stringify([...publicAccounts, adminAccount, reviewerAccount], null, 2)}\n`, { mode: 0o600 });

const csv = [
  "username,password,cohort,sequence",
  ...credentials.map((row) => [row.username, row.password, row.cohort, row.sequence].join(",")),
].join("\n");
await writeFile(resolve(privateDir, "participant-credentials.csv"), `${csv}\n`, { mode: 0o600 });
await writeFile(
  resolve(privateDir, "admin-credential.txt"),
  `username=${adminCredential.username}\npassword=${adminCredential.password}\n`,
  { mode: 0o600 },
);
await writeFile(
  resolve(privateDir, "reviewer-credential.txt"),
  `username=${reviewerCredential.username}\npassword=${reviewerCredential.password}\n`,
  { mode: 0o600 },
);
console.log(`Generated ${credentials.length} accounts.`);
console.log(resolve(privateDir, "participant-credentials.csv"));
console.log(resolve(privateDir, "admin-credential.txt"));
console.log(resolve(privateDir, "reviewer-credential.txt"));
