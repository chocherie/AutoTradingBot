import { NextResponse } from "next/server";
import { getPositionJournal } from "@/lib/data";

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
    const limit = Math.min(100, Math.max(1, parseInt(searchParams.get("limit") || "20", 10)));
    const ticker = searchParams.get("ticker") || undefined;
    return NextResponse.json(await getPositionJournal(page, limit, ticker));
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
