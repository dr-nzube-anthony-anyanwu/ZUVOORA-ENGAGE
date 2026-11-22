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

## Clinic content: draft and publish (Phase 2a, ADR-021)
Tables `clinic_profiles` (one per tenant), `branches`, `services`, `faqs`. Same tenancy rules:
all members read, owners/admins (and MFA platform admins) write; no DELETE (archive instead).
- Each row has a `draft` and an optional `published` copy (validated JSON, ≤ 64 KB). Only
  `published` content will ever reach the public assistant (Phase 3).
- **The database owns the bookkeeping.** `engage_app` may write only `draft`, `published` and
  `archived_at` (column grants; no insert of `published`). Triggers:
  - increment `revision` whenever the draft changes;
  - allow `published` to be set only to the current `draft`, stamping `published_revision`,
    `published_at`, `published_by` (the caller) — a client cannot publish unreviewed text or
    spoof the publisher;
  - archiving always unpublishes; archived content cannot be published; archive time/actor are
    server-set;
  - content can never move to another tenant.
- **Optimistic locking in the API.** Draft edits carry the revision the editor loaded and
  publishing carries the exact revision the reviewer approved; any mismatch returns
  `409 revision_conflict`, so nobody overwrites or publishes changes they have not seen.
- Editing a published item leaves the published copy live (`state = changes_pending`) until the
  new revision is published.
- Text is plain text only (NFC-normalised, control and bidi-override characters rejected,
  single-line fields reject line breaks). Opening hours are structured (7 days, ≤ 3
  non-overlapping 24h ranges per day, dated exceptions) so the assistant can answer
  deterministically. Per-tenant caps: 50 branches, 200 services, 500 FAQs.
- Every create/edit/publish/unpublish/archive/restore writes an audit event in the same
  transaction.

## Website domains (Phase 2b, ADR-022)
- A clinic registers a hostname (owner/admin). The database generates a 256-bit
  `verification_token`; hostname and token are immutable. The clinic publishes
  `TXT _zuvoora-engage.<hostname> = zuvoora-engage-verification=<token>`.
- The API verifies with a **DNS TXT lookup only** (never an HTTP fetch, so no SSRF surface),
  outside any database transaction, with a per-domain cooldown (default 15 s) and a 4 s timeout.
- Hostnames are normalised (lower-case, trailing dot removed, IDN → punycode) and rejected if
  they contain a scheme/path/port, are IP addresses, single-label, or use private/reserved TLDs
  (`localhost`, `local`, `internal`, `test`, `example`, …). The database re-checks the format.
- **Anti-squatting:** many clinics may *claim* a hostname, but a partial unique index allows only
  one *verified* holder. A claim never blocks the real owner; a second verifier gets
  `409 domain_taken` (attempt and audit kept).
- Domains are removed (`removed_at`, server-stamped), never deleted; removal drops verification
  and frees the hostname; a new claim gets a new token. Max 10 active domains per clinic.
- Every add/verify attempt/removal is audited (hostname and outcome only).
- Limitation: verification is checked once; periodic re-verification (record removed later)
  is planned with the Phase 3 widget/domain checks.

## Knowledge documents (Phase 2c, ADR-023)
- Owners/admins upload PDF, Word (.docx), plain text and Markdown files up to 10 MB; all members
  can read documents and extracted text; only owners/admins approve, reject, archive, rename.
- **Screening:** the type is decided from the file's own bytes and the extension must agree;
  the browser's MIME type is ignored. Request bodies over the limit are refused while streaming
  (ASGI middleware), before multipart parsing.
- **Isolated extraction:** parsing runs only in `extract_worker.py`, a separate `python -I`
  process with a 30 s timeout, an empty environment (no secrets), no database access and, on
  Linux/Docker, memory (768 MB), CPU and file-write limits. Rejected: encrypted PDFs; PDF
  JavaScript, launch/submit/import actions, XFA forms and embedded files/attachments; Word
  macros, embedded objects/ActiveX; zip bombs (size, entry count, compression ratio); non-UTF-8
  text; documents without selectable text (scans) or over 300,000 characters. Extracted text is
  normalised plain text (control and bidi characters removed).
- **Rejected files are never stored**; the rejection reason is audited.
- **Originals** go to the private `knowledge-originals` bucket as opaque
  `application/octet-stream`, never overwritten, at a database-generated path
  `tenant/document/version`. `storage.objects` has **no policies**, so browser keys (anon or
  signed-in) cannot list, read, sign or write them — only the backend's secret key can. The
  database row and the stored object are written in one transaction (storage failure rolls back).
  Originals are not served to anyone in Phase 2.
- **Versions are immutable** (text, hash, size, path). Status moves only `extracted → approved |
  rejected`, stamped with reviewer and time by the database. Only an approved version of the
  same document and tenant can be published (trigger + composite foreign key). New uploads never
  replace the published version until approved; archiving unpublishes; restoring never
  republishes. Identical re-uploads are refused. Caps: 100 documents, 50 versions each.

