# Phase 6 — Deployment Plan and Readiness Report (Contabo VPS)

**Status: plan only. Nothing in this document has been carried out.** Written on 2026-11-24 from an
inspection of the repository (Dockerfiles, `docker-compose.yml`, `.env.example`, API settings and
health checks, worker, CI workflows, web security headers). Nobody has connected to the VPS,
changed DNS, opened ports, created credentials or deployed anything. Every stage below waits for the
founder's approval. Phase 6 is **not** complete.

Related documents:

| Document | Purpose |
|---|---|
| [CONTABO_VPS_SETUP.md](CONTABO_VPS_SETUP.md) | Read-only inspection, then server hardening (after approval) |
| [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) | How a release reaches staging and then production |
| [ROLLBACK_AND_RECOVERY.md](ROLLBACK_AND_RECOVERY.md) | Rollback, backups, restore drill, incident first steps |
| [../security/PRODUCTION_SECURITY_CHECKLIST.md](../security/PRODUCTION_SECURITY_CHECKLIST.md) | Go/no-go checklist before pilot clinics |
| [PHASE6_FOUNDER_GUIDE.md](PHASE6_FOUNDER_GUIDE.md) | Step-by-step tasks only the founder can do |

---

## 1. Confirmed direction (from the founder)

| Item | Decision |
|---|---|
| Hosting | Contabo, the existing Cloud VPS 6. Ubuntu, but the exact version is still to be checked. |
| Neighbour | The main ZUVOORA application may already run on this VPS. It must not be disturbed. |
| Domain | `zuvoora.com`, with DNS at Cloudflare |
| Production | Dashboard on `engage.zuvoora.com`; API and widget on `api-engage.zuvoora.com` |
| Staging | Dashboard on `staging-engage.zuvoora.com`; API and widget on `staging-api-engage.zuvoora.com` |
| Runtime | Docker Compose for the pilot; no Kubernetes |
| Database | Supabase Cloud. The existing cloud project becomes **staging**, and a **new** project becomes production. |
| Providers | OpenRouter (AI), Resend (email), Cal.com and Calendly (booking) |
| First customers | Three pilot eye clinics |

**The host names suit Cloudflare.** Each one sits one level below `zuvoora.com`, for example
`api-engage.zuvoora.com`. Cloudflare's free certificate covers `*.zuvoora.com` but not names two
levels down such as `api.engage.zuvoora.com`, which `.env.example` used to suggest. Use the
single-level names.

## 1a. Founder decisions (2026-11-24) and what follows from them

### The VPS (from the Contabo panel)

| Item | Value |
|---|---|
| Plan | Cloud VPS 6 (2026) |
| CPU and memory | 6 cores, 12 GB RAM |
| Disk | 200 GB |
| Region | EU |
| Default user | `root` |
| VNC console | Enabled |
| Auto Backup add-on | Not active |
| Snapshots | None yet |
| Ubuntu version | **24.04.5 LTS** (from the inspection on 2026-11-25) |
| What runs on it | **Nothing.** A fresh server: no Docker, no web server, no ZUVOORA application. Only SSH listens. |
| Security today | UFW off; root and password SSH login on; no fail2ban; 21 updates waiting; no swap. The founder logs in with an SSH key added through Contabo. |

The IP address is deliberately not recorded in this public repository.

### Decisions

| # | Decision | Consequence |
|---|---|---|
| D1 | **Staging shares the VPS** with production (and ZUVOORA, if present). It moves to its own VPS, or the plan is upgraded, later. | §6 mitigations are mandatory. Staging is stopped when not needed. 12 GB is enough for both environments (see the budget in §5). |
| D2 | **No Supabase Pro for now.** Both projects stay on the Free plan, with an upgrade when paying clinics arrive. | Free projects have **no Supabase backups**, so our own nightly encrypted backup (6G) is the **only** backup. It and a successful restore drill are hard requirements before any real data. Free limits apply: 500 MB database, 1 GB file storage, a project pause after inactivity (the worker and uptime checks keep it active; a pause raises an alert), and no leaked-password protection (risk accepted for the pilot). The Free plan allows only **two active free projects**, so check whether ZUVOORA already uses one. |
| D3 | **Email.** ZUVOORA Engage sends from its own address on `engage.zuvoora.com`. The founder's personal mailbox receives alerts and replies for now; the address is kept only in the server env file, never in Git. Each clinic's emails show the **clinic's name** and set **Reply-To to the clinic's contact address**. Fully custom clinic sending domains come later. | Resend cannot send *from* a Gmail address, because only domains you own can be verified. So the sender is, for example, `ZUVOORA Engage <no-reply@engage.zuvoora.com>`. Official addresses such as `support@engage.zuvoora.com` can forward to the founder's mailbox for free through Cloudflare Email Routing. The Resend Free plan allows 1 domain, 100 emails a day and 3,000 a month, shared by staging, production and Supabase Auth; 6G alerts before the cap is reached. Custom clinic domains each need DNS verification and a paid Resend plan, so they move to the backlog. |
| D4 | **AI on at launch**: answers and document reading, with the production OpenRouter key and its credit limit as the hard stop | The budgets stay as they are (clinic $0.20 a day, platform $0.50 a day, $2 a month) until usage is known. The live evaluation on staging (6F) must pass first. |
| D5 | **Scan uploads for viruses during the pilot** | ClamAV is added in 6A (below). R16 becomes a build item. |
| D6 | **No lawyer yet** | Everything technical can go ahead, including production deployment with test data. **Real patient conversations wait** for reviewed legal documents (R5). Claude can prepare clearly marked *drafts* (privacy notice, terms, DPA, retention schedule) to shorten the lawyer's work; they are not legal advice. |

