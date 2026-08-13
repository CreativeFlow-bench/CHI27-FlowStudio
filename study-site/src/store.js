import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

async function readJson(path, fallback) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return fallback;
    throw error;
  }
}

async function sqlite(databasePath, sql) {
  const { stdout } = await execFileAsync("sqlite3", ["-batch", databasePath, sql], { maxBuffer: 8 * 1024 * 1024 });
  return stdout;
}

function sqlText(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

export async function readAccounts(path) {
  return readJson(path, []);
}

export async function initializeDatabase(databasePath) {
  await sqlite(databasePath, `
    PRAGMA journal_mode=WAL;
    PRAGMA synchronous=FULL;
    PRAGMA busy_timeout=10000;
    CREATE TABLE IF NOT EXISTS responses (
      username TEXT PRIMARY KEY,
      record_json TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
  `);
}

export async function readRecords(databasePath) {
  const output = await sqlite(databasePath, `
    PRAGMA busy_timeout=10000;
    SELECT COALESCE(json_group_object(username, json(record_json)), '{}') FROM responses;
  `);
  return JSON.parse(output.trim().split("\n").at(-1) || "{}");
}

export async function writeRecord(databasePath, username, record) {
  const updatedAt = record.updatedAt || new Date().toISOString();
  await sqlite(databasePath, `
    PRAGMA busy_timeout=10000;
    BEGIN IMMEDIATE;
    INSERT OR REPLACE INTO responses (username, record_json, updated_at)
    VALUES (${sqlText(username)}, ${sqlText(JSON.stringify(record))}, ${sqlText(updatedAt)});
    COMMIT;
  `);
}
