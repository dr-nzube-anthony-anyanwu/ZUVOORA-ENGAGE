import Link from "next/link";

export const metadata = { title: "Accessibility" };

/** Accessibility statement. Describes what has actually been done and tested; claims no
 *  conformance certification. */
export default function AccessibilityPage() {
  return (
    <div className="mk-page">
      <div className="mk-container mk-page-narrow">
        <p className="mk-eyebrow">Accessibility</p>
        <h1>Accessibility statement</h1>
        <p className="mk-lead">
          We want ZUVOORA Engage to be usable by everyone — the patients who visit clinic websites and
          the clinic teams who use the dashboard.
        </p>

        <h2>Our target</h2>
        <p>
          We design and test against the Web Content Accessibility Guidelines (WCAG) 2.2 at level AA.
          This is our target, not a certified conformance claim.
        </p>

        <h2>What we do</h2>
        <ul>
          <li>Semantic page structure with headings, landmarks and a &quot;skip to main content&quot; link.</li>
          <li>Everything can be used with a keyboard, with a clearly visible focus indicator.</li>
          <li>Text and interface colours chosen to meet WCAG AA contrast ratios.</li>
          <li>Form fields have visible labels; hints and errors are announced to assistive technology.</li>
          <li>Animations are minimal and switched off when your device asks for reduced motion.</li>
          <li>Pages adapt to small screens and to browser zoom.</li>
          <li>Automated accessibility checks (axe) run on our public pages as part of our test suite.</li>
        </ul>

        <h2>Known limitations</h2>
        <ul>
          <li>The plan comparison table scrolls sideways on narrow screens.</li>
          <li>The product previews on the homepage are illustrations built with a sample clinic; what they show is also described in the surrounding text.</li>
          <li>We have not yet had an independent accessibility audit.</li>
        </ul>

        <h2>Tell us about a problem</h2>
        <p>
          If something is difficult to use, please tell us through the{" "}
          <Link href="/request-demo?interest=accessibility">contact form</Link> and choose
          &quot;Accessibility feedback&quot;. We will reply and work on a fix.
        </p>

        <p className="mk-fineprint">Last reviewed: 22 November 2026.</p>
      </div>
    </div>
  );
}
