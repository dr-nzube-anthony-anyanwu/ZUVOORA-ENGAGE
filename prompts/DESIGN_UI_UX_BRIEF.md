# ZUVOORA Engage — Brand, Product Story and UI/UX Brief

Tailored on 2026-11-22 from the founder's research (ChatGPT output) to what ZUVOORA Engage
actually does after Phases 0–5 and 3g. This brief is a separate design track: it does not replace
the security and deployment work of Phase 6 and must not weaken any control built so far.

Read with: `CLAUDE.md`, `prompts/MASTER_BUILDER_PROMPT.md`, `docs/product/PRD.md`,
`docs/commercial/COMMERCIAL_GTM_STRATEGY.md`, `docs/operations/IMPLEMENTATION.md`,
`docs/security/TENANCY_AND_RLS.md`.

---

## 1. Role and mission

Act as principal product designer, senior UI engineer, accessibility specialist and
conversion-focused product strategist for ZUVOORA Engage (ZubeVision Technologies Ltd.).

Make ZUVOORA Engage look and read like a credible, premium, international HealthTech product — not
a generic chatbot template — and turn qualified eye-clinic decision-makers (owners, practice
managers, administrators) into demo requests and pilot enquiries.

## 2. Positioning

| | |
|---|---|
| Category | The AI-powered digital front desk for eye care |
| Tagline | Every patient enquiry deserves a response. |
| Hero headline | Your clinic is caring for patients. Who's welcoming the next one? |
| Supporting copy | Turn your eye clinic's website into a responsive digital front desk that answers questions, books appointments and keeps your team connected. |
| Core promise | Clinic-approved answers, simpler appointment booking and a person whenever one is needed. |
| Never | An autonomous clinical or diagnostic system; a replacement for staff; a source of medical advice. |

Supporting lines: "Your website. Now ready to engage." · "Built for eye care. Designed around
people." · "Let your team focus on care. Let Engage handle the first conversation." · "Human care,
supported by intelligent technology."

Central story (homepage and onboarding): a visitor lands on the clinic's website at 10:47 PM with a
question about an eye examination; reception has gone home; Engage answers from the clinic's
approved information, offers available appointment times, and passes the conversation to the team
the next morning if a person is needed. Do not claim that every unanswered enquiry is a lost
patient.

## 3. What may be claimed — verified capabilities

Every product claim must map to a row marked **Live**. Planned items may appear only with a clear
"Coming soon" treatment.

| Capability | Status | Basis |
|---|---|---|
| Chat widget on the clinic's existing website (embed snippet; no rebuild) | Live | Phase 3b; loads only on DNS-verified domains |
| Answers only from the clinic's published facts, FAQs, services and approved documents | Live | Phase 3c/3d; output guard; honest "I don't have that information" |
| Emergency guidance and refusal of medical advice | Live | Phase 3c; evaluated 100% in safety categories |
| Human handover: call-back requests and staff inbox | Live | Phase 3e |
| Live appointment booking with confirmation only after the provider confirms | Live (Cal.com; Calendly built, awaiting live test) | Phase 4 |
| Confirmation emails, 24 h and optional 2 h reminders, cancellations | Live (reminders from Professional) | Phase 4 |
| Clinic content with review before publishing; documents incl. photos/scans read by AI | Live | Phases 2, 3g |
| Team roles: owner, admin, receptionist, viewer; invitation-only; MFA | Live | Phase 1 |
| Analytics (basic all plans; full from Professional) | Live | Phase 5c |
| Four plans with usage limits and alerts | Live (assigned by ZubeVision; no online payment) | Phase 5 |
| Each clinic's data isolated from other clinics | Live | RLS + API checks, tested |
| WhatsApp | Coming soon | Not built |
| Voice AI | Coming soon | Not built |
| Full ZUVOORA ecosystem integration | Coming soon | Not built |
| Self-service sign-up, online payment, data export | Not available | Accounts are invitation-only |

Security and privacy copy may state only implemented controls: per-clinic data isolation enforced in
the database, invitation-only accounts, two-factor authentication for administrators, staff review
before anything is published, AI only from approved content through providers that do not retain
or train on the data, encrypted storage of scheduling credentials, audit trail of staff actions.
**No** compliance, certification or "secure/HIPAA/NDPA-compliant" claims, statistics, outcomes,
guarantees, testimonials, ratings or partner logos without evidence.

## 4. Brand system

