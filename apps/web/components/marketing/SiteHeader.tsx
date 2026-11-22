import Link from "next/link";
import { IconMenu } from "./Icons";
import { Wordmark } from "./Wordmark";

const LINKS = [
  { href: "/#product", label: "Product" },
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#plans", label: "Plans" },
  { href: "/#questions", label: "Questions" },
];

/** Public site header. The mobile menu is a native <details> element: keyboard and screen-reader
 *  accessible without JavaScript. */
export function SiteHeader() {
  return (
    <header className="mk-header">
      <div className="mk-container mk-header-inner">
        <Link href="/" className="mk-logo-link">
          <Wordmark alt="ZUVOORA Engage home" priority />
        </Link>
        <nav aria-label="Main" className="mk-nav">
          <ul>
            {LINKS.map((l) => <li key={l.href}><Link href={l.href}>{l.label}</Link></li>)}
          </ul>
        </nav>
        <div className="mk-header-actions">
          <Link href="/login" className="mk-link-quiet">Sign in</Link>
          <Link href="/request-demo" className="mk-btn mk-btn-primary">Request a demo</Link>
        </div>
        <details className="mk-mobile-menu">
          <summary aria-label="Menu"><IconMenu /></summary>
          <nav aria-label="Mobile">
            <ul>
              {LINKS.map((l) => <li key={l.href}><Link href={l.href}>{l.label}</Link></li>)}
              <li><Link href="/login">Sign in</Link></li>
              <li><Link href="/request-demo" className="mk-btn mk-btn-primary">Request a demo</Link></li>
            </ul>
          </nav>
        </details>
      </div>
    </header>
  );
}