### Virus scanning design (D5)

- **One ClamAV service per environment** (`clamav/clamav` image, pinned by digest).
  - It sits on that environment's private network only, with no host port.
  - Signatures are updated automatically by `freshclam`.
  - It uses about 1–1.5 GB of memory each. Staging's copy stops with staging.
- **The API sends each upload to it before anything is stored or read** (clamd `INSTREAM` over
  the private network, with a size limit and a timeout).
  - **Infected:** rejected and audited (`document.malware_rejected`, with the signature name only).
  - **Scanner unavailable:** the upload is refused with "Virus scanning is unavailable, try again
    shortly". The check **fails closed**.
  - Scanning happens before the existing checks (type sniffing, active content, the isolated
    parser, image re-encoding), and those checks stay in place.
- **Tests:**
  - an EICAR test file is rejected;
  - a clean file passes;
  - scanner down means refused and nothing stored;
  - a timeout means refused;
  - a fake clamd is used in the unit and integration tests, and the real one in a CI job.

## 2. What already exists

- **Images.**
  - API image: two stages. It builds the widget, then runs the Python API as the non-root user
    `app`.
  - Dashboard image: three stages. It also runs as non-root, and the build fails if a server
    secret reaches the browser files.
  - Dockerignore files keep env files out of the images.
- **Compose file.**
  - It defines `api`, `web` and `worker` on a private bridge network. The web container gets only
    browser-safe values and never the shared `.env`.
  - It has an API health check and `restart: unless-stopped`.
- **The API refuses to start when misconfigured** in staging or production:
  - required secrets are missing;
  - `SUPABASE_URL` is not https;
  - `WIDGET_TOKEN_SECRET` is shorter than 32 characters;
  - http widget frames are allowed;
  - CORS uses `*`;
  - the legacy JWT secret is set;
  - `EMAIL_ALLOWED_RECIPIENTS` is set in production.
- **Health and API docs.** `/health/live` and `/health/ready` (the readiness check pings the
  database). The interactive API documentation is turned off in production.
- **Worker.** Leased job claims with idempotency keys, retries with backoff, a dead-letter state,
  and periodic purges.
- **Dashboard security headers:** CSP, HSTS in production, X-Frame-Options DENY, nosniff,
  Referrer-Policy and Permissions-Policy.
- **Data protection in the product.**
  - Tenant isolation enforced by RLS, with 416 pgTAP tests.
  - Least-privilege database roles (`engage_api`, `engage_app`, `engage_widget`, `engage_jobs`).
  - Signed webhooks.
  - Upload screening in an isolated subprocess.
  - AI price caps and budgets.
- **CI.** Database lint and pgTAP, Ruff and pytest, Playwright E2E with axe, ESLint and tsc, the
  bundle-secret check, gitleaks, Semgrep (OWASP), and a Trivy filesystem scan. Actions are pinned
  by commit SHA.
- **Cloud migrations** are already applied to the staging project, up to
  `20261130000001_demo_requests.sql`.

## 3. What is missing

| # | Missing piece |
|---|---|
| M1 | A production Compose file. The current one publishes ports on every network interface and has no resource limits, hardening or log rotation. |
| M2 | Reverse proxy configuration, TLS and Cloudflare origin protection |
| M3 | Environment templates per environment (staging and production) and a server-side secret layout |
| M4 | Deploy, rollback and preflight scripts; image versioning and image delivery to the VPS |
| M5 | A schedule for `reverify_domains` (it currently runs nowhere) and health checks for the worker and dashboard |
| M6 | Backups beyond the Supabase defaults: database, stored files and off-site copies, plus a restore drill |
| M7 | Monitoring and alerts: uptime, dead jobs, disk, memory, certificate expiry, AI budget |
| M8 | Image build and scan in CI, digest-pinned base images, and the dependency audits listed in `SECURITY_BASELINE.md` (`pip-audit`, `npm audit`). The OWASP ZAP scan on staging is also missing. |
| M9 | Production Supabase project: Auth URLs, custom SMTP, MFA, disabled sign-ups and the new API keys |
| M10 | Legal: privacy notice, terms, data processing agreement and retention schedule, all reviewed by a qualified professional |

## 4. Security risks found

