import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

import { buildParticipantSchedules } from "./schedules.js";

const PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";

function randomPassword() {
  const bytes = randomBytes(12);
  let password = "";
  for (const byte of bytes) password += PASSWORD_ALPHABET[byte % PASSWORD_ALPHABET.length];
  return password;
}

function hashPassword(password, salt) {
  return scryptSync(password, salt, 32).toString("hex");
}

export function buildAccounts(passwordFactory = randomPassword) {
  const credentials = [];
  const publicAccounts = buildParticipantSchedules().map((schedule) => {
    const password = passwordFactory();
    const salt = randomBytes(16).toString("hex");
    credentials.push({ username: schedule.username, password, cohort: schedule.cohort, sequence: schedule.sequence });
    return { ...schedule, role: "participant", salt, passwordHash: hashPassword(password, salt) };
  });
  return { publicAccounts, credentials };
}

export function buildAdminAccount(passwordFactory = randomPassword) {
  const password = passwordFactory();
  const salt = randomBytes(16).toString("hex");
  return {
    account: { username: "ADMIN", role: "admin", salt, passwordHash: hashPassword(password, salt) },
    credential: { username: "ADMIN", password, role: "admin" },
  };
}

export function buildReviewerAccount(passwordFactory = randomPassword) {
  const password = passwordFactory();
  const salt = randomBytes(16).toString("hex");
  return {
    account: { username: "P000", role: "reviewer", salt, passwordHash: hashPassword(password, salt) },
    credential: { username: "P000", password, role: "reviewer" },
  };
}

export function verifyPassword(password, account) {
  const expected = Buffer.from(account.passwordHash, "hex");
  const actual = Buffer.from(hashPassword(password, account.salt), "hex");
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}
