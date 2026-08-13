import { createHash, randomBytes } from "node:crypto";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { verifyPassword } from "./auth.js";
import { createInitialRecord, submitCurrentStep } from "./workflow.js";
import { initializeDatabase, readAccounts, readRecords, writeRecord } from "./store.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const publicDir = resolve(root, "public");
const accountsPath = resolve(root, "data/accounts.json");
const databasePath = resolve(root, "data/study.sqlite3");
const port = Number(process.env.PORT || 5190);
const sessions = new Map();

await initializeDatabase(databasePath);

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

function json(response, status, payload, headers = {}) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers });
  response.end(JSON.stringify(payload));
}

function sessionCookie(request, token, maxAge) {
  const secure = request.headers["x-forwarded-proto"] === "https" ? "; Secure" : "";
  return `study_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=${maxAge}${secure}`;
}

async function body(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 256_000) throw new Error("payload_too_large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

function cookies(request) {
  return Object.fromEntries((request.headers.cookie || "").split(";").filter(Boolean).map((part) => {
    const [key, ...value] = part.trim().split("=");
    return [key, decodeURIComponent(value.join("="))];
  }));
}

function sessionAccount(request, accounts) {
  const token = cookies(request).study_session;
  const username = token ? sessions.get(createHash("sha256").update(token).digest("hex")) : null;
  return accounts.find((account) => account.username === username) || null;
}

function publicAccount(account) {
  const { passwordHash, salt, ...safe } = account;
  return safe;
}

async function serveStatic(pathname, response) {
  const requested = pathname === "/" ? "/index.html" : pathname;
  const path = resolve(publicDir, `.${requested}`);
  if (!path.startsWith(publicDir)) return false;
  try {
    const info = await stat(path);
    if (!info.isFile()) return false;
    response.writeHead(200, { "content-type": mimeTypes[extname(path)] || "application/octet-stream", "cache-control": "no-cache" });
    createReadStream(path).pipe(response);
    return true;
  } catch {
    return false;
  }
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);
    const accounts = await readAccounts(accountsPath);

    if (request.method === "GET" && url.pathname === "/api/health") {
      await readRecords(databasePath);
      return json(response, 200, { ok: true });
    }

    if (request.method === "POST" && url.pathname === "/api/login") {
      const input = await body(request);
      const account = accounts.find((item) => item.username.toUpperCase() === String(input.username || "").trim().toUpperCase());
      if (!account || !verifyPassword(String(input.password || ""), account)) return json(response, 401, { error: "账号或密码不正确" });
      const token = randomBytes(32).toString("base64url");
      sessions.set(createHash("sha256").update(token).digest("hex"), account.username);
      return json(response, 200, { ok: true }, { "set-cookie": sessionCookie(request, token, 43200) });
    }

    if (request.method === "POST" && url.pathname === "/api/logout") {
      const token = cookies(request).study_session;
      if (token) sessions.delete(createHash("sha256").update(token).digest("hex"));
      return json(response, 200, { ok: true }, { "set-cookie": sessionCookie(request, "", 0) });
    }

    if (url.pathname.startsWith("/api/")) {
      const account = sessionAccount(request, accounts);
      if (!account) return json(response, 401, { error: "请先登录" });
      const records = await readRecords(databasePath);

      if (account.role === "reviewer") {
        if (request.method === "GET" && url.pathname === "/api/session") {
          return json(response, 200, { account: publicAccount(account), reviewer: true });
        }
        return json(response, 403, { error: "审阅账号只用于查看研究材料" });
      }

      if (account.role === "admin") {
        if (request.method === "GET" && url.pathname === "/api/session") {
          return json(response, 200, { account: publicAccount(account), admin: true });
        }
        if (request.method === "GET" && url.pathname === "/api/admin/participants") {
          const participants = accounts.filter((item) => item.role === "participant").map((item) => {
            const record = records[item.username] || createInitialRecord(item);
            const current = item.steps[record.currentStep];
            return {
              username: item.username,
              cohort: item.cohort,
              sequence: item.sequence,
              order: item.order,
              currentStep: record.currentStep,
              totalSteps: item.steps.length,
              currentStage: current?.kind || "complete",
              percent: Math.round((record.currentStep / (item.steps.length - 1)) * 100),
              updatedAt: record.updatedAt,
              completedAt: record.completedAt,
            };
          });
          return json(response, 200, { participants });
        }
        if (request.method === "GET" && url.pathname === "/api/admin/export") {
          return json(response, 200, { exportedAt: new Date().toISOString(), records });
        }
        return json(response, 403, { error: "管理员不能提交参与者问卷" });
      }

      const record = records[account.username] || createInitialRecord(account);

      if (request.method === "GET" && url.pathname === "/api/session") {
        return json(response, 200, { account: publicAccount(account), record });
      }

      if (request.method === "POST" && url.pathname === "/api/submit") {
        const input = await body(request);
        const next = submitCurrentStep(record, account, String(input.stepId || ""), input.answers);
        await writeRecord(databasePath, account.username, next);
        return json(response, 200, { record: next });
      }

      return json(response, 404, { error: "not_found" });
    }

    if (!(await serveStatic(url.pathname, response))) json(response, 404, { error: "not_found" });
  } catch (error) {
    const status = error.message === "step_mismatch" ? 409 : error.message === "payload_too_large" ? 413 : 400;
    json(response, status, { error: error.message || "request_failed" });
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`FlowStudio study site: http://127.0.0.1:${port}`);
});
