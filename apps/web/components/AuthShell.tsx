import Link from "next/link";
import type { ReactNode } from "react";
import { Wordmark } from "@/components/marketing/Wordmark";

/**
 * Branded layout for sign-in, two-factor and password pages. Presentation only: each page keeps
 * its own authentication logic unchanged.
 */
export function AuthShell({
  title, intro, children, asideTitle, asideText,
}: {
  title: string; intro?: string; children: ReactNode; asideTitle: string; asideText: string;
}) {
  return (
    <div className="auth">
      <aside className="auth-aside">
        <Link href="/" className="auth-home"><Wordmark size="lg" withTagline alt="ZUVOORA Engage home" priority /></Link>
        <div className="auth-aside-copy">
          <p className="auth-aside-title">{asideTitle}</p>
          <p>{asideText}</p>
        </div>
        <p className="auth-aside-foot">Every patient enquiry deserves a response.</p>
      </aside>
      <main className="auth-main">
        <div className="auth-card">
          <h1>{title}</h1>
          {intro && <p className="auth-intro">{intro}</p>}
          {children}
        </div>
        <p className="auth-legal">© ZubeVision Technologies Ltd. · <Link href="/accessibility">Accessibility</Link></p>
      </main>
    </div>
  );
}
