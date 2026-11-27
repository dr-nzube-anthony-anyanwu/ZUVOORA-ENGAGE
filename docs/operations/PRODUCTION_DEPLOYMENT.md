# Staging and Production Deployment

Part of [PHASE6_DEPLOYMENT_PLAN.md](PHASE6_DEPLOYMENT_PLAN.md) (stages 6E and 6I).

**Status: tooling built and tested locally (stage 6A, 2026-11-25); nothing has been deployed.**
The procedure uses:

- `deploy/compose.yml`: the hardened Compose file for both environments.
- `deploy/proxy/`: the Caddy edge proxy and its Compose file.
- `deploy/env/*.env.example`: the settings templates.
- `deploy/scripts/preflight.sh`, `deploy.sh` and `rollback.sh`.
- `.github/workflows/images.yml`: builds, scans and publishes images for a release tag.

Backups (`backup.sh`, restore check) are built in stage 6G.

## 1. Principles

- **The same release runs on staging first,** then production. A release is a Git tag, for
  example `v0.6.0`, on a commit whose CI is green. Its images are identified by **digest**.
- **A person starts each deployment.** CI never deploys.
- **Database migrations come before the code that needs them.** Migrations must be backward
  compatible ("expand, then contract"): add columns or tables first; remove old ones in a later
  release. The previous code version must keep working against the new schema, because that is
  what makes a code rollback safe.
- **Secrets live only in the password manager and in `/opt/zuvoora-engage/<env>/.env`** (root
  only, mode 600). Never in Git, images, CI logs or chat.
- **Every deployment is recorded** in `/opt/zuvoora-engage/<env>/releases.log`: time, tag, image
  digests and the operator.

## 2. Environments

| | Staging | Production |
|---|---|---|
| Compose project | `engage-staging` | `engage-prod` |
| Dashboard | `https://staging-engage.zuvoora.com` (Cloudflare Access) | `https://engage.zuvoora.com` |
| API and widget | `https://staging-api-engage.zuvoora.com` | `https://api-engage.zuvoora.com` |
| Supabase | Existing cloud project | New production project |
| `APP_ENV` | `staging` | `production` |
| Email | Resend, staging key; `EMAIL_ALLOWED_RECIPIENTS` = test inboxes only | Resend, production key; no allow-list |
| AI | Staging OpenRouter key (credit limit $1) | Production key (credit limit $5); on at launch (D4) |
| Data | Synthetic only | Pilot clinics |
| Private networks (edge / internal) | `10.73.10.0/24` / `10.73.11.0/24` | `10.73.0.0/24` / `10.73.1.0/24` |
| Containers | api, worker, web, clamav; no published ports | the same |

### Settings per environment

Names only; values never appear here. The templates in `deploy/env/` explain each one.

**Shared by API and worker:**

- **Environment and URLs:**
  - `APP_ENV`
  - `API_CORS_ORIGINS` = the dashboard URL
  - `DASHBOARD_URL`
  - `PUBLIC_API_URL` = the API URL
  - `FORWARDED_ALLOW_IPS` (new in 6A)
- **Supabase and database:**
  - `SUPABASE_URL`
  - `SUPABASE_PUBLISHABLE_KEY`
  - `SUPABASE_SECRET_KEY`
  - `DATABASE_URL`: the `engage_api` role through the Supabase pooler, with `sslmode=require`
- **Widget and calendar keys:**
  - `WIDGET_TOKEN_SECRET` (at least 32 random characters)
  - `INTEGRATIONS_ENCRYPTION_KEY`, which must be **backed up**: losing it disconnects every
    clinic's calendar
- **Email:**
  - `EMAIL_DELIVERY=resend`
  - `RESEND_API_KEY`
  - `EMAIL_FROM`
  - `DEMO_REQUEST_NOTIFY_EMAIL` (production)
- **AI:**
  - `OPENROUTER_API_KEY`
  - `AI_ENABLED`
  - `AI_VISION_ENABLED`
  - the budget settings
- **Calendar:** `CALCOM_API_URL`

**Dashboard image build** (public values only, set as GitHub Actions *variables*, not secrets):

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

