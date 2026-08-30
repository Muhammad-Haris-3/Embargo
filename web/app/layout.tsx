import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Embargo — the results nobody can read yet",
  description:
    "Measuring the gap between a clinical trial result existing and being readable, and estimating how many are sitting in that gap.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site">
          <div className="inner">
            <Link href="/" className="brand">
              Embargo
            </Link>
            <nav>
              <Link href="/cohorts">The wait</Link>
              <Link href="/register">The register</Link>
              <Link href="/coverage">Coverage</Link>
              <a
                href="https://github.com/Muhammad-Haris-3/Embargo"
                target="_blank"
                rel="noreferrer"
              >
                Source
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
