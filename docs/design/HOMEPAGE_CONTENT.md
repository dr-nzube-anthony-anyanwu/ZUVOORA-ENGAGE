# Homepage Content Specification

The approved copy and the evidence behind every product claim on the public homepage
(`apps/web/app/(marketing)/page.tsx`, which is the source of truth for exact wording). Change a
claim only if the capability it depends on changes. Rules: `prompts/DESIGN_UI_UX_BRIEF.md` §3.

| # | Section | Headline | Key claims | Evidence (implementation) |
|---|---|---|---|---|
| 1 | Hero | "Your clinic is caring for patients. Who's welcoming the next one?" | Answers only from approved information; appointments booked in the existing calendar; team one click away | Phase 3c/3d grounding + guard; Phase 4 Cal.com/Calendly booking; Phase 3e handover |
| — | Story | "Your clinic closes for the day. Your patients' questions don't." | Narrative (10:47 PM visitor); no statistics | — |
| 2 | Challenge | "A patient may be ready to reach out. Your website may not be ready to respond." | After-hours questions, no immediate guidance, booking friction, busy front desk | Qualitative; no numbers |
| 3 | Solution | "Your website can do more than tell people about your clinic." | One snippet, no rebuild; answers; bookings from Cal.com/Calendly; call-backs to the inbox | Phase 3b embed on verified domains; Phase 4; Phase 3e |
| 4 | Audience | "Built for eye care. Designed around people." | Optometry, ophthalmology, optical centres, hospitals/groups (branches by plan) | PRD audience; branches limit per plan |
| 5 | Features | "Everything your digital front desk needs." | Grounded answers + emergency guidance + no medical advice; review before publishing incl. photos/scans read by AI; booking confirmed only after the calendar confirms; staff see and cancel bookings; inbox; analytics (trends/topics on higher plans); roles, audit, 2FA for administrators | Phases 3c/3d/3f; 2c + 3g; 4c/4d; 3e; 5c; 1 |
| 6 | Value | "More than conversations. A better way to welcome patients." | Responsiveness, experience, efficiency, visibility, control, growth | Qualitative |
| 7 | Questions | "Powerful technology shouldn't mean giving up control." | Not replacing staff; no medical advice; no rebuild; clinic data separated (database + tests); conversation data visible to the clinic only, AI providers without retention/training; no patient uploads; roles and 2FA; stopping keeps data | RLS (TENANCY_AND_RLS.md); ZDR + `data_collection: deny`; Phase 5 cancelled subscription keeps data |
| 8 | How it works | "From your website to meaningful conversations in three steps." | Configure → Embed (DNS verification + snippet) → Engage | Phases 2, 2b, 3 |
| 9 | Demo | "See the experience your patients could have." | Scripted, labelled; no AI call | `DemoConversation.tsx` |
| 10 | Plans | "Start with what your clinic needs. Grow when you're ready." | Four plans; reminders/full analytics/multiple branches from Professional; highest limits Premium+; WhatsApp/voice/ecosystem "Coming soon"; no public prices | `20261126000001_plans_entitlements.sql` seed |
| 11 | Roadmap | "What's coming next." | WhatsApp, voice assistant, ZUVOORA ecosystem — not available | Not built |
| 12 | Responsibility | "Designed with healthcare responsibilities in mind." | Data separation tested; staff approve content; careful AI; invitation-only, roles, 2FA, audit | Phases 1, 2, 3 |
| 13 | Pilot | "Built with real clinics in mind." | Invitation to a pilot; no testimonials | Commercial strategy (pilot) |
| 14 | Final CTA | "Your next patient conversation could start on your website." | Request a demo; clinic sign in | — |

Not included until supplied by the founder: founder/company story, official logo, contact
details, prices, testimonials or pilot results (with consent).

Wording to avoid: "secure", "compliant", "certified", "guaranteed", "never wrong", "replaces
staff", "diagnoses", any percentage or customer count, and any planned feature described as live.