**Dashboard runtime:**

- `ENGAGE_API_URL=http://api:8073` (internal)
- `ENGAGE_PUBLIC_API_URL`

### Generating the app's own secrets

Generate these **on the server**, straight into the env file, never through chat:

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(48))"            # WIDGET_TOKEN_SECRET
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip('='))"  # INTEGRATIONS_ENCRYPTION_KEY
```

Copy each value into the password manager as well. Staging and production always get
**different** values.

## 2b. One-time server setup (after stage 6B; commands given step by step at the time)

1. **Get the deployment files.** The repository is public, so no credentials are needed. Use a
   release tag, never a moving branch:
   ```bash
   sudo git clone https://github.com/dr-nzube-anthony-anyanwu/ZUVOORA-ENGAGE.git /opt/zuvoora-engage/app
   sudo git -C /opt/zuvoora-engage/app checkout v0.6.0
   ```
   The scripts below run from `/opt/zuvoora-engage/app`.
2. **Create the settings file.** Copy the template to `/opt/zuvoora-engage/<env>/.env` (root,
   600), fill it from the password manager (founder guide, Part 7), then run
   `sudo deploy/scripts/preflight.sh <env>`.
3. **Install the proxy certificates.** Put them in `/opt/zuvoora-engage/proxy/certs/` (root,
   600; stage 6D):
   - `origin.pem` and `origin-key.pem` (the Cloudflare Origin CA certificate);
   - `cloudflare-origin-pull-ca.pem` (Cloudflare's public Authenticated Origin Pulls CA).
4. **Start the proxy.** Do this after the first `deploy.sh` for both environments, because that
   creates the two edge networks:
   `sudo docker compose -p engage-proxy -f deploy/proxy/compose.yml up -d --wait`. After any
   change to the Caddyfile, validate first with
   `sudo docker exec engage-proxy caddy validate --config /etc/caddy/Caddyfile`, then restart
   with `sudo docker restart engage-proxy`.
5. **GitHub, once:**
   - Make the three packages **public** (decision D8). Go to Packages → the package → Package
     settings → Change visibility. The server then pulls without a token.
   - Set the four repository *variables* listed in `.github/workflows/images.yml`. These are
     public browser values, never secrets.

## 3. Release procedure

### Step 1 — Prepare (laptop)

1. All work is merged on `main`, and CI shows both workflows green.
2. Check the migration list: `npx supabase migration list --linked` for staging.
3. Tag the release: `git tag v0.6.0 && git push origin v0.6.0` (with approval). The `images`
   workflow builds the API image and the two dashboard images (staging and production, each with
   its own public Supabase values). It scans them with Trivy, failing on HIGH or CRITICAL issues
   that have a fix, publishes them, and prints the exact `deploy.sh` commands with digests in the
   run summary.
4. On the server, update the deployment files to the same tag:
   `sudo git -C /opt/zuvoora-engage/app fetch --tags && sudo git -C /opt/zuvoora-engage/app checkout v0.6.0`.

### Step 2 — Migrate staging (laptop, linked to the staging project)

```powershell
npx supabase db push --dry-run    # read the list; stop if anything unexpected
npx supabase db push --linked
npx supabase db lint --linked --level warning
```

### Step 3 — Deploy to staging (server)

```bash
cd /opt/zuvoora-engage/app
sudo deploy/scripts/deploy.sh staging ghcr.io/<owner>/zuvoora-engage-api@sha256:<...> ghcr.io/<owner>/zuvoora-engage-web-staging@sha256:<...>
```
Copy the exact line from the `images` run summary.

`deploy.sh` does the following, in order, and stops at the first failure:

1. `preflight.sh`:
   - the env file exists, is owned by root and has mode 600;
   - every required name is present (values are never printed);
   - `APP_ENV` matches the target;
   - the URLs are https;
   - no staging value equals a production value (compared by hash).
2. Create the environment's edge network with its fixed subnet, if it is missing.
3. Write the release (the image digests) to `release.env`. The previous release is kept as
   `release.env.previous`.
4. `docker compose pull`, then `up -d --wait`, which waits for every health check: api, worker
   heartbeat, web and ClamAV.
5. Smoke checks inside the containers:
   - `/health/ready` returns 200 (the database is reachable);
   - `/widget/v1/loader.js` is served;
   - `/docs` returns 404;
   - the worker heartbeat is fresh;
   - the dashboard `/healthz` answers.
6. On any failure it **rolls back automatically** to the previous release and exits non-zero.
7. It appends the result to `releases.log`.

From the laptop afterwards, check the public addresses (padlock, sign-in page, widget on a test
page), and that a CORS request from another origin is refused.

### Step 4 — Verify staging (people)

Follow the demo guide's Acts 1–6 on staging with synthetic data. Check Mailpit is **not** used;
real test inboxes receive the mail. Check the worker processed jobs, with none `dead`.

### Step 5 — Production (after the founder approves the release)

1. Take a fresh database backup with `sudo deploy/scripts/backup.sh production` (built in 6G).
   Confirm it uploaded.
2. Migrate production. The CLI is linked to production **only** in the separate folder
   `D:\technologies\engage-prod-ops`; the repository stays linked to staging. Commands must run
   **from inside** that folder, because the repository's gitignored `.env` holds the staging
   `SUPABASE_DB_PASSWORD`, which the CLI would otherwise pick up and use against production:
   ```powershell
   Copy-Item D:\technologies\ZUVOORA-ENGAGE\supabase\migrations\*.sql D:\technologies\engage-prod-ops\supabase\migrations\
   Set-Location D:\technologies\engage-prod-ops
   $sb = "D:\technologies\ZUVOORA-ENGAGE\node_modules\.bin\supabase.cmd"
   & $sb db push --linked --dry-run     # read the list; stop if anything unexpected
   & $sb db push --linked
   & $sb db lint --linked --level warning
   ```
3. Deploy the **same API digest** that staging ran, with the production dashboard image:
   `sudo deploy/scripts/deploy.sh production <api@sha256> <web-production@sha256>`.
4. Run the smoke tests (automatic), then a manual check: sign in, open one clinic, ask the widget
   a question on a test page.
5. Watch for 30 minutes: uptime monitors, `docker compose ps`, worker logs (counts only).

### First production platform admin (one time)

Self-signup is off. In the production Supabase dashboard:

1. Authentication → Add user → email of the ZubeVision admin → "Auto confirm" on, with a strong
   password from the password manager.
2. In the SQL editor:

   ```sql
   insert into public.platform_admins (user_id, note)
   select id, 'founder' from auth.users where email = '<admin email>';
   ```

3. Sign in at `https://engage.zuvoora.com/login` and set up two-factor authentication at `/mfa`
   immediately.

