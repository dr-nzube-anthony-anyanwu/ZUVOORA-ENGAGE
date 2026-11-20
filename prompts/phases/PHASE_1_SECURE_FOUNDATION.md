# Phase 1 — Authentication, tenancy, RBAC and RLS

Create a dedicated Supabase Engage project. Implement migrations, Supabase Auth, tenant memberships, roles, server-side session verification and audit foundation. Enable RLS on all tenant-owned tables.

Required negative tests:
- Tenant A cannot read/update Tenant B data.
- Changing browser-supplied tenant_id does not change authorised tenant.
- Anonymous users cannot read private tables.
- Receptionist cannot perform owner/platform actions.
- Revoked membership loses access.
- Suspended tenant is blocked.
- Service-role secrets never appear in browser bundles.

Do not proceed until migrations apply cleanly and all tenant/role negative tests pass.
