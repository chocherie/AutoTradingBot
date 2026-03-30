import fs from "fs";
import Database from "better-sqlite3";
import path from "path";
import { DASHBOARD_BLOB_PATHNAME } from "./dashboard-blob";

let _db: Database.Database | null = null;
/** `uploadedAt` from Blob (ms), or 0 for local file */
let _dbSourceTime = 0;

/** Resolved path for error messages and local dev. */
export function resolveDbPath(): string {
  return (
    process.env.DATABASE_PATH ||
    path.resolve(process.cwd(), "..", "storage", "trading_bot.db")
  );
}

function closeDb(): void {
  if (_db) {
    try {
      _db.close();
    } catch {
      /* ignore */
    }
    _db = null;
    _dbSourceTime = 0;
  }
}

async function openFromBlob(): Promise<Database.Database> {
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!token) {
    throw new Error("BLOB_READ_WRITE_TOKEN is not set");
  }
  const { list } = await import("@vercel/blob");
  const { blobs } = await list({
    prefix: `${DASHBOARD_BLOB_PATHNAME.split("/")[0]}/`,
    token,
  });
  const match = blobs
    .filter((b) => b.pathname === DASHBOARD_BLOB_PATHNAME)
    .sort(
      (a, b) =>
        new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime(),
    )[0];
  if (!match) {
    throw new Error(
      `No blob at ${DASHBOARD_BLOB_PATHNAME}. Run the Python bot with DASHBOARD_DB_SYNC_URL configured, or wait for the first upload.`,
    );
  }
  const uploadedMs = new Date(match.uploadedAt).getTime();
  if (_db && _dbSourceTime >= uploadedMs) {
    return _db;
  }
  closeDb();
  const res = await fetch(match.downloadUrl);
  if (!res.ok) {
    throw new Error(`Blob download failed: ${res.status}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  const tmp = path.join("/tmp", "trading_bot_vercel.db");
  fs.writeFileSync(tmp, buf);
  _db = new Database(tmp, { readonly: true, fileMustExist: true });
  _dbSourceTime = uploadedMs;
  return _db;
}

function openLocalFile(dbPath: string): Database.Database {
  if (!fs.existsSync(dbPath)) {
    throw new Error(
      `SQLite database not found at ${dbPath}. Run the Python bot locally, set DATABASE_PATH, or configure Vercel Blob sync.`,
    );
  }
  closeDb();
  _db = new Database(dbPath, { readonly: true, fileMustExist: true });
  _dbSourceTime = 0;
  return _db;
}

/**
 * Open read-only DB: local file if DATABASE_PATH or default path exists;
 * otherwise latest SQLite from Vercel Blob when BLOB_READ_WRITE_TOKEN is set.
 */
export async function getDbAsync(): Promise<Database.Database> {
  const explicit = process.env.DATABASE_PATH;
  const localPath = explicit || resolveDbPath();
  if (explicit && fs.existsSync(explicit)) {
    if (_db && _dbSourceTime === 0) return _db;
    return openLocalFile(explicit);
  }
  if (!explicit && fs.existsSync(localPath)) {
    if (_db && _dbSourceTime === 0) return _db;
    return openLocalFile(localPath);
  }
  if (process.env.BLOB_READ_WRITE_TOKEN) {
    return openFromBlob();
  }
  throw new Error(
    `No database: missing file ${localPath} and BLOB_READ_WRITE_TOKEN is not set.`,
  );
}