## 4. Routine operations

| Task | Command (server, in `/opt/zuvoora-engage`) |
|---|---|
| Status | `sudo docker compose -p engage-prod ps` |
| Logs (last 200 lines; no patient content is logged) | `sudo docker compose -p engage-prod logs --tail 200 api` |
| Restart one service | `sudo docker compose -p engage-prod restart worker` |
| Stop staging to save memory | `sudo docker compose -p engage-staging stop` |
| Clean old images (keeps those in use) | `sudo docker image prune -a --filter "until=720h"` |

Never run `docker system prune --volumes` or anything that touches ZUVOORA's containers or
volumes.

## 5. Changing a secret

1. Create the new value at the provider. Keep the old one active.
2. Update the password manager.
3. Run `sudo nano /opt/zuvoora-engage/<env>/.env`, then (in `/opt/zuvoora-engage/app`)
   `sudo deploy/scripts/deploy.sh <env> --current`. That recreates the containers with the new value.
4. Check that everything is healthy, then revoke the old value at the provider.

**`INTEGRATIONS_ENCRYPTION_KEY` is different.** Put the new key in `INTEGRATIONS_ENCRYPTION_KEY`
and the old one in `INTEGRATIONS_ENCRYPTION_KEY_PREVIOUS`. Remove the old key only after the
re-encryption has completed (ADR-034).
