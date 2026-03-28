import { NextResponse } from "next/server";
import { getPerformanceBundle } from "@/lib/data";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(getPerformanceBundle());
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