IDs are referenced in the checklist and the implementation tracker. "Blocker" means no pilot clinic
until it is resolved.

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| R1 | **Blocker** | **Docker-published ports bypass the Ubuntu firewall.** The Compose file publishes `8073` and `3073` on every interface. Docker writes its own iptables rules ahead of UFW, so the API and dashboard would be reachable on the server's public IP over plain http, skipping the proxy, TLS and Cloudflare, even with UFW "on". | `docker-compose.yml`: `ports: ["${API_PORT:-8073}:8073"]` |
| R2 | **Blocker** | **Visitor IP behind a proxy.** Uvicorn runs without `--proxy-headers`, so behind Caddy or Nginx every visitor seems to come from the proxy. All per-IP limits (widget frames, sessions, messages, bookings, call-backs, webhooks, demo requests) collapse into one shared bucket, and one abusive visitor could stop chat for every clinic. Trusting headers naively causes the opposite problem: the dashboard takes the **first** `X-Forwarded-For` value, which a visitor can forge. | `apps/api/Dockerfile` CMD; `widget_public.py:_client_ip`; `apps/web/lib/public-actions.ts:46` |
| R3 | **Blocker** | **No production backups or tested restore.** A Supabase Free project has no backups and pauses after inactivity. The founder chose Free for now (D2), so our own encrypted backup is the only one. Stored documents are not included in database backups. No restore has ever been practised. | — |
| R4 | **Blocker** | **Staff emails on the new production project.** Supabase's built-in email sender is heavily rate-limited, so clinic staff invitations and password resets need custom SMTP (Resend). The Site URL and redirect URLs must point to `engage.zuvoora.com`. | `SUPABASE_CLOUD_SETUP.md` |
| R5 | **Blocker** | **Legal documents.** There is no reviewed privacy notice, terms, data processing agreement or retention schedule, and the website footer does not link them. Real patient data cannot be processed before these exist. | Phase 6 brief |
| R6 | **Blocker (decision)** | **Shared host.** Staging, production and the main ZUVOORA application would share one machine. Anyone with root or Docker access to that host can read every environment's secrets, and a compromise of one application exposes the others. This needs an explicit founder decision with the mitigations in §6. | — |
| R7 | **Blocker** | **No deployment assets**: M1–M4 | — |
| R8 | High | **Unsafe production settings are accepted.** Production starts with `EMAIL_DELIVERY=log`, where emails are silently not sent; with an http `DASHBOARD_URL`; and without `PUBLIC_API_URL`, in which case Cal.com webhooks are not registered. | `app/config.py:enforce_production_safety` |
| R9 | High | **Document reading can outlast Cloudflare's 100-second proxy limit.** 10 pages at 4 in parallel with 40 seconds each can take up to about 120 seconds. The user then sees an error while the model calls are still being paid for. | `services/ai/vision.py`, `AI_VISION_TIMEOUT_SECONDS=40` |
| R10 | High | **No container limits or hardening.** No memory, CPU or process limits; writable root filesystems; default Linux capabilities; and Docker logs that grow forever. A runaway container or a full disk could also take down the main ZUVOORA application. | `docker-compose.yml` |
| R11 | High | **Silent background failures.** A dead worker means no reminders or alerts and nobody notices. Domain re-verification is not scheduled at all. | `SCHEDULED_JOBS.md` |
| R12 | High | **No monitoring or alerting** | — |
| R13 | High | **Images are neither built nor scanned in CI**, base images are pinned by tag rather than digest, and the dependency audits do not run | `.github/workflows/*` |
| R14 | High | **Interactive API docs will be public on staging.** `/docs` and `/openapi.json` are only disabled when `APP_ENV=production`, and staging will be on the internet. | `app/main.py:99` |
| R15 | Medium | **The dashboard image carries all development dependencies** and has no health check | `apps/web/Dockerfile` |
| R16 | Medium | **Uploaded files are not scanned for malware.** The risk is reduced: only owners and admins can upload, images are re-encoded, and documents are parsed in an isolated process. The founder decided to add ClamAV scanning, failing closed (D5), in 6A. | Implementation tracker |
| R17 | Medium | **Retention is not implemented** for conversations, call-backs, provider events and audit records | Implementation tracker |
| R18 | Medium | **The dashboard CSP still allows inline scripts.** A nonce-based policy is planned. | `apps/web/next.config.ts` |
| R19 | Medium | **Cloudflare bot protection** (Bot Fight Mode, challenges) can block Cal.com and Calendly webhooks and widget API calls unless the API host is exempted | — |
| R20 | Medium | **Real-provider tests still missing.** Cal.com signature encoding has not been checked against a real delivery, and Calendly has never been tested live. | Implementation tracker |
| R21 | Low | `.env.example` suggested the `api.engage.zuvoora.com` style of name (see §1). **Fixed** in the example on 2026-11-24. | `.env.example` |

## 5. Recommended architecture

