import { DemoRequestForm } from "@/components/marketing/DemoRequestForm";
import { IconCheck } from "@/components/marketing/Icons";

export const metadata = { title: "Request a demo" };

export default async function RequestDemoPage({ searchParams }: {
  searchParams: Promise<{ interest?: string }>;
}) {
  const { interest } = await searchParams;
  return (
    <div className="mk-page mk-section-mist">
      <div className="mk-container mk-request">
        <div className="mk-request-intro">
          <p className="mk-eyebrow">Request a demo</p>
          <h1>Let&apos;s make your clinic easier to reach.</h1>
          <p className="mk-lead">
            Tell us a little about your clinic. We&apos;ll show you how Engage fits your existing website
            and the way your team works.
          </p>
          <ul className="mk-checks">
            <li><IconCheck /> A walkthrough with your own clinic&apos;s questions in mind</li>
            <li><IconCheck /> Plans and pricing for your clinic</li>
            <li><IconCheck /> Information about the pilot programme</li>
          </ul>
          <p className="mk-fineprint">Accounts are set up with you during onboarding — there is no self sign-up.</p>
        </div>
        <div className="mk-request-card">
          <DemoRequestForm interest={interest} />
        </div>
      </div>
    </div>
  );
}
