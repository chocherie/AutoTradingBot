import { NextResponse } from "next/server";
import { getPositions } from "@/lib/data";

export async function GET(req: Request) {
  try {
    const { searchParams } = new URL(req.url);
    const status = searchParams.get("status") || "OPEN";
    if (status !== "OPEN" && status !== "CLOSED") {
      return NextResponse.json({ error: "status must be OPEN or CLOSED" }, { status: 400 });
    }
    return NextResponse.json({ positions: await getPositions(status) });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
