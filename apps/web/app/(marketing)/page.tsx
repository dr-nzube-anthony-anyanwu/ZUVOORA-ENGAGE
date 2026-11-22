import Link from "next/link";
import type { ReactNode } from "react";
import { DemoConversation } from "@/components/marketing/DemoConversation";
import {
  IconArrow, IconBook, IconBuilding, IconCalendar, IconChart, IconChat, IconCheck, IconClock,
  IconEye, IconGlasses, IconGlobe, IconHandshake, IconInbox, IconLock, IconMoon, IconSettings,
  IconShield, IconSpark, IconUsers,
} from "@/components/marketing/Icons";
import {
  AnalyticsPreview, BookingPreview, ChatPreview, InboxPreview, KnowledgePreview, TeamPreview,
} from "@/components/marketing/Previews";

export const metadata = {
  title: { absolute: "ZUVOORA Engage — the AI-powered digital front desk for eye care" },
};

/* ----- small building blocks ------------------------------------------------------------------ */
function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="mk-eyebrow">{children}</p>;
}

function SectionHead({ eyebrow, title, intro, id }: { eyebrow: string; title: string; intro?: string; id: string }) {
  return (
    <div className="mk-section-head">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h2 id={id}>{title}</h2>
      {intro && <p className="mk-lead">{intro}</p>}
    </div>
  );
}

/* ----- content (kept in sync with docs/design/HOMEPAGE_CONTENT.md) ----------------------------- */
const CHALLENGES = [
  { icon: <IconMoon />, title: "Questions after hours", text: "Visitors often look for answers in the evening or at weekends, when reception is closed." },
  { icon: <IconInbox />, title: "Enquiries without guidance", text: "A phone number or contact form doesn't give the visitor an answer at the moment they need one." },
  { icon: <IconCalendar />, title: "Booking takes extra steps", text: "Finding the right appointment and a free time can mean calls, messages and waiting." },
  { icon: <IconUsers />, title: "A busy front desk", text: "Your team is juggling calls, walk-ins, scheduling and the same everyday questions." },
];

const AUDIENCES = [
  { icon: <IconEye />, title: "Optometry practices", text: "Clear answers about eye examinations, contact lenses, opening hours and appointments." },
  { icon: <IconShield />, title: "Ophthalmology and specialist clinics", text: "Administrative guidance for visitors, with emergencies and medical questions passed to your team." },
  { icon: <IconGlasses />, title: "Optical centres", text: "Answers about services, store information and enquiries, every day of the week." },
  { icon: <IconBuilding />, title: "Eye hospitals and clinic groups", text: "Consistent information across branches, with roles for every member of the team." },
];

const VALUES = [
  { icon: <IconClock />, title: "Responsiveness", text: "Visitors get an answer outside working hours, not just a phone number." },
  { icon: <IconChat />, title: "Patient experience", text: "The right information, in plain language, without searching the whole website." },
  { icon: <IconSpark />, title: "Team efficiency", text: "Fewer repeated everyday questions for the front desk to answer." },
  { icon: <IconChart />, title: "Visibility", text: "See what visitors ask, what was answered and what needs a person." },
  { icon: <IconLock />, title: "Control", text: "Engage only uses information your clinic has reviewed and approved." },
  { icon: <IconSettings />, title: "Room to grow", text: "Start with what you need and add capabilities as your clinic grows." },
];

const QUESTIONS: { q: string; a: ReactNode }[] = [
  {
    q: "Will Engage replace our receptionists?",
    a: "No. Engage handles routine website questions and appointment requests so your team can focus on patients. Whenever a visitor needs a person — or Engage doesn't have an answer — it offers to have your team contact them, and the request appears in your inbox.",
  },
  {
    q: "Could it give patients incorrect medical advice?",
    a: "Engage is designed not to give medical advice at all. It does not diagnose, interpret symptoms or recommend treatment. Urgent symptoms get emergency guidance first, medical questions are passed to your clinicians, and answers come only from information your clinic has approved. If the answer isn't there, Engage says so instead of guessing.",
  },
  {
    q: "Do we need to rebuild our website?",
    a: "No. You verify that you own your website's domain and paste one short code snippet into your existing site. The assistant only appears on domains you have verified.",
  },
  {
    q: "Could our information be mixed with another clinic's?",
    a: "No. Each clinic's information, conversations and settings are kept separate and are only available to that clinic's own team. This separation is enforced in the database itself and is covered by automated tests.",
  },
  {
    q: "What does Engage do with the information in conversations?",
    a: "Conversations are visible only to your clinic's authorised staff. When AI is used to answer, only your published clinic information and the visitor's question are sent, through AI providers that do not keep the data or use it for training. Patients cannot upload files to the assistant.",
  },
  {
    q: "What if our team doesn't understand AI?",
    a: "You don't need to. Your team fills in familiar things — services, prices, opening hours, FAQs and documents — reviews them and publishes. We help you set up during onboarding.",
  },
  {
    q: "Who on our team can change things?",
    a: "Accounts are by invitation only, and every person has a role: owners and admins manage content and settings, receptionists work the inbox and appointments, and viewers can only look. Administrators can protect their accounts with two-factor authentication.",
  },
  {
    q: "What if we want to stop?",
    a: "Remove the snippet from your website and the assistant disappears. If your subscription ends, the assistant stops but your clinic's information is kept, so you can return without starting again.",
  },
];

