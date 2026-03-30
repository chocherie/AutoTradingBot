import { NextResponse } from "next/server";
import { getNavHistory } from "@/lib/data";

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const days = Math.min(2000, Math.max(1, parseInt(searchParams.get("days") || "365", 10)));
    return NextResponse.json({ series: await getNavHistory(days) });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
