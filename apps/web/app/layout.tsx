import type { Metadata } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

// Self-hosted at build time by next/font: no requests to Google from visitors' browsers
// (the CSP allows fonts from this site only).
const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-sans" });
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"], display: "swap", variable: "--font-display", weight: ["600", "700", "800"],
});

export const metadata: Metadata = {
  title: {
    default: "ZUVOORA Engage — the AI-powered digital front desk for eye care",
    template: "%s · ZUVOORA Engage",
  },
  description:
    "ZUVOORA Engage turns an eye clinic's website into a responsive digital front desk: answers " +
    "from clinic-approved information, appointment booking and a person whenever one is needed.",
  applicationName: "ZUVOORA Engage",
  authors: [{ name: "ZubeVision Technologies Ltd." }],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Browser extensions (e.g. Grammarly, ColorZilla) add attributes to <body> before React
  // hydrates. suppressHydrationWarning applies to this element's own attributes only; real
  // mismatches in the page content are still reported.
  return (
    <html lang="en" className={`${inter.variable} ${jakarta.variable}`}>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