```
 Clinic websites (widget)      Clinic staff / ZubeVision admins          Cal.com, Calendly
          │                               │                                    │ webhooks
          └───────────────┬───────────────┴────────────────────────────────────┘
                          ▼  HTTPS
              Cloudflare (DNS, proxy "orange cloud", TLS, WAF skip rules for webhooks)
                          │  HTTPS, Origin certificate + Authenticated Origin Pulls
                          ▼
 ┌──────────────────────── Contabo VPS (Ubuntu LTS) ───────────────────────────────┐
 │  UFW: allow 22 (SSH, restricted), 80, 443. Nothing else listens publicly.       │
 │                                                                                  │
 │  Edge reverse proxy (ONE per server; owns 80/443; shared with main ZUVOORA)     │
 │     engage.zuvoora.com ──────────────► prod  web    (container, no host port)   │
 │     api-engage.zuvoora.com ──────────► prod  api    (container, no host port)   │
 │     staging-engage.zuvoora.com ──────► stage web   (Cloudflare Access login)    │
 │     staging-api-engage.zuvoora.com ──► stage api                                │
 │                                                                                  │
 │  Compose project "engage-prod"            Compose project "engage-staging"      │
 │    api  (uvicorn, proxy headers)            api                                  │
 │    web  (Next.js standalone)                web                                  │
 │    worker (jobs + daily re-verify)          worker                               │
 │  private networks per project; staging and production never share a network    │
 │                                                                                  │
 │  Main ZUVOORA application — untouched                                            │
 └──────────────────────────────────────────────────────────────────────────────────┘
          │ TLS (Postgres, Auth, Storage)                    │ HTTPS
          ▼                                                  ▼
  Supabase Cloud: staging project | production project     OpenRouter, Resend, Cal.com, Calendly
  Encrypted off-site backups (separate storage account; VPS can write, cannot read or delete)
```

### Reverse proxy: Caddy or Nginx

Only one program can own ports 80 and 443 on a server, so the inspection decides this:

- **If the main ZUVOORA application already runs Nginx (or Caddy, or Traefik) on 80/443, add the
  four Engage sites to that proxy.** A second proxy cannot take ports that are already in use,
  and replacing the existing one would disturb ZUVOORA. Engage containers then publish only to
  `127.0.0.1` (production `8073`/`3073`, staging `8173`/`3173`). Those addresses are invisible from
  the internet.
- **If nothing owns 80/443, use Caddy.** The whole configuration is a short file; TLS, HSTS and
  sensible defaults come built in; the config can be checked with `caddy validate` before
  reloading; and there is far less room for the mistakes that Nginx TLS blocks invite. Nginx is
  equally capable but needs more hand-written TLS and header settings, and its
  `X-Forwarded-For` handling is easy to get wrong. Caddy would run in Docker on an `edge` network
  with no host ports used by the applications.

### TLS and the origin

- Cloudflare SSL mode **Full (strict)**.
- The origin presents a **Cloudflare Origin CA certificate** (trusted only by Cloudflare; valid for
  up to 15 years; no renewal jobs).
- **Authenticated Origin Pulls**: the origin accepts TLS only from Cloudflare's client
  certificate. Direct visits to the server IP are refused even though port 443 is open.

This is set per host name, so it does not affect the main ZUVOORA sites.

### Real visitor IP (fixes R2)

1. Cloudflare puts the true IP in `CF-Connecting-IP`.
2. The proxy accepts that header only from Authenticated Origin Pull connections. It then
   **replaces** `X-Forwarded-For` with that single address and never appends to it.
3. Uvicorn runs with `--proxy-headers --forwarded-allow-ips=<proxy and dashboard container
   addresses>`.
4. The dashboard trusts only the value its own proxy set.

A test proves that a forged header is ignored.

### Resource budget (VPS: 6 cores, 12 GB RAM, 200 GB disk)

| Container | Memory limit | CPU limit | Notes |
|---|---|---|---|
| api | 768 MB | 1.0 | Document reading (Pillow, PDF rendering) is the peak |
| web | 512 MB | 0.75 | Next.js standalone server |
| worker | 256 MB | 0.5 | I/O-bound |
| clamav | 1.5 GB | 0.5 | Virus signatures held in memory (D5) |
| Caddy, if used | 64 MB | 0.25 | One for the whole server |

- **One environment:** about 3 GB of memory limits. **Both environments:** about 6 GB, leaving
  about 5 GB for Ubuntu and ZUVOORA. Real use is normally well below the limits. If memory is
  short, staging is stopped first.
- **Disk:** images about 1.5 GB per release (keep 3 releases), with logs capped at 3 × 10 MB per
  container.
- **Staging** can be stopped when it is not in use.
- **Images are built in CI, not on the VPS.** A Next.js build needs around 2 GB of memory and
  could starve the main application.

### Isolation

- Separate Compose projects, networks, env files and Supabase projects for staging and production.
- Containers run with:
  - a non-root user;
  - `read_only: true` with a small `tmpfs` at `/tmp`;
  - `cap_drop: [ALL]` and `security_opt: [no-new-privileges:true]`;
  - `pids_limit`;
  - memory and CPU limits;
  - `restart: unless-stopped`;
  - json-file logs with rotation.

### Delivering images (recommended)

1. A GitHub Actions workflow builds both images when a **release tag** is pushed.
2. It runs a Trivy **image** scan and pushes to GitHub Container Registry (GHCR), tagged with the
   commit SHA.
