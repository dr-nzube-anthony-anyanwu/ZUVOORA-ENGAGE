# Provider Account Setup Checklist

Create accounts only when their implementation phase begins.

## GitHub — Phase 0
Create a new private repository for Engage. Do not reuse the existing ZUVOORA repo. Protect `main`; keep Actions permissions minimal.

## Supabase — Phase 1
Create a dedicated Engage project, separate from ZUVOORA Core. Keep service-role key server-only. Configure Auth redirect URLs per environment. Apply migrations to staging first and test RLS with separate tenant users.

## OpenRouter — Phase 3
Create server-side API key. Configure spend limits/alerts if available. Evaluate candidate models for grounded answers, refusals, latency, cost and provider data terms. Never expose key to widget.

## Resend — Phase 4
Verify a sending domain, publish DNS records, configure SPF/DKIM/DMARC, create a restricted API key, test delivery/bounces/complaints. Minimise personal/health data in email.

## Cal.com and Calendly — Phase 4
Use test accounts. Verify current API, OAuth, webhooks, scopes, rate limits and plan requirements. Test booking/cancellation/rescheduling. Do not promise production integration until tested on the clinic's account.

## Domain/DNS and monitoring
Choose dashboard/API/widget subdomains when staging is ready. Do not point production DNS at an unprepared server.

Never paste passwords/API keys into chat, prompts, screenshots or Git.