type PlanRow = { feature: string; plans: [boolean | "soon", boolean | "soon", boolean | "soon", boolean | "soon"] };
const PLAN_ROWS: PlanRow[] = [
  { feature: "Website assistant with clinic-approved answers", plans: [true, true, true, true] },
  { feature: "Knowledge base, documents and photo/scan reading", plans: [true, true, true, true] },
  { feature: "Inbox and call-back requests", plans: [true, true, true, true] },
  { feature: "Live appointment booking (Cal.com, Calendly)", plans: [true, true, true, true] },
  { feature: "Basic analytics", plans: [true, true, true, true] },
  { feature: "Appointment reminders (24 h, optional 2 h)", plans: [false, true, true, true] },
  { feature: "Full analytics: trends, AI cost, unanswered topics", plans: [false, true, true, true] },
  { feature: "Multiple branches", plans: [false, true, true, true] },
  { feature: "Highest usage limits for larger clinics and groups", plans: [false, false, true, true] },
  { feature: "WhatsApp", plans: [false, "soon", "soon", "soon"] },
  { feature: "Voice assistant", plans: [false, false, "soon", "soon"] },
  { feature: "ZUVOORA ecosystem integration", plans: [false, false, false, "soon"] },
];
const PLANS = [
  { name: "Essentials", text: "The digital front desk: answers, booking and handover for a single clinic." },
  { name: "Professional", text: "Everything in Essentials, plus reminders, full analytics and multiple branches." },
  { name: "Premium", text: "Professional with higher limits for larger clinics and clinic groups." },
  { name: "Full ZUVOORA", text: "Engage as part of the wider ZUVOORA eye-care platform." },
];

function Availability({ value }: { value: boolean | "soon" }) {
  if (value === "soon") return <span className="mk-soon">Coming soon</span>;
  return value
    ? <span className="mk-yes"><IconCheck /><span className="sr-only">Included</span></span>
    : <span className="mk-no" aria-label="Not included">—</span>;
}