3. The VPS pulls by digest.

The images contain no secrets, because public Supabase values are already public. They can
therefore be public packages, and the server needs no registry password. If you prefer private
images, the server gets a read-only GHCR token instead. Deployment is always started by a person,
never automatically.

## 6. Shared-host mitigations (R6)

If staging, production and ZUVOORA share the VPS:

1. Only named administrators can log in, with SSH keys only. No shared accounts.
2. Docker group membership is equivalent to root, so it is limited to those administrators.
3. Env files are `root:root 600`, under `/opt/zuvoora-engage/<env>/`.
4. Staging secrets are always different from production secrets.
5. The staging dashboard sits behind Cloudflare Access, with a login for named people.
6. Production keys (Supabase secret, OpenRouter, Resend, encryption key) are never used in staging.
7. Container hardening (§5) and log caps protect the neighbour application.

The safer alternative is a small separate VPS for staging, around €5–8 a month. That is a
founder decision.

---

## 7. Stages

Each stage is small, can be verified on its own, and needs founder approval before it starts.
"Evidence" is what is recorded in `IMPLEMENTATION.md` before the stage is accepted.

### 6A — Repository readiness (no server) and read-only VPS inspection

**Files to create or modify** (all reviewable in Git):

- **Deployment layout.**
  - `deploy/compose.yml`: hardened production-style Compose for both environments (selected with
    `--project-name` and `--env-file`); no public ports; limits, logs and health checks.
  - `deploy/proxy/Caddyfile.example`, or `deploy/proxy/nginx-engage.conf.example` once the
    inspection shows what is installed.
  - `deploy/env/staging.env.example` and `deploy/env/production.env.example`: placeholders and the
    meaning of each setting.
  - `deploy/scripts/preflight.sh`: checks env-file permissions and the required names without
    printing values.
  - `deploy/scripts/deploy.sh`, `rollback.sh`, `backup.sh`, `restore-check.sh`.
- **Virus scanning (D5).**
  - `apps/api/app/services/malware_scan.py`: clamd client with size limit, timeout and
    fail-closed behaviour.
  - Called from `routes/knowledge.py` before `_screen`.
  - A `clamav` service in `deploy/compose.yml`, and settings `CLAMAV_HOST`, `CLAMAV_PORT`,
    `MALWARE_SCAN_REQUIRED` (true in staging and production).
- **Email identity (D3).** Booking and clinic emails use the clinic name in the sender's display
  name and `Reply-To` set to the clinic's contact address. Templates and tests are updated.
- **API.**
  - `apps/api/Dockerfile`: digest-pinned base images, fixed UID, `HEALTHCHECK`, and uvicorn
    `--proxy-headers --forwarded-allow-ips` from settings, plus `--no-server-header`.
  - `apps/api/app/config.py`: in production, require `EMAIL_DELIVERY=resend` and https
    `DASHBOARD_URL`, `PUBLIC_API_URL` and CORS origins. Turn off the API docs in staging too.
    Add a `FORWARDED_ALLOW_IPS` setting.
  - `apps/api/app/services/ai/vision.py`: one overall deadline (for example 75 seconds) for a
    whole document. Pages not read in time cancel the read with a clear message, and only
    attempted calls are charged.
  - `apps/api/app/worker.py`: heartbeat file for the health check, and the daily
    `reverify_domains` run (guarded so that several workers do not repeat it).
- **Dashboard.**
  - `apps/web/next.config.ts`: `output: "standalone"`.
  - `apps/web/Dockerfile`: standalone runtime, digest pins, `HEALTHCHECK`.
  - `apps/web/app/healthz/route.ts`: health endpoint.
  - `apps/web/lib/public-actions.ts`: trust only the proxy-set visitor IP.
- **CI.**
  - `.github/workflows/quality.yml`: `pip-audit`, `npm audit --audit-level=high`,
    `docker compose -f deploy/compose.yml config`.
  - `.github/workflows/images.yml`, new: build both images, Trivy image scan, and push to GHCR on
    a release tag only.
- **Docs:** `.env.example` (host names), `README.md`, `IMPLEMENTATION.md`, ADR-043.

**Commands (local):** `ruff check .`, `pytest`, `npx supabase test db`, `npm run lint`,
`npm run typecheck`, `npm run build`, `npm run test:e2e`, `docker compose -f deploy/compose.yml
config`, `docker build` for both images, Trivy image scan, Semgrep, gitleaks.

**Accounts:** none.

**Security checks:**
- No image publishes on `0.0.0.0`.
- Containers run as non-root with a read-only root filesystem.
- No secret in any image layer (`docker history`, and a Trivy secret scan).

**Automated tests (new):**
- Production settings rejected without resend, https URLs or `PUBLIC_API_URL`.
- Docs off in staging.
- A forged `X-Forwarded-For` from an untrusted peer is ignored; the trusted proxy's value is used.
- The dashboard ignores client-supplied forwarding chains.
- The vision deadline cancels remaining pages, and billing covers only attempted calls.
- The worker heartbeat goes stale when the loop stops.
- Only one daily re-verification runs with two workers.
- A Compose policy test (a script) fails if any service lacks limits, `read_only`, `cap_drop` or
  log rotation, or publishes on a non-loopback address.

