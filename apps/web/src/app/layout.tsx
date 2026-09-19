import type { Metadata } from "next";
import { Fraunces, Source_Sans_3 } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const display = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const body = Source_Sans_3({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Make Politics Traceable Again",
  description:
    "Evidence-based records of elected representatives in India. Every claim links to a source. No scores or rankings.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <header className="site-header">
          <div className="shell header-inner">
            <Link href="/" className="brand">
              Make Politics Traceable Again
            </Link>
            <nav aria-label="Primary">
              <Link href="/methodology">Methodology</Link>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="site-footer">
          <div className="shell">
            <p>
              Politically neutral. No scores, rankings, or endorsements. Apache-2.0.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