## Public widget path (Phase 3a, ADR-025)
- Anonymous widget traffic runs as `engage_widget` (NOLOGIN; the backend switches to it per
  transaction). The tenant and conversation come from server-side settings
  (`request.widget.tenant_id`, `request.widget.conversation_id`) derived from a verified widget
  token — never from request bodies.
- **Published content only:** column grants give `engage_widget` only the `published` copy of
  profiles, branches, services and FAQs, and only the published version's text of approved
  documents; drafts, storage paths, domains, memberships and the audit log are unreadable. RLS
  limits everything to the widget's tenant, which must be `active`.
- A visitor can create a conversation for its tenant, read and post messages only in its own
  conversation, request a handover (consent required, phone or email required) and mark its own
  conversation for handover; it cannot close conversations or edit/delete messages.
- `app_private.resolve_widget(key, host)` returns a tenant only for an enabled widget, an active
  tenant and a **verified** host. `widget_allowed_hosts(key)` feeds the iframe's
  `frame-ancestors` policy.
- Messages and the AI usage ledger are append-only. `rate_limit_hit` stores HMAC'd bucket keys
  (no raw IPs). `ai_spend()` returns tenant/global spend for budget enforcement.
- Staff: owners/admins/**receptionists** (the front desk) read message text and handover contact
  details and handle them (close conversations, move handovers new → in progress → resolved);
  viewers and MFA platform admins see conversation metadata only (status, counts, times) —
  migration `20261122000002_inbox_privacy.sql`, ADR-030. Contact details are immutable; status
  changes are stamped by the database and audited by the API, as is every transcript view.
  AI costs are visible to owners/admins; only owners/admins configure the widget or rotate its key.

## Public widget (Phase 3b, ADR-027)
- The API serves the embed script (`/widget/v1/loader.js`), the chat iframe
  (`/widget/v1/frame?key=…`) and the public endpoints from one origin, so the iframe needs no
  CORS and rate limits see the visitor's IP. Assets come from a fixed allow-list.
- **Browser-enforced domains:** the iframe response carries
  `Content-Security-Policy: frame-ancestors https://<verified host>…` built from the clinic's
  verified, non-removed domains (`'none'` if there are none or the key is unknown), plus
  `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'` and
  `Referrer-Policy: no-referrer`. http:// embedding is allowed only with
  `WIDGET_ALLOW_HTTP_FRAMES` (development/test; refused in staging/production).
- **Static frame, no server-rendered data:** `/widget/v1/frame` is a fixed HTML file; only its
  CSP header varies per key. The frame's script calls `POST /api/v1/public/widget/frame-config`
  with the key and the embedding hostname (passed by the loader), which returns the clinic name,
  greeting and a frame ticket only for a verified host (Semgrep finding on server-built HTML,
  fixed by design). The close button posts only to the embedding page's origin.
- **Frame ticket → conversation token:** a frame ticket (15 min) is issued only if the embedding
  host is a verified domain of an enabled widget of an active clinic. Starting a chat requires the ticket and re-checks it; the
  API generates the conversation id. Conversation tokens (2 h) are HS256 with a dedicated
  `WIDGET_TOKEN_SECRET`, separate audiences per token type, and carry ids only. A token forged
  with the real key but pairing another clinic with a conversation is still blocked by RLS
  (tested).
- **Limits:** per visitor IP (keyed hash), per conversation and per clinic; messages ≤ 1,000
  characters; ≤ 50 messages per conversation; request bodies capped by the global middleware.
- **Rendering:** the iframe UI and loader insert text with `textContent` only; the iframe is
  sandboxed (`allow-scripts allow-same-origin allow-forms`); the loader only accepts `close`
  messages from the Engage origin and frame. Conversation tokens are held in memory only.
- **Handover:** consent checkbox required; phone or email required; one request per
  conversation; the conversation moves to `handover_requested`.
- **Retention:** messages and the usage ledger are immutable and undeletable by application
  roles; only the database owner can delete (tenant deletion, lawful deletion/retention jobs).

## Background jobs (Phase 4a, ADR-033) and scheduling credentials (Phase 4b, ADR-034)

- `app_private.jobs` has no grants to any application role. Jobs are enqueued by the database in
  the same transaction as their cause; the worker role `engage_jobs` (NOLOGIN, no table access)
  only executes `claim_jobs`, `complete_job`, `skip_job`, `fail_job`, `purge_finished_jobs` and
  send-time data functions that re-check the clinic is active and return staff recipients only.
- Scheduling API keys are encrypted by the API (AES-256-GCM, associated data = purpose, tenant,
  connection id) before storage. No role can SELECT `credential_ciphertext`;
  `app_private.scheduling_credential()` returns it only to that clinic's owner/admin/receptionist
  or to that active clinic's widget. Owners/admins connect, choose appointment types and
  disconnect; disconnecting erases the ciphertext. The widget sees only enabled appointment
  types of an active connection, and only `id, tenant_id, provider, status` of the connection.
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