/* ----- page ------------------------------------------------------------------------------------ */
export default function HomePage() {
  return (
    <>
      {/* 01 · Hero */}
      <section className="mk-hero" aria-labelledby="hero-title">
        <div className="mk-container mk-hero-grid">
          <div className="mk-hero-copy">
            <Eyebrow>The AI-powered digital front desk for eye care</Eyebrow>
            <h1 id="hero-title">Your clinic is caring for patients. Who&apos;s welcoming the next one?</h1>
            <p className="mk-lead">
              Turn your eye clinic&apos;s website into a responsive digital front desk that answers
              questions, books appointments and keeps your team connected.
            </p>
            <div className="mk-cta-row">
              <Link href="/request-demo" className="mk-btn mk-btn-primary mk-btn-lg">Request a demo</Link>
              <a href="#story" className="mk-btn mk-btn-ghost mk-btn-lg">Explore Engage <IconArrow /></a>
            </div>
            <ul className="mk-hero-points">
              <li><IconCheck /> Answers only from your clinic&apos;s approved information</li>
              <li><IconCheck /> Appointments booked in your existing calendar</li>
              <li><IconCheck /> Your team, one click away</li>
            </ul>
          </div>
          <div className="mk-hero-visual">
            <ChatPreview />
          </div>
        </div>
      </section>

      {/* Story */}
      <section className="mk-story" aria-labelledby="story-title" id="story">
        <div className="mk-container mk-story-inner">
          <p className="mk-story-time" aria-hidden="true">10:47 PM</p>
          <div>
            <h2 id="story-title">Your clinic closes for the day. Your patients&apos; questions don&apos;t.</h2>
            <p>
              Someone visits your website late in the evening. They want to know whether you offer
              glaucoma screening, what an eye examination costs, and how to book. Your reception team
              has gone home; the website shows an address and a phone number.
            </p>
            <p className="mk-story-turn">
              What if your website could welcome them — answer from your approved information, offer a
              time that suits them, and pass the conversation to your team in the morning if a person
              is needed?
            </p>
          </div>
        </div>
      </section>

      {/* 02 · Challenge */}
      <section className="mk-section" aria-labelledby="challenge-title">
        <div className="mk-container">
          <SectionHead id="challenge-title" eyebrow="The challenge"
            title="A patient may be ready to reach out. Your website may not be ready to respond." />
          <ul className="mk-challenges">
            {CHALLENGES.map((c) => (
              <li key={c.title}><span className="mk-icon-tile">{c.icon}</span><h3>{c.title}</h3><p>{c.text}</p></li>
            ))}
          </ul>
        </div>
      </section>

      {/* 03 · Solution */}
      <section className="mk-section mk-section-mist" aria-labelledby="solution-title">
        <div className="mk-container mk-solution">
          <div>
            <SectionHead id="solution-title" eyebrow="The solution"
              title="Your website can do more than tell people about your clinic."
              intro="It can help them take the next step. Engage sits on your existing website and turns visits into conversations — with your team always in control." />
          </div>
          <ol className="mk-flow" aria-label="How a visit becomes a conversation">
            <li><span className="mk-flow-icon"><IconGlobe /></span><div><h3>Your existing website</h3><p>Add one snippet. No rebuild.</p></div></li>
            <li><span className="mk-flow-icon"><IconChat /></span><div><h3>Answers</h3><p>From the services, hours, prices, FAQs and documents you approved.</p></div></li>
            <li><span className="mk-flow-icon"><IconCalendar /></span><div><h3>Bookings</h3><p>Real available times from your Cal.com or Calendly calendar.</p></div></li>
            <li><span className="mk-flow-icon"><IconHandshake /></span><div><h3>Handover</h3><p>Call-back requests go straight to your team&apos;s inbox.</p></div></li>
          </ol>
        </div>
      </section>

      {/* 04 · Audience */}
      <section className="mk-section" aria-labelledby="audience-title">
        <div className="mk-container">
          <SectionHead id="audience-title" eyebrow="Who it's for" title="Built for eye care. Designed around people."
            intro="For clinic owners, practice managers and administrators who already have a website and want it to do more." />
          <ul className="mk-audience">
            {AUDIENCES.map((a) => (
              <li key={a.title}><span className="mk-icon-tile">{a.icon}</span><div><h3>{a.title}</h3><p>{a.text}</p></div></li>
            ))}
          </ul>
        </div>
      </section>

      {/* 05 · Features */}
      <section className="mk-section mk-section-mist" aria-labelledby="product-title" id="product">
        <div className="mk-container">
          <SectionHead id="product-title" eyebrow="The product" title="Everything your digital front desk needs." />
          <div className="mk-feature">
            <div className="mk-feature-copy">
              <span className="mk-icon-tile"><IconChat /></span>
              <h3>Answers grounded in your clinic&apos;s information</h3>
              <p>Visitors ask about services, prices, opening hours, locations and how to prepare for a visit. Engage answers from what your clinic has published — and says plainly when it doesn&apos;t know, instead of inventing an answer.</p>
              <ul className="mk-checks">
                <li><IconCheck /> Emergency guidance comes first for urgent symptoms</li>
                <li><IconCheck /> No diagnoses, medical advice or treatment recommendations</li>
                <li><IconCheck /> Shows only on your verified website</li>
              </ul>
            </div>
            <ChatPreview />
          </div>
          <div className="mk-feature mk-feature-flip">
            <div className="mk-feature-copy">
              <span className="mk-icon-tile"><IconBook /></span>
              <h3>Your knowledge, reviewed before it&apos;s used</h3>
              <p>Add your clinic profile, branches and opening hours, services, FAQs and documents — PDF, Word, or even a photo or scan of a price list, read by AI. Nothing reaches patients until someone on your team has reviewed and approved it.</p>
              <ul className="mk-checks">
                <li><IconCheck /> Draft, review and publish, with versions</li>
                <li><IconCheck /> AI-read text is flagged for careful checking</li>
              </ul>
            </div>
            <KnowledgePreview />
          </div>
          <div className="mk-feature">
            <div className="mk-feature-copy">
              <span className="mk-icon-tile"><IconCalendar /></span>
              <h3>A simpler path to appointments</h3>
              <p>Visitors choose an appointment type and a free time from your Cal.com or Calendly calendar without leaving the chat. A booking is confirmed only after your calendar confirms it; confirmations and reminders follow by email.</p>
              <ul className="mk-checks">
                <li><IconCheck /> You choose which appointment types can be booked</li>
                <li><IconCheck /> Your team sees bookings made through Engage and can cancel them</li>
              </ul>
            </div>
            <BookingPreview />
          </div>
          <div className="mk-feature mk-feature-flip">
            <div className="mk-feature-copy">
              <span className="mk-icon-tile"><IconHandshake /></span>
              <h3>Human support when it matters</h3>
              <p>A &quot;Contact the clinic team&quot; option is always one click away. Call-back requests land in your inbox with the conversation that led to them, so your team can follow up quickly and mark them resolved.</p>
            </div>
            <InboxPreview />
          </div>
          <div className="mk-feature">
            <div className="mk-feature-copy">
              <span className="mk-icon-tile"><IconChart /></span>
              <h3>See what your visitors need</h3>
              <p>Track conversations, bookings and call-backs, see how questions were answered, and — on higher plans — follow daily trends and the topics visitors ask about that your clinic hasn&apos;t covered yet.</p>
            </div>
            <AnalyticsPreview />
          </div>
          <div className="mk-feature mk-feature-flip">
            <div className="mk-feature-copy">
              <span className="mk-icon-tile"><IconUsers /></span>
              <h3>Your team, your rules</h3>
              <p>Invite owners, admins, receptionists and viewers, each with the access their role needs. Every important change is recorded, and administrators can use two-factor authentication.</p>
            </div>
            <TeamPreview />
          </div>
        </div>
      </section>

      {/* 06 · Value */}
      <section className="mk-section" aria-labelledby="value-title">
        <div className="mk-container">
          <SectionHead id="value-title" eyebrow="Why it matters"
            title="More than conversations. A better way to welcome patients." />
          <ul className="mk-values">
            {VALUES.map((v) => (
              <li key={v.title}><span className="mk-icon-inline">{v.icon}</span><h3>{v.title}</h3><p>{v.text}</p></li>
            ))}
          </ul>
        </div>
      </section>

      {/* 07 · Objections */}
      <section className="mk-section mk-section-navy" aria-labelledby="questions-title" id="questions">
        <div className="mk-container mk-questions">
          <div>
            <Eyebrow>Your questions</Eyebrow>
            <h2 id="questions-title">Powerful technology shouldn&apos;t mean giving up control.</h2>
            <p className="mk-lead">Straight answers about how Engage works today.</p>
          </div>
          <div className="mk-accordion">
            {QUESTIONS.map((item) => (
              <details key={item.q}>
                <summary><span>{item.q}</span></summary>
                <p>{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* 08 · How it works */}
      <section className="mk-section" aria-labelledby="how-title" id="how-it-works">
        <div className="mk-container">
          <SectionHead id="how-title" eyebrow="How it works" title="From your website to meaningful conversations in three steps." />
          <ol className="mk-steps">
            <li><span className="mk-step-no">1</span><h3>Configure</h3><p>Add your services, prices, opening hours, FAQs and documents. Review them and publish. Connect your Cal.com or Calendly calendar if you want online booking.</p></li>
            <li><span className="mk-step-no">2</span><h3>Embed</h3><p>Verify your website&apos;s domain with a DNS record and paste one snippet into your site. The assistant appears only there.</p></li>
            <li><span className="mk-step-no">3</span><h3>Engage</h3><p>Visitors get answers, book appointments and ask for a call-back. Your team follows up from the inbox and sees what&apos;s working.</p></li>
          </ol>
        </div>
      </section>

      {/* 09 · Demo */}
      <section className="mk-section mk-section-mist" aria-labelledby="demo-title" id="demo">
        <div className="mk-container">
          <SectionHead id="demo-title" eyebrow="See it in action" title="See the experience your patients could have."
            intro="A scripted demonstration with a sample clinic. Pick a question to see how Engage responds." />
          <DemoConversation />
        </div>
      </section>

      {/* 10 · Plans */}
      <section className="mk-section" aria-labelledby="plans-title" id="plans">
        <div className="mk-container">
          <SectionHead id="plans-title" eyebrow="Plans" title="Start with what your clinic needs. Grow when you're ready."
            intro="Every plan includes the website assistant, approved knowledge, the inbox and live booking. Pricing is shared during your demo." />
          <ul className="mk-plan-cards">
            {PLANS.map((p) => <li key={p.name}><h3>{p.name}</h3><p>{p.text}</p></li>)}
          </ul>
          <div className="mk-table-wrap" tabIndex={0} role="region" aria-label="Plan comparison (scrolls sideways on small screens)">
            <table className="mk-plan-table">
              <caption className="sr-only">What each plan includes</caption>
              <thead>
                <tr><th scope="col">Feature</th>{PLANS.map((p) => <th scope="col" key={p.name}>{p.name}</th>)}</tr>
              </thead>
              <tbody>
                {PLAN_ROWS.map((row) => (
                  <tr key={row.feature}>
                    <th scope="row">{row.feature}</th>
                    {row.plans.map((v, i) => <td key={i}><Availability value={v} /></td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mk-center"><Link href="/request-demo" className="mk-btn mk-btn-primary">Request a demo for pricing</Link></div>
        </div>
      </section>

      {/* 11 · Roadmap */}
      <section className="mk-section mk-section-mist" aria-labelledby="roadmap-title" id="roadmap">
        <div className="mk-container mk-roadmap">
          <SectionHead id="roadmap-title" eyebrow="Roadmap" title="What's coming next."
            intro="These are in development and not yet available. We'll only list them as features once they work." />
          <ul>
            <li><span className="mk-soon">Coming soon</span><h3>WhatsApp</h3><p>Continue conversations on WhatsApp.</p></li>
            <li><span className="mk-soon">Coming soon</span><h3>Voice assistant</h3><p>Help callers with everyday questions by phone.</p></li>
            <li><span className="mk-soon">Coming soon</span><h3>ZUVOORA ecosystem</h3><p>Engage connected to the wider ZUVOORA eye-care platform.</p></li>
          </ul>
        </div>
      </section>

      {/* 12 · Trust */}
      <section className="mk-section" aria-labelledby="trust-title">
        <div className="mk-container mk-trust">
          <SectionHead id="trust-title" eyebrow="Responsibility" title="Designed with healthcare responsibilities in mind." />
          <ul>
            <li><IconShield /><div><h3>Each clinic&apos;s data kept apart</h3><p>Separation between clinics is enforced in the database and tested automatically.</p></div></li>
            <li><IconUsers /><div><h3>People stay in charge</h3><p>Staff approve every piece of information before it is used, and can take over any conversation.</p></div></li>
            <li><IconLock /><div><h3>Careful with AI</h3><p>AI receives only approved clinic information and the visitor&apos;s question, through providers that don&apos;t keep or train on the data.</p></div></li>
            <li><IconCheck /><div><h3>Accountable</h3><p>Invitation-only accounts, roles, two-factor authentication for administrators, and a record of important changes.</p></div></li>
          </ul>
        </div>
      </section>

      {/* 13 · Pilot */}
      <section className="mk-section mk-section-mist" aria-labelledby="pilot-title" id="pilot">
        <div className="mk-container mk-pilot">
          <div>
            <Eyebrow>Pilot programme</Eyebrow>
            <h2 id="pilot-title">Built with real clinics in mind.</h2>
            <p className="mk-lead">
              We are inviting a small number of eye clinics to pilot ZUVOORA Engage with us: guided
              set-up, close support, and a direct say in what we build next.
            </p>
          </div>
          <Link href="/request-demo?interest=pilot" className="mk-btn mk-btn-primary mk-btn-lg">Ask about the pilot</Link>
        </div>
      </section>

      {/* 14 · Final CTA */}
      <section className="mk-final" aria-labelledby="final-title">
        <div className="mk-container mk-final-inner">
          <h2 id="final-title">Your next patient conversation could start on your website.</h2>
          <p>See ZUVOORA Engage with your own clinic&apos;s questions in mind.</p>
          <div className="mk-cta-row">
            <Link href="/request-demo" className="mk-btn mk-btn-light mk-btn-lg">Request a demo</Link>
            <Link href="/login" className="mk-btn mk-btn-outline-light mk-btn-lg">Clinic sign in</Link>
          </div>
        </div>
      </section>
    </>
  );
}
