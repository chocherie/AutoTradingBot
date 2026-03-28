import fs from "fs";
import Database from "better-sqlite3";
import path from "path";

let _db: Database.Database | null = null;

/** Resolved path for error messages and deploy docs. */
export function resolveDbPath(): string {
  return (
    process.env.DATABASE_PATH ||
    path.resolve(process.cwd(), "..", "storage", "trading_bot.db")
  );
}

/**
 * Open read-only SQLite. Fails if the file is missing (never creates an empty DB —
 * that caused "no such table" on Vercel when storage/ was absent).
 */
export function getDb(): Database.Database {
  if (_db) return _db;
  const dbPath = resolveDbPath();
  if (!fs.existsSync(dbPath)) {
    throw new Error(
      `SQLite database not found at ${dbPath}. ` +
        `Run the Python bot locally to create storage/trading_bot.db, or set DATABASE_PATH to a deployed file.`,
    );
  }
  const db = new Database(dbPath, { readonly: true, fileMustExist: true });
  _db = db;
  return db;
}