- **Official logo supplied (2026-11-22)**: `docs/brand/`, used through one component; colours
  are sampled from it (`docs/design/DESIGN_SYSTEM.md`). An SVG version and a reversed (white)
  version are still wanted from the designer.
- Current tokens in the app and widget: navy `#15324B`, teal `#167D8D`, ink `#203040`, muted
  `#607080`, line `#DCE5E9`, surface `#F4F8F9`.
- Proposed working palette (to be checked against the logo): Deep Navy `#102C3B`, Brand Teal
  `#168B87`, Soft Aqua `#7ED9D0` (decorative only — fails contrast as text on white), Mist
  `#F0F8F7`, White `#FFFFFF`, Slate `#506872`. Every text/background pair must meet WCAG 2.2 AA
  (4.5:1 body, 3:1 large text and UI components).
- Typography: Plus Jakarta Sans (headings) and Inter (interface/body), self-hosted with `next/font`
  (the CSP allows only `font-src 'self'`; no runtime calls to Google).
- Icons: inline SVG components or one pinned, MIT-licensed icon package; no icon fonts.
- Imagery: genuine screenshots of the application taken from synthetic data (Playwright), simple
  illustrations; licensed clinic photography only if supplied. No AI-generated "patients" or fake
  dashboards.
- Tokens live in one place (CSS custom properties) and are shared by the marketing site, the
  dashboard and the chat widget. A design-system document records them.

## 5. Page map

| Route | Purpose | Notes |
|---|---|---|
| `/` | Public homepage (story and conversion) | Replaces the current development placeholder |
| `/request-demo` | Demo / pilot request form | Needs a new, approved lead-capture endpoint (see §7) |
| `/accessibility` | Accessibility statement | Factual; can be written now |
| `/privacy`, `/terms` | Legal pages | Only after professional review (Phase 6); no links until they exist |
| `/login`, `/mfa`, `/account/set-password` | Sign-in, two-factor, invitation acceptance | Restyle only; logic unchanged |
| `/dashboard`, `/clinics/...`, `/platform/...` | Staff and platform workspaces | Visual consistency only; workflows, labels and roles unchanged |
| Chat widget (`apps/widget`) | The patient-facing experience | Restyle with brand tokens; behaviour unchanged |

There is no public registration page: accounts are created by invitation. "Get started" means
"Request a demo".

## 6. Homepage sections

1. **Navigation** — logo, Product, How it works, Plans, About; "Sign in"; primary "Request a demo".
   Keyboard and mobile accessible.
2. **Hero** — asymmetric split: headline, supporting copy, "Request a demo" + "Explore Engage";
   on the right a clearly labelled *illustrative* conversation (e.g. glaucoma screening → opening
   hours → book an appointment → speak to the clinic), styled exactly like the real widget.
3. **The challenge** — "A patient may be ready to reach out. Your website may not be ready to
   respond.": questions after hours, enquiries without immediate guidance, booking friction, busy
   reception. No statistics.
4. **The solution** — existing website + Engage → Answers · Bookings · Handover.
5. **Who it's for** — optometry practices, ophthalmology clinics, optical centres, eye hospitals and
   groups (multi-branch subject to plan).
6. **Features** — alternating screenshot/copy rows: grounded answers; clinic-approved knowledge
   (review before publishing, photos and scans read by AI); appointments; human handover and inbox;
   analytics; team and administration.
7. **Value** — responsiveness, patient experience, team efficiency, visibility, control, growth.
8. **"Powerful technology shouldn't mean giving up control."** — accessible accordion answering:
   Will it replace our receptionists? Will it give medical advice? Do we need to rebuild our
   website? Could our information mix with another clinic's? What if we don't understand AI? What
   if we want to stop? — answers drawn only from §3.
9. **How it works** — Configure (clinic information, reviewed) → Embed (verify your domain, paste one
   snippet) → Engage (answers, bookings, handover, reminders).
10. **See it in action** — a scripted, clearly labelled sample-clinic conversation (no live AI call
    from the marketing page, no cost, no data stored).
11. **Plans** — Essentials, Professional, Premium, Full ZUVOORA with honest availability (see §3);
    pricing display per founder decision.
12. **Roadmap** — WhatsApp, voice AI, ZUVOORA ecosystem as "Coming soon".
13. **About / founder** — written from facts supplied by the founder only.
14. **Pilot programme** — an invitation to join the pilot instead of testimonials; real pilot
    evidence only later, with consent.
