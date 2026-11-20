# Supabase Cloud Setup (Phase 1, final step)

Do this yourself in the Supabase dashboard. **Never paste keys or passwords into chat, Git,
tickets or screenshots.** Values go only into your local, gitignored env files or a secret
manager.

## 1. Create the project
- New **dedicated** project for Engage (not the ZUVOORA Core project).
- Region: closest to your users that meets your data-protection obligations (record the choice).
- Generate a strong database password and store it in your password manager.

## 2. Authentication settings
- Authentication → Sign In / Providers:
  - **Allow new users to sign up: OFF** (accounts are invitation-only).
  - Email provider: enabled. Confirm email: on.
  - Minimum password length **12**, require lower/upper case letters and digits.
- Authentication → Multi-Factor: **TOTP enabled** (enrol + verify).
- Authentication → URL Configuration:
  - Site URL: your dashboard URL (for now `http://localhost:3000`).
  - Redirect URLs: `http://localhost:3000/auth/confirm` (add the staging URL later).
- Authentication → Email Templates → **Invite user**: paste the body of
  `supabase/templates/invite.html` (subject: "You have been invited to ZUVOORA Engage").
- Note: the built-in email sender is heavily rate-limited. Production email moves to Resend
  (custom SMTP) in Phase 4.

## 3. Apply the migration
From the repository root (you will be prompted to log in to the Supabase CLI in your browser
and for the database password; neither is shown to anyone else):
```powershell
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase db push          # applies supabase/migrations (NOT seed.sql)
```

## 4. Set the backend role password
SQL editor, using a **new** strong random password (different from the DB owner password):
```sql
alter role engage_api with password 'PASTE_A_NEW_STRONG_RANDOM_PASSWORD';
```

## 5. Data API
Settings → Data API: Engage tables are not reachable through it by design (no grants to
`anon`/`authenticated`/`service_role`). For defence in depth, remove `public` from exposed
schemas (or disable the Data API) if your project does not need it.

## 6. First platform admin (you)
1. Authentication → Users → Add user → your email, strong password, auto-confirm.
2. SQL editor:
   ```sql
   insert into public.platform_admins (user_id, note)
   select id, 'founder' from auth.users where email = 'YOUR_EMAIL';
   ```
3. Sign in to the dashboard and enrol TOTP at `/mfa` (required for platform actions).

## 7. Local env files pointing at the cloud project (when ready)
Fill these by hand from Settings → API Keys and Database → Connect (Session pooler):
- `apps/api/.env`: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `DATABASE_URL` (user
  `engage_api.<project-ref>`, `sslmode=require`).
- `apps/web/.env.local`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.

The only value to share with Claude is the **project URL / ref** (not secret).