**VPS inspection:** the founder runs the read-only commands in
[CONTABO_VPS_SETUP.md §1](CONTABO_VPS_SETUP.md) and shares the output with private details
removed. No changes are made.

**Manual acceptance:**
- The full stack runs locally from `deploy/compose.yml` against local Supabase with
  `APP_ENV=staging`-style settings.
- A request to the host's IP on 8073/3073 from another machine fails.
- Containers restart after `docker kill`.

**Rollback:** revert the commits; nothing outside Git changes.

**Evidence:** test counts; scan output; `docker inspect` showing no public ports; the inspection
summary (OS, CPU, memory, disk, existing proxy and ports).

**As built (2026-11-25); differences from the plan above:**
- **Proxy file:** `deploy/proxy/Caddyfile` plus `deploy/proxy/compose.yml`. The server is empty,
  so Caddy was chosen.
- **Visitor IP:** the trusted-proxy check is done inside the app
  (`app/middleware.py:install_proxy_headers`, settings `FORWARDED_ALLOW_IPS`), and uvicorn runs
  with `--no-proxy-headers`. One place decides, and it is unit-tested.
- **Releases:** a release is pinned in `/opt/zuvoora-engage/<env>/release.env`, written by
  `deploy.sh`. The previous one is kept as `release.env.previous`; `rollback.sh` swaps them.
  `deploy.sh` rolls back automatically when a health or smoke check fails.
- **Document-reading deadline:** handled through settings, not by cancelling running calls
  (which would still be billed). `AI_VISION_PARALLEL` (5) and `AI_VISION_DEADLINE_SECONDS` (85)
  are checked at start-up: rounds × timeout must fit within the deadline, which itself stays
  below Cloudflare's 100 seconds. The worst case is 2 × 40 = 80 seconds.
- **Daily re-verification:** the worker runs it hourly. It is idempotent, because only domains
  not checked in the last 20 hours are due, and only in workers with
  `WORKER_RUN_SCHEDULES=true`. The Compose file runs exactly one worker per environment.
- **Virus-scan audit:** rejections are audited as `knowledge.upload_rejected` with
  `reason=malware` and `signature`, like every other upload rejection.
- **Moved to 6G:** `backup.sh` and `restore-check.sh`. They need the backup accounts from 6C.
- **Extra:** a preflight test script (`deploy/scripts/test_preflight.sh`), shellcheck, a real
  ClamAV EICAR test in CI, and a policy check on both Compose files.

### 6B — Server hardening (after the inspection; tailored commands)

**Files:** `docs/operations/CONTABO_VPS_SETUP.md`, the server-specific section.

**Commands:** see that document. In order:
1. Take a Contabo snapshot.
2. Create a named admin user and add an SSH key.
3. Test the key login **in a second window**.
4. Turn off password and root login.
5. Configure UFW (keeping whatever ZUVOORA needs).
6. Install fail2ban and unattended security upgrades.
7. Keep Docker and Compose up to date.
8. Configure Docker daemon log defaults and `live-restore`.
9. Optionally set up swap.

**Accounts:** Contabo panel, for the snapshot and rescue console.

**Security checks:**
- `sshd -T` shows `passwordauthentication no` and `permitrootlogin no`.
- `ufw status` lists only the agreed ports.
- An `nmap` from outside shows only 22, 80 and 443 (and whatever ZUVOORA needs).

**Automated tests:** none on the server. `preflight.sh` runs later.

**Manual acceptance:**
- The main ZUVOORA application still works, checked before and after each step.
- A key login works; a password login is refused.

**Rollback:**
- Contabo rescue console or VNC, then revert the sshd drop-in file and `ufw disable`.
- Restore the snapshot as a last resort.

**Evidence:** outputs of the checks above, with IPs redacted.

### 6C — Accounts, environments and secrets

**Founder actions:** see the [founder guide](PHASE6_FOUNDER_GUIDE.md).
- Create the production Supabase project and choose the plan (see the questions).
- Resend: verify a sending domain; create separate staging and production keys plus an SMTP key
  for Supabase Auth.
- OpenRouter: separate staging and production keys, each with its own credit limit.
- Create an off-site backup bucket and a backup encryption key pair; the private key stays
  offline.
- Create an uptime monitor account.
- Create Cal.com and Calendly test accounts.

**Claude actions:**
- Apply all migrations to the new production project: dry run, push, lint, then the pgTAP suite
  against a **scratch** copy, never production data.
- Configure Auth on both projects: sign-ups off, Site URL, redirect URLs, custom SMTP, TOTP MFA,
  new API keys, and legacy JWT keys disabled.

**Security checks:**
- The staging and production keys differ.
- Each secret is stored only in the password manager and the server env file.
- `preflight.sh` passes without printing values.

**Rollback:** revoke and recreate keys. An empty production project can be deleted.

**Evidence:** migration list equal on both projects; `db lint` clean; screenshots of the Auth
settings without keys.