15. **Final call to action** — "Your next patient conversation could start on your website."
16. **Footer** — ZubeVision Technologies Ltd. identity, product links, sign in, accessibility,
    contact; only pages that exist; no invented social accounts.

Vary compositions (editorial split, banners, timeline, accordion, screenshot rows); avoid repeated
card grids, heavy gradients, autoplaying media and excessive motion. Any carousel needs manual
controls, keyboard support, no autoplay, and no essential content hidden inside it.

## 7. Conversion and lead capture

- Primary CTA "Request a demo"; secondary "Explore Engage" (scrolls to the product story).
- **No lead-capture endpoint exists.** Proposed secure design, to be approved before it is built:
  a public API endpoint storing requests in a platform-admin-only table (RLS), minimal fields
  (name, role, clinic name, city/country, work email, optional phone, optional message, consent to
  be contacted), no health or patient information, rate limiting and a honeypot field, an email
  notification to ZubeVision through the existing job queue, a "Demo requests" list in the
  platform console, and a retention period.
- No analytics or tracking scripts until a privacy and consent decision exists.

## 8. Authentication and product pages

- Login: "Welcome back to better patient conversations." Same Supabase logic, generic error
  message, MFA redirect, invitation-only note; accessible labels, errors and focus states.
- MFA and set-password pages: same brand treatment, logic unchanged.
- Dashboard: calm, efficient, consistent tokens and components; no marketing content; every
  existing label, role restriction and workflow preserved (the Playwright suite relies on them).
- Onboarding message: "Let's teach Engage about your clinic." on the existing setup checklist.

## 9. Accessibility and performance

WCAG 2.2 AA: semantic landmarks and headings, skip link, visible focus, keyboard-operable menus
and accordions, labelled forms with clear errors, contrast-checked tokens, `prefers-reduced-motion`
respected, touch targets ≥ 24 px. Automated checks with axe (Playwright) on the homepage and auth
pages, plus manual keyboard and screen-size review (mobile 375 px, tablet 768 px, desktop 1440 px).
Performance: Server Components by default, self-hosted fonts, optimised images, no heavy animation
libraries, measure Core Web Vitals locally (Lighthouse).

## 10. Engineering constraints

- Next.js 16 / React 19 App Router as installed; inspect before adding any package; pin versions.
- Keep the existing CSP and security headers; do not add third-party scripts, fonts or images
  from other origins.
- No backend or database changes except the approved lead-capture feature.
- Do not break routes, authentication, MFA, RLS, entitlements, scheduling, conversations, analytics
  or the widget. Full regression: lint, typecheck, build, bundle-secret scan, Playwright, pytest
  (if the API changes), pgTAP (if the database changes), Semgrep, gitleaks.
- No deployment. Commit in reviewable slices.
- Deliverables: `docs/design/DESIGN_SYSTEM.md` (tokens, typography, components, accessibility
  rules), `docs/design/HOMEPAGE_CONTENT.md` (approved copy per section), screenshots of mobile /
  tablet / desktop, limitations and test results in `IMPLEMENTATION.md`.

## 11. Sequence

1. **D1 — Design system and homepage**: tokens, fonts, layout primitives; homepage (static, no new
   backend); accessibility statement; product screenshots from synthetic data; axe checks.
2. **D2 — Sign-in experience**: login, MFA, set-password restyled; logic unchanged.
3. **D3 — Demo requests** (after approval): API endpoint, table, notification, platform list,
   `/request-demo` page.
4. **D4 — Dashboard and widget consistency**: shared tokens and components across the workspace,
   platform console and chat widget; onboarding copy.
5. **D5 — Review**: visual QA at three sizes, Lighthouse, documentation.

## 12. Founder decisions (2026-11-22)

- **Logo:** official logo supplied later the same day and now used everywhere (see
  docs/design/DESIGN_SYSTEM.md); palette taken from it (navy, royal blue, green).
- **Prices:** not shown publicly; plans show what is included and "Request a demo for pricing".
- **Demo requests:** approved — build the secure lead-capture feature in §7 as its own slice.
- **Founder section:** skipped for now; added later from founder-supplied facts only.

## 13. Still needed from the founder

- Official logo files (SVG preferred) and any brand guide or colour codes, when available.
- Founder/company story facts, when the founder section is wanted.
- Contact details to show publicly (business email; phone optional) and the company's public
  location.
- The email address that should receive demo-request notifications.
- Any licensed photography to use.
