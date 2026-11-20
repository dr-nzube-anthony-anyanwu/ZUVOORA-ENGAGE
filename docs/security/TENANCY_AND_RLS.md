# Tenancy, Authorisation and RLS (Phase 1)

Source of truth: `supabase/migrations/20261120000001_tenant_foundation.sql`.
Verified by: `supabase/tests/01_tenant_rls.test.sql` (pgTAP) and
`apps/api/tests/integration/test_tenancy_api.py` (real Supabase Auth + API).

## Request path
```text
Browser (dashboard) ──Supabase Auth (email+password, TOTP MFA)──► access token (ES256 JWT)
Dashboard server ──Bearer token──► FastAPI
FastAPI: verify JWT (JWKS, iss, aud, exp, role=authenticated, aal)
       → open transaction as engage_api
       → SET LOCAL ROLE engage_app + set_config('request.jwt.claims', <verified claims>)
       → app_private.tenant_role(path tenant_id)   (404 if none, 403 if role too low)
       → action + audit_events insert in the SAME transaction (RLS applies to both)
```

## Database roles (ADR-016)
| Role | Purpose | Privileges on Engage tables |
|---|---|---|
| `anon`, `authenticated`, `service_role` | Supabase Data API (PostgREST/GraphQL) | **None** |
| `engage_api` | Backend login role, NOINHERIT | None directly; can only `SET ROLE engage_app` |
| `engage_app` | NOLOGIN; target of every RLS policy | Least-privilege column grants, no DELETE |

The Data API cannot read or write Engage tables even with a valid owner session or the
service-role key; this is tested. Direct browser-to-database access is therefore impossible,
and every write passes through the API's authorisation and audit logging.

## Access rules
- A user acts in a tenant only with an **active** membership in a tenant whose status is
  `pending` or `active`. Suspended/closed tenants and revoked memberships lose access on the
  next request (no token expiry wait).
- The tenant comes from the URL path only. Bodies forbid unknown fields, so `tenant_id`,
  `role`, `status` etc. cannot be smuggled in. Inaccessible tenants return **404**, identical to
  non-existent ones, so tenant ids cannot be probed.
- Roles: `owner` > `admin` > `receptionist` > `viewer`.
  - owner/admin: manage members, edit the clinic profile, read the tenant audit log.
  - admin cannot grant `owner`, nor change or revoke an owner.
  - receptionist/viewer: read-only access to their clinic.
  - A tenant always keeps at least one active owner (trigger).
- Platform admins (ZubeVision staff) need an active `platform_admins` row **and** an
  MFA-verified session (`aal2`). MFA alone grants nothing. Platform admins create, suspend and
  reactivate tenants. `platform_admins` is managed only by SQL from a database owner.
- Identity columns (ids, `tenant_id`, `user_id`) are immutable via column-level grants.

## Audit
`audit_events` is append-only: no UPDATE/DELETE/TRUNCATE for any role, enforced by grants and
triggers (even for the table owner). Events record actor, tenant, action, target and request
id. Metadata never contains message content, tokens or secrets. Users can only write events as
themselves about tenants they belong to.

## Adding a tenant-owned table (checklist)
1. `tenant_id uuid not null references public.tenants(id)`.
2. `enable` + `force row level security`.
3. Policies `to engage_app` using `app_private.has_tenant_role(tenant_id, …)`.
4. `revoke all … from public, anon, authenticated, service_role`; explicit grants to
   `engage_app` only (column-level for UPDATE; avoid DELETE).
5. pgTAP tests: anon denied, Data API (`authenticated`) denied, cross-tenant read/write denied,
   role restrictions, suspended tenant, revoked member.
6. API integration tests for the same through the HTTP layer.

## Known limitations (tracked)
- Dashboard CSP still allows inline scripts (Next.js hydration); nonce-based CSP in Phase 6.
- API rate limiting arrives with the public widget endpoints (Phase 3); Supabase Auth applies
  its own sign-in rate limits.
- If an invitation email is sent but the database transaction then fails, the invitee exists
  without a membership; re-sending the invitation adds the membership (no duplicate users).