### 6D — DNS, reverse proxy and HTTPS

**Changes:**
- Four proxied DNS records at Cloudflare.
- SSL mode Full (strict), Origin CA certificate, Authenticated Origin Pulls, Always Use HTTPS.
- Minimum TLS 1.2.
- WAF skip rule for `/api/v1/webhooks/*` and the widget API on the API hosts.
- Cloudflare Access on `staging-engage.zuvoora.com`.
- Proxy site blocks:
  - security headers;
  - 12 MB body limit;
  - a 110-second upstream timeout on API upload routes;
  - an `X-Forwarded-For` overwrite.

**Caution:** Cloudflare's SSL mode applies to the whole `zuvoora.com` zone. If the main ZUVOORA
site cannot use Full (strict) yet, set it for the four Engage host names only, with a
Configuration Rule, and leave the zone setting alone.

**Security checks:**
- `curl https://<server-ip>` without the Cloudflare client certificate fails.
- SSL Labs or `testssl.sh` shows A-grade TLS.
- HSTS is present.
- The ZUVOORA sites are unchanged.

**Manual acceptance:** each host answers with a holding page or 502 before deployment, with valid
TLS.

**Rollback:**
- Set the DNS records back to DNS-only, or delete them.
- Remove the proxy site blocks and reload the proxy; validate the config first.

**Evidence:** `curl -sI` header captures, the TLS report and the direct-IP refusal.

### 6E — Staging deployment

**Commands:** the `deploy.sh staging <release-tag>` flow in
[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md): pull by digest, preflight, `up -d`, wait
for health, record the release.

**Data:** synthetic only. The `demo:setup` equivalent for staging uses `@example.com`-style
addresses that route to an allowed test inbox.

**Security checks:**
- `EMAIL_ALLOWED_RECIPIENTS` restricts staging email.
- The staging dashboard requires a Cloudflare Access login.
- `/docs` returns 404.

**Automated tests:** a post-deploy smoke script (health, login page, widget loader, a CORS
preflight from a disallowed origin is refused) and Playwright smoke tests pointed at staging (read
only).

**Manual acceptance:** walk through the demo guide's Acts 1–6 on staging.

**Rollback:** `rollback.sh staging`, which returns to the previous release.

**Evidence:** smoke output, a release record and the walkthrough checklist.

### 6F — Real integrations on staging

**Work:**
- Resend delivery, bounce and complaint, including a Supabase Auth invite.
- Cal.com: a real booking, cancellation and reschedule, with webhook signature checks on real
  deliveries (R20).
- A Calendly live test.
- Turn on AI answers and document reading with the **staging** OpenRouter key and a small credit
  limit.
- Run the live evaluation, capped at `EVAL_CAP_USD=0.10`.

**Security checks:**
- Webhooks with bad signatures are rejected (logged evidence).
- AI requests carry the ZDR, `data_collection: deny` and `max_price` settings.
- Budgets stop calls once reached.

**Rollback:** turn the `AI_*` switches off; disconnect the calendars.

**Evidence:** delivery records, webhook logs (IDs only), the evaluation report and its cost.

### 6G — Monitoring, backups and restore drill

**Monitoring:**
- External uptime checks on both API `/health/ready` endpoints and both dashboards, every 1–5
  minutes, with email or phone alerts.
- A server check script (systemd timer) that emails an alert when:
  - disk is above 80%;
  - memory is high;
  - a container is unhealthy or restarting;
  - the worker heartbeat is stale;
  - any jobs are `dead`;
  - the AI daily budget has been reached.

**Backups:**
- Supabase daily backups need the paid plan, which is not bought for now (D2). Until then, the
  nightly backup below is the **only** backup. The backup must run, its alert must be tested and
  the restore drill must pass before any real data.
- A nightly `backup.sh`:
  - a logical `pg_dump` of the production database plus a copy of the storage bucket;
  - encrypted with the **public** backup key (age);
  - uploaded to the off-site bucket with **write-only** credentials;
  - versioning or object lock, so the server cannot delete old backups;
  - retained for 30 days.

**Restore drill:**
- Decrypt the latest backup on the founder's laptop, restore it into a **scratch** Supabase
  project or the local stack, then run pgTAP, the API smoke tests and spot checks.
- Record the timings.

**Targets for the pilot (to confirm):** RPO 24 hours (or minutes with point-in-time recovery); RTO
4 hours.

**Evidence:** an alert received for each check type, plus the drill log with timings.

### 6H — Security and acceptance testing

**On staging:**
- OWASP ZAP baseline scan of the dashboard and API.
- Tenant-isolation spot checks: two clinics, guessed IDs, storage URLs.
- Rate limits checked from two different IPs (R2 proof).
- Forged forwarding headers.
- Large and malicious upload samples (EICAR test file and decompression bomb).
- Webhook replay.
- Failure drills: kill the worker, stop the database connection, and let the AI provider time
  out. Confirm alerts fire and recovery works.
- Review [PRODUCTION_SECURITY_CHECKLIST.md](../security/PRODUCTION_SECURITY_CHECKLIST.md) line by
  line.

