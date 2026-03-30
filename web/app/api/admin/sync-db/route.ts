import { put } from "@vercel/blob";
import { NextResponse } from "next/server";
import { DASHBOARD_BLOB_PATHNAME } from "@/lib/dashboard-blob";

export const runtime = "nodejs";
export const maxDuration = 60;

/** Browser / health check: confirms this route is deployed (use POST for uploads). */
export async function GET() {
  return NextResponse.json({
    ok: true,
    route: "/api/admin/sync-db",
    usage:
      "POST raw SQLite bytes with Authorization: Bearer <DB_UPLOAD_SECRET>",
  });
}

/**
 * POST raw SQLite bytes (application/octet-stream).
 * Auth: Authorization: Bearer <DB_UPLOAD_SECRET>
 * Called by the Python bot after each daily cycle.
 */
export async function POST(req: Request) {
  const secret = process.env.DB_UPLOAD_SECRET;
  if (!secret) {
    return NextResponse.json(
      { error: "DB_UPLOAD_SECRET not configured on Vercel" },
      { status: 503 },
    );
  }
  const auth = req.headers.get("authorization") || "";
  if (auth !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const token = process.env.BLOB_READ_WRITE_TOKEN;
  if (!token) {
    return NextResponse.json(
      { error: "BLOB_READ_WRITE_TOKEN not configured" },
      { status: 503 },
    );
  }
  const buf = Buffer.from(await req.arrayBuffer());
  if (buf.length < 512) {
    return NextResponse.json({ error: "Body too small for a SQLite file" }, { status: 400 });
  }
  await put(DASHBOARD_BLOB_PATHNAME, buf, {
    access: "public",
    addRandomSuffix: false,
    token,
    contentType: "application/x-sqlite3",
  });
  return NextResponse.json({ ok: true, bytes: buf.length });
}
