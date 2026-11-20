import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ZUVOORA Engage",
  description: "Clinic administration workspace for ZUVOORA Engage.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
