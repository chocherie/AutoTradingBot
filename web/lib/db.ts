import Database from "better-sqlite3";
import path from "path";

let _db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (_db) return _db;
  const dbPath =
    process.env.DATABASE_PATH ||
    path.resolve(process.cwd(), "..", "storage", "trading_bot.db");
  _db = new Database(dbPath, { readonly: true, fileMustExist: false });
  return _db;
}
