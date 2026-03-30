import { NextResponse } from "next/server";
import { getAnalysis } from "@/lib/data";

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10));
    const limit = Math.min(100, Math.max(1, parseInt(searchParams.get("limit") || "20", 10)));
    return NextResponse.json(await getAnalysis(page, limit));
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
