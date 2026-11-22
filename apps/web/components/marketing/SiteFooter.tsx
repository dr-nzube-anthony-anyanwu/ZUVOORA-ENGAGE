import Link from "next/link";
import { Wordmark } from "./Wordmark";

/** Public site footer. Links only to pages that exist (no legal pages until they are reviewed). */
export function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="mk-footer">
      <div className="mk-container mk-footer-grid">
        <div className="mk-footer-brand">
          <Wordmark size="lg" withTagline />
          <p>The AI-powered digital front desk for eye care.</p>
          <p className="mk-footer-tag">Every patient enquiry deserves a response.</p>
        </div>
        <nav aria-label="Product" className="mk-footer-col">
          <h2>Product</h2>
          <ul>
            <li><Link href="/#product">Features</Link></li>
            <li><Link href="/#how-it-works">How it works</Link></li>
            <li><Link href="/#plans">Plans</Link></li>
            <li><Link href="/#roadmap">Roadmap</Link></li>
          </ul>
        </nav>
        <nav aria-label="Get started" className="mk-footer-col">
          <h2>Get started</h2>
          <ul>
            <li><Link href="/request-demo">Request a demo</Link></li>
            <li><Link href="/#pilot">Pilot programme</Link></li>
            <li><Link href="/login">Clinic sign in</Link></li>
          </ul>
        </nav>
        <nav aria-label="Company" className="mk-footer-col">
          <h2>Company</h2>
          <ul>
            <li><Link href="/#questions">Questions</Link></li>
            <li><Link href="/accessibility">Accessibility</Link></li>
          </ul>
        </nav>
      </div>
      <div className="mk-container mk-footer-legal">
        <p>© {year} ZubeVision Technologies Ltd. ZUVOORA and ZUVOORA Engage are products of ZubeVision Technologies Ltd.</p>
        <p>ZUVOORA Engage provides administrative information and appointment support. It does not provide medical advice or diagnosis.</p>
      </div>
    </footer>
  );
}
