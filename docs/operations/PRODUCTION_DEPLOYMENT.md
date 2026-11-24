# Staging and Production Deployment

Part of [PHASE6_DEPLOYMENT_PLAN.md](PHASE6_DEPLOYMENT_PLAN.md) (stages 6E and 6I).

**Status: planned, not yet usable.** The files this procedure relies on are created in stage 6A
and do not exist yet:

- `deploy/compose.yml`
- `deploy/env/*.env.example`
- `deploy/scripts/*.sh`
- the image workflow

Nothing has been deployed.

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
| AI | Staging OpenRouter key with a small credit limit | Production key; off until approved |
| Data | Synthetic only | Pilot clinics |
| Local ports, if an existing host proxy is used | `127.0.0.1:8173` (API), `127.0.0.1:3173` (web) | `127.0.0.1:8073`, `127.0.0.1:3073` |

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

## 3. Release procedure

### Step 1 — Prepare (laptop)

1. All work is merged on `main`, and CI shows both workflows green.
2. Check the migration list: `npx supabase migration list --linked` for staging.
3. Tag the release: `git tag v0.6.0 && git push origin v0.6.0` (with approval). The image workflow
   builds, scans (Trivy, fails on HIGH or CRITICAL) and publishes both images, and prints their
   digests.

### Step 2 — Migrate staging (laptop, linked to the staging project)

```powershell
npx supabase db push --dry-run    # read the list; stop if anything unexpected
npx supabase db push --linked
npx supabase db lint --linked --level warning
```

### Step 3 — Deploy to staging (server)

```bash
cd /opt/zuvoora-engage
sudo ./deploy/scripts/deploy.sh staging v0.6.0
```

`deploy.sh` does the following, in order, and stops at the first failure:

1. `preflight.sh`:
   - the env file exists, is owned by root and has mode 600;
   - every required name is present (values are never printed);
   - `APP_ENV` matches the target;
   - the URLs are https;
   - no staging value equals a production value (compared by hash).
2. `docker compose pull` of the exact image digests for the tag.
3. Remember the current release as "previous".
4. `docker compose --project-name engage-staging --env-file ... up -d --wait` (waits for health
   checks).
5. Smoke tests:
   - `/health/ready` returns 200;
   - the dashboard `/healthz` returns 200;
   - `/widget/loader.js` returns 200;
   - a CORS preflight from `https://example.invalid` is refused;
   - `/docs` returns 404.
6. On failure, it **rolls back automatically** to the previous release and exits non-zero.
7. It appends to `releases.log`.

### Step 4 — Verify staging (people)

Follow the demo guide's Acts 1–6 on staging with synthetic data. Check Mailpit is **not** used;
real test inboxes receive the mail. Check the worker processed jobs, with none `dead`.

### Step 5 — Production (after the founder approves the release)

1. Take a fresh database backup: `sudo ./deploy/scripts/backup.sh production`. Confirm it uploaded.
2. Migrate production. Link the CLI to the production project, `db push --dry-run`, read it, then
   `db push --linked` and `db lint --linked`. Relink to staging afterwards so that day-to-day work
   cannot touch production by accident.
3. Deploy: `sudo ./deploy/scripts/deploy.sh production v0.6.0`.
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
3. Run `sudo nano /opt/zuvoora-engage/<env>/.env`, then `sudo ./deploy/scripts/deploy.sh <env>
   <current tag>`. That recreates the containers with the new value.
4. Check that everything is healthy, then revoke the old value at the provider.

**`INTEGRATIONS_ENCRYPTION_KEY` is different.** Put the new key in `INTEGRATIONS_ENCRYPTION_KEY`
and the old one in `INTEGRATIONS_ENCRYPTION_KEY_PREVIOUS`. Remove the old key only after the
re-encryption has completed (ADR-034).
