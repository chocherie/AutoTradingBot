import type { Metadata } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const dm = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
});
const jet = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "AutoTradingBot",
  description: "Paper portfolio dashboard",
};

const links = [
  ["/", "Dashboard"],
  ["/positions", "Positions"],
  ["/trades", "Trades"],
  ["/performance", "Performance"],
  ["/analysis", "Analysis"],
] as const;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${dm.variable} ${jet.variable}`}>
      <body className="font-sans">
        <header className="border-b border-[var(--border)] bg-[var(--surface)]/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center gap-6">
            <Link href="/" className="font-semibold text-lg tracking-tight">
              AutoTrading<span className="text-tape-amber">Bot</span>
            </Link>
            <nav className="flex flex-wrap gap-5">
              {links.map(([href, label]) => (
                <Link key={href} href={href} className="nav-link">
                  {label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
