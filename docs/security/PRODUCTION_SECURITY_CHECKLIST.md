# Production Security Checklist (go / no-go before pilot clinics)

Every box must be ticked, with evidence recorded in `docs/operations/IMPLEMENTATION.md`, before
a pilot clinic is onboarded. Items not done are marked **risk accepted** with the founder's name
and date, or the pilot waits. Finding IDs (R1–R21) refer to
[PHASE6_DEPLOYMENT_PLAN.md](../operations/PHASE6_DEPLOYMENT_PLAN.md) §4.

**Status: no box is ticked yet.** This checklist does not amount to a certification or a statement
of legal compliance.

## Server (VPS)
- [ ] Ubuntu LTS is supported, with no pending security updates; unattended security upgrades are on.
- [ ] SSH works with keys only; root login and password login are off; named admin users only.
- [ ] The sudo and docker groups contain only named administrators. Docker group membership is equivalent to root (R6).
- [ ] UFW allows only 22, 80, 443 and the documented ZUVOORA ports. An external scan confirms nothing else is reachable.
- [ ] No Engage container publishes a port on a public interface (R1). Checked with `docker ps` and an external scan of 8073, 3073, 8173 and 3173.
- [ ] fail2ban is active for SSH. Time sync is on.
- [ ] A snapshot or rebuild procedure exists, and VNC console access has been tested.

## Containers
- [ ] Every container runs as non-root, with `read_only` root filesystem, `cap_drop: ALL`, `no-new-privileges`, `pids_limit`, memory and CPU limits, and log rotation (R10).
- [ ] Base images are pinned by digest. The Trivy image scan has no unfixed HIGH or CRITICAL findings, or each one is risk-accepted (R13).
- [ ] No secrets in image layers (`docker history`; Trivy secret scan).
- [ ] Health checks exist for api, web and worker. Restart policy is `unless-stopped` (R11).
- [ ] Staging and production use separate Compose projects, networks, env files and Supabase projects.

## Network, TLS and edge
- [ ] Cloudflare SSL is Full (strict), with an Origin CA certificate and Authenticated Origin Pulls. Direct requests to the server IP are refused.
- [ ] Minimum TLS 1.2. HSTS is set on the dashboard and API. A TLS scan grades A.
- [ ] The visitor IP is correct: rate limits are per visitor, and a forged `X-Forwarded-For` is ignored. Tested from two IPs (R2).
- [ ] Webhook and widget paths are exempt from bot challenges, and a real webhook delivery succeeds (R19).
- [ ] The staging dashboard is behind Cloudflare Access. `/docs` and `/openapi.json` return 404 on staging and production (R14).
- [ ] CORS allows only the dashboard origin in each environment.
- [ ] Upload size limits are aligned across Cloudflare, the proxy (12 MB) and the API (10 MB). Long document reads finish within the proxy timeout (R9).

## Secrets
- [ ] Every secret is in the password manager and the server env file only (root, mode 600). None is in Git, CI logs, images or chat.
- [ ] Staging and production secrets all differ (preflight check).
- [ ] The Supabase production project uses the new `sb_secret_` / `sb_publishable_` keys; legacy JWT keys are disabled.
- [ ] Separate OpenRouter keys for staging and production, each with a hard credit limit. Resend keys are sending-only and restricted to the domain.
- [ ] `INTEGRATIONS_ENCRYPTION_KEY` and the backup private key are stored offline as well.
- [ ] A rotation procedure has been tested once on staging.

## Application configuration
- [ ] `APP_ENV=production`. The API refuses to start with unsafe settings (R8): resend email, https URLs, `PUBLIC_API_URL` set, no `EMAIL_ALLOWED_RECIPIENTS`, no http widget frames.
- [ ] Supabase Auth:
  - sign-ups disabled;
  - Site URL and redirect URLs set to `https://engage.zuvoora.com` only;
  - custom SMTP through Resend (R4);
  - TOTP MFA enabled;
  - leaked-password protection on (Pro only; risk accepted while on Free, D2);
  - sensible session limits.
- [ ] Platform admins have MFA enabled. Clinic owners are encouraged to use MFA.
- [ ] AI settings are deliberate (on or off, budgets, price caps). Live evaluation results are recorded.

## Data protection
- [ ] The pgTAP tenancy and RLS suite passes against a scratch copy of the production schema. Spot checks on staging with two clinics pass.
- [ ] Logs contain no patient message content, contact details or tokens (sampled review).
- [ ] Upload virus scanning (ClamAV) is active in staging and production and fails closed. EICAR is rejected, and a stopped scanner refuses uploads (R16, D5).
- [ ] The retention schedule is decided and implemented, or a dated plan is accepted (R17).
- [ ] Only synthetic data in staging.

## Backups, monitoring and recovery
- [ ] Supabase daily backups are active on the production project (R3), **or**, while on the Free plan (founder decision D2, 2026-11-24), the nightly encrypted backup and a passed restore drill are the accepted substitute.
- [ ] The nightly encrypted off-site backup of the database and stored files runs. The server cannot read or delete backups.
- [ ] The restore drill is completed and its timings recorded (RTO and RPO met).
- [ ] Uptime monitors are set on both APIs and both dashboards, and an alert has been received in a test.
- [ ] Alerts exist for disk, memory, unhealthy containers, a stale worker heartbeat, dead jobs, a missing backup and the AI budget reached. Each has been tested once (R12).

## CI and supply chain
- [ ] CI is green on the release commit: tests, Semgrep, gitleaks, Trivy filesystem and image scans, `pip-audit`, `npm audit` (R13).
- [ ] Branch protection is on `main`, and 2FA is on every provider account: GitHub, Cloudflare, Contabo, Supabase, Resend, OpenRouter, Cal.com and Calendly.
- [ ] Deployment is manual. CI has no server credentials.

## Testing on staging
- [ ] The OWASP ZAP baseline scan is reviewed; findings are fixed or accepted.
- [ ] Malicious upload samples are rejected: an EICAR test file, a decompression bomb, an active-content PDF.
- [ ] Webhook replay and bad signatures are rejected (R20). The Calendly live test has passed.
- [ ] Failure drills pass: worker killed, database unreachable, AI timeout and Resend failure. Alerts fire and the service recovers.

## Legal and operations
- [ ] Privacy notice and terms are reviewed by a qualified professional, published, and linked in the footer and the demo form (R5).
- [ ] The data processing agreement is signed with each pilot clinic. The list of subprocessors is complete: Supabase, Contabo, Cloudflare, OpenRouter and its providers, Resend, Cal.com and Calendly.
- [ ] The incident runbook is reviewed, and contacts are named.
- [ ] Support procedure: contact address, response times and who is on call.
- [ ] The founder's written go-ahead is recorded.