**Evidence:** the ZAP report (accepted or fixed findings), the drill notes and the signed
checklist.

### 6I — Production deployment

**Preconditions:**
- 6A–6H accepted.
- Legal documents published (R5).
- A backup taken immediately before.
- The founder's written go-ahead.

**Steps:**
1. Run `deploy.sh production <tag>` with the same release staging ran.
2. Run the smoke tests.
3. Create the first platform admin with MFA.
4. Turn the uptime monitors on.

AI stays off until founder approval.

**Rollback:** see [ROLLBACK_AND_RECOVERY.md](ROLLBACK_AND_RECOVERY.md).

**Evidence:** release record, smoke output and monitor screenshots.

### 6J — Pilot onboarding (three clinics)

**Per clinic:**
1. A signed agreement and DPA.
2. Create the clinic and invite the owner (owner MFA recommended).
3. The clinic adds content and documents.
4. Verify the clinic's website domain with the DNS TXT record.
5. Connect the calendar.
6. A test booking on a clinic test page.
7. Turn the widget on with the clinic's consent.

Clinics go live **one at a time**, with a check-in after week 1. Support procedure: a contact
address, response times and an incident contact.

**Evidence:** an onboarding checklist for each clinic.

---

## 8. Questions for the founder

**All questions are answered.**
- **2026-11-24:** Q2 (D1), Q3 (D2), Q5 (D3), Q8 (D5), Q9 (D4) and Q12 (D6).
- **2026-11-25, Q1:** answered by the inspection.
- **2026-11-25, the rest:** the founder said "use your recommendation" for the remaining questions,
  recorded as D7–D12:

| # | Question | Decision |
|---|---|---|
| D7 | Q4 Production region | Same region as the existing (staging) Supabase project. The VPS is in the EU, so an EU region is preferred if a choice is ever needed. |
| D8 | Q6 Images | **Public** GHCR packages. The images contain no secrets; the browser values in them are public anyway. The server then needs no registry token. |
| D9 | Q7 Staging access | Cloudflare Access (Zero Trust, free) in front of `staging-engage.zuvoora.com`, allowing the founder's email only |
| D10 | Q10 Monitoring | UptimeRobot (free) with alerts to the founder's mailbox. No third-party error tracking for now, so no patient content leaves the system. |
| D11 | Q11 Backup storage | Backblaze B2: a write-only application key, and Object Lock so backups cannot be deleted early |
| D12 | Q13 Retention (**provisional**, until the lawyer reviews it) | Conversations and call-back requests: 12 months after the last activity. Provider and webhook events: 90 days. Audit events: 24 months. Demo requests: 12 months (already built). Finished jobs: as built. To be implemented before the pilot (R17). |

1. **VPS details.** Answered: EU, Ubuntu 24.04.5 LTS, and the server is empty. **Proxy: Caddy**,
   because nothing owns ports 80 and 443. Details in `CONTABO_VPS_SETUP.md`, "Inspection results".
2. **Shared host.** Is it acceptable for staging and production to share the VPS with ZUVOORA
   under the §6 mitigations? Or should staging get a small separate VPS?
3. **Production database plan.** Supabase Pro (about $25 a month) gives daily backups, no pausing
   and leaked-password protection, and is needed for production. Add point-in-time recovery (paid
   add-on) now, or later?
4. **Production region.** The new Supabase project should be in the same region as the existing
   staging project and close to the VPS. Confirm.
5. **Email domain.** Which address sends email, for example `no-reply@notify.zuvoora.com`? Does the
   main ZUVOORA product already use Resend on `zuvoora.com`? A separate subdomain keeps the two
   reputations apart. Which address receives demo-request alerts?
6. **Images.** Are public images on GHCR acceptable (they contain no secrets), or should they be
   private with a read-only token on the server?
7. **Staging access.** Is Cloudflare Access (free for small teams) acceptable in front of the
   staging dashboard?
8. **Upload malware scanning.** Accept the documented residual risk for the pilot, or add ClamAV
   (about 1 GB more memory)?
9. **AI in production.** Off at launch and turned on after a week? Or on from day one, and with
   what OpenRouter credit limit and budgets?
10. **Monitoring.** Which uptime service (UptimeRobot and Better Stack both have free tiers)? Where
    should alerts go? Is optional error tracking such as Sentry wanted? If so, a privacy review is
    needed first, because errors must not carry patient content.
11. **Backup storage.** Backblaze B2 (recommended: it can issue a write-only key, and has a free
    tier of 10 GB) or Cloudflare R2? This matters more now that our backup is the only one (D2).
12. **Legal.** Who reviews the privacy notice, terms, DPA and retention schedule, and by when?
    Pilot onboarding waits for this.
13. **Retention.** How long are conversations, call-backs and audit records kept? This needs legal
    input; R17 implements the answer.

## 9. Out of scope for Phase 6

Kubernetes, multiple servers or regions, automatic production deployment, SOC 2, ISO or HIPAA
claims, patient-uploaded images, and public prices.
