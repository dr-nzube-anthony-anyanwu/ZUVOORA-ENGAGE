import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZUVOORA Engage",
  description: "Clinic administration workspace for ZUVOORA Engage.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Browser extensions (e.g. Grammarly, ColorZilla) add attributes to <body> before React
  // hydrates. suppressHydrationWarning applies to this element's own attributes only; real
  // mismatches in the page content are still reported.
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
